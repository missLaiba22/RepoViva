"""Regression: pooled connections must not outlive an idle database."""

import asyncio

from repository_service import db


def test_pool_keeps_no_idle_connections_and_times_out_queries(monkeypatch):
    seen = {}

    async def create_pool(dsn, **kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(db.asyncpg, "create_pool", create_pool)
    monkeypatch.setattr(db, "_pool", None)

    asyncio.run(db.init_pool())

    assert seen["min_size"] == 0
    assert seen["command_timeout"] > 0
