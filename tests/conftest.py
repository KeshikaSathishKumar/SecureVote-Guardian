"""
Shared pytest fixtures.
Uses a temporary file-based SQLite DB per test (in-memory doesn't work well
because sqlite3 closes connections between calls).
"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.backend.db as db_module


@pytest.fixture(scope="function", autouse=True)
def fresh_db(tmp_path):
    """Point DB at a temp file for each test. Cleaned up automatically."""
    db_file = str(tmp_path / "test_securevote.db")
    db_module.DB_PATH = db_file
    db_module.init_db()
    db_module.seed_db()
    yield
    # tmp_path cleanup is automatic


@pytest.fixture(scope="function")
def db(fresh_db):
    """Return a live connection to the test DB."""
    return db_module.get_db()


def _setup_app():
    """Configure the Flask app singleton for testing."""
    from src.backend.app import app as flask_app
    flask_app.config["TESTING"]    = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    return flask_app


@pytest.fixture(scope="function")
def client(fresh_db):
    app = _setup_app()
    with app.test_client() as c:
        yield c


@pytest.fixture
def admin_client(fresh_db):
    """Independent test client logged in as admin (own session cookie jar)."""
    app = _setup_app()
    c = app.test_client()
    c.post("/login", data={"username": "admin", "password": "admin123"})
    yield c


@pytest.fixture
def voter_client(fresh_db):
    """Independent test client logged in as voter1 (own session cookie jar)."""
    app = _setup_app()
    c = app.test_client()
    c.post("/login", data={"username": "voter1", "password": "voter123"})
    yield c


@pytest.fixture
def trustee_client(fresh_db):
    """Independent test client logged in as trustee1 (own session cookie jar)."""
    app = _setup_app()
    c = app.test_client()
    c.post("/login", data={"username": "trustee1", "password": "trustee1pass"})
    yield c