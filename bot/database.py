from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    qr_limit INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    approved_by INTEGER
);

CREATE TABLE IF NOT EXISTS wireguard_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    private_key_encrypted TEXT NOT NULL,
    public_key TEXT NOT NULL UNIQUE,
    vpn_address TEXT NOT NULL,
    routeros_peer_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    deleted_at TEXT,
    deleted_by INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_users_status
    ON users(status);

CREATE INDEX IF NOT EXISTS idx_wg_user_status
    ON wireguard_configs(user_id, status);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self):
        with self.connect() as db:
            db.executescript(SCHEMA)

    def get_user(self, telegram_id: int):
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM users WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()

    def get_user_by_id(self, user_id: int):
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()

    def upsert_pending_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ):
        with self.connect() as db:
            existing = db.execute(
                "SELECT * FROM users WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()

            if existing:
                db.execute(
                    """
                    UPDATE users
                    SET username=?, first_name=?, last_name=?
                    WHERE telegram_id=?
                    """,
                    (
                        username,
                        first_name,
                        last_name,
                        telegram_id,
                    ),
                )
                return existing["id"]

            cur = db.execute(
                """
                INSERT INTO users
                (
                    telegram_id,
                    username,
                    first_name,
                    last_name,
                    status,
                    qr_limit,
                    created_at
                )
                VALUES (?, ?, ?, ?, 'pending', 1, ?)
                """,
                (
                    telegram_id,
                    username,
                    first_name,
                    last_name,
                    utcnow(),
                ),
            )

            return cur.lastrowid

    def approve_user(
        self,
        user_id: int,
        admin_id: int,
        qr_limit: int,
    ):
        with self.connect() as db:
            db.execute(
                """
                UPDATE users
                SET status='approved',
                    qr_limit=?,
                    approved_at=?,
                    approved_by=?
                WHERE id=?
                """,
                (
                    qr_limit,
                    utcnow(),
                    admin_id,
                    user_id,
                ),
            )

    def reject_user(
        self,
        user_id: int,
        admin_id: int,
    ):
        with self.connect() as db:
            db.execute(
                """
                UPDATE users
                SET status='rejected',
                    approved_at=?,
                    approved_by=?
                WHERE id=?
                """,
                (
                    utcnow(),
                    admin_id,
                    user_id,
                ),
            )

    def set_status(self, user_id: int, status: str):
        with self.connect() as db:
            db.execute(
                "UPDATE users SET status=? WHERE id=?",
                (
                    status,
                    user_id,
                ),
            )

    def set_qr_limit(self, user_id: int, limit: int):
        with self.connect() as db:
            db.execute(
                "UPDATE users SET qr_limit=? WHERE id=?",
                (
                    limit,
                    user_id,
                ),
            )

    def pending_users(self):
        with self.connect() as db:
            return db.execute(
                """
                SELECT *
                FROM users
                WHERE status='pending'
                ORDER BY created_at
                """
            ).fetchall()

    def approved_users(self):
        with self.connect() as db:
            return db.execute(
                """
                SELECT *
                FROM users
                WHERE status='approved'
                ORDER BY created_at
                """
            ).fetchall()

    def count_active_configs(self, user_id: int) -> int:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT COUNT(*) AS n
                FROM wireguard_configs
                WHERE user_id=?
                  AND status='active'
                """,
                (user_id,),
            ).fetchone()

            return int(row["n"])

    def active_configs(self, user_id: int):
        with self.connect() as db:
            return db.execute(
                """
                SELECT *
                FROM wireguard_configs
                WHERE user_id=?
                  AND status='active'
                ORDER BY id
                """,
                (user_id,),
            ).fetchall()

    def get_config(self, config_id: int):
        with self.connect() as db:
            return db.execute(
                """
                SELECT *
                FROM wireguard_configs
                WHERE id=?
                """,
                (config_id,),
            ).fetchone()

    def allocate_vpn_address(self, prefix="10.200.0.", start=2, end=254):
        """Return the first VPN /32 address not used by an active configuration."""
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT vpn_address
                FROM wireguard_configs
                WHERE status = 'active'
                """
            ).fetchall()

        used = {row[0] for row in rows if row[0]}

        for host in range(start, end + 1):
            address = f"{prefix}{host}/32"
            if address not in used:
                return address

        raise RuntimeError("No free WireGuard VPN addresses available")

    def create_config(
        self,
        user_id: int,
        name: str,
        private_key_encrypted: str,
        public_key: str,
        vpn_address: str,
        routeros_peer_id: str,
    ):
        with self.connect() as db:
            cur = db.execute(
                """
                INSERT INTO wireguard_configs
                (
                    user_id,
                    name,
                    private_key_encrypted,
                    public_key,
                    vpn_address,
                    routeros_peer_id,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    user_id,
                    name,
                    private_key_encrypted,
                    public_key,
                    vpn_address,
                    routeros_peer_id,
                    utcnow(),
                ),
            )

            return cur.lastrowid

    def mark_config_deleted(
        self,
        config_id: int,
        admin_id: int,
    ):
        with self.connect() as db:
            db.execute(
                """
                UPDATE wireguard_configs
                SET status='deleted',
                    deleted_at=?,
                    deleted_by=?
                WHERE id=?
                  AND status='active'
                """,
                (
                    utcnow(),
                    admin_id,
                    config_id,
                ),
            )

    def active_vpn_addresses(self):
        with self.connect() as db:
            return [
                row["vpn_address"]
                for row in db.execute(
                    """
                    SELECT vpn_address
                    FROM wireguard_configs
                    WHERE status='active'
                    """
                ).fetchall()
            ]

    def next_config_number(self, telegram_id: int) -> int:
        """
        Возвращает первый свободный номер WireGuard-конфигурации
        для данного Telegram ID.

        Например:
        wg-123-1
        wg-123-2
        wg-123-3

        Если №1 удалён, а №2 и №3 существуют,
        вернётся 1.
        """
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT name
                FROM wireguard_configs
                WHERE name LIKE ?
                """,
                (f"wg-{telegram_id}-%",),
            ).fetchall()

        used_numbers = set()

        prefix = f"wg-{telegram_id}-"

        for row in rows:
            name = row["name"]

            if not name.startswith(prefix):
                continue

            suffix = name[len(prefix):]

            try:
                number = int(suffix)
            except ValueError:
                continue

            if number > 0:
                used_numbers.add(number)

        number = 1

        while number in used_numbers:
            number += 1

        return number
