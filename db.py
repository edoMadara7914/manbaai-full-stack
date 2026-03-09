from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import SETTINGS


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_days_iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._init_db()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    language_code TEXT DEFAULT 'uz',
                    interface_language TEXT,
                    role TEXT DEFAULT 'user',
                    is_active INTEGER DEFAULT 1,
                    current_plan TEXT DEFAULT 'free',
                    plan_expires_at TEXT,
                    daily_questions_used INTEGER DEFAULT 0,
                    daily_questions_date TEXT,
                    referrer_id INTEGER,
                    referral_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_chat_id TEXT NOT NULL,
                    title TEXT,
                    url TEXT,
                    is_required INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_user_id INTEGER NOT NULL,
                    telegram_file_id TEXT,
                    telegram_file_unique_id TEXT,
                    original_file_name TEXT,
                    display_name TEXT,
                    mime_type TEXT,
                    source_kind TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    moderation_status TEXT DEFAULT 'approved',
                    preview_text TEXT,
                    page_count INTEGER DEFAULT 0,
                    section_hint TEXT,
                    content_hash TEXT,
                    file_size INTEGER DEFAULT 0,
                    is_deleted INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS document_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    chunk_text TEXT NOT NULL,
                    source_page TEXT,
                    source_section TEXT,
                    embedding_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id)
                );

                CREATE TABLE IF NOT EXISTS question_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER NOT NULL,
                    question_text TEXT NOT NULL,
                    question_language TEXT,
                    private_answer TEXT,
                    public_answer TEXT,
                    private_source TEXT,
                    public_source TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    category TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS exports_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_user_id INTEGER NOT NULL,
                    export_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS moderation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    admin_user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_user_id INTEGER NOT NULL,
                    plan TEXT NOT NULL,
                    source TEXT NOT NULL,
                    amount INTEGER DEFAULT 0,
                    provider TEXT,
                    granted_by_admin_id INTEGER,
                    started_at TEXT NOT NULL,
                    expires_at TEXT,
                    status TEXT DEFAULT 'active'
                );
                """
            )

    @staticmethod
    def serialize_embedding(vec: list[float]) -> str:
        return json.dumps(vec)

    @staticmethod
    def deserialize_embedding(raw: str | None) -> list[float]:
        if not raw:
            return []
        try:
            return json.loads(raw)
        except Exception:
            return []

    def upsert_user(self, telegram_user_id: int, username: str | None, full_name: str, language_code: str | None) -> None:
        now = utcnow()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (telegram_user_id, username, full_name, language_code, created_at, updated_at, daily_questions_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    username=excluded.username,
                    full_name=excluded.full_name,
                    language_code=excluded.language_code,
                    updated_at=excluded.updated_at
                """,
                (telegram_user_id, username, full_name, language_code or 'uz', now, now, datetime.now(timezone.utc).date().isoformat()),
            )

    def ensure_admin_roles(self) -> None:
        with self.connect() as conn:
            for admin_id in SETTINGS.admin_user_ids:
                conn.execute("UPDATE users SET role='admin', updated_at=? WHERE telegram_user_id=?", (utcnow(), admin_id))

    def set_interface_language(self, user_id: int, lang: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE users SET interface_language=?, updated_at=? WHERE telegram_user_id=?", (lang, utcnow(), user_id))

    def get_interface_language(self, user_id: int) -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT interface_language FROM users WHERE telegram_user_id=?", (user_id,)).fetchone()
            return row["interface_language"] if row and row["interface_language"] else SETTINGS.default_language

    def get_role(self, user_id: int) -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT role FROM users WHERE telegram_user_id=?", (user_id,)).fetchone()
            return row["role"] if row else "user"

    def list_required_channels(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM channels WHERE is_required=1 AND is_active=1 ORDER BY id ASC").fetchall()

    def add_channel(self, chat_id: str, title: str, url: str, is_required: int = 1) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO channels (telegram_chat_id, title, url, is_required, is_active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
                (chat_id, title, url, is_required, utcnow()),
            )

    def add_document(self, **kwargs: Any) -> int:
        now = utcnow()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO documents (
                    owner_user_id, telegram_file_id, telegram_file_unique_id, original_file_name, display_name,
                    mime_type, source_kind, scope, moderation_status, preview_text, page_count,
                    section_hint, content_hash, file_size, is_deleted, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    kwargs["owner_user_id"],
                    kwargs.get("telegram_file_id"),
                    kwargs.get("telegram_file_unique_id"),
                    kwargs.get("original_file_name"),
                    kwargs.get("display_name"),
                    kwargs.get("mime_type"),
                    kwargs["source_kind"],
                    kwargs["scope"],
                    kwargs.get("moderation_status", "approved"),
                    kwargs.get("preview_text"),
                    kwargs.get("page_count", 1),
                    kwargs.get("section_hint"),
                    kwargs.get("content_hash"),
                    kwargs.get("file_size", 0),
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def add_chunks(self, document_id: int, chunks: list[dict]) -> None:
        with self.connect() as conn:
            for chunk in chunks:
                conn.execute(
                    """
                    INSERT INTO document_chunks (document_id, chunk_index, chunk_text, source_page, source_section, embedding_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        chunk["chunk_index"],
                        chunk["chunk_text"],
                        chunk.get("source_page", ""),
                        chunk.get("source_section", ""),
                        self.serialize_embedding(chunk.get("embedding", [])),
                        utcnow(),
                    ),
                )

    def find_duplicate_by_hash(self, content_hash: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, COALESCE(display_name, original_file_name, 'Fayl') AS file_name FROM documents WHERE content_hash=? AND is_deleted=0 ORDER BY id DESC LIMIT 1",
                (content_hash,),
            ).fetchone()

    def list_user_documents(self, user_id: int, scope: str | None = None) -> list[sqlite3.Row]:
        with self.connect() as conn:
            if scope:
                return conn.execute(
                    "SELECT * FROM documents WHERE owner_user_id=? AND scope=? AND is_deleted=0 ORDER BY id DESC",
                    (user_id, scope),
                ).fetchall()
            return conn.execute("SELECT * FROM documents WHERE owner_user_id=? AND is_deleted=0 ORDER BY id DESC", (user_id,)).fetchall()

    def list_public_documents(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM documents WHERE scope='public' AND is_deleted=0 ORDER BY id DESC"
            ).fetchall()

    def list_pending_public_documents(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM documents WHERE scope='public' AND moderation_status='pending' AND is_deleted=0 ORDER BY id DESC"
            ).fetchall()

    def get_document(self, doc_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()

    def rename_document(self, doc_id: int, new_name: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE documents SET display_name=?, updated_at=? WHERE id=?", (new_name, utcnow(), doc_id))

    def soft_delete_document(self, doc_id: int) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE documents SET is_deleted=1, updated_at=? WHERE id=?", (utcnow(), doc_id))

    def set_document_moderation_status(self, doc_id: int, status: str, admin_user_id: int | None = None) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE documents SET moderation_status=?, updated_at=? WHERE id=?", (status, utcnow(), doc_id))
            if admin_user_id:
                conn.execute(
                    "INSERT INTO moderation_log (document_id, admin_user_id, action, created_at) VALUES (?, ?, ?, ?)",
                    (doc_id, admin_user_id, status, utcnow()),
                )

    def list_searchable_documents(self, user_id: int, scope: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            if scope == "private":
                return conn.execute(
                    """
                    SELECT dc.*, d.id AS document_id, COALESCE(d.display_name, d.original_file_name) AS file_name,
                           d.section_hint, d.display_name
                    FROM document_chunks dc
                    JOIN documents d ON d.id = dc.document_id
                    WHERE d.owner_user_id=? AND d.scope='private' AND d.is_deleted=0
                    ORDER BY d.id DESC, dc.chunk_index ASC
                    """,
                    (user_id,),
                ).fetchall()
            return conn.execute(
                """
                SELECT dc.*, d.id AS document_id, COALESCE(d.display_name, d.original_file_name) AS file_name,
                       d.section_hint, d.display_name
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                WHERE d.scope='public' AND d.moderation_status='approved' AND d.is_deleted=0
                ORDER BY d.id DESC, dc.chunk_index ASC
                """
            ).fetchall()

    def add_history(self, **kwargs: Any) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO question_history (telegram_user_id, question_text, question_language, private_answer, public_answer, private_source, public_source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kwargs["telegram_user_id"], kwargs["question_text"], kwargs.get("question_language"),
                    kwargs.get("private_answer"), kwargs.get("public_answer"), kwargs.get("private_source"), kwargs.get("public_source"), utcnow()
                ),
            )
            return int(cur.lastrowid)

    def list_history(self, user_id: int, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM question_history WHERE telegram_user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()

    def clear_history(self, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM question_history WHERE telegram_user_id=?", (user_id,))

    def add_log(self, level: str, category: str, message: str, payload: dict | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO logs (level, category, message, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (level, category, message, json.dumps(payload or {}, ensure_ascii=False), utcnow()),
            )

    def list_logs(self, limit: int = 25) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def add_export_log(self, admin_user_id: int, export_type: str, file_path: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO exports_log (admin_user_id, export_type, file_path, created_at) VALUES (?, ?, ?, ?)",
                (admin_user_id, export_type, file_path, utcnow()),
            )

    def dashboard_stats(self) -> dict[str, int]:
        with self.connect() as conn:
            def scalar(query: str) -> int:
                return int(conn.execute(query).fetchone()[0])

            today = datetime.now(timezone.utc).date().isoformat()
            return {
                "users": scalar("SELECT COUNT(*) FROM users"),
                "documents": scalar("SELECT COUNT(*) FROM documents WHERE is_deleted=0"),
                "public_documents": scalar("SELECT COUNT(*) FROM documents WHERE scope='public' AND is_deleted=0"),
                "private_documents": scalar("SELECT COUNT(*) FROM documents WHERE scope='private' AND is_deleted=0"),
                "pending_public": scalar("SELECT COUNT(*) FROM documents WHERE scope='public' AND moderation_status='pending' AND is_deleted=0"),
                "questions_today": int(conn.execute("SELECT COUNT(*) FROM question_history WHERE substr(created_at, 1, 10)=?", (today,)).fetchone()[0]),
                "uploads_today": int(conn.execute("SELECT COUNT(*) FROM documents WHERE substr(created_at, 1, 10)=?", (today,)).fetchone()[0]),
            }

    def ensure_daily_counter(self, user_id: int) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        with self.connect() as conn:
            row = conn.execute("SELECT daily_questions_date FROM users WHERE telegram_user_id=?", (user_id,)).fetchone()
            if row and row["daily_questions_date"] != today:
                conn.execute("UPDATE users SET daily_questions_used=0, daily_questions_date=?, updated_at=? WHERE telegram_user_id=?", (today, utcnow(), user_id))

    def get_plan(self, user_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT current_plan, plan_expires_at, daily_questions_used, daily_questions_date FROM users WHERE telegram_user_id=?",
                (user_id,),
            ).fetchone()
            if not row:
                return {"plan": "free", "expires_at": None, "used": 0}
            plan = row["current_plan"] or "free"
            expires = row["plan_expires_at"]
            if expires:
                try:
                    if datetime.fromisoformat(expires) < datetime.now(timezone.utc):
                        self.set_plan(user_id, "free", None, source="system")
                        return {"plan": "free", "expires_at": None, "used": 0}
                except Exception:
                    pass
            return {"plan": plan, "expires_at": expires, "used": row["daily_questions_used"] or 0}

    def set_plan(self, user_id: int, plan: str, expires_at: str | None, source: str, amount: int = 0, provider: str | None = None, granted_by_admin_id: int | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET current_plan=?, plan_expires_at=?, updated_at=? WHERE telegram_user_id=?",
                (plan, expires_at, utcnow(), user_id),
            )
            conn.execute(
                "INSERT INTO subscriptions (telegram_user_id, plan, source, amount, provider, granted_by_admin_id, started_at, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
                (user_id, plan, source, amount, provider, granted_by_admin_id, utcnow(), expires_at),
            )

    def grant_plan_days(self, user_id: int, plan: str, days: int, source: str, amount: int = 0, provider: str | None = None, granted_by_admin_id: int | None = None) -> None:
        current = self.get_plan(user_id)
        now = datetime.now(timezone.utc)
        start_from = now
        if current["plan"] == plan and current.get("expires_at"):
            try:
                expires_dt = datetime.fromisoformat(current["expires_at"])
                if expires_dt > now:
                    start_from = expires_dt
            except Exception:
                pass
        expires_at = (start_from + timedelta(days=days)).isoformat()
        self.set_plan(user_id, plan, expires_at, source=source, amount=amount, provider=provider, granted_by_admin_id=granted_by_admin_id)

    def get_daily_limit(self, user_id: int) -> int:
        plan = self.get_plan(user_id)["plan"]
        if plan == "basic":
            return SETTINGS.basic_daily_limit
        if plan == "premium":
            return SETTINGS.premium_daily_limit
        return SETTINGS.free_daily_limit

    def can_ask_question(self, user_id: int) -> tuple[bool, int, int]:
        self.ensure_daily_counter(user_id)
        plan = self.get_plan(user_id)
        limit = self.get_daily_limit(user_id)
        used = int(plan.get("used") or 0)
        return used < limit, used, limit

    def increase_daily_questions(self, user_id: int) -> None:
        self.ensure_daily_counter(user_id)
        with self.connect() as conn:
            conn.execute("UPDATE users SET daily_questions_used = COALESCE(daily_questions_used, 0) + 1, updated_at=? WHERE telegram_user_id=?", (utcnow(), user_id))

    def add_referral(self, new_user_id: int, referrer_id: int) -> bool:
        if new_user_id == referrer_id:
            return False
        with self.connect() as conn:
            row = conn.execute("SELECT referrer_id FROM users WHERE telegram_user_id=?", (new_user_id,)).fetchone()
            if not row or row["referrer_id"]:
                return False
            conn.execute("UPDATE users SET referrer_id=?, updated_at=? WHERE telegram_user_id=?", (referrer_id, utcnow(), new_user_id))
            conn.execute("UPDATE users SET referral_count = COALESCE(referral_count, 0) + 1, updated_at=? WHERE telegram_user_id=?", (utcnow(), referrer_id))
            ref_count = conn.execute("SELECT referral_count FROM users WHERE telegram_user_id=?", (referrer_id,)).fetchone()[0]
            if ref_count and ref_count % 5 == 0:
                self.grant_plan_days(referrer_id, "basic", 7, source="referral")
            return True

    def get_referral_info(self, user_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT referral_count FROM users WHERE telegram_user_id=?", (user_id,)).fetchone()
            count = int(row[0]) if row else 0
            progress = count % 5
            remaining = 5 - progress if progress else 5
            if count and progress == 0:
                remaining = 5
            return {"count": count, "remaining": remaining}


DB = Database(SETTINGS.database_path)
