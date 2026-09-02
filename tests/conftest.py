import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import rag_server.main as rag_main
from rag_server.main import Base

# Setup in-memory SQLite engine for tests
test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
)
TestAsyncSession = sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)

# Patch rag_server sessionmaker to use in-memory SQLite
rag_main.AsyncRagSession = TestAsyncSession


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
