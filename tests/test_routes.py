"""
Integration tests — Flask routes + database working together.
Every test gets a clean in-memory DB via the fixtures in conftest.py.
"""
import pytest


# ── Home / public pages ───────────────────────────────────────────────────────

class TestPublicPages:
    def test_home_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_about_returns_200(self, client):
        assert client.get("/about").status_code == 200

    def test_elections_returns_200(self, client):
        assert client.get("/elections").status_code == 200

    def test_results_returns_200(self, client):
        assert client.get("/results").status_code == 200

    def test_unknown_route_returns_404(self, client):
        assert client.get("/does-not-exist").status_code == 404


# ── Authentication ────────────────────────────────────────────────────────────

class TestAuth:
    def test_login_page_loads(self, client):
        assert client.get("/login").status_code == 200

    def test_register_page_loads(self, client):
        assert client.get("/register").status_code == 200

    def test_valid_admin_login_redirects(self, client):
        r = client.post("/login",
                        data={"username": "admin", "password": "admin123"},
                        follow_redirects=False)
        assert r.status_code == 302
        assert "/admin" in r.headers["Location"]

    def test_valid_voter_login_redirects_to_elections(self, client):
        r = client.post("/login",
                        data={"username": "voter1", "password": "voter123"},
                        follow_redirects=False)
        assert r.status_code == 302
        assert "/elections" in r.headers["Location"]

    def test_invalid_login_shows_error(self, client):
        r = client.post("/login",
                        data={"username": "admin", "password": "wrongpass"},
                        follow_redirects=True)
        assert b"Invalid credentials" in r.data

    def test_register_new_voter(self, client):
        r = client.post("/register", data={
            "username": "newvoter",
            "email":    "newvoter@example.com",
            "password": "pass1234",
            "role":     "voter",
        }, follow_redirects=True)
        assert b"Awaiting admin approval" in r.data

    def test_duplicate_username_rejected(self, client):
        r = client.post("/register", data={
            "username": "admin",          # already exists
            "email":    "other@test.com",
            "password": "pass1234",
            "role":     "voter",
        }, follow_redirects=True)
        assert b"taken" in r.data

    def test_logout_clears_session(self, admin_client):
        r = admin_client.get("/logout", follow_redirects=True)
        assert r.status_code == 200
        # After logout, admin dashboard should redirect
        r2 = admin_client.get("/admin", follow_redirects=False)
        assert r2.status_code == 302


# ── Access control ────────────────────────────────────────────────────────────

class TestAccessControl:
    def test_admin_dashboard_requires_login(self, client):
        r = client.get("/admin", follow_redirects=False)
        assert r.status_code == 302

    def test_voter_cannot_access_admin(self, voter_client):
        r = voter_client.get("/admin")
        assert r.status_code == 403

    def test_voter_cannot_access_trustee_dashboard(self, voter_client):
        r = voter_client.get("/trustee")
        assert r.status_code == 403

    def test_admin_can_access_dashboard(self, admin_client):
        r = admin_client.get("/admin")
        assert r.status_code == 200

    def test_trustee_can_access_trustee_dashboard(self, trustee_client):
        r = trustee_client.get("/trustee")
        assert r.status_code == 200

    def test_vote_page_requires_login(self, client):
        r = client.get("/vote/1", follow_redirects=False)
        assert r.status_code == 302


# ── Admin election management ─────────────────────────────────────────────────

