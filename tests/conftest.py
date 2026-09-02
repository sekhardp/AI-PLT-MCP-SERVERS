import pytest
import rag_server.db as rag_db
from rag_server.settings import settings

# Ensures tests use the PostgreSQL engine directly
@pytest.fixture(scope="session")
def engine():
    return rag_db.get_engine()
