"""
情感分析结果存储（design/03 §6，D5「Web 只读」的唯一写例外）

写入路径收敛在本模块一处（ai_runner 落库），其余端点严格只读：
- 写：当日 news 库追加 ai_sentiment_results；独立连接 + BEGIN IMMEDIATE +
  INSERT OR IGNORE（UNIQUE 判重）+ ensure_table()；失败即弃（缓存层仍会命中，
  不阻塞管线主写入）
- 读：mode=ro URI（永不误建空库）；缺表/缺库静默跳过

存储域归属标注（02-D5 修正案）：Track B 落地 workbench.db 时本表迁移到独立库，
接口语义不变。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, timedelta
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_sentiment_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL DEFAULT '',
    date_start TEXT NOT NULL,
    date_end   TEXT NOT NULL,
    platforms  TEXT DEFAULT '',
    prompt_hash TEXT NOT NULL,
    result_json TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(topic, date_start, date_end, platforms, prompt_hash)
)
"""


class SentimentStore:
    """ai_sentiment_results 的唯一读写入口（按日分库，锚定 date_end 当日库）"""

    def __init__(self, output_root: Path):
        self._news_dir = Path(output_root) / "news"
        self._write_lock = threading.Lock()  # BEGIN IMMEDIATE 串行化（单进程 web）

    # ---------- 路径 ----------

    def _db_path(self, day: date) -> Path:
        return self._news_dir / f"{day.isoformat()}.db"

    def _connect_ro(self, db_path: Path) -> sqlite3.Connection:
        """只读 URI 连接（URL 编码，与 parser_service._open_sqlite 同约定）"""
        import urllib.parse

        uri = "file:" + urllib.parse.quote(str(db_path.resolve())) + "?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=5)

    # ---------- 写（唯一写路径） ----------

    def save(
        self,
        *,
        date_end: date,
        topic: str,
        date_start: str,
        date_end_str: str,
        platforms: str,
        prompt_hash: str,
        result: dict,
        model: str,
    ) -> None:
        """
        落库；失败即弃（打日志不抛错——分析结果已在响应与缓存层，写库只为回看）。
        BEGIN IMMEDIATE + INSERT OR IGNORE：UNIQUE 判重，重复写静默忽略。
        """
        sql = """
INSERT OR IGNORE INTO ai_sentiment_results
    (topic, date_start, date_end, platforms, prompt_hash, result_json, model)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""
        try:
            with self._write_lock:
                conn = sqlite3.connect(str(self._db_path(date_end)), timeout=5)
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(_SCHEMA)  # ensure_table（旧库无此表，新库已由 schema.sql 建好）
                    conn.execute(sql, (
                        topic, date_start, date_end_str, platforms,
                        prompt_hash, json.dumps(result, ensure_ascii=False), model,
                    ))
                    conn.commit()
                finally:
                    conn.close()
        except sqlite3.Error as e:
            print(f"Warning: ai_sentiment_results 落库失败（已忽略）: {e}")

    # ---------- 读 ----------

    def find(
        self,
        *,
        date_end: date,
        topic: str,
        date_start: str,
        date_end_str: str,
        platforms: str,
        prompt_hash: str,
    ) -> dict | None:
        """按唯一键查历史结果（进程重启后缓存命中走这里）；缺库/缺表返回 None"""
        sql = """
SELECT result_json, model, created_at FROM ai_sentiment_results
WHERE topic=? AND date_start=? AND date_end=? AND platforms=? AND prompt_hash=?
LIMIT 1
"""
        try:
            conn = self._connect_ro(self._db_path(date_end))
            try:
                row = conn.execute(sql, (topic, date_start, date_end_str, platforms, prompt_hash)).fetchone()
            finally:
                conn.close()
        except sqlite3.Error:
            return None  # 缺库/缺表
        if not row:
            return None
        try:
            return {"result": json.loads(row[0]), "model": row[1], "created_at": row[2]}
        except (ValueError, TypeError):
            return None

    def query(
        self,
        *,
        topic: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        跨日历史查询：遍历窗口内实际存在的日库（mode=ro，缺表静默跳过），
        按创建时间倒序合并，limit 截断。
        """
        days = self._existing_days()
        if not days:
            return []

        where = ["1=1"]
        params: list = []
        if topic:
            where.append("topic = ?")
            params.append(topic)
        if date_start:
            where.append("date_end >= ?")
            params.append(date_start)
        if date_end:
            where.append("date_end <= ?")
            params.append(date_end)

        sql = f"""
SELECT topic, date_start, date_end, platforms, prompt_hash, result_json, model, created_at
FROM ai_sentiment_results
WHERE {' AND '.join(where)}
ORDER BY created_at DESC
LIMIT ?
"""
        params.append(int(limit))

        rows: list[dict] = []
        for day in days:
            try:
                conn = self._connect_ro(self._db_path(day))
                try:
                    for r in conn.execute(sql, params):
                        try:
                            result = json.loads(r[5])
                        except (ValueError, TypeError):
                            continue
                        rows.append({
                            "topic": r[0], "date_start": r[1], "date_end": r[2],
                            "platforms": r[3], "prompt_hash": r[4], "result": result,
                            "model": r[6], "created_at": r[7],
                        })
                finally:
                    conn.close()
            except sqlite3.Error:
                continue  # 缺表/被管线占锁的日库跳过

        rows.sort(key=lambda x: str(x.get("created_at")), reverse=True)
        return rows[: int(limit)]

    def _existing_days(self) -> list[date]:
        """窗口内的实际日库（磁盘上存在的 db 文件），升序"""
        if not self._news_dir.is_dir():
            return []
        days: list[date] = []
        for p in self._news_dir.glob("*.db"):
            try:
                days.append(date.fromisoformat(p.stem))
            except ValueError:
                continue  # 非日期命名的库文件
        return sorted(days)
