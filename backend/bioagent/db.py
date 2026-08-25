import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import aiosqlite


@dataclass
class Database:
    """SQLite 连接 + 共享锁的捆绑；connect() 创建并返回，全项目共用这一个。

    conn 全项目共享；lock 串行化并发访问（同一连接不能并发 execute/commit）。
    """

    conn: aiosqlite.Connection
    lock: asyncio.Lock

# 迁移列表：每项 (version, (单条 SQL))。升序；已应用（≤ schema_version）的跳过。
_MIGRATIONS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
            """CREATE TABLE task (
                id TEXT PRIMARY KEY,            -- uuid4
                user_message TEXT NOT NULL,     -- 用户原始问题
                status TEXT NOT NULL,           -- TaskStatus（.value）
                plan TEXT NOT NULL,             -- JSON 数组（planner 线性步骤，空 = "[]"）
                steps TEXT NOT NULL,            -- JSON 数组（executor 每步结果，空 = "[]"）
                report TEXT NOT NULL,           -- 最终报告 markdown（空 = ""）
                error TEXT,                     -- 失败原因（str | None，仅 FAILED 时写）
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )""",
            "CREATE INDEX idx_task_created_at ON task(created_at)",
            """CREATE TABLE upload (
                id TEXT PRIMARY KEY,            -- uuid4（file_id）
                original_name TEXT NOT NULL,    -- 原始文件名（元数据展示）
                path TEXT NOT NULL,             -- 落盘绝对路径（uuid 重命名后）
                size INTEGER NOT NULL,          -- 字节数
                created_at REAL NOT NULL
            )""",
            """CREATE TABLE eval_report (
                id TEXT PRIMARY KEY,
                output_id TEXT NOT NULL,
                module TEXT NOT NULL,
                type TEXT NOT NULL,             -- "report" | "tool_call"
                scores TEXT NOT NULL,           -- JSON（EvalScores 5 维）
                token_usage TEXT NOT NULL,      -- JSON {input, output}
                correlation_id TEXT NOT NULL,
                created_at REAL NOT NULL
            )""",
            """CREATE TABLE token_usage (
                id TEXT PRIMARY KEY,
                correlation_id TEXT,            -- str | None，可空
                module TEXT NOT NULL,
                purpose TEXT NOT NULL,          -- intent / plan / report / eval
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                created_at REAL NOT NULL
            )""",
            "CREATE INDEX idx_token_usage_corr ON token_usage(correlation_id)",
        ),
    ),
)


async def connect(path: str) -> Database:
    """打开（或创建）SQLite：设 pragma + row_factory，跑迁移，返回 conn+lock 捆绑。

    path 由组合根（10-api）从 config.db.db_path 传入，本函数不解析默认值。
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)  # 确保父目录存在（首次启动 data/ 尚不存在）
    conn = await aiosqlite.connect(path, isolation_level=None)  # autocommit：migrate 手动 BEGIN 唯一事务控制
    try:
        conn.row_factory = sqlite3.Row
        await conn.execute("PRAGMA foreign_keys = ON")   # 防御性：当前 schema 无 FK，预留将来加表
        await conn.execute("PRAGMA journal_mode = WAL")  # 崩溃安全 + 读写不互斥
        await migrate(conn)
    except BaseException:
        await conn.close()   # 迁移失败：关连接避免泄漏，原异常上抛
        raise
    return Database(conn=conn, lock=asyncio.Lock())


async def migrate(conn: aiosqlite.Connection) -> None:
    """版本化迁移：schema_version 单行记录当前版本，逐版本套用未应用的迁移。

    每版本一个事务（BEGIN/COMMIT/ROLLBACK）：失败整体回滚、版本不推进，
    重启后干净重试——避免非原子迁移部分建表后重跑撞「表已存在」。
    """
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL)"
    )
    cursor = await conn.execute("SELECT version FROM schema_version")
    row = await cursor.fetchone()
    if row is None:
        await conn.execute("INSERT INTO schema_version (id, version) VALUES (1, 0)")
        current = 0
    else:
        current = int(row[0])
    for version, statements in _MIGRATIONS:
        if version <= current:
            continue
        await conn.execute("BEGIN")
        try:
            for stmt in statements:
                await conn.execute(stmt)
            await conn.execute("UPDATE schema_version SET version = ? WHERE id = 1", (version,))
            await conn.commit()
        except BaseException:
            await conn.rollback()
            raise