class TestAdminElectionManagement:
    def test_new_election_page_loads(self, admin_client):
        assert admin_client.get("/admin/elections/new").status_code == 200

    def test_create_election_success(self, admin_client, db):
        from datetime import datetime, timedelta
        start = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        end   = (datetime.utcnow() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        # Need trustee IDs from DB
        t1 = db.execute("SELECT id FROM user WHERE username='trustee1'").fetchone()["id"]
        t2 = db.execute("SELECT id FROM user WHERE username='trustee2'").fetchone()["id"]
        r = admin_client.post("/admin/elections/new", data={
            "name":               "Test Election",
            "description":        "A test",
            "category":           "General",
            "start_time":         start,
            "end_time":           end,
            "threshold":          "2",
            "n_trustees":         "2",
            "candidate_name[]":   ["Alice", "Bob"],
            "candidate_symbol[]": ["🔵", "🔴"],
            "candidate_manifesto[]": ["", ""],
            "trustees":           [str(t1), str(t2)],
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b"Test Election" in r.data

    def test_create_election_fails_without_enough_trustees(self, admin_client, db):
        from datetime import datetime, timedelta
        start = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        end   = (datetime.utcnow() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        t1 = db.execute("SELECT id FROM user WHERE username='trustee1'").fetchone()["id"]
        r = admin_client.post("/admin/elections/new", data={
            "name": "Bad Election", "description": "", "category": "General",
            "start_time": start, "end_time": end,
            "threshold": "2", "n_trustees": "2",
            "candidate_name[]": ["Alice"], "candidate_symbol[]": ["🔵"],
            "candidate_manifesto[]": [""],
            "trustees": [str(t1)],   # only 1 trustee, threshold=2
        }, follow_redirects=True)
        assert b"Assign at least" in r.data


# ── Voter flow ────────────────────────────────────────────────────────────────

class TestVoterFlow:
    @pytest.fixture
    def open_election(self, admin_client, db):
        """Create and open an election, return its id."""
        from datetime import datetime, timedelta
        start = (datetime.utcnow() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")
        end   = (datetime.utcnow() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        t1 = db.execute("SELECT id FROM user WHERE username='trustee1'").fetchone()["id"]
        t2 = db.execute("SELECT id FROM user WHERE username='trustee2'").fetchone()["id"]
        admin_client.post("/admin/elections/new", data={
            "name": "Live Election", "description": "", "category": "General",
            "start_time": start, "end_time": end,
            "threshold": "2", "n_trustees": "2",
            "candidate_name[]": ["Alice", "Bob"],
            "candidate_symbol[]": ["🔵", "🔴"],
            "candidate_manifesto[]": ["", ""],
            "trustees": [str(t1), str(t2)],
        })
        eid = db.execute("SELECT id FROM election ORDER BY id DESC LIMIT 1").fetchone()["id"]
        admin_client.post(f"/admin/elections/{eid}/open")
        return eid

    def test_voter_can_see_vote_page(self, voter_client, open_election):
        r = voter_client.get(f"/vote/{open_election}")
        assert r.status_code == 200
        assert b"Alice" in r.data
        assert b"Bob"   in r.data

    def test_voter_can_cast_vote(self, voter_client, open_election, db):
        cid = db.execute(
            "SELECT id FROM candidate WHERE election_id=? ORDER BY position LIMIT 1",
            (open_election,)).fetchone()["id"]
        r = voter_client.post(f"/vote/{open_election}",
                              data={"candidate_id": str(cid), "ciphertext_hex": ""},
                              follow_redirects=True)
        assert r.status_code == 200
        assert b"receipt" in r.data.lower() or b"recorded" in r.data.lower()

    def test_voter_cannot_vote_twice(self, voter_client, open_election, db):
        cid = db.execute(
            "SELECT id FROM candidate WHERE election_id=? ORDER BY position LIMIT 1",
            (open_election,)).fetchone()["id"]
        voter_client.post(f"/vote/{open_election}",
                          data={"candidate_id": str(cid), "ciphertext_hex": ""})
        r = voter_client.post(f"/vote/{open_election}",
                              data={"candidate_id": str(cid), "ciphertext_hex": ""},
                              follow_redirects=True)
        assert b"already voted" in r.data.lower()

    def test_vote_appears_in_audit_trail(self, voter_client, open_election, db):
        cid = db.execute(
            "SELECT id FROM candidate WHERE election_id=? ORDER BY position LIMIT 1",
            (open_election,)).fetchone()["id"]
        voter_client.post(f"/vote/{open_election}",
                          data={"candidate_id": str(cid), "ciphertext_hex": ""})
        r = voter_client.get(f"/audit/{open_election}")
        assert b"vote_received" in r.data

    def test_admin_cannot_vote(self, admin_client, open_election, db):
        cid = db.execute(
            "SELECT id FROM candidate WHERE election_id=? ORDER BY position LIMIT 1",
            (open_election,)).fetchone()["id"]
        r = admin_client.post(f"/vote/{open_election}",
                              data={"candidate_id": str(cid)},
                              follow_redirects=True)
        assert b"Only voters" in r.data
