"""
Database layer — raw sqlite3, no ORM.
DB file lives at project root so it is easy to find and back up.
"""
import sqlite3
import os

# Always resolve DB path relative to project root (two levels up from this file)
_HERE    = os.path.dirname(__file__)               # src/backend/
_ROOT    = os.path.abspath(os.path.join(_HERE, "..", ".."))
DB_PATH  = os.environ.get("DB_PATH", os.path.join(_ROOT, "securevote.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS user (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT UNIQUE NOT NULL,
        email         TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role          TEXT DEFAULT 'voter',
        approved      INTEGER DEFAULT 0,
        created_at    TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS election (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        name             TEXT NOT NULL,
        description      TEXT,
        category         TEXT DEFAULT 'General',
        start_time       TEXT,
        end_time         TEXT,
        status           TEXT DEFAULT 'draft',
        public_key_json  TEXT,
        shamir_prime_hex TEXT,
        threshold        INTEGER DEFAULT 2,
        n_trustees       INTEGER DEFAULT 3,
        created_by       INTEGER
    );
    CREATE TABLE IF NOT EXISTS candidate (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        election_id INTEGER,
        name        TEXT NOT NULL,
        symbol      TEXT DEFAULT '🏛️',
        manifesto   TEXT,
        position    INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS vote (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        election_id INTEGER,
        voter_id    INTEGER,
        ciphertext  TEXT NOT NULL,
        receipt     TEXT UNIQUE,
        timestamp   TEXT DEFAULT (datetime('now')),
        UNIQUE(election_id, voter_id)
    );
    CREATE TABLE IF NOT EXISTS trustee_assignment (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        election_id INTEGER,
        trustee_id  INTEGER
    );
    CREATE TABLE IF NOT EXISTS trustee_share (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        election_id  INTEGER,
        trustee_id   INTEGER,
        share_x      INTEGER,
        share_y_hex  TEXT,
        acknowledged INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS trustee_submission (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        election_id  INTEGER,
        trustee_id   INTEGER,
        share_x      INTEGER,
        share_y_hex  TEXT,
        submitted_at TEXT DEFAULT (datetime('now')),
        UNIQUE(election_id, trustee_id)
    );
    CREATE TABLE IF NOT EXISTS election_result (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        election_id INTEGER UNIQUE,
        tally_json  TEXT,
        computed_at TEXT DEFAULT (datetime('now')),
        tally_hash  TEXT
    );
    CREATE TABLE IF NOT EXISTS audit_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        election_id INTEGER,
        event_type  TEXT,
        payload     TEXT,
        action_hash TEXT,
        timestamp   TEXT DEFAULT (datetime('now'))
    );
    """)
    conn.commit()
    conn.close()


def migrate_db():
    """Safe, additive migrations — never drops data."""
    conn = get_db()
    # Add any columns introduced after initial release
    for stmt in [
        "ALTER TABLE election ADD COLUMN private_key_json TEXT",  # legacy, harmless
    ]:
        try:
            conn.execute(stmt)
            conn.commit()
        except Exception:
            pass
    # Ensure trustee_submission table exists (added in v2)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trustee_submission (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            election_id  INTEGER,
            trustee_id   INTEGER,
            share_x      INTEGER,
            share_y_hex  TEXT,
            submitted_at TEXT DEFAULT (datetime('now')),
            UNIQUE(election_id, trustee_id)
        )
    """)
    conn.commit()
    conn.close()


def seed_db():
    """Insert default demo accounts only if the DB is empty."""
    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM user").fetchone()[0] > 0:
        conn.close()
        return
    from werkzeug.security import generate_password_hash
    users = [
        ("admin",    "admin@example.com",    generate_password_hash("admin123"),    "admin",   1),
        ("trustee1", "trustee1@example.com", generate_password_hash("trustee1pass"),"trustee", 1),
        ("trustee2", "trustee2@example.com", generate_password_hash("trustee2pass"),"trustee", 1),
        ("trustee3", "trustee3@example.com", generate_password_hash("trustee3pass"),"trustee", 1),
        ("voter1",   "voter1@example.com",   generate_password_hash("voter123"),    "voter",   1),
    ]
    conn.executemany(
        "INSERT INTO user(username,email,password_hash,role,approved) VALUES(?,?,?,?,?)", users)
    conn.commit()
    conn.close()
    print("✅  Demo accounts seeded — admin/admin123 | voter1/voter123 | trustee1/trustee1pass")
