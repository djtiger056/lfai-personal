from pathlib import Path

from backend.accounts import AccountRegistry


def test_account_registry_crud(tmp_path: Path):
    registry = AccountRegistry(tmp_path / "accounts.db")

    alice = registry.upsert_account(
        platform="linyu",
        account_name="alice",
        remote_user_id="uuid-alice",
        display_name="Alice",
        enabled=True,
    )
    bob = registry.upsert_account(
        platform="linyu",
        account_name="bob",
        remote_user_id="uuid-bob",
        display_name="Bob",
        enabled=True,
    )
    assert alice["id"]
    assert alice["platform"] == "linyu"
    assert alice["account_name"] == "alice"
    assert alice["enabled"] is True

    updated = registry.update_account(alice["id"], {"display_name": "Alice 2", "enabled": False})
    assert updated["display_name"] == "Alice 2"
    assert updated["enabled"] is False

    rain = registry.upsert_linyu_ai_account(
        account_name="bot-rain",
        companion_name="小雨",
        password="pw",
        bound_account_ids=[alice["id"], bob["id"]],
        enabled=True,
    )
    snow = registry.upsert_linyu_ai_account(
        account_name="bot-snow",
        companion_name="小雪",
        password="pw",
        bound_account_ids=[alice["id"]],
        enabled=True,
    )
    assert rain["companion_name"] == "小雨"
    assert rain["account_name"] == "bot-rain"
    assert set(rain["bound_account_ids"]) == {alice["id"], bob["id"]}
    assert {item["account_name"] for item in rain["bound_accounts"]} == {"alice", "bob"}

    alice_ai_accounts = registry.list_linyu_ai_accounts_for_user(alice["id"], enabled=True)
    assert {item["companion_name"] for item in alice_ai_accounts} == {"小雨", "小雪"}

    updated_rain = registry.set_linyu_ai_bindings(rain["id"], [bob["id"]])
    assert updated_rain["bound_account_ids"] == [bob["id"]]
    assert registry.list_linyu_ai_accounts_for_user(alice["id"], enabled=True)[0]["id"] == snow["id"]

    assert registry.delete_account(alice["id"]) is True
    assert registry.get_account(alice["id"]) is None
    assert registry.get_linyu_ai_account(snow["id"])["bound_account_ids"] == []


def test_account_registry_migrates_legacy_ai_account_bindings(tmp_path: Path):
    db_path = tmp_path / "accounts.db"
    registry = AccountRegistry(db_path)

    user = registry.upsert_account(
        platform="linyu",
        account_name="alice",
        remote_user_id="uuid-alice",
        display_name="Alice",
        enabled=True,
    )
    companion = registry.upsert_linyu_ai_account(
        account_name="bot-rain",
        companion_name="小雨",
        password="pw",
        remote_user_id="bot-uuid",
        bound_account_ids=[],
        enabled=True,
    )

    with registry._connect() as conn:
        conn.execute("DROP TABLE account_bindings")
        conn.execute(
            """
            INSERT OR IGNORE INTO linyu_ai_accounts(
                id, companion_name, account_name, account, password, remote_user_id,
                enabled, metadata, created_at, updated_at
            )
            VALUES (?, '小雨', 'bot-rain', 'bot-rain', 'pw', 'bot-uuid',
                    1, '{}', '2026-01-01T00:00:00+08:00', '2026-01-01T00:00:00+08:00')
            """,
            (companion["id"],),
        )
        conn.execute(
            """
            CREATE TABLE account_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ai_account_id INTEGER NOT NULL,
                user_account_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(ai_account_id, user_account_id),
                FOREIGN KEY(ai_account_id) REFERENCES linyu_ai_accounts(id) ON DELETE CASCADE,
                FOREIGN KEY(user_account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            INSERT INTO account_bindings(ai_account_id, user_account_id, created_at, updated_at)
            VALUES (?, ?, '2026-01-01T00:00:00+08:00', '2026-01-01T00:00:00+08:00')
            """,
            (companion["id"], user["id"]),
        )

    migrated = AccountRegistry(db_path)
    companions = migrated.list_companions()
    assert len(companions) == 1
    assert companions[0]["id"] == companion["id"]
    assert companions[0]["bound_account_ids"] == [user["id"]]

    with migrated._connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(account_bindings)").fetchall()}
        rows = conn.execute("SELECT companion_id, user_account_id FROM account_bindings").fetchall()
    assert "companion_id" in columns
    assert "ai_account_id" not in columns
    assert [(row["companion_id"], row["user_account_id"]) for row in rows] == [(companion["id"], user["id"])]


def test_resolve_legacy_linyu_ai_prompt_identity(tmp_path: Path):
    registry = AccountRegistry(tmp_path / "accounts.db")

    companion = registry.upsert_linyu_ai_account(
        account_name="bot-rain",
        companion_name="小雨",
        password="pw",
        remote_user_id="bot-uuid",
        enabled=True,
    )

    with registry._connect() as conn:
        conn.execute(
            """
            INSERT INTO linyu_ai_accounts(
                id, companion_name, account_name, account, password, remote_user_id,
                enabled, metadata, created_at, updated_at
            )
            VALUES (9, '小雨', 'bot-rain', 'bot-rain', 'pw', 'bot-uuid',
                    1, '{}', '2026-01-01T00:00:00+08:00', '2026-01-01T00:00:00+08:00')
            """
        )

    assert registry.resolve_legacy_linyu_ai_companion_id(9) == companion["id"]
