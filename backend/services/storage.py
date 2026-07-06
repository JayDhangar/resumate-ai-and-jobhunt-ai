"""Pluggable document storage.

Two interchangeable backends behind one interface:

* :class:`SQLiteStore` (default) — zero-config, stores JSON documents in
  ``database/resume_builder.db``.
* :class:`MongoStore` — enabled automatically when ``MONGODB_URL`` is set in
  the environment / ``.env`` file.

All documents are plain JSON-serialisable dicts with an ``id`` key.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from typing import Any

from core.config import get_settings
from core.logging_config import get_logger

logger = get_logger("storage")


class DocumentStore(ABC):
    """Minimal document-store interface shared by all backends."""

    @abstractmethod
    def put(self, collection: str, doc: dict[str, Any]) -> None: ...

    @abstractmethod
    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def delete(self, collection: str, doc_id: str) -> bool: ...

    @abstractmethod
    def list(self, collection: str) -> list[dict[str, Any]]: ...

    def find(self, collection: str, predicate) -> list[dict[str, Any]]:
        return [d for d in self.list(collection) if predicate(d)]

    def close(self) -> None:  # pragma: no cover - optional hook
        pass


class SQLiteStore(DocumentStore):
    """JSON document store backed by a single SQLite table."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                collection TEXT NOT NULL,
                id TEXT NOT NULL,
                data TEXT NOT NULL,
                PRIMARY KEY (collection, id)
            )
            """
        )
        self._conn.commit()
        logger.info("SQLiteStore ready at %s", path)

    def put(self, collection: str, doc: dict[str, Any]) -> None:
        doc_id = str(doc["id"])
        payload = json.dumps(doc, default=str)
        with self._lock:
            self._conn.execute(
                "INSERT INTO documents (collection, id, data) VALUES (?, ?, ?) "
                "ON CONFLICT(collection, id) DO UPDATE SET data = excluded.data",
                (collection, doc_id, payload),
            )
            self._conn.commit()

    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM documents WHERE collection = ? AND id = ?",
                (collection, str(doc_id)),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def delete(self, collection: str, doc_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM documents WHERE collection = ? AND id = ?",
                (collection, str(doc_id)),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def list(self, collection: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM documents WHERE collection = ?", (collection,)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class MongoStore(DocumentStore):
    """MongoDB-backed store, selected when MONGODB_URL is configured."""

    def __init__(self, url: str, db_name: str) -> None:
        try:
            from pymongo import MongoClient
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "MONGODB_URL is set but pymongo is not installed. "
                "Run: pip install pymongo"
            ) from exc
        self._client = MongoClient(url, serverSelectionTimeoutMS=5000)
        self._db = self._client[db_name]
        # fail fast so we can fall back to SQLite on bad URLs
        self._client.admin.command("ping")
        logger.info("MongoStore connected to database '%s'", db_name)

    def put(self, collection: str, doc: dict[str, Any]) -> None:
        payload = json.loads(json.dumps(doc, default=str))
        self._db[collection].replace_one({"id": str(doc["id"])}, payload, upsert=True)

    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        doc = self._db[collection].find_one({"id": str(doc_id)}, {"_id": 0})
        return doc

    def delete(self, collection: str, doc_id: str) -> bool:
        res = self._db[collection].delete_one({"id": str(doc_id)})
        return res.deleted_count > 0

    def list(self, collection: str) -> list[dict[str, Any]]:
        return list(self._db[collection].find({}, {"_id": 0}))

    def close(self) -> None:
        self._client.close()


_store: DocumentStore | None = None
_store_lock = threading.Lock()


def get_store() -> DocumentStore:
    """Return the process-wide store, choosing Mongo when configured."""
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is not None:
            return _store
        settings = get_settings()
        if settings.mongodb_url:
            try:
                _store = MongoStore(settings.mongodb_url, settings.mongodb_db_name)
                return _store
            except Exception as exc:
                logger.error("MongoDB unavailable (%s); falling back to SQLite", exc)
        _store = SQLiteStore(settings.sqlite_path)
        return _store


def reset_store() -> None:
    """Used by tests to swap backends."""
    global _store
    with _store_lock:
        if _store is not None:
            _store.close()
        _store = None
