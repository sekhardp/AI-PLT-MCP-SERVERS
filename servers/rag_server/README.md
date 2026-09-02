# RAG MCP Server

A lightweight, high-performance Model Context Protocol (MCP) server providing direct semantic document search using `pgvector` and Vertex AI embeddings.

## Features
- **Direct Semantic Search**: Uses Vertex AI (`text-embedding-005`) and `pgvector` cosine similarity to retrieve matching raw text passages (10-15 chunks) in a single tool call.
- **Single Source of Truth**: Centralized configuration loaded from `settings.py`.
- **Tools**:
  - `search_knowledge_base`: Searches and returns top 10-15 raw text chunks based on cosine similarity.
  - `check_document_vector_status`: Checks if a document has been successfully vectorized and is ready for retrieval.
  - `list_available_documents`: Lists all uploaded documents in the knowledge base with chunk counts.
- **Dual Transport**: Supports `stdio` (local agent process) and `sse` (HTTP streaming for Cloud Run / Agent Gateway).


