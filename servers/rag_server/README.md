# RAG MCP Server

A specialized Model Context Protocol (MCP) server providing Hybrid Knowledge Base Search (pgvector + BM25 with Reciprocal Rank Fusion) and document chunk retrieval.

## Features
- **Hybrid Search**: Combines dense Vertex AI embeddings (`text-embedding-005`) with sparse BM25 lexical ranking.
- **Tenant Isolation**: Validates `user_id` on all queries to enforce strict workspace data isolation.
- **Tools**:
  - `search_knowledge_base`: Hybrid document search.
  - `list_user_documents`: Lists ready indexed documents for user.
  - `get_document_snippet`: Fetches raw chunk text and metadata.
- **Dual Transport**: Supports `stdio` (local agent process) and `sse` (HTTP streaming for Cloud Run / Agent Gateway).
