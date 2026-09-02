import json
import uuid
import pytest
import pytest_asyncio
from rag_server.main import (
    mcp,
    search_knowledge_base,
    list_user_documents,
    get_document_snippet,
    rag_research_workflow,
    UserDocument,
    DocumentChunk,
    AsyncRagSession,
)


@pytest.mark.asyncio
async def test_tool_discovery():
    """Verify that all 3 RAG tools are registered with FastMCP."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "search_knowledge_base" in tool_names
    assert "list_user_documents" in tool_names
    assert "get_document_snippet" in tool_names


@pytest.mark.asyncio
async def test_search_empty_query():
    """Verify that searching with an empty query returns an error response."""
    result = await search_knowledge_base(query="", user_id="test@example.com")
    parsed = json.loads(result)
    assert "error" in parsed
    assert parsed["results"] == []


@pytest.mark.asyncio
async def test_list_user_documents():
    """Verify listing documents for a user returns valid JSON structure."""
    result = await list_user_documents(user_id="nonexistent@example.com")
    parsed = json.loads(result)
    assert "user_id" in parsed
    assert parsed["user_id"] == "nonexistent@example.com"
    assert "documents" in parsed
    assert isinstance(parsed["documents"], list)


@pytest.mark.asyncio
async def test_get_invalid_chunk_snippet():
    """Verify invalid UUID returns proper error."""
    result = await get_document_snippet(chunk_id="not-a-valid-uuid", user_id="test@example.com")
    parsed = json.loads(result)
    assert "error" in parsed
    assert "Invalid chunk UUID" in parsed["error"]


@pytest.mark.asyncio
async def test_search_and_tenant_isolation():
    """Verify searching documents respects user tenant boundary."""
    user_a = "alice@example.com"
    user_b = "bob@example.com"
    doc_id_a = uuid.uuid4()

    # Seed Alice's document into in-memory SQLite
    async with AsyncRagSession() as session:
        doc = UserDocument(
            id=doc_id_a,
            user_id=user_a,
            filename="Financial_Report_2025.pdf",
            file_size_bytes=1024,
            mime_type="application/pdf",
            status="ready",
        )
        chunk = DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc_id_a,
            chunk_index=0,
            chunk_text="In FY2025, operating revenue increased by 22 percent in European markets.",
            token_count=12,
            embedding=[0.1] * 768,
        )
        session.add(doc)
        session.add(chunk)
        await session.commit()

    # 1. Alice lists her documents -> finds 1 document
    alice_docs = json.loads(await list_user_documents(user_id=user_a))
    assert alice_docs["total_documents"] == 1
    assert alice_docs["documents"][0]["filename"] == "Financial_Report_2025.pdf"

    # 2. Bob lists his documents -> finds 0 documents
    bob_docs = json.loads(await list_user_documents(user_id=user_b))
    assert bob_docs["total_documents"] == 0

    # 3. Alice searches with BM25 mode -> finds chunk
    alice_search = json.loads(
        await search_knowledge_base(
            query="European revenue operating",
            user_id=user_a,
            mode="bm25",
        )
    )
    assert alice_search["total_retrieved"] >= 1
    assert "European markets" in alice_search["results"][0]["chunk_text"]

    # 4. Bob searches -> finds 0 results (Tenant isolation enforced)
    bob_search = json.loads(
        await search_knowledge_base(
            query="European revenue operating",
            user_id=user_b,
            mode="bm25",
        )
    )
    assert len(bob_search["results"]) == 0


def test_rag_research_workflow_prompt():
    """Verify that the workflow prompt renders the user query and citation instructions."""
    prompt_text = rag_research_workflow(user_query="What was Q3 profit?")
    assert "What was Q3 profit?" in prompt_text
    assert "search_knowledge_base" in prompt_text
    assert "citations" in prompt_text.lower()


def test_unconfigured_db_session_error(monkeypatch):
    """Verify that _get_session raises RuntimeError when AsyncRagSession is None."""
    import rag_server.main as rag_main
    monkeypatch.setattr(rag_main, "AsyncRagSession", None)
    with pytest.raises(RuntimeError, match="AsyncRagSession is not configured"):
        rag_main._get_session()


