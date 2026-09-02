import argparse
import asyncio
import json
import logging
import os
import re
import uuid
from typing import Any, List, Optional

from fastmcp import FastMCP
from fastmcp_docs import FastMCPDocs
from google import genai
from pgvector.sqlalchemy import Vector
from rank_bm25 import BM25Plus
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag-server")

# 1. Initialize FastMCP Server & Documentation
mcp = FastMCP("rag-server")
docs = FastMCPDocs(mcp, title="RAG Knowledge Base Tools")

# 2. Database Models & Session Management
Base = declarative_base()


class UserDocument(Base):
    __tablename__ = "user_documents"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(128), index=True, nullable=False)
    filename = Column(String(255), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    mime_type = Column(String(64), nullable=False)
    status = Column(String(32), default="indexing", nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_documents.id", ondelete="CASCADE"), index=True, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=True)
    embedding = Column(Vector(768), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document = relationship("UserDocument", back_populates="chunks")


# DB Engine configuration (No fallback: strictly requires RAG_DB_URL in environment)
_rag_db_url = os.environ.get("RAG_DB_URL")
rag_engine = None
AsyncRagSession = None

if _rag_db_url:
    if _rag_db_url.startswith("postgresql://"):
        _rag_db_url = _rag_db_url.replace("postgresql://", "postgresql+psycopg://")
    elif _rag_db_url.startswith("sqlite:///"):
        _rag_db_url = _rag_db_url.replace("sqlite:///", "sqlite+aiosqlite:///")

    _engine_kwargs: dict[str, Any] = {"future": True}
    if "sqlite" in _rag_db_url:
        _engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        _engine_kwargs["pool_pre_ping"] = True
        _engine_kwargs["pool_size"] = int(os.environ.get("DB_POOL_SIZE", "5"))
        _engine_kwargs["max_overflow"] = int(os.environ.get("DB_MAX_OVERFLOW", "10"))
        _engine_kwargs["pool_timeout"] = int(os.environ.get("DB_POOL_TIMEOUT", "10"))

    rag_engine = create_async_engine(_rag_db_url, **_engine_kwargs)
    AsyncRagSession = sessionmaker(
        rag_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


def _get_session():
    """Retrieve an async session or raise an informative error if RAG_DB_URL is not set."""
    if AsyncRagSession is None:
        raise RuntimeError("RAG_DB_URL environment variable is not configured.")
    return AsyncRagSession()

# 3. Vertex AI Embedding Client
_genai_client = None
GCP_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
GCP_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-005")
EMBEDDING_TIMEOUT_SECONDS = float(os.environ.get("EMBEDDING_TIMEOUT_SECONDS", "5.0"))


def get_genai_client():
    global _genai_client
    if _genai_client is None:
        try:
            client_kwargs: dict[str, Any] = {"vertexai": True}
            if GCP_PROJECT:
                client_kwargs["project"] = GCP_PROJECT
            if GCP_LOCATION:
                client_kwargs["location"] = GCP_LOCATION
            _genai_client = genai.Client(**client_kwargs)
        except Exception as e:
            logger.warning("Failed to initialize Google GenAI Client: %s", e)
    return _genai_client


async def generate_query_embedding(query: str) -> Optional[List[float]]:
    """Generate 768-dim query embedding using Vertex AI."""
    client = get_genai_client()
    if not client:
        return None
    try:
        response = await asyncio.wait_for(
            client.aio.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=[query],
            ),
            timeout=EMBEDDING_TIMEOUT_SECONDS,
        )
        if hasattr(response, "embeddings") and response.embeddings:
            return response.embeddings[0].values
        elif hasattr(response, "embedding") and response.embedding:
            return response.embedding.values
    except Exception as e:
        logger.warning("Query embedding generation failed: %s", e)
    return None


def _tokenize_text(text: str) -> List[str]:
    return [w.lower() for w in re.findall(r"\w+", text) if w.strip()]


# 4. MCP Tools
@mcp.tool(tags=["rag", "documents", "search"])
async def search_knowledge_base(
    query: str,
    user_id: str,
    document_ids: Optional[List[str]] = None,
    top_k: int = 5,
    mode: str = "hybrid",
) -> str:
    """
    Search across vectorized document passages using Hybrid Search (pgvector cosine similarity + BM25 keyword matching with Reciprocal Rank Fusion).

    Args:
        query: Search query. Transform conversational questions into 2-4 dense keyword/semantic terms for highest retrieval quality.
        user_id: Authenticated user ID or email (enforces strict tenant isolation).
        document_ids: Optional list of document UUIDs to filter search scope. If omitted, searches all ready documents belonging to the user.
        top_k: Number of most relevant document chunks to return (default: 5).
        mode: Search mode - 'hybrid' (vector + BM25 with RRF), 'vector' (pgvector dense search), or 'bm25' (lexical search).
    """
    clean_query = query.strip()
    if not clean_query:
        return json.dumps({"error": "Empty query provided.", "results": []})

    async with _get_session() as session:
        try:
            # 1. Resolve accessible document IDs for this user
            user_doc_query = select(UserDocument.id, UserDocument.filename).where(
                UserDocument.status == "ready"
            )
            # Filter by user
            user_doc_query = user_doc_query.where(
                (UserDocument.user_id == user_id) | (UserDocument.user_id == str(user_id).lower().strip())
            )
            if document_ids:
                parsed_uuids = []
                for d in document_ids:
                    try:
                        parsed_uuids.append(uuid.UUID(str(d).strip()))
                    except ValueError:
                        continue
                if parsed_uuids:
                    user_doc_query = user_doc_query.where(UserDocument.id.in_(parsed_uuids))

            doc_results = (await session.execute(user_doc_query)).all()
            if not doc_results:
                return json.dumps({
                    "query": clean_query,
                    "results": [],
                    "message": "No indexed documents found matching criteria for this user.",
                })

            accessible_doc_ids = [row[0] for row in doc_results]

            vector_candidates: List[dict[str, Any]] = []
            bm25_candidates: List[dict[str, Any]] = []

            # 2. Dense Vector Retrieval (pgvector)
            if mode in ("hybrid", "vector"):
                query_vec = await generate_query_embedding(clean_query)
                if query_vec:
                    vector_limit = max(top_k * 3, 15)
                    stmt = (
                        select(
                            DocumentChunk.id,
                            DocumentChunk.chunk_text,
                            DocumentChunk.chunk_index,
                            DocumentChunk.document_id,
                            UserDocument.filename,
                            (1.0 - DocumentChunk.embedding.cosine_distance(query_vec)).label("similarity"),
                        )
                        .join(UserDocument, DocumentChunk.document_id == UserDocument.id)
                        .where(DocumentChunk.document_id.in_(accessible_doc_ids))
                        .order_by(DocumentChunk.embedding.cosine_distance(query_vec))
                        .limit(vector_limit)
                    )
                    v_res = await session.execute(stmt)
                    for row in v_res.all():
                        vector_candidates.append({
                            "chunk_id": str(row[0]),
                            "chunk_text": row[1],
                            "chunk_index": row[2],
                            "document_id": str(row[3]),
                            "filename": row[4],
                            "similarity": round(float(row[5]), 4),
                        })

            # 3. BM25 Keyword Retrieval (BM25Plus)
            if mode in ("hybrid", "bm25"):
                all_chunks_stmt = (
                    select(
                        DocumentChunk.id,
                        DocumentChunk.chunk_text,
                        DocumentChunk.chunk_index,
                        DocumentChunk.document_id,
                        UserDocument.filename,
                    )
                    .join(UserDocument, DocumentChunk.document_id == UserDocument.id)
                    .where(DocumentChunk.document_id.in_(accessible_doc_ids))
                )
                c_res = await session.execute(all_chunks_stmt)
                all_chunks = c_res.all()

                if all_chunks:
                    tokenized_corpus = [_tokenize_text(row[1]) for row in all_chunks]
                    query_tokens = _tokenize_text(clean_query)
                    if query_tokens:
                        bm25 = BM25Plus(tokenized_corpus)
                        scores = bm25.get_scores(query_tokens)
                        scored_chunks = []
                        for idx, score in enumerate(scores):
                            # Include if score is positive or if any query token overlaps
                            has_term_match = any(t in tokenized_corpus[idx] for t in query_tokens)
                            if score > 0 or has_term_match:
                                effective_score = float(score) if score > 0 else 1.0
                                scored_chunks.append((effective_score, all_chunks[idx]))
                        scored_chunks.sort(key=lambda x: x[0], reverse=True)
                        bm25_limit = max(top_k * 3, 15)
                        for score, row in scored_chunks[:bm25_limit]:
                            bm25_candidates.append({
                                "chunk_id": str(row[0]),
                                "chunk_text": row[1],
                                "chunk_index": row[2],
                                "document_id": str(row[3]),
                                "filename": row[4],
                                "bm25_score": round(float(score), 4),
                                "similarity": round(float(score), 4),
                            })

            # 4. Score Fusion (RRF)
            if mode == "vector":
                final_chunks = vector_candidates[:top_k]
            elif mode == "bm25":
                final_chunks = bm25_candidates[:top_k]
            else:
                k_rrf = 60
                rrf_scores: dict[str, float] = {}
                chunk_map: dict[str, dict[str, Any]] = {}

                for rank, item in enumerate(vector_candidates):
                    cid = item["chunk_id"]
                    chunk_map[cid] = item
                    rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (k_rrf + rank + 1))

                for rank, item in enumerate(bm25_candidates):
                    cid = item["chunk_id"]
                    if cid in chunk_map:
                        chunk_map[cid]["bm25_score"] = item.get("bm25_score")
                    else:
                        chunk_map[cid] = item
                    rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (k_rrf + rank + 1))

                sorted_cids = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
                final_chunks = []
                for cid, score in sorted_cids[:top_k]:
                    item = dict(chunk_map[cid])
                    item["rrf_score"] = round(score, 6)
                    final_chunks.append(item)

            # Ensure citation tags on all returned chunks
            for item in final_chunks:
                item["citation_tag"] = f"[Document: {item.get('filename')}, Chunk #{item.get('chunk_index')}]"

            return json.dumps({
                "query": clean_query,
                "total_retrieved": len(final_chunks),
                "results": final_chunks,
            }, indent=2)

        except Exception as e:
            logger.error("RAG search failed: %s", e)
            return json.dumps({"error": f"Search execution failed: {str(e)}", "results": []})


@mcp.tool(tags=["rag", "documents", "list"])
async def list_user_documents(user_id: str) -> str:
    """
    List all ready and indexed documents available for the given user identity.

    Args:
        user_id: Authenticated user ID or email.
    """
    async with _get_session() as session:
        try:
            stmt = (
                select(UserDocument)
                .where(
                    (UserDocument.user_id == user_id) | (UserDocument.user_id == str(user_id).lower().strip())
                )
                .order_by(UserDocument.created_at.desc())
            )
            res = await session.execute(stmt)
            docs_list = res.scalars().all()

            return json.dumps({
                "user_id": user_id,
                "total_documents": len(docs_list),
                "documents": [
                    {
                        "document_id": str(d.id),
                        "filename": d.filename,
                        "file_size_mb": round(d.file_size_bytes / (1024 * 1024), 2),
                        "status": d.status,
                        "created_at": d.created_at.isoformat() if d.created_at else None,
                    }
                    for d in docs_list
                ],
            }, indent=2)
        except Exception as e:
            logger.error("Failed to list documents: %s", e)
            return json.dumps({"error": str(e), "documents": []})


@mcp.tool(tags=["rag", "documents", "snippet"])
async def get_document_snippet(chunk_id: str, user_id: str) -> str:
    """
    Retrieve the full raw text and metadata for a specific chunk.

    Args:
        chunk_id: UUID of the document chunk.
        user_id: Authenticated user ID or email for access verification.
    """
    try:
        chunk_uuid = uuid.UUID(chunk_id.strip())
    except ValueError:
        return json.dumps({"error": "Invalid chunk UUID format."})

    async with _get_session() as session:
        try:
            stmt = (
                select(DocumentChunk, UserDocument)
                .join(UserDocument, DocumentChunk.document_id == UserDocument.id)
                .where(DocumentChunk.id == chunk_uuid)
                .where(
                    (UserDocument.user_id == user_id) | (UserDocument.user_id == str(user_id).lower().strip())
                )
            )
            res = await session.execute(stmt)
            row = res.first()
            if not row:
                return json.dumps({"error": "Chunk not found or unauthorized access."})

            chunk, doc = row
            return json.dumps({
                "chunk_id": str(chunk.id),
                "document_id": str(doc.id),
                "filename": doc.filename,
                "chunk_index": chunk.chunk_index,
                "token_count": chunk.token_count,
                "chunk_text": chunk.chunk_text,
                "created_at": chunk.created_at.isoformat() if chunk.created_at else None,
            }, indent=2)
        except Exception as e:
            logger.error("Failed to get document snippet: %s", e)
            return json.dumps({"error": str(e)})


# 5. MCP Workflow Prompt
@mcp.prompt()
def rag_research_workflow(user_query: str = "") -> str:
    """
    Standard operating procedure prompt for researching knowledge base documents.
    """
    return f"""
You are an expert enterprise research assistant equipped with RAG knowledge base tools.

User Query: {user_query}

Execution Instructions:
1. If the user refers to specific files, check their IDs via `list_user_documents(user_id=...)`.
2. Formulate 2-3 focused keyword/semantic queries from the user question.
3. Call `search_knowledge_base` with `mode='hybrid'`.
4. Synthesize findings with strict citations: `[Document: <filename>, Chunk #<index>]`.
5. If no relevant chunks are found, state clearly that the uploaded documents do not contain the answer.
"""


# 6. CLI Runner for stdio and SSE transports
def main():
    parser = argparse.ArgumentParser(description="Run the RAG MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol: 'stdio' (default, local process) or 'sse' (network)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8020,
        help="Port to run the HTTP/SSE server (only used for '--transport sse')",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host address to run the HTTP/SSE server (default: 0.0.0.0)",
    )
    args = parser.parse_args()

    asyncio.run(docs.setup())

    if args.transport == "sse":
        print(f"Starting rag-server on SSE transport at http://{args.host}:{args.port}")
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
