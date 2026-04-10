"""
Unit tests for src/crypto/paillier.py
Covers: key generation, encrypt/decrypt, homomorphic addition,
        Shamir secret sharing, and receipt/audit hashing.
"""
import pytest
from src.crypto.paillier import (
    generate_keypair, encrypt, decrypt,
    add_enc, add_enc_list,
    share_secret, reconstruct_secret,
    receipt_hash, audit_hash,
    pk_to_dict, pk_from_dict, mod_inv,
)

# Use small keys (128-bit) so tests run fast
BITS = 128


@pytest.fixture(scope="module")
def keypair():
    return generate_keypair(bits=BITS)


# ── Key generation ────────────────────────────────────────────────────────────

class TestKeyGeneration:
    def test_public_key_has_required_fields(self, keypair):
        pk, _ = keypair
        assert "n" in pk and "g" in pk and "n_sq" in pk

    def test_n_sq_equals_n_squared(self, keypair):
        pk, _ = keypair
        assert pk["n_sq"] == pk["n"] ** 2

    def test_g_equals_n_plus_one(self, keypair):
        pk, _ = keypair
        assert pk["g"] == pk["n"] + 1

    def test_private_key_has_required_fields(self, keypair):
        _, sk = keypair
        assert "lam" in sk and "mu" in sk


# ── Encrypt / Decrypt ─────────────────────────────────────────────────────────

class TestEncryptDecrypt:
    def test_decrypt_recovers_zero(self, keypair):
        pk, sk = keypair
        assert decrypt(pk, sk, encrypt(pk, 0)) == 0

    def test_decrypt_recovers_one(self, keypair):
        pk, sk = keypair
        assert decrypt(pk, sk, encrypt(pk, 1)) == 1

    def test_decrypt_recovers_large_value(self, keypair):
        pk, sk = keypair
        m = 9999
        assert decrypt(pk, sk, encrypt(pk, m)) == m

    def test_encrypt_is_probabilistic(self, keypair):
        """Same message encrypted twice must produce different ciphertexts."""
        pk, _ = keypair
        c1 = encrypt(pk, 5)
        c2 = encrypt(pk, 5)
        assert c1 != c2

    def test_encrypt_rejects_negative(self, keypair):
        pk, _ = keypair
        with pytest.raises((AssertionError, ValueError)):
            encrypt(pk, -1)

    def test_ciphertext_is_less_than_n_sq(self, keypair):
        pk, _ = keypair
        ct = encrypt(pk, 42)
        assert ct < pk["n_sq"]


# ── Homomorphic addition ──────────────────────────────────────────────────────

class TestHomomorphicAddition:
    def test_add_two_ciphertexts(self, keypair):
        pk, sk = keypair
        c1 = encrypt(pk, 3)
        c2 = encrypt(pk, 7)
        assert decrypt(pk, sk, add_enc(pk, c1, c2)) == 10

    def test_add_list_of_ciphertexts(self, keypair):
        pk, sk = keypair
        values = [0, 1, 2, 3, 4]
        cs     = [encrypt(pk, v) for v in values]
        assert decrypt(pk, sk, add_enc_list(pk, cs)) == sum(values)

    def test_add_zeros(self, keypair):
        pk, sk = keypair
        cs = [encrypt(pk, 0) for _ in range(5)]
        assert decrypt(pk, sk, add_enc_list(pk, cs)) == 0

    def test_homomorphic_sum_matches_direct_sum(self, keypair):
        pk, sk = keypair
        values = [1, 1, 0, 1, 0, 1]
        cs     = [encrypt(pk, v) for v in values]
        assert decrypt(pk, sk, add_enc_list(pk, cs)) == sum(values)


# ── Shamir's Secret Sharing ───────────────────────────────────────────────────

class TestShamirSecretSharing:
    @pytest.fixture
    def shares_fixture(self, keypair):
        _, sk    = keypair
        secret   = sk["lam"]
        shares, prime = share_secret(secret, threshold=2, n_shares=3)
        return secret, shares, prime

    def test_prime_larger_than_secret(self, shares_fixture):
        secret, _, prime = shares_fixture
        assert prime > secret

    def test_reconstruct_with_threshold_shares(self, shares_fixture):
        secret, shares, prime = shares_fixture
        recovered = reconstruct_secret(shares[:2], prime)
        assert recovered == secret

    def test_reconstruct_with_all_shares(self, shares_fixture):
        secret, shares, prime = shares_fixture
        recovered = reconstruct_secret(shares, prime)
        assert recovered == secret

    def test_reconstruct_different_share_pairs(self, shares_fixture):
        """Any 2-of-3 combination must recover the secret."""
        secret, shares, prime = shares_fixture
        for combo in [(0, 1), (0, 2), (1, 2)]:
            selected  = [shares[i] for i in combo]
            recovered = reconstruct_secret(selected, prime)
            assert recovered == secret, f"Failed for combo {combo}"

    def test_decryption_works_after_shamir_reconstruction(self, keypair):
        pk, sk = keypair
        lam    = sk["lam"]
        shares, prime = share_secret(lam, threshold=2, n_shares=3)
        recon_lam = reconstruct_secret(shares[:2], prime)
        recon_mu  = mod_inv(recon_lam, pk["n"])
        sk2       = {"lam": recon_lam, "mu": recon_mu}
        for m in range(5):
            ct = encrypt(pk, m)
            assert decrypt(pk, sk2, ct) == m


# ── Serialisation ─────────────────────────────────────────────────────────────

class TestSerialisation:
    def test_pk_roundtrip(self, keypair):
        pk, _ = keypair
        assert pk_from_dict(pk_to_dict(pk)) == pk

    def test_serialised_pk_values_are_hex_strings(self, keypair):
        pk, _ = keypair
        d     = pk_to_dict(pk)
        assert all(isinstance(v, str) and v.startswith("0x") for v in d.values() if isinstance(v, str))


# ── Hashing ───────────────────────────────────────────────────────────────────

class TestHashing:
    def test_receipt_hash_is_64_chars(self):
        h = receipt_hash(1, 1, "0xdeadbeef")
        assert len(h) == 64

    def test_receipt_hash_is_deterministic(self):
        assert receipt_hash(1, 1, "0xabc") == receipt_hash(1, 1, "0xabc")

    def test_receipt_hash_changes_with_input(self):
        assert receipt_hash(1, 1, "0xabc") != receipt_hash(1, 1, "0xdef")

    def test_audit_hash_is_deterministic(self):
        h1 = audit_hash("vote_cast", {"election_id": 1})
        h2 = audit_hash("vote_cast", {"election_id": 1})
        assert h1 == h2

    def test_audit_hash_changes_with_event(self):
        h1 = audit_hash("vote_cast",      {"election_id": 1})
        h2 = audit_hash("election_closed", {"election_id": 1})
        assert h1 != h2
