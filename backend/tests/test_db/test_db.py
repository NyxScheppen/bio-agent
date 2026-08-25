import asyncio
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiosqlite
import pytest
import pytest_asyncio

import bioagent.db as db


@pytest_asyncio.fixture
async def conn() -> AsyncIterator[aiosqlite.Connection]:
    c = await aiosqlite.connect(":memory:", isolation_level=None)
    c.row_factory = sqlite3.Row
    yield c
    await c.close()


# 测试需检查最高版本 / monkeypatch 追加迁移；直接绑定私有迁移表（spec 03 测试要点要求）
_MIGRATIONS = db._MIGRATIONS  # pyright: ignore[reportPrivateUsage]


async def _table_names(c: aiosqlite.Connection) -> set[str]:
    cur = await c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    rows = await cur.fetchall()
    return {r["name"] for r in rows}


async def _index_names(c: aiosqlite.Connection) -> set[str]:
    cur = await c.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
    )
    rows = await cur.fetchall()
    return {r["name"] for r in rows}


async def _version(c: aiosqlite.Connection) -> int:
    cur = await c.execute("SELECT version FROM schema_version")
    row = await cur.fetchone()
    assert row is not None
    return int(row[0])


async def _notnull(c: aiosqlite.Connection, table: str, column: str) -> int:
    cur = await c.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    for r in rows:
        if r["name"] == column:
            return int(r["notnull"])
    raise AssertionError(f"{table}.{column} 不存在")


async def test_migrate_creates_all_tables_and_indexes(conn: aiosqlite.Connection) -> None:
    await db.migrate(conn)
    assert await _table_names(conn) == {
        "task",
        "upload",
        "eval_report",
        "token_usage",
        "schema_version",
    }
    assert await _index_names(conn) == {"idx_task_created_at", "idx_token_usage_corr"}
    assert await _version(conn) == max(v for v, _ in _MIGRATIONS)


async def test_migrate_nullability_alignment(conn: aiosqlite.Connection) -> None:
    await db.migrate(conn)
    # 可空列（01-types 的 X | None）
    assert await _notnull(conn, "token_usage", "correlation_id") == 0
    assert await _notnull(conn, "task", "error") == 0
    # 非 Optional 字段 → NOT NULL
    assert await _notnull(conn, "eval_report", "correlation_id") == 1
    assert await _notnull(conn, "task", "user_message") == 1
    assert await _notnull(conn, "upload", "original_name") == 1


async def test_migrate_idempotent(conn: aiosqlite.Connection) -> None:
    await db.migrate(conn)
    await db.migrate(conn)
    assert await _version(conn) == max(v for v, _ in _MIGRATIONS)
    assert len(await _table_names(conn)) == 5


async def test_migrate_incremental_gate(
    conn: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    await db.migrate(conn)  # 到 v1
    monkeypatch.setattr(
        db,
        "_MIGRATIONS",
        _MIGRATIONS + ((2, ("CREATE TABLE foo (id TEXT PRIMARY KEY)",)),),
    )
    await db.migrate(conn)  # 只套 v2
    assert await _version(conn) == 2
    assert "foo" in await _table_names(conn)
    assert "task" in await _table_names(conn)


async def test_migrate_atomic_rollback(
    conn: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        db,
        "_MIGRATIONS",
        ((1, ("CREATE TABLE ok (id TEXT PRIMARY KEY)", "这不是合法 SQL")),),
    )
    with pytest.raises(sqlite3.Error):
        await db.migrate(conn)
    assert "ok" not in await _table_names(conn)
    assert await _version(conn) == 0


async def test_connect_returns_database(tmp_path: Path) -> None:
    p = tmp_path / "test.db"
    database = await db.connect(str(p))
    try:
        assert isinstance(database, db.Database)
        assert isinstance(database.lock, asyncio.Lock)
        assert p.exists()

        cur = await database.conn.execute("PRAGMA journal_mode")
        row = await cur.fetchone()
        assert row is not None and row[0] == "wal"

        cur = await database.conn.execute("PRAGMA foreign_keys")
        row = await cur.fetchone()
        assert row is not None and row[0] == 1

        cur = await database.conn.execute("SELECT 1 AS x")
        row = await cur.fetchone()
        assert row is not None and row["x"] == 1
    finally:
        await database.conn.close()


async def test_connect_closes_conn_on_migrate_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "test.db"
    real_connect = aiosqlite.connect

    async def boom(conn: aiosqlite.Connection) -> None:
        raise sqlite3.Error("boom")

    monkeypatch.setattr(db, "migrate", boom)

    closed: list[bool] = []

    async def spy_connect(*args: Any, **kwargs: Any) -> aiosqlite.Connection:
        c = await real_connect(*args, **kwargs)
        original_close = c.close

        async def tracked_close() -> None:
            closed.append(True)
            await original_close()

        monkeypatch.setattr(c, "close", tracked_close)
        return c

    monkeypatch.setattr(db.aiosqlite, "connect", spy_connect)

    with pytest.raises(sqlite3.Error):
        await db.connect(str(p))

    assert closed == [True]
