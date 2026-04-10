"""
Entry point — run from project root:
    python app.py
or via Docker / gunicorn:
    gunicorn app:app
"""
import os
import sys

# Ensure project root is on the path so `src.*` imports resolve
sys.path.insert(0, os.path.dirname(__file__))

from src.backend.db  import init_db, migrate_db, seed_db
from src.backend.app import app

if __name__ == "__main__":
    init_db()
    migrate_db()
    seed_db()
    app.run(
        host=os.environ.get("FLASK_HOST", "0.0.0.0"),
        port=int(os.environ.get("FLASK_PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "true").lower() == "true",
    )
