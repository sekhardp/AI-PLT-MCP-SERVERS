from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    """
    Single source of truth for RAG MCP Server configuration.
    All runtime parameters, secrets, and retrieval defaults are centralized here.
    """

    # Database Configuration
    db_url: str = os.environ.get(
        "RAG_DB_URL",
        "postgresql+psycopg://postgres:W0uld_Y0u_C0nn3ct_M3@35.184.111.56:5432/postgres",
    )

    # Google Cloud & Vertex AI
    gcp_project: str = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCP_PROJECT")
        or "beam-suntory-gemini-llm-poc"
    )
    gcp_location: str = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    embedding_model: str = os.environ.get("EMBEDDING_MODEL", "text-embedding-005")
    embedding_timeout_seconds: float = float(os.environ.get("EMBEDDING_TIMEOUT_SECONDS", "5.0"))

    # Retrieval Strategy Defaults (Basic Cosine Similarity: 10-15 chunks)
    default_top_k: int = int(os.environ.get("DEFAULT_TOP_K", "10"))
    max_top_k: int = int(os.environ.get("MAX_TOP_K", "15"))

    # Server Defaults
    server_host: str = os.environ.get("SERVER_HOST", "0.0.0.0")
    server_port: int = int(os.environ.get("PORT", "8020"))

    @property
    def normalized_db_url(self) -> str:
        """Ensure psycopg async driver dialect in PostgreSQL connection string."""
        url = self.db_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://")
        return url


# Exported singleton instance
settings = Settings()
