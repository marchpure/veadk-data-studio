from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.db.base import Base
from server.models.query_cache import QueryCache
from server.repositories.query_cache import QueryCacheRepository


@pytest_asyncio.fixture
async def cache_test_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_set_cache_upserts_existing_cache_key(cache_test_session) -> None:
    repo = QueryCacheRepository(cache_test_session)
    query_id = str(uuid4())

    first = await repo.set_cache(
        cache_key="cache:key:1",
        query_id=query_id,
        result_data={"data": [1]},
        ttl_seconds=60,
        has_filters=False,
    )
    second = await repo.set_cache(
        cache_key="cache:key:1",
        query_id=query_id,
        result_data={"data": [2]},
        ttl_seconds=120,
        has_filters=True,
    )

    assert first.cache_key == "cache:key:1"
    assert second.cache_key == "cache:key:1"

    result = await cache_test_session.execute(select(QueryCache).where(QueryCache.cache_key == "cache:key:1"))
    rows = result.scalars().all()

    assert len(rows) == 1
    assert rows[0].result_data == {"data": [2]}
    assert rows[0].ttl_seconds == 120
    assert rows[0].has_filters is True
