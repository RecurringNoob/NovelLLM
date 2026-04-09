"""
tests/conftest.py — Shared fixtures for the Novel Writing Assistant test suite.

Provides:
  - async_engine   (session-scoped) — real asyncpg engine against TEST_DATABASE_URL
  - db_session     (function-scoped) — nested transaction, auto-rollback after each test
  - async_client   (function-scoped) — httpx.AsyncClient with dependency overrides
  - fake_redis     (function-scoped) — fakeredis.aioredis.FakeRedis instance

Environment variable required:
  TEST_DATABASE_URL — e.g. postgresql+asyncpg://notelm:notelm_secret@localhost:5432/notelm_test
  Falls back to the default dev DATABASE_URL when not set (use with care).
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ── Import app AFTER setting env so config picks up test overrides ──────
from app.main import app
from app.dependencies import get_current_user, get_db

# Dev user UUID matches settings.dev_user_id
DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# ── Determine test database URL ─────────────────────────────────────────
def _test_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "Set TEST_DATABASE_URL (or DATABASE_URL) to run infrastructure tests against a real DB."
        )
    return url


# ── Session-scoped engine (one per test run) ────────────────────────────
@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default asyncio policy; required by pytest-asyncio in strict mode."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture(scope="session")
async def async_engine():
    """
    Session-scoped async SQLAlchemy engine.

    Uses prepared_statement_cache_size=0 to match the production config required
    for Neon Postgres / PgBouncer in transaction mode.
    """
    url = _test_db_url()
    engine = create_async_engine(
        url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        connect_args={
            "prepared_statement_cache_size": 0,
            "server_settings": {"application_name": "notelm_test"},
        },
    )
    yield engine
    await engine.dispose()


# ── Function-scoped DB session with rollback isolation ──────────────────
@pytest_asyncio.fixture
async def db_session(async_engine):
    """
    Provide a database session that wraps each test in a SAVEPOINT (nested
    transaction). The outer BEGIN is rolled back at the end of the test so
    each test starts with a clean slate without truncating tables.
    """
    async with async_engine.connect() as conn:
        await conn.begin()
        # Use begin_nested() for SAVEPOINT support
        await conn.begin_nested()

        session_factory = async_sessionmaker(
            bind=conn,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        async with session_factory() as session:
            yield session

        await conn.rollback()


# ── Fake Redis fixture ───────────────────────────────────────────────────
@pytest_asyncio.fixture
async def fake_redis():
    """
    In-memory FakeRedis that supports the full redis.asyncio API surface
    (Pub/Sub, Streams, xadd, subscribe, etc.).
    """
    try:
        import fakeredis.aioredis as aioredis_fake
        r = aioredis_fake.FakeRedis(decode_responses=True)
    except ImportError:
        pytest.skip("fakeredis not installed — pip install fakeredis")
    yield r
    await r.aclose()


# ── HTTP client with dependency overrides ────────────────────────────────
@pytest_asyncio.fixture
async def async_client(db_session, fake_redis):
    """
    httpx.AsyncClient wired to the FastAPI app with:
      - get_db overridden to use db_session (with rollback isolation)
      - get_current_user overridden to return a static DevUser
      - Redis pool overridden to use FakeRedis
    """
    from app.dependencies import DevUser
    from app.core import redis_client as _rc

    # Override DB dependency
    async def _override_get_db():
        yield db_session

    # Override auth dependency
    async def _override_get_current_user():
        return DevUser(user_id=str(DEV_USER_ID))

    # Inject fake redis into the module-level pool
    _original_pool = _rc._redis_pool
    _rc._redis_pool = fake_redis

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    # Restore
    app.dependency_overrides.clear()
    _rc._redis_pool = _original_pool
