"""
AgentContext — SQLite 持久化上下文

使用时间戳 + 对话文本递增存储。
每次写入时自动检查最老记录，超过 retention_hours 则批量删除。
to_prompt_block 同时受 max_messages / max_chars 双约束，避免 system prompt 膨胀。

所有 I/O 方法都是 async，内部用 asyncio.to_thread 包装同步 sqlite3 调用，
避免阻塞 asyncio 事件循环。
"""
import asyncio
import sqlite3
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_HOURS = 24
DEFAULT_MAX_MESSAGES = 30
DEFAULT_MAX_CHARS = 5000


class AgentContext:
    """SQLite 持久化的对话上下文（async 接口）"""

    def __init__(self, db_path: Path,
                 retention_hours: int = DEFAULT_RETENTION_HOURS,
                 max_messages: int = DEFAULT_MAX_MESSAGES,
                 max_chars: int = DEFAULT_MAX_CHARS):
        self._db_path = db_path
        self._retention_hours = retention_hours
        self._max_messages = max_messages
        self._max_chars = max_chars
        self._init_db()

    # ── 数据库初始化 ──

    def _init_db(self):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id    INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts    REAL NOT NULL,
                    text  TEXT NOT NULL
                )
            """)
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn

    # ── 写入 ──

    async def add_conversation(self, text: str):
        """追加一条对话记录（带时间戳），并触发过期清理"""
        await asyncio.to_thread(self._add_conversation_sync, text)

    def _add_conversation_sync(self, text: str):
        now = time.time()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO conversations (ts, text) VALUES (?, ?)",
                (now, text),
            )
            conn.commit()
        self._cleanup_old_sync()

    # ── 过期清理 ──

    def _cleanup_old_sync(self):
        """批量删除超过 retention_hours 的记录"""
        cutoff = time.time() - self._retention_hours * 3600
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM conversations WHERE ts < ?", (cutoff,))
            if cur.rowcount > 0:
                logger.debug("[上下文] 批量清理过期记录 %d 条", cur.rowcount)
            conn.commit()

    # ── 读取 ──

    async def get_all(self) -> list[dict]:
        """返回所有未过期记录（按时间正序）"""
        return await asyncio.to_thread(self._get_all_sync)

    def _get_all_sync(self) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, ts, text FROM conversations ORDER BY id ASC"
            ).fetchall()
        return [{"id": r["id"], "ts": r["ts"], "text": r["text"]} for r in rows]

    async def is_empty(self) -> bool:
        return await asyncio.to_thread(self._is_empty_sync)

    def _is_empty_sync(self) -> bool:
        with self._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM conversations").fetchone()
            return row["cnt"] == 0

    async def to_prompt_block(self) -> str:
        """转为注入 System Prompt 的文本块

        双约束截断：
        1. 仅取最近 max_messages 条（按 id 倒序取，再正序拼）
        2. 总字符数不超过 max_chars，从最新记录向前累计，超出则丢弃更老的
        """
        return await asyncio.to_thread(self._to_prompt_block_sync)

    def _to_prompt_block_sync(self) -> str:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT text FROM conversations ORDER BY id DESC LIMIT ?",
                (self._max_messages,),
            ).fetchall()
        if not rows:
            return "## 当前游戏上下文\n（暂无记录）"

        # 从最新向前累计，超出 max_chars 则丢弃更老的
        picked = []
        total = 0
        for r in rows:
            text = r["text"]
            if total + len(text) > self._max_chars and picked:
                break
            picked.append(text)
            total += len(text)
        picked.reverse()  # 恢复时间正序
        return "\n".join(picked)
