import argparse
import asyncio
import logging
import uuid
from typing import List, Optional

from fastmcp import FastMCP
from fastmcp_docs import FastMCPDocs
from sqlalchemy import text

from rag_server.db import get_engine
from rag_server.embeddings import get_embedding
from rag_server.models import DocumentItem, DocumentVectorStatus
from rag_server.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag-server")

# 1. Initialize FastMCP Server & Documentation
mcp = FastMCP("rag-server")
docs = FastMCPDocs(mcp, title="RAG Knowledge Base Tools")


# 2. Pure PostgreSQL MCP Tools
@mcp.tool(tags=["rag", "search"])
async def search_knowledge_base(
    query: str,
    document_id: Optional[str] = None,
    top_k: int = settings.default_top_k,
) -> str:
    """
    Search document knowledge base using cosine similarity retrieval.
    Returns the top matching raw text passages (default 10-15 chunks) directly.

    Args:
        query: User question or search query to find relevant text for.
        document_id: Optional document UUID to restrict search scope. If omitted, searches all documents.
        top_k: Number of relevant text chunks to return (default: 10, max: 15).
    """
    clean_query = query.strip()
    if not clean_query:
        return "Error: Empty query provided."

    query_vec = await get_embedding(clean_query)
    if not query_vec:
        return "Error: Failed to generate embedding for query."

    limit = min(max(top_k, 1), settings.max_top_k)
    params = {
        "vec": f"[{','.join(str(x) for x in query_vec)}]",
        "top_k": limit,
    }

    where_clause = ""
    if document_id:
        try:
            params["doc_id"] = str(uuid.UUID(document_id.strip()))
            where_clause = "WHERE document_id = :doc_id"
        except ValueError:
            return f"Error: Invalid document UUID '{document_id}'."

    sql = text(f"""
        SELECT chunk_index, chunk_text, (1.0 - (embedding <=> (:vec)::vector)) AS similarity
        FROM document_chunks
        {where_clause}
        ORDER BY embedding <=> (:vec)::vector
        LIMIT :top_k
    """)

    engine = get_engine()
    async with engine.connect() as conn:
        try:
            res = await conn.execute(sql, params)
            rows = res.all()
            if not rows:
                return "No relevant text chunks found for the given query."

            return "\n\n".join(
                f"--- [Chunk #{r[0]} | Relevance: {round(float(r[2]), 4)}] ---\n{r[1]}"
                for r in rows
            )
        except Exception as e:
            logger.error("Failed to search knowledge base: %s", e)
            return f"Search error: {str(e)}"


@mcp.tool(tags=["rag", "status"])
async def check_document_vector_status(document_id: str) -> DocumentVectorStatus:
    """
    Check if a document has been successfully vectorized and is ready for semantic retrieval.

    Args:
        document_id: UUID of the document to inspect.
    """
    try:
        doc_str = str(uuid.UUID(document_id.strip()))
    except ValueError:
        return DocumentVectorStatus(
            document_id=document_id,
            status="error",
            is_vectorized=False,
            error_message="Invalid document UUID format",
        )

    engine = get_engine()
    async with engine.connect() as conn:
        try:
            doc_res = await conn.execute(
                text("SELECT filename, status, error_message FROM user_documents WHERE id = :doc_uuid"),
                {"doc_uuid": doc_str},
            )
            doc = doc_res.first()
            if not doc:
                return DocumentVectorStatus(
                    document_id=doc_str,
                    status="not_found",
                    is_vectorized=False,
                    error_message="Document not found",
                )

            chunk_res = await conn.execute(
                text("SELECT COUNT(*) FROM document_chunks WHERE document_id = :doc_uuid"),
                {"doc_uuid": doc_str},
            )
            chunk_count = chunk_res.scalar() or 0

            return DocumentVectorStatus(
                document_id=doc_str,
                filename=doc[0],
                status=doc[1],
                is_vectorized=(doc[1] == "ready" and chunk_count > 0),
                total_chunks=chunk_count,
                error_message=doc[2],
            )
        except Exception as e:
            logger.error("Failed to check document vector status: %s", e)
            return DocumentVectorStatus(
                document_id=doc_str,
                status="error",
                is_vectorized=False,
                error_message=str(e),
            )


@mcp.tool(tags=["rag", "documents"])
async def list_available_documents(limit: int = 50) -> List[DocumentItem]:
    """
    List all available documents in the knowledge base.

    Args:
        limit: Maximum number of documents to return (default: 50).
    """
    engine = get_engine()
    async with engine.connect() as conn:
        try:
            res = await conn.execute(
                text("""
                    SELECT id, filename, status, created_at
                    FROM user_documents
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            )
            return [
                DocumentItem(
                    document_id=str(row[0]),
                    filename=row[1],
                    status=row[2],
                    created_at=row[3].isoformat() if hasattr(row[3], "isoformat") else str(row[3]) if row[3] else None,
                )
                for row in res.all()
            ]
        except Exception as e:
            logger.error("Failed to list available documents: %s", e)
            return []


# 3. CLI Runner
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
        default=settings.server_port,
        help=f"Port to run the HTTP/SSE server (default: {settings.server_port})",
    )
    parser.add_argument(
        "--host",
        default=settings.server_host,
        help=f"Host address to run the HTTP/SSE server (default: {settings.server_host})",
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
