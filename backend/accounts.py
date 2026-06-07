"""External account registry for the personal edition."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from backend.personal_storage import LEGACY_ACCOUNTS_DB_PATH, PERSONAL_ACCOUNTS_DB_PATH
from backend.utils.datetime_utils import get_now
from backend.utils.companion_identity import companion_user_id


class AccountRegistry:
    def __init__(self, db_path: str | Path = PERSONAL_ACCOUNTS_DB_PATH):
        project_root = Path(__file__).resolve().parents[1]
        self.db_path = Path(db_path)
        if not self.db_path.is_absolute():
            self.db_path = project_root / self.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_db()
        self.init_db()

    def _migrate_legacy_db(self) -> None:
        if self.db_path != PERSONAL_ACCOUNTS_DB_PATH:
            return
        if self.db_path.exists() or not LEGACY_ACCOUNTS_DB_PATH.exists():
            return
        try:
            LEGACY_ACCOUNTS_DB_PATH.replace(self.db_path)
        except PermissionError:
            shutil.copyfile(LEGACY_ACCOUNTS_DB_PATH, self.db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    account_name TEXT NOT NULL DEFAULT '',
                    remote_user_id TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(platform, remote_user_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS companions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    companion_name TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS companion_platform_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    companion_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    account_name TEXT NOT NULL DEFAULT '',
                    remote_user_id TEXT NOT NULL DEFAULT '',
                    password TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    is_primary INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(platform, account_name),
                    FOREIGN KEY(companion_id) REFERENCES companions(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS account_bindings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    companion_id INTEGER NOT NULL,
                    user_account_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(companion_id, user_account_id),
                    FOREIGN KEY(companion_id) REFERENCES companions(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_account_id) REFERENCES accounts(id) ON DELETE CASCADE
                )
                """
            )

            self._ensure_column(conn, "accounts", "account_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "companions", "companion_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "companions", "enabled", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "companions", "metadata", "TEXT NOT NULL DEFAULT '{}'")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS linyu_ai_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    companion_name TEXT NOT NULL DEFAULT '',
                    account_name TEXT NOT NULL DEFAULT '',
                    remote_user_id TEXT NOT NULL DEFAULT '',
                    account TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL DEFAULT '',
                    target_account_id INTEGER,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(conn, "linyu_ai_accounts", "companion_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "linyu_ai_accounts", "account_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "linyu_ai_accounts", "remote_user_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "linyu_ai_accounts", "target_account_id", "INTEGER")

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_accounts_platform_account_name ON accounts(platform, account_name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_companion_accounts_companion ON companion_platform_accounts(companion_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_companion_accounts_platform ON companion_platform_accounts(platform)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_account_bindings_user ON account_bindings(user_account_id)"
            )

            conn.execute(
                """
                UPDATE accounts
                SET account_name = CASE
                    WHEN COALESCE(NULLIF(display_name, ''), '') != '' THEN display_name
                    ELSE remote_user_id
                END
                WHERE COALESCE(account_name, '') = ''
                """
            )
            self._migrate_legacy_companions(conn)
            self._migrate_account_bindings(conn)

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        if column in self._table_columns(conn, table):
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _json_loads(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(value or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _clean_ids(ids: Optional[Sequence[Any]]) -> List[int]:
        if ids is None:
            return []
        cleaned: List[int] = []
        seen: set[int] = set()
        for item in ids:
            try:
                value = int(item)
            except Exception:
                continue
            if value <= 0 or value in seen:
                continue
            seen.add(value)
            cleaned.append(value)
        return cleaned

    @staticmethod
    def _row_to_account(row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["enabled"] = bool(data.get("enabled"))
        data["metadata"] = AccountRegistry._json_loads(data.get("metadata"))
        if "account_name" not in data or not data.get("account_name"):
            data["account_name"] = data.get("display_name") or data.get("remote_user_id") or ""
        return data

    @staticmethod
    def _row_to_companion(row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["enabled"] = bool(data.get("enabled"))
        data["metadata"] = AccountRegistry._json_loads(data.get("metadata"))
        data["companion_id"] = companion_user_id(data["id"])
        data["platform_accounts"] = []
        data["bound_accounts"] = []
        data["bound_account_ids"] = []
        data["primary_platform"] = ""
        data["primary_account_name"] = ""
        data["primary_remote_user_id"] = ""
        # Backward compatibility fields still expected by current frontend/tests.
        data["account_name"] = ""
        data["account"] = ""
        data["remote_user_id"] = ""
        data["password"] = ""
        data["target_account_id"] = None
        return data

    @staticmethod
    def _row_to_platform_account(row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["enabled"] = bool(data.get("enabled"))
        data["is_primary"] = bool(data.get("is_primary"))
        data["metadata"] = AccountRegistry._json_loads(data.get("metadata"))
        return data

    def _migrate_legacy_companions(self, conn: sqlite3.Connection) -> None:
        if conn.execute("SELECT COUNT(*) FROM companions").fetchone()[0] > 0:
            return
        rows = conn.execute(
            """
            SELECT * FROM linyu_ai_accounts
            ORDER BY id
            """
        ).fetchall()
        if not rows:
            return

        now = get_now().isoformat()
        for row in rows:
            data = dict(row)
            companion_name = str(data.get("companion_name") or data.get("account_name") or data.get("account") or "").strip()
            enabled = 1 if bool(data.get("enabled")) else 0
            metadata = data.get("metadata") or "{}"

            cur = conn.execute(
                """
                INSERT INTO companions(companion_name, enabled, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    companion_name,
                    enabled,
                    metadata if isinstance(metadata, str) else json.dumps(metadata, ensure_ascii=False),
                    data.get("created_at") or now,
                    data.get("updated_at") or now,
                ),
            )
            companion_id = int(cur.lastrowid)

            account_name = str(data.get("account_name") or data.get("account") or "").strip()
            conn.execute(
                """
                INSERT OR IGNORE INTO companion_platform_accounts(
                    companion_id, platform, account_name, remote_user_id, password,
                    enabled, is_primary, metadata, created_at, updated_at
                )
                VALUES (?, 'linyu', ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    companion_id,
                    account_name,
                    str(data.get("remote_user_id") or "").strip(),
                    str(data.get("password") or ""),
                    enabled,
                    metadata if isinstance(metadata, str) else json.dumps(metadata, ensure_ascii=False),
                    data.get("created_at") or now,
                    data.get("updated_at") or now,
                ),
            )

            target_account_id = data.get("target_account_id")
            binding_ids: List[int] = []
            if target_account_id:
                try:
                    binding_ids.append(int(target_account_id))
                except Exception:
                    pass
            if binding_ids:
                self._replace_bindings(conn, companion_id, binding_ids)

    def _migrate_account_bindings(self, conn: sqlite3.Connection) -> None:
        columns = self._table_columns(conn, "account_bindings")
        if not columns:
            return
        if "companion_id" in columns and "ai_account_id" not in columns:
            return

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS account_bindings_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                companion_id INTEGER NOT NULL,
                user_account_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(companion_id, user_account_id),
                FOREIGN KEY(companion_id) REFERENCES companions(id) ON DELETE CASCADE,
                FOREIGN KEY(user_account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
            """
        )

        if "companion_id" in columns:
            rows = conn.execute(
                """
                SELECT companion_id, user_account_id, created_at, updated_at
                FROM account_bindings
                """
            ).fetchall()
            for row in rows:
                companion_id = self._resolve_existing_companion_id(conn, row["companion_id"])
                if companion_id is None:
                    continue
                self._insert_binding_row(
                    conn,
                    "account_bindings_new",
                    companion_id=companion_id,
                    user_account_id=row["user_account_id"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
        elif "ai_account_id" in columns:
            rows = conn.execute(
                """
                SELECT b.ai_account_id, b.user_account_id, b.created_at, b.updated_at,
                       la.account, la.account_name, la.companion_name, la.remote_user_id
                FROM account_bindings b
                LEFT JOIN linyu_ai_accounts la ON la.id = b.ai_account_id
                """
            ).fetchall()
            for row in rows:
                companion_id = self._resolve_legacy_ai_companion_id(
                    conn,
                    legacy_ai_account_id=row["ai_account_id"],
                    account_name=row["account_name"],
                    legacy_account=row["account"],
                    companion_name=row["companion_name"],
                    remote_user_id=row["remote_user_id"],
                )
                if companion_id is None:
                    continue
                self._insert_binding_row(
                    conn,
                    "account_bindings_new",
                    companion_id=companion_id,
                    user_account_id=row["user_account_id"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

        conn.execute("DROP TABLE account_bindings")
        conn.execute("ALTER TABLE account_bindings_new RENAME TO account_bindings")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_account_bindings_user ON account_bindings(user_account_id)"
        )

    @staticmethod
    def _insert_binding_row(
        conn: sqlite3.Connection,
        table: str,
        *,
        companion_id: int,
        user_account_id: Any,
        created_at: Any,
        updated_at: Any,
    ) -> None:
        companion_exists = conn.execute("SELECT 1 FROM companions WHERE id = ?", (companion_id,)).fetchone()
        user_exists = conn.execute("SELECT 1 FROM accounts WHERE id = ?", (user_account_id,)).fetchone()
        if not companion_exists or not user_exists:
            return
        now = get_now().isoformat()
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {table}(companion_id, user_account_id, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                int(companion_id),
                int(user_account_id),
                str(created_at or now),
                str(updated_at or created_at or now),
            ),
        )

    @staticmethod
    def _resolve_existing_companion_id(conn: sqlite3.Connection, companion_id: Any) -> Optional[int]:
        try:
            candidate = int(companion_id)
        except Exception:
            return None
        exists = conn.execute("SELECT 1 FROM companions WHERE id = ?", (candidate,)).fetchone()
        return candidate if exists else None

    def _resolve_legacy_ai_companion_id(
        self,
        conn: sqlite3.Connection,
        *,
        legacy_ai_account_id: Any,
        account_name: Any,
        legacy_account: Any,
        companion_name: Any,
        remote_user_id: Any,
    ) -> Optional[int]:
        remote_user_id = str(remote_user_id or "").strip()
        if remote_user_id:
            row = conn.execute(
                """
                SELECT companion_id
                FROM companion_platform_accounts
                WHERE platform = 'linyu' AND remote_user_id = ?
                ORDER BY id
                LIMIT 1
                """,
                (remote_user_id,),
            ).fetchone()
            if row:
                return int(row["companion_id"])

        login_name = str(account_name or legacy_account or "").strip()
        if login_name:
            row = conn.execute(
                """
                SELECT companion_id
                FROM companion_platform_accounts
                WHERE platform = 'linyu' AND account_name = ?
                ORDER BY id
                LIMIT 1
                """,
                (login_name,),
            ).fetchone()
            if row:
                return int(row["companion_id"])

        display_name = str(companion_name or "").strip()
        if display_name:
            row = conn.execute(
                """
                SELECT id
                FROM companions
                WHERE companion_name = ?
                ORDER BY id
                LIMIT 1
                """,
                (display_name,),
            ).fetchone()
            if row:
                return int(row["id"])

        return self._resolve_existing_companion_id(conn, legacy_ai_account_id)

    def list_accounts(self, platform: Optional[str] = None, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM accounts"
        params: list[Any] = []
        where: list[str] = []
        if platform:
            where.append("platform = ?")
            params.append(platform)
        if enabled is not None:
            where.append("enabled = ?")
            params.append(1 if enabled else 0)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY platform, account_name, id"
        with self._connect() as conn:
            return [self._row_to_account(row) for row in conn.execute(sql, params).fetchall()]

    def get_account(self, account_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return self._row_to_account(row) if row else None

    def get_account_by_remote_id(self, platform: str, remote_user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE platform = ? AND remote_user_id = ?",
                (platform, remote_user_id),
            ).fetchone()
        return self._row_to_account(row) if row else None

    def get_account_by_account_name(self, platform: str, account_name: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE platform = ? AND account_name = ? ORDER BY id LIMIT 1",
                (platform, account_name),
            ).fetchone()
        return self._row_to_account(row) if row else None

    def upsert_account(
        self,
        *,
        platform: str,
        remote_user_id: str,
        account_name: str = "",
        display_name: str = "",
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        remote_user_id = str(remote_user_id or "").strip()
        account_name = str(account_name or "").strip() or remote_user_id
        display_name = str(display_name or "").strip() or account_name
        if not platform or not remote_user_id:
            raise ValueError("platform and remote_user_id are required")

        now = get_now().isoformat()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO accounts(platform, account_name, remote_user_id, display_name, enabled, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, remote_user_id) DO UPDATE SET
                    account_name = excluded.account_name,
                    display_name = excluded.display_name,
                    enabled = excluded.enabled,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                (platform, account_name, remote_user_id, display_name, 1 if enabled else 0, metadata_json, now, now),
            )
            row = conn.execute(
                "SELECT * FROM accounts WHERE platform = ? AND remote_user_id = ?",
                (platform, remote_user_id),
            ).fetchone()
        return self._row_to_account(row)

    def update_account(self, account_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"platform", "account_name", "remote_user_id", "display_name", "enabled", "metadata"}
        values: Dict[str, Any] = {}
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key == "enabled":
                value = 1 if value else 0
            elif key == "metadata":
                value = json.dumps(value or {}, ensure_ascii=False)
            else:
                value = str(value or "").strip()
            values[key] = value
        if not values:
            return self.get_account(account_id)
        values["updated_at"] = get_now().isoformat()
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE accounts SET {assignments} WHERE id = ?",
                [*values.values(), account_id],
            )
        return self.get_account(account_id)

    def delete_account(self, account_id: int) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM account_bindings WHERE user_account_id = ?", (account_id,))
            cur = conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
            return cur.rowcount > 0

    def list_companions(
        self,
        enabled: Optional[bool] = None,
        *,
        include_bindings: bool = True,
        include_platform_accounts: bool = True,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM companions"
        params: list[Any] = []
        if enabled is not None:
            sql += " WHERE enabled = ?"
            params.append(1 if enabled else 0)
        sql += " ORDER BY companion_name, id"
        with self._connect() as conn:
            companions = [self._row_to_companion(row) for row in conn.execute(sql, params).fetchall()]
            for companion in companions:
                self._attach_companion_details(
                    conn,
                    companion,
                    include_bindings=include_bindings,
                    include_platform_accounts=include_platform_accounts,
                )
            return companions

    def get_companion(
        self,
        companion_id: int,
        *,
        include_bindings: bool = True,
        include_platform_accounts: bool = True,
    ) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM companions WHERE id = ?", (companion_id,)).fetchone()
            if not row:
                return None
            companion = self._row_to_companion(row)
            self._attach_companion_details(
                conn,
                companion,
                include_bindings=include_bindings,
                include_platform_accounts=include_platform_accounts,
            )
            return companion

    def upsert_companion(
        self,
        *,
        companion_name: str,
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        platform_accounts: Optional[Sequence[Dict[str, Any]]] = None,
        bound_account_ids: Optional[Sequence[Any]] = None,
        companion_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        companion_name = str(companion_name or "").strip()
        if not companion_name:
            raise ValueError("companion_name is required")

        now = get_now().isoformat()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self._connect() as conn:
            if companion_id:
                conn.execute(
                    """
                    UPDATE companions
                    SET companion_name = ?, enabled = ?, metadata = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (companion_name, 1 if enabled else 0, metadata_json, now, int(companion_id)),
                )
                target_companion_id = int(companion_id)
            else:
                cur = conn.execute(
                    """
                    INSERT INTO companions(companion_name, enabled, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (companion_name, 1 if enabled else 0, metadata_json, now, now),
                )
                target_companion_id = int(cur.lastrowid)

            if platform_accounts is not None:
                self._replace_platform_accounts(conn, target_companion_id, platform_accounts)
            if bound_account_ids is not None:
                self._replace_bindings(conn, target_companion_id, self._clean_ids(bound_account_ids))

        return self.get_companion(target_companion_id)  # type: ignore[return-value]

    def update_companion(self, companion_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        existing = self.get_companion(companion_id)
        if not existing:
            return None

        companion_name = str(updates.get("companion_name") or existing.get("companion_name") or "").strip()
        enabled = bool(updates.get("enabled")) if "enabled" in updates else bool(existing.get("enabled", True))
        metadata = updates.get("metadata")
        if metadata is None:
            metadata = existing.get("metadata") or {}

        platform_accounts = updates.get("platform_accounts")
        if platform_accounts is None:
            platform_accounts = existing.get("platform_accounts") or []

        bound_account_ids = updates.get("bound_account_ids")
        if bound_account_ids is None:
            bound_account_ids = existing.get("bound_account_ids") or []

        return self.upsert_companion(
            companion_id=companion_id,
            companion_name=companion_name,
            enabled=enabled,
            metadata=metadata,
            platform_accounts=platform_accounts,
            bound_account_ids=bound_account_ids,
        )

    def delete_companion(self, companion_id: int) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM account_bindings WHERE companion_id = ?", (companion_id,))
            conn.execute("DELETE FROM companion_platform_accounts WHERE companion_id = ?", (companion_id,))
            cur = conn.execute("DELETE FROM companions WHERE id = ?", (companion_id,))
            return cur.rowcount > 0

    def set_companion_bindings(self, companion_id: int, user_account_ids: Sequence[Any]) -> Optional[Dict[str, Any]]:
        if not self.get_companion(companion_id, include_bindings=False):
            return None
        with self._connect() as conn:
            self._replace_bindings(conn, companion_id, self._clean_ids(user_account_ids))
        return self.get_companion(companion_id)

    def list_companions_for_user(self, user_account_id: int, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
        sql = """
            SELECT c.*
            FROM companions c
            JOIN account_bindings b ON b.companion_id = c.id
            WHERE b.user_account_id = ?
        """
        params: list[Any] = [user_account_id]
        if enabled is not None:
            sql += " AND c.enabled = ?"
            params.append(1 if enabled else 0)
        sql += " ORDER BY c.companion_name, c.id"
        with self._connect() as conn:
            companions = [self._row_to_companion(row) for row in conn.execute(sql, params).fetchall()]
            for companion in companions:
                self._attach_companion_details(conn, companion, include_bindings=True, include_platform_accounts=True)
            return companions

    def list_companions_for_remote_user(
        self,
        platform: str,
        remote_user_id: str,
        *,
        enabled: Optional[bool] = True,
    ) -> List[Dict[str, Any]]:
        user = self.get_account_by_remote_id(platform, remote_user_id)
        if not user:
            return []
        return self.list_companions_for_user(int(user["id"]), enabled=enabled)

    def list_companion_platform_accounts(
        self,
        companion_id: int,
        *,
        platform: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM companion_platform_accounts WHERE companion_id = ?"
        params: list[Any] = [companion_id]
        if platform:
            sql += " AND platform = ?"
            params.append(platform)
        if enabled is not None:
            sql += " AND enabled = ?"
            params.append(1 if enabled else 0)
        sql += " ORDER BY is_primary DESC, platform, id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_platform_account(row) for row in rows]

    def get_companion_platform_account_by_login(self, platform: str, account_name: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM companion_platform_accounts
                WHERE platform = ? AND account_name = ?
                ORDER BY is_primary DESC, id
                LIMIT 1
                """,
                (platform, str(account_name or "").strip()),
            ).fetchone()
        return self._row_to_platform_account(row) if row else None

    def get_companion_platform_account_by_remote_id(self, platform: str, remote_user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM companion_platform_accounts
                WHERE platform = ? AND remote_user_id = ?
                ORDER BY is_primary DESC, id
                LIMIT 1
                """,
                (platform, str(remote_user_id or "").strip()),
            ).fetchone()
        return self._row_to_platform_account(row) if row else None

    def get_companion_by_platform_identity(
        self,
        platform: str,
        *,
        remote_user_id: str = "",
        account_name: str = "",
    ) -> Optional[Dict[str, Any]]:
        platform_account = None
        if remote_user_id:
            platform_account = self.get_companion_platform_account_by_remote_id(platform, remote_user_id)
        if not platform_account and account_name:
            platform_account = self.get_companion_platform_account_by_login(platform, account_name)
        if not platform_account:
            return None
        return self.get_companion(int(platform_account["companion_id"]), include_bindings=True, include_platform_accounts=True)

    def _replace_platform_accounts(
        self,
        conn: sqlite3.Connection,
        companion_id: int,
        accounts: Sequence[Dict[str, Any]],
    ) -> None:
        now = get_now().isoformat()
        conn.execute("DELETE FROM companion_platform_accounts WHERE companion_id = ?", (companion_id,))
        normalized = [self._normalize_platform_account_payload(item) for item in accounts]
        primary_seen = False
        for index, account in enumerate(normalized):
            if not account["platform"] or not account["account_name"]:
                continue
            is_primary = bool(account["is_primary"])
            if not primary_seen and (is_primary or index == 0):
                is_primary = True
                primary_seen = True
            else:
                is_primary = False
            conn.execute(
                """
                INSERT INTO companion_platform_accounts(
                    companion_id, platform, account_name, remote_user_id, password,
                    enabled, is_primary, metadata, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    companion_id,
                    account["platform"],
                    account["account_name"],
                    account["remote_user_id"],
                    account["password"],
                    1 if account["enabled"] else 0,
                    1 if is_primary else 0,
                    json.dumps(account["metadata"], ensure_ascii=False),
                    now,
                    now,
                ),
            )

    @staticmethod
    def _normalize_platform_account_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        platform = str(payload.get("platform") or "").strip().lower()
        account_name = str(payload.get("account_name") or "").strip()
        return {
            "platform": platform,
            "account_name": account_name,
            "remote_user_id": str(payload.get("remote_user_id") or "").strip(),
            "password": str(payload.get("password") or ""),
            "enabled": bool(payload.get("enabled", True)),
            "is_primary": bool(payload.get("is_primary", False)),
            "metadata": payload.get("metadata") or {},
        }

    def _replace_bindings(
        self,
        conn: sqlite3.Connection,
        companion_id: int,
        user_account_ids: Sequence[int],
    ) -> None:
        now = get_now().isoformat()
        cleaned = self._clean_ids(user_account_ids)
        conn.execute("DELETE FROM account_bindings WHERE companion_id = ?", (companion_id,))
        for user_account_id in cleaned:
            exists = conn.execute("SELECT 1 FROM accounts WHERE id = ?", (user_account_id,)).fetchone()
            if not exists:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO account_bindings(companion_id, user_account_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (companion_id, user_account_id, now, now),
            )

    def _get_bound_accounts(self, conn: sqlite3.Connection, companion_id: int) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT a.*
            FROM accounts a
            JOIN account_bindings b ON b.user_account_id = a.id
            WHERE b.companion_id = ?
            ORDER BY a.platform, a.account_name, a.id
            """,
            (companion_id,),
        ).fetchall()
        return [self._row_to_account(row) for row in rows]

    def _attach_companion_details(
        self,
        conn: sqlite3.Connection,
        companion: Dict[str, Any],
        *,
        include_bindings: bool,
        include_platform_accounts: bool,
    ) -> None:
        companion_id = int(companion["id"])
        platform_accounts: List[Dict[str, Any]] = []
        if include_platform_accounts:
            rows = conn.execute(
                """
                SELECT * FROM companion_platform_accounts
                WHERE companion_id = ?
                ORDER BY is_primary DESC, platform, id
                """,
                (companion_id,),
            ).fetchall()
            platform_accounts = [self._row_to_platform_account(row) for row in rows]
            companion["platform_accounts"] = platform_accounts

        if include_bindings:
            bound_accounts = self._get_bound_accounts(conn, companion_id)
            companion["bound_accounts"] = bound_accounts
            companion["bound_account_ids"] = [int(account["id"]) for account in bound_accounts]
            companion["target_account_id"] = companion["bound_account_ids"][0] if companion["bound_account_ids"] else None

        primary = next((item for item in platform_accounts if item.get("is_primary")), platform_accounts[0] if platform_accounts else None)
        if primary:
            companion["primary_platform"] = primary.get("platform") or ""
            companion["primary_account_name"] = primary.get("account_name") or ""
            companion["primary_remote_user_id"] = primary.get("remote_user_id") or ""
            companion["account_name"] = primary.get("account_name") or ""
            companion["account"] = primary.get("account_name") or ""
            companion["remote_user_id"] = primary.get("remote_user_id") or ""
            companion["password"] = primary.get("password") or ""
        else:
            companion["account_name"] = ""
            companion["account"] = ""
            companion["remote_user_id"] = ""
            companion["password"] = ""

    # ---- Backward-compatible wrappers ----

    def list_linyu_ai_accounts(
        self,
        enabled: Optional[bool] = None,
        *,
        include_bindings: bool = True,
    ) -> List[Dict[str, Any]]:
        companions = self.list_companions(
            enabled=enabled,
            include_bindings=include_bindings,
            include_platform_accounts=True,
        )
        for companion in companions:
            linyu_accounts = [item for item in companion.get("platform_accounts", []) if item.get("platform") == "linyu"]
            if linyu_accounts:
                primary = next((item for item in linyu_accounts if item.get("is_primary")), linyu_accounts[0])
                companion["account_name"] = primary.get("account_name") or ""
                companion["account"] = companion["account_name"]
                companion["remote_user_id"] = primary.get("remote_user_id") or ""
                companion["password"] = primary.get("password") or ""
            else:
                companion["account_name"] = ""
                companion["account"] = ""
                companion["remote_user_id"] = ""
                companion["password"] = ""
        return companions

    def get_linyu_ai_account(self, ai_account_id: int, *, include_bindings: bool = True) -> Optional[Dict[str, Any]]:
        return self.get_companion(ai_account_id, include_bindings=include_bindings, include_platform_accounts=True)

    def get_linyu_ai_account_by_account_name(self, account_name: str) -> Optional[Dict[str, Any]]:
        platform_account = self.get_companion_platform_account_by_login("linyu", account_name)
        if not platform_account:
            return None
        return self.get_companion(int(platform_account["companion_id"]), include_bindings=True, include_platform_accounts=True)

    def resolve_legacy_linyu_ai_companion_id(self, legacy_ai_account_id: int) -> Optional[int]:
        """Map a legacy linyu_ai_accounts id to the current companion id.

        Older prompt URLs used identities like companion:linyu:3, where 3 was
        the old linyu_ai_accounts.id. The runtime now uses companions.id, so
        prompt APIs need this mapping to avoid writing orphan prompt files.
        """
        try:
            legacy_id = int(legacy_ai_account_id)
        except Exception:
            return None

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT account, account_name, remote_user_id, companion_name
                FROM linyu_ai_accounts
                WHERE id = ?
                """,
                (legacy_id,),
            ).fetchone()
            if not row:
                return None

            return self._resolve_legacy_ai_companion_id(
                conn=conn,
                legacy_ai_account_id=legacy_id,
                account_name=row["account_name"],
                legacy_account=row["account"],
                companion_name=row["companion_name"],
                remote_user_id=row["remote_user_id"],
            )

    def upsert_linyu_ai_account(
        self,
        *,
        account_name: Optional[str] = None,
        account: Optional[str] = None,
        password: str,
        companion_name: str = "",
        remote_user_id: str = "",
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        bound_account_ids: Optional[Sequence[Any]] = None,
        target_account_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        login_account = str(account_name or account or "").strip()
        if not login_account:
            raise ValueError("account_name is required")
        companion_name = str(companion_name or "").strip() or login_account
        binding_ids = self._clean_ids(bound_account_ids)
        if target_account_id:
            binding_ids.append(int(target_account_id))
        return self.upsert_companion(
            companion_name=companion_name,
            enabled=enabled,
            metadata=metadata,
            platform_accounts=[
                {
                    "platform": "linyu",
                    "account_name": login_account,
                    "remote_user_id": str(remote_user_id or "").strip(),
                    "password": "" if password is None else str(password),
                    "enabled": enabled,
                    "is_primary": True,
                    "metadata": (metadata or {}).get("linyu", {}) if isinstance(metadata, dict) else {},
                }
            ],
            bound_account_ids=binding_ids,
        )

    def update_linyu_ai_account(self, ai_account_id: int, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        existing = self.get_companion(ai_account_id, include_bindings=True, include_platform_accounts=True)
        if not existing:
            return None

        current_linyu = next(
            (item for item in existing.get("platform_accounts", []) if item.get("platform") == "linyu"),
            {
                "platform": "linyu",
                "account_name": "",
                "remote_user_id": "",
                "password": "",
                "enabled": existing.get("enabled", True),
                "is_primary": True,
                "metadata": {},
            },
        )
        account_name = str(updates.get("account_name") or updates.get("account") or current_linyu.get("account_name") or "").strip()
        current_linyu["account_name"] = account_name
        if "remote_user_id" in updates:
            current_linyu["remote_user_id"] = str(updates.get("remote_user_id") or "").strip()
        if "password" in updates:
            current_linyu["password"] = "" if updates.get("password") is None else str(updates.get("password"))
        if "enabled" in updates:
            current_linyu["enabled"] = bool(updates.get("enabled"))

        companion_name = updates.get("companion_name")
        if companion_name is None:
            companion_name = existing.get("companion_name") or account_name

        metadata = updates.get("metadata")
        if metadata is None:
            metadata = existing.get("metadata") or {}

        binding_ids = updates.get("bound_account_ids")
        legacy_target_id = updates.get("target_account_id")
        if binding_ids is None:
            binding_ids = existing.get("bound_account_ids") or []
        if legacy_target_id:
            binding_ids = list(binding_ids) + [int(legacy_target_id)]

        return self.upsert_companion(
            companion_id=ai_account_id,
            companion_name=str(companion_name or account_name).strip(),
            enabled=bool(updates.get("enabled")) if "enabled" in updates else bool(existing.get("enabled", True)),
            metadata=metadata,
            platform_accounts=[current_linyu],
            bound_account_ids=binding_ids,
        )

    def delete_linyu_ai_account(self, ai_account_id: int) -> bool:
        return self.delete_companion(ai_account_id)

    def set_linyu_ai_bindings(self, ai_account_id: int, user_account_ids: Sequence[Any]) -> Optional[Dict[str, Any]]:
        return self.set_companion_bindings(ai_account_id, user_account_ids)

    def list_linyu_ai_bindings(self, ai_account_id: int) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            return self._get_bound_accounts(conn, ai_account_id)

    def list_linyu_ai_accounts_for_user(self, user_account_id: int, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
        return self.list_companions_for_user(user_account_id, enabled=enabled)

    def list_linyu_ai_accounts_for_remote_user(
        self,
        remote_user_id: str,
        *,
        enabled: Optional[bool] = True,
    ) -> List[Dict[str, Any]]:
        return self.list_companions_for_remote_user("linyu", remote_user_id, enabled=enabled)


account_registry = AccountRegistry()
