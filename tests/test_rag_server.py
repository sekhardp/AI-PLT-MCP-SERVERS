import pytest
from rag_server.main import (
    mcp,
    search_knowledge_base,
    check_document_vector_status,
    list_available_documents,
)


@pytest.mark.asyncio
async def test_tool_discovery():
    """Verify that the 3 clean RAG tools are registered with FastMCP."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    assert "search_knowledge_base" in tool_names
    assert "check_document_vector_status" in tool_names
    assert "list_available_documents" in tool_names


@pytest.mark.asyncio
async def test_search_empty_query():
    """Verify that searching with an empty query returns an informative error message."""
    result = await search_knowledge_base(query="")
    assert "Error: Empty query provided" in result


@pytest.mark.asyncio
async def test_check_document_vector_status_invalid_uuid():
    """Verify checking status for an invalid UUID string."""
    result = await check_document_vector_status(document_id="invalid-uuid-123")
    assert result.is_vectorized is False
    assert "Invalid document UUID" in result.error_message


@pytest.mark.asyncio
async def test_check_document_vector_status_existing():
    """Verify checking status for an existing document in PostgreSQL."""
    doc_id = "82f969e9-2746-4be2-8369-094c46b3cea1"
    status = await check_document_vector_status(document_id=doc_id)
    assert status.is_vectorized is True
    assert status.total_chunks > 0
    assert status.filename == "Carbon_Credits_Guide.pdf"


@pytest.mark.asyncio
async def test_search_knowledge_base_live():
    """Verify real vector search over PostgreSQL with pgvector."""
    doc_id = "82f969e9-2746-4be2-8369-094c46b3cea1"
    result = await search_knowledge_base(
        query="carbon credits payment components",
        document_id=doc_id,
        top_k=5,
    )
    assert "Relevance:" in result
    assert "Chunk #" in result


@pytest.mark.asyncio
async def test_list_available_documents():
    """Verify listing available documents from PostgreSQL."""
    docs = await list_available_documents(limit=10)
    assert len(docs) >= 1
    assert any(d.filename == "Carbon_Credits_Guide.pdf" for d in docs)
