"""
Looploop SQLite 数据库层

替代内存 dict 作为任务存储，提供持久化和历史记录能力。
使用 aiosqlite 异步驱动，与 FastAPI 的 async/await 模型一致。
"""

import json
import aiosqlite
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "looploop.db"


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接"""
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    """初始化数据库表（在应用启动时调用）"""
    db = await get_db()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'Untitled',
            status TEXT NOT NULL DEFAULT 'pending',
            progress REAL NOT NULL DEFAULT 0.0,
            stage TEXT DEFAULT '',
            message TEXT DEFAULT '',
            result_json TEXT,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_tasks_created_at
        ON tasks(created_at DESC)
    """)
    await db.commit()
    await db.close()


async def create_task(task_id: str, title: str = "Untitled") -> dict:
    """创建新任务"""
    db = await get_db()
    await db.execute(
        "INSERT INTO tasks (task_id, title) VALUES (?, ?)",
        (task_id, title),
    )
    await db.commit()
    await db.close()
    return {"task_id": task_id, "title": title, "status": "pending"}


async def get_task(task_id: str) -> Optional[dict]:
    """获取单个任务"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
    )
    row = await cursor.fetchone()
    await db.close()
    if row is None:
        return None
    return _row_to_dict(row)


async def update_task(task_id: str, **kwargs):
    """更新任务字段"""
    if not kwargs:
        return
    # 对 result_json 特殊处理
    if "result" in kwargs:
        kwargs["result_json"] = json.dumps(kwargs.pop("result"), ensure_ascii=False)
    if "data" in kwargs:
        kwargs.pop("data")  # data 字段暂不存储，仅用于 SSE 传输

    sets = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values())
    values.append(task_id)

    db = await get_db()
    await db.execute(
        f"UPDATE tasks SET {sets} WHERE task_id = ?", values
    )
    await db.commit()
    await db.close()


async def list_tasks(limit: int = 20) -> list[dict]:
    """列出最近的任务（按创建时间倒序）"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT task_id, title, status, progress, stage, message, "
        "created_at FROM tasks ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    await db.close()
    return [_row_to_dict(r) for r in rows]


async def delete_task(task_id: str):
    """删除任务"""
    db = await get_db()
    await db.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
    await db.commit()
    await db.close()


async def save_screenplay(task_id: str, screenplay_data: dict):
    """保存编辑后的剧本"""
    db = await get_db()
    await db.execute(
        "UPDATE tasks SET result_json = ? WHERE task_id = ?",
        (json.dumps(screenplay_data, ensure_ascii=False), task_id),
    )
    await db.commit()
    await db.close()


def _row_to_dict(row: aiosqlite.Row) -> dict:
    """将数据库行转为 dict，解析 result_json"""
    d = dict(row)
    if d.get("result_json"):
        try:
            d["result"] = json.loads(d["result_json"])
        except json.JSONDecodeError:
            d["result"] = None
        del d["result_json"]
    return d
