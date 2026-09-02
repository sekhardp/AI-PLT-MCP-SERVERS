from typing import Optional
from pydantic import BaseModel, Field


class DocumentVectorStatus(BaseModel):
    """Schema representing the vectorization and readiness status of a document."""
    document_id: str = Field(description="UUID of the document")
    filename: Optional[str] = Field(default=None, description="Original filename of the document")
    status: str = Field(description="Indexing status: 'ready', 'indexing', or 'failed'")
    is_vectorized: bool = Field(description="Whether the document is ready and has vector chunks in pgvector")
    total_chunks: int = Field(default=0, description="Total number of vectorized chunks available")
    error_message: Optional[str] = Field(default=None, description="Error message if indexing failed")


class DocumentItem(BaseModel):
    """Schema representing a document item in the knowledge base list."""
    document_id: str = Field(description="UUID of the document")
    filename: str = Field(description="Original filename of the document")
    status: str = Field(description="Document status: 'ready', 'indexing', or 'failed'")
    created_at: Optional[str] = Field(default=None, description="ISO timestamp of when the document was created")
