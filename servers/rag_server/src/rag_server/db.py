from typing import Optional
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from rag_server.settings import settings

_engine: Optional[AsyncEngine] = None


def get_engine() -> AsyncEngine:
    """Lazily initialize and return the PostgreSQL AsyncEngine with connection health checks."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.normalized_db_url,
            future=True,
            pool_pre_ping=True,
        )
    return _engine
