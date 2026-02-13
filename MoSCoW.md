# MoSCoW Prioritization for SecureVote Guardian

## Must Have

Non-negotiable items required for a viable, secure election system MVP.

* **Core cryptography**: Paillier key generation, client-side encryption, homomorphic tally, threshold decryption (3-of-5).
* **Basic user roles**: Admin, Voter, Trustee workflows (create election, cast vote, partial decrypt, view results).
* **Secure vote storage**: Encrypted votes in PostgreSQL, token-based single voting, eligibility list handling.
* **Minimal web UI**: Browser-based voting form, admin panel to open/close election and see results.
* **Secure deployment baseline**: Flask backend, PostgreSQL, Nginx reverse proxy with HTTPS on a single server/VM or container setup.

## Should Have

Important and highly desirable for smooth usage and evaluation, but system still works without them.

* **Admin dashboards**: Turnout statistics, status indicators (OPEN/CLOSED/DECRYPTING/COMPLETE).
* **Trustee dashboard**: List of pending elections, one-click partial decryption, progress indicator (e.g., "2/5 trustees done").
* **Audit export**: Bundle with ciphertexts, public key, encrypted tally, final tally, and basic logs.
* **Performance tuning**: Verified handling of around 10k encrypted votes per election within acceptable tally time.
* **Basic error handling and validation**: Clear user-friendly messages for invalid tokens, closed election, malformed requests.

## Could Have

Nice-to-have features that add polish or advanced capability; only if time and resources allow.

* Responsive/mobile-optimized UI with nicer styling and animations.
* Detailed analytics: Charts for turnout by time, comparison across elections.
* Documentation site (GitHub Pages) beyond README: API docs, crypto explanation, tutorials.
* Docker + CI/CD pipeline for one-click deploy to cloud.
* Role-based access control refinements (separate super-admin, audit-viewer roles).

## Won't Have (This Time)

Explicitly out of scope for this semester/release to prevent scope creep.

* National-scale or government-grade deployment and performance.
* Native mobile apps (Android/iOS); only web is supported.
* Complex external integrations (university SSO, SMS/email gateways in production).
* Advanced formal verification or zero-knowledge proofs beyond basic cryptographic correctness.
* Multi-tenant SaaS platform for many organizations on one instance.
