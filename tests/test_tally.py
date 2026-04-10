"""
End-to-end election flow tests.
Simulates the complete lifecycle:
  create → open → vote (multiple) → close →
  trustees submit shares → admin computes tally → verify results.
"""
import json
import pytest
from src.backend.db      import get_db
from src.crypto.paillier import (
    generate_keypair, encrypt, decrypt,
    share_secret, reconstruct_secret,
    pk_to_dict, pk_from_dict, mod_inv,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_open_election(admin_client, db, threshold=2, n_trustees=2):
    """Create and open an election. Returns election_id."""
    from datetime import datetime, timedelta
    start = (datetime.utcnow() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")
    end   = (datetime.utcnow() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    t_rows = db.execute(
        "SELECT id FROM user WHERE role='trustee' AND approved=1 LIMIT ?",
        (n_trustees,)).fetchall()
    tids = [str(r["id"]) for r in t_rows]
    admin_client.post("/admin/elections/new", data={
        "name": "E2E Election", "description": "", "category": "General",
        "start_time": start, "end_time": end,
        "threshold": str(threshold), "n_trustees": str(n_trustees),
        "candidate_name[]":     ["Alice", "Bob", "Charlie"],
        "candidate_symbol[]":   ["🔵",   "🔴",  "🟢"],
        "candidate_manifesto[]":["",      "",    ""],
        "trustees": tids,
    })
    eid = db.execute("SELECT id FROM election ORDER BY id DESC LIMIT 1").fetchone()["id"]
    admin_client.post(f"/admin/elections/{eid}/open")
    return eid


def _cast_vote(client, eid, candidate_position, db):
    """Cast a server-side encrypted vote for a candidate at given position."""
    cid = db.execute(
        "SELECT id FROM candidate WHERE election_id=? AND position=?",
        (eid, candidate_position)).fetchone()["id"]
    client.post(f"/vote/{eid}", data={"candidate_id": str(cid), "ciphertext_hex": ""})


# ── Full election lifecycle ───────────────────────────────────────────────────

class TestFullElectionFlow:
    def test_election_created_in_db(self, admin_client, db):
        eid = _create_open_election(admin_client, db)
        e   = db.execute("SELECT * FROM election WHERE id=?", (eid,)).fetchone()
        assert e is not None
        assert e["status"] == "ongoing"
        assert e["public_key_json"] is not None
        assert e["shamir_prime_hex"] is not None

    def test_candidates_created(self, admin_client, db):
        eid   = _create_open_election(admin_client, db)
        cands = db.execute("SELECT * FROM candidate WHERE election_id=?", (eid,)).fetchall()
        assert len(cands) == 3
        names = [c["name"] for c in cands]
        assert "Alice" in names and "Bob" in names and "Charlie" in names

    def test_trustee_shares_distributed(self, admin_client, db):
        eid    = _create_open_election(admin_client, db, threshold=2, n_trustees=2)
        shares = db.execute("SELECT * FROM trustee_share WHERE election_id=?", (eid,)).fetchall()
        assert len(shares) == 2

    def test_vote_stored_encrypted(self, admin_client, voter_client, db):
        eid = _create_open_election(admin_client, db)
        _cast_vote(voter_client, eid, 0, db)
        vote = db.execute("SELECT * FROM vote WHERE election_id=?", (eid,)).fetchone()
        assert vote is not None
        assert vote["ciphertext"].startswith("0x")
        assert vote["receipt"] is not None

    def test_ciphertext_is_not_plaintext(self, admin_client, voter_client, db):
        """The stored ciphertext must not equal the candidate position."""
        eid = _create_open_election(admin_client, db)
        _cast_vote(voter_client, eid, 0, db)
        vote = db.execute("SELECT * FROM vote WHERE election_id=?", (eid,)).fetchone()
        # Plaintext 0 would be stored as "0x0" — a real ciphertext is much larger
        ct_int = int(vote["ciphertext"], 16)
        assert ct_int > 1000  # any real Paillier ciphertext is enormous

    def test_tally_requires_trustee_submissions(self, admin_client, voter_client, db):
        eid = _create_open_election(admin_client, db)
        _cast_vote(voter_client, eid, 0, db)
        admin_client.post(f"/admin/elections/{eid}/close")
        # Try tally without any trustee submissions
        r = admin_client.post(f"/admin/tally/{eid}", follow_redirects=True)
        assert b"Need" in r.data or b"submissions" in r.data.lower()

    def test_complete_tally_with_trustee_submissions(self, admin_client, voter_client, trustee_client, client, db):
        """Full flow: vote → close → trustees submit → tally → verify count."""
        eid = _create_open_election(admin_client, db, threshold=2, n_trustees=2)

        # voter1 votes for Alice (position 0)
        _cast_vote(voter_client, eid, 0, db)

        # Close election
        admin_client.post(f"/admin/elections/{eid}/close")

        # trustee1 submits their share
        trustee_client.post(f"/trustee/submit/{eid}")

        # trustee2 also submits — reuse the client fixture (same DB)
        client.post("/login", data={"username": "trustee2", "password": "trustee2pass"})
        client.post(f"/trustee/submit/{eid}")

        # Admin computes tally
        r = admin_client.post(f"/admin/tally/{eid}", follow_redirects=True)
        assert r.status_code == 200

        # Check result in DB
        result = db.execute("SELECT * FROM election_result WHERE election_id=?", (eid,)).fetchone()
        assert result is not None
        tally = json.loads(result["tally_json"])
        total_votes = sum(tally.values())
        assert total_votes == 1  # exactly one vote was cast

        # Alice (position 0) should have 1 vote
        alice = db.execute(
            "SELECT id FROM candidate WHERE election_id=? AND position=0", (eid,)).fetchone()
        assert tally[str(alice["id"])] == 1

    def test_election_marked_completed_after_tally(self, admin_client, voter_client, trustee_client, client, db):
        eid = _create_open_election(admin_client, db)
        _cast_vote(voter_client, eid, 0, db)
        admin_client.post(f"/admin/elections/{eid}/close")
        trustee_client.post(f"/trustee/submit/{eid}")
        client.post("/login", data={"username": "trustee2", "password": "trustee2pass"})
        client.post(f"/trustee/submit/{eid}")
        admin_client.post(f"/admin/tally/{eid}")
        e = db.execute("SELECT status FROM election WHERE id=?", (eid,)).fetchone()
        assert e["status"] == "completed"

    def test_results_page_shows_tally(self, admin_client, voter_client, trustee_client, client, db):
        eid = _create_open_election(admin_client, db)
        _cast_vote(voter_client, eid, 0, db)
        admin_client.post(f"/admin/elections/{eid}/close")
        trustee_client.post(f"/trustee/submit/{eid}")
        client.post("/login", data={"username": "trustee2", "password": "trustee2pass"})
        client.post(f"/trustee/submit/{eid}")
        admin_client.post(f"/admin/tally/{eid}")
        r = admin_client.get(f"/results/{eid}")
        assert r.status_code == 200
        assert b"Alice" in r.data


# ── Crypto correctness ────────────────────────────────────────────────────────

class TestCryptoTallyCorrectness:
    """Direct crypto tests that don't go through HTTP — verify math is sound."""

    def test_tally_3_candidates_10_votes(self):
        pk, sk = generate_keypair(bits=128)
        # 4 votes for 0, 4 for 1, 2 for 2
        vote_positions = [0,0,0,0, 1,1,1,1, 2,2]
        expected       = {0:4, 1:4, 2:2}

        tally = {0:0, 1:0, 2:0}
        for pos in vote_positions:
            ct = encrypt(pk, pos)
            mi = decrypt(pk, sk, ct)
            tally[mi] += 1
        assert tally == expected

    def test_tally_with_shamir_reconstruction(self):
        pk, sk = generate_keypair(bits=128)
        lam    = sk["lam"]
        shares, prime = share_secret(lam, threshold=2, n_shares=3)

        vote_positions = [0, 1, 0, 2, 1, 0]
        expected       = {0:3, 1:2, 2:1}

        # Reconstruct key from 2-of-3 shares
        recon_lam = reconstruct_secret(shares[:2], prime)
        recon_mu  = mod_inv(recon_lam, pk["n"])
        sk2       = {"lam": recon_lam, "mu": recon_mu}

        tally = {0:0, 1:0, 2:0}
        for pos in vote_positions:
            ct = encrypt(pk, pos)
            mi = decrypt(pk, sk2, ct)
            tally[mi] += 1
        assert tally == expected

    def test_tally_unanimous_vote(self):
        pk, sk  = generate_keypair(bits=128)
        n_votes = 5
        tally   = {0:0, 1:0}
        for _ in range(n_votes):
            ct = encrypt(pk, 0)
            mi = decrypt(pk, sk, ct)
            tally[mi] += 1
        assert tally == {0:5, 1:0}

    def test_shamir_any_threshold_combination(self):
        """Every possible 2-of-4 combination must yield the same tally."""
        from itertools import combinations
        pk, sk = generate_keypair(bits=128)
        lam    = sk["lam"]
        shares, prime = share_secret(lam, threshold=2, n_shares=4)

        # Encrypt one vote
        ct = encrypt(pk, 1)

        results = set()
        for combo in combinations(range(4), 2):
            selected  = [shares[i] for i in combo]
            r_lam     = reconstruct_secret(selected, prime)
            r_mu      = mod_inv(r_lam, pk["n"])
            sk2       = {"lam": r_lam, "mu": r_mu}
            results.add(decrypt(pk, sk2, ct))

        assert results == {1}, f"Not all combos decrypted correctly: {results}"


# ── Regression tests ──────────────────────────────────────────────────────────

class TestRegressions:
    """
    Regression tests — pin known-good behaviour so future changes don't break it.
    Add a test here every time a bug is fixed.
    """

    def test_reg_candidates_visible_on_vote_page(self, admin_client, voter_client, db):
        """Regression: candidates were not showing on vote page (election.candidates bug)."""
        eid = _create_open_election(admin_client, db)
        r   = voter_client.get(f"/vote/{eid}")
        assert b"Alice" in r.data
        assert b"Bob"   in r.data

    def test_reg_ongoing_election_not_reverted_to_upcoming(self, admin_client, db):
        """Regression: compute_status() was overriding admin-set 'ongoing' back to 'upcoming'."""
        eid = _create_open_election(admin_client, db)
        e   = db.execute("SELECT status FROM election WHERE id=?", (eid,)).fetchone()
        assert e["status"] == "ongoing"
        # Calling elections page should not revert status
        admin_client.get("/elections")
        e = db.execute("SELECT status FROM election WHERE id=?", (eid,)).fetchone()
        assert e["status"] == "ongoing"

    def test_reg_tally_zero_without_trustee_shares(self, admin_client, voter_client, db):
        """Regression: tally returned 0 for all candidates when Shamir prime < lam."""
        pk, sk = generate_keypair(bits=128)
        lam    = sk["lam"]
        shares, prime = share_secret(lam, threshold=2, n_shares=2)
        # Prime must always be larger than lam
        assert prime > lam
        # Reconstruction must be exact
        recon = reconstruct_secret(shares, prime)
        assert recon == lam

    def test_reg_double_vote_prevented(self, admin_client, voter_client, db):
        """Regression: verify DB UNIQUE constraint prevents double voting."""
        eid = _create_open_election(admin_client, db)
        _cast_vote(voter_client, eid, 0, db)
        _cast_vote(voter_client, eid, 1, db)  # second vote silently redirects
        count = db.execute(
            "SELECT COUNT(*) FROM vote WHERE election_id=?", (eid,)).fetchone()[0]
        assert count == 1

    def test_reg_audit_log_records_every_vote(self, admin_client, voter_client, db):
        """Regression: every vote must produce an audit_log entry."""
        eid = _create_open_election(admin_client, db)
        _cast_vote(voter_client, eid, 0, db)
        logs = db.execute(
            "SELECT * FROM audit_log WHERE election_id=? AND event_type='vote_received'",
            (eid,)).fetchall()
        assert len(logs) == 1
