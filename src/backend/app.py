"""
SecureVote Guardian — Flask application.
All imports use absolute src.* paths so the app works from any working directory.
"""
import os
import json
import hashlib
from datetime import datetime
from functools import wraps

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, abort)
from werkzeug.security import generate_password_hash, check_password_hash

from src.backend.db import get_db, init_db, migrate_db, seed_db
from src.crypto.paillier import (
    generate_keypair, encrypt, decrypt,
    share_secret, reconstruct_secret,
    receipt_hash, audit_hash,
    pk_to_dict, pk_from_dict, mod_inv,
)

# ── Resolve template / static paths relative to src/ ─────────────────────────
_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

app = Flask(
    __name__,
    template_folder=os.path.join(_SRC, "templates"),
    static_folder=os.path.join(_SRC, "static"),
)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")


# ── Jinja date filter ─────────────────────────────────────────────────────────
@app.template_filter("fmtdate")
def fmtdate(value, fmt="%Y-%m-%d %H:%M"):
    if not value:
        return "—"
    if isinstance(value, str):
        for pat in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, pat).strftime(fmt)
            except ValueError:
                continue
        return value
    try:
        return value.strftime(fmt)
    except Exception:
        return str(value)


# ── Helpers ───────────────────────────────────────────────────────────────────
def compute_status(status, start_time, end_time):
    """Auto-advance 'upcoming' → 'ongoing'/'counting' based on clock.
    Admin-set statuses (ongoing, counting, completed, draft) are never overridden."""
    if status in ("ongoing", "counting", "completed", "draft"):
        return status
    if status == "upcoming" and start_time:
        try:
            now = datetime.utcnow()
            st  = datetime.fromisoformat(start_time.replace("T", " "))
            et  = datetime.fromisoformat(end_time.replace("T", " ")) if end_time else None
            if now >= st:
                return "counting" if (et and now > et) else "ongoing"
        except Exception:
            pass
    return status


def log_event(conn, event, payload, eid=None):
    h = audit_hash(event, payload)
    conn.execute(
        "INSERT INTO audit_log(election_id,event_type,payload,action_hash) VALUES(?,?,?,?)",
        (eid, event, json.dumps(payload), h),
    )


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_db()
    u = conn.execute("SELECT * FROM user WHERE id=?", (uid,)).fetchone()
    conn.close()
    return u


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user():
            flash("Please log in.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            u = current_user()
            if not u or u["role"] not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def home():
    conn   = get_db()
    active = conn.execute("SELECT COUNT(*) FROM election WHERE status='ongoing'").fetchone()[0]
    total  = conn.execute("SELECT COUNT(*) FROM election").fetchone()[0]
    conn.close()
    return render_template("home.html", active=active, total=total)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/elections")
def elections():
    sf = request.args.get("status",   "all")
    cf = request.args.get("category", "all")
    conn = get_db()
    for e in conn.execute("SELECT * FROM election").fetchall():
        cs = compute_status(e["status"], e["start_time"], e["end_time"])
        if cs != e["status"]:
            conn.execute("UPDATE election SET status=? WHERE id=?", (cs, e["id"]))
    conn.commit()
    q, params = "SELECT * FROM election WHERE status != 'draft'", []
    if sf != "all": q += " AND status=?";   params.append(sf)
    if cf != "all": q += " AND category=?"; params.append(cf)
    els = conn.execute(q + " ORDER BY start_time DESC", params).fetchall()
    conn.close()
    return render_template("elections.html", elections=els, sf=sf, cf=cf)


@app.route("/elections/<int:eid>")
def election_detail(eid):
    conn = get_db()
    e = conn.execute("SELECT * FROM election WHERE id=?", (eid,)).fetchone()
    if not e: abort(404)
    cs = compute_status(e["status"], e["start_time"], e["end_time"])
    conn.execute("UPDATE election SET status=? WHERE id=?", (cs, eid))
    conn.commit()
    e          = conn.execute("SELECT * FROM election WHERE id=?", (eid,)).fetchone()
    candidates = conn.execute("SELECT * FROM candidate WHERE election_id=? ORDER BY position", (eid,)).fetchall()
    u          = current_user()
    voted      = False
    if u:
        voted = conn.execute(
            "SELECT 1 FROM vote WHERE election_id=? AND voter_id=?", (eid, u["id"])
        ).fetchone() is not None
    conn.close()
    return render_template("election_detail.html", election=e, candidates=candidates, already_voted=voted)


# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = get_db()
        u = conn.execute("SELECT * FROM user WHERE username=?", (request.form["username"],)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            if not u["approved"]:
                conn.close()
                flash("Account pending approval.", "warning")
                return redirect(url_for("login"))
            session["user_id"] = u["id"]
            log_event(conn, "user_login", {"user": u["username"]})
            conn.commit(); conn.close()
            flash(f"Welcome, {u['username']}!", "success")
            if u["role"] == "admin":   return redirect(url_for("admin_dashboard"))
            if u["role"] == "trustee": return redirect(url_for("trustee_dashboard"))
            return redirect(url_for("elections"))
        conn.close()
        flash("Invalid credentials.", "danger")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        un, em, pw = request.form["username"], request.form["email"], request.form["password"]
        role = request.form.get("role", "voter")
        conn = get_db()
        if conn.execute("SELECT 1 FROM user WHERE username=?", (un,)).fetchone():
            conn.close(); flash("Username taken.", "danger"); return redirect(url_for("register"))
        if conn.execute("SELECT 1 FROM user WHERE email=?", (em,)).fetchone():
            conn.close(); flash("Email taken.", "danger"); return redirect(url_for("register"))
        conn.execute(
            "INSERT INTO user(username,email,password_hash,role,approved) VALUES(?,?,?,?,0)",
            (un, em, generate_password_hash(pw), role),
        )
        log_event(conn, "user_registered", {"username": un, "role": role})
        conn.commit(); conn.close()
        flash("Registered! Awaiting admin approval.", "info")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("home"))


# ══════════════════════════════════════════════════════════════════════════════
# VOTING
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/vote/<int:eid>", methods=["GET", "POST"])
@login_required
def vote(eid):
    u = current_user()
    if u["role"] != "voter":
        flash("Only voters can vote.", "danger")
        return redirect(url_for("election_detail", eid=eid))
    conn = get_db()
    e = conn.execute("SELECT * FROM election WHERE id=?", (eid,)).fetchone()
    if not e: conn.close(); abort(404)
    if e["status"] != "ongoing":
        conn.close(); flash("Voting is not currently open.", "warning")
        return redirect(url_for("election_detail", eid=eid))
    if conn.execute("SELECT 1 FROM vote WHERE election_id=? AND voter_id=?", (eid, u["id"])).fetchone():
        conn.close(); flash("You have already voted.", "info")
        return redirect(url_for("receipt", eid=eid))
    candidates = conn.execute(
        "SELECT * FROM candidate WHERE election_id=? ORDER BY position", (eid,)).fetchall()

    if request.method == "POST":
        cid    = int(request.form["candidate_id"])
        ct_hex = request.form.get("ciphertext_hex", "").strip()
        if not ct_hex:
            pk   = pk_from_dict(json.loads(e["public_key_json"]))
            cand = conn.execute("SELECT * FROM candidate WHERE id=?", (cid,)).fetchone()
            if not cand or cand["election_id"] != eid:
                conn.close(); flash("Invalid candidate.", "danger")
                return redirect(url_for("vote", eid=eid))
            ct_hex = hex(encrypt(pk, cand["position"]))
        rh = receipt_hash(u["id"], eid, ct_hex)
        conn.execute(
            "INSERT INTO vote(election_id,voter_id,ciphertext,receipt) VALUES(?,?,?,?)",
            (eid, u["id"], ct_hex, rh),
        )
        log_event(conn, "vote_received", {"election_id": eid, "receipt": rh}, eid)
        conn.commit(); conn.close()
        flash("Your encrypted vote has been recorded!", "success")
        return redirect(url_for("receipt", eid=eid))

    conn.close()
    return render_template("vote.html", election=e, candidates=candidates, pk_json=e["public_key_json"])


@app.route("/receipt/<int:eid>")
@login_required
def receipt(eid):
    u    = current_user()
    conn = get_db()
    v    = conn.execute("SELECT * FROM vote WHERE election_id=? AND voter_id=?", (eid, u["id"])).fetchone()
    e    = conn.execute("SELECT * FROM election WHERE id=?", (eid,)).fetchone()
    conn.close()
    if not v: abort(404)
    return render_template("receipt.html", vote=v, election=e)


# ══════════════════════════════════════════════════════════════════════════════
# RESULTS & AUDIT
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/results")
def results():
    conn = get_db()
    els  = conn.execute("SELECT * FROM election WHERE status IN ('completed','counting')").fetchall()
    rm   = {}
    cmap = {}
    for e in els:
        r = conn.execute("SELECT * FROM election_result WHERE election_id=?", (e["id"],)).fetchone()
        if r: rm[e["id"]] = json.loads(r["tally_json"])
        cmap[e["id"]] = conn.execute(
            "SELECT * FROM candidate WHERE election_id=? ORDER BY position", (e["id"],)).fetchall()
    conn.close()
    return render_template("results.html", elections=els, results_map=rm, candidates_map=cmap)


@app.route("/results/<int:eid>")
def results_detail(eid):
    conn  = get_db()
    e     = conn.execute("SELECT * FROM election WHERE id=?", (eid,)).fetchone()
    r     = conn.execute("SELECT * FROM election_result WHERE election_id=?", (eid,)).fetchone()
    tally = json.loads(r["tally_json"]) if r else {}
    cands = {str(c["id"]): c for c in conn.execute(
        "SELECT * FROM candidate WHERE election_id=?", (eid,)).fetchall()}
    conn.close()
    return render_template("results_detail.html", election=e, tally=tally, candidates=cands, result=r)


@app.route("/audit/<int:eid>")
def audit(eid):
    conn  = get_db()
    e     = conn.execute("SELECT * FROM election WHERE id=?", (eid,)).fetchone()
    votes = conn.execute("SELECT * FROM vote WHERE election_id=? ORDER BY timestamp", (eid,)).fetchall()
    logs  = conn.execute("SELECT * FROM audit_log WHERE election_id=? ORDER BY timestamp", (eid,)).fetchall()
    conn.close()
    return render_template("audit.html", election=e, votes=votes, logs=logs)


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/admin")
@login_required
@role_required("admin")
def admin_dashboard():
    conn     = get_db()
    elections = conn.execute("SELECT * FROM election ORDER BY id DESC").fetchall()
    voters   = conn.execute("SELECT * FROM user WHERE role='voter'").fetchall()
    pending  = conn.execute("SELECT * FROM user WHERE approved=0").fetchall()
    today    = datetime.utcnow().strftime("%Y-%m-%d")
    vt       = conn.execute("SELECT COUNT(*) FROM vote WHERE timestamp LIKE ?", (today + "%",)).fetchone()[0]
    conn.close()
    return render_template("admin_dashboard.html",
                           elections=elections, voters=voters, pending=pending, votes_today=vt)


@app.route("/admin/approve/<int:uid>", methods=["POST"])
@login_required
@role_required("admin")
def approve_user(uid):
    conn = get_db()
    u    = conn.execute("SELECT * FROM user WHERE id=?", (uid,)).fetchone()
    conn.execute("UPDATE user SET approved=1 WHERE id=?", (uid,))
    log_event(conn, "user_approved", {"username": u["username"]})
    conn.commit(); conn.close()
    flash(f"Approved {u['username']}.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/elections/new", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_new_election():
    conn     = get_db()
    trustees = conn.execute("SELECT * FROM user WHERE role='trustee' AND approved=1").fetchall()
    if request.method == "POST":
        name      = request.form["name"]
        desc      = request.form.get("description", "")
        cat       = request.form.get("category", "General")
        st        = request.form["start_time"]
        et        = request.form["end_time"]
        threshold = int(request.form.get("threshold", 2))
        nt        = int(request.form.get("n_trustees", 3))
        cnames    = request.form.getlist("candidate_name[]")
        csyms     = request.form.getlist("candidate_symbol[]")
        cmans     = request.form.getlist("candidate_manifesto[]")
        tids      = [int(x) for x in request.form.getlist("trustees") if x]

        if len(tids) < threshold:
            conn.close()
            flash(f"Assign at least {threshold} trustees (selected {len(tids)}).", "danger")
            return redirect(url_for("admin_new_election"))

        pk, sk       = generate_keypair(bits=256)
        lam          = sk["lam"]
        shares, prime = share_secret(lam, threshold, len(tids))
        pk_json      = json.dumps(pk_to_dict(pk))
        prime_hex    = hex(prime)
        u            = current_user()

        cur = conn.execute(
            """INSERT INTO election
               (name,description,category,start_time,end_time,status,
                public_key_json,shamir_prime_hex,threshold,n_trustees,created_by)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (name, desc, cat, st, et, "upcoming", pk_json, prime_hex, threshold, len(tids), u["id"]),
        )
        eid = cur.lastrowid

        for i, cn in enumerate(cnames):
            if cn.strip():
                conn.execute(
                    "INSERT INTO candidate(election_id,name,symbol,manifesto,position) VALUES(?,?,?,?,?)",
                    (eid, cn.strip(),
                     csyms[i] if i < len(csyms) else "🏛️",
                     cmans[i] if i < len(cmans) else "",
                     i),
                )

        for idx, tid in enumerate(tids):
            x, y = shares[idx]
            conn.execute(
                "INSERT INTO trustee_share(election_id,trustee_id,share_x,share_y_hex) VALUES(?,?,?,?)",
                (eid, tid, x, hex(y)),
            )
            conn.execute(
                "INSERT INTO trustee_assignment(election_id,trustee_id) VALUES(?,?)", (eid, tid))

        log_event(conn, "election_created", {"name": name, "threshold": threshold}, eid)
        conn.commit(); conn.close()
        flash(f"Election '{name}' created — key split across {len(tids)} trustees "
              f"({threshold}-of-{len(tids)} required to decrypt).", "success")
        return redirect(url_for("admin_dashboard"))

    conn.close()
    return render_template("admin_new_election.html", trustees=trustees)


@app.route("/admin/elections/<int:eid>")
@login_required
@role_required("admin")
def admin_election_detail(eid):
    conn  = get_db()
    e     = conn.execute("SELECT * FROM election WHERE id=?", (eid,)).fetchone()
    vc    = conn.execute("SELECT COUNT(*) FROM vote WHERE election_id=?", (eid,)).fetchone()[0]
    result = conn.execute("SELECT * FROM election_result WHERE election_id=?", (eid,)).fetchone()
    tids  = [r["trustee_id"] for r in conn.execute(
        "SELECT trustee_id FROM trustee_assignment WHERE election_id=?", (eid,)).fetchall()]
    trustees = conn.execute(
        f"SELECT * FROM user WHERE id IN ({','.join('?'*len(tids))})", tids
    ).fetchall() if tids else []
    shares      = conn.execute("SELECT * FROM trustee_share WHERE election_id=?", (eid,)).fetchall()
    submissions = conn.execute("SELECT * FROM trustee_submission WHERE election_id=?", (eid,)).fetchall()
    submitted_trustee_ids = {s["trustee_id"] for s in submissions}
    conn.close()
    return render_template("admin_election_detail.html",
                           election=e, vote_count=vc, result=result,
                           trustees=trustees, shares=shares,
                           submissions=submissions,
                           submitted_trustee_ids=submitted_trustee_ids)


@app.route("/admin/elections/<int:eid>/open", methods=["POST"])
@login_required
@role_required("admin")
def open_election(eid):
    conn = get_db()
    conn.execute("UPDATE election SET status='ongoing' WHERE id=?", (eid,))
    log_event(conn, "election_opened", {"election_id": eid}, eid)
    conn.commit(); conn.close()
    flash("Election is now open for voting.", "success")
    return redirect(url_for("admin_election_detail", eid=eid))


@app.route("/admin/elections/<int:eid>/close", methods=["POST"])
@login_required
@role_required("admin")
def close_election(eid):
    conn = get_db()
    conn.execute("UPDATE election SET status='counting' WHERE id=?", (eid,))
    log_event(conn, "election_closed", {"election_id": eid}, eid)
    conn.commit(); conn.close()
    flash("Election closed. Trustees must now submit their key shares.", "info")
    return redirect(url_for("admin_election_detail", eid=eid))


@app.route("/admin/tally/<int:eid>", methods=["POST"])
@login_required
@role_required("admin")
def compute_tally(eid):
    conn = get_db()
    e    = conn.execute("SELECT * FROM election WHERE id=?", (eid,)).fetchone()

    if e["status"] != "counting":
        conn.close(); flash("Close the election first.", "warning")
        return redirect(url_for("admin_election_detail", eid=eid))

    submissions = conn.execute(
        "SELECT * FROM trustee_submission WHERE election_id=?", (eid,)).fetchall()

    if len(submissions) < e["threshold"]:
        conn.close()
        flash(f"Need {e['threshold']} trustee submissions — only {len(submissions)} so far.", "danger")
        return redirect(url_for("admin_election_detail", eid=eid))

    votes = conn.execute("SELECT * FROM vote WHERE election_id=?", (eid,)).fetchall()
    if not votes:
        conn.close(); flash("No votes to tally.", "warning")
        return redirect(url_for("admin_election_detail", eid=eid))

    prime  = int(e["shamir_prime_hex"], 16)
    shares = [(s["share_x"], int(s["share_y_hex"], 16)) for s in submissions[:e["threshold"]]]

    try:
        lam = reconstruct_secret(shares, prime)
        pk  = pk_from_dict(json.loads(e["public_key_json"]))
        mu  = mod_inv(lam, pk["n"])
        sk  = {"lam": lam, "mu": mu}
    except Exception as ex:
        conn.close(); flash(f"Key reconstruction failed: {ex}", "danger")
        return redirect(url_for("admin_election_detail", eid=eid))

    candidates = conn.execute(
        "SELECT * FROM candidate WHERE election_id=? ORDER BY position", (eid,)).fetchall()
    tally  = {str(c["id"]): 0 for c in candidates}
    errors = 0
    for v in votes:
        try:
            mi = decrypt(pk, sk, int(v["ciphertext"], 16))
            matched = False
            for c in candidates:
                if mi == c["position"]:
                    tally[str(c["id"])] += 1; matched = True; break
            if not matched: errors += 1
        except Exception:
            errors += 1

    th = hashlib.sha256(json.dumps(tally, sort_keys=True).encode()).hexdigest()
    conn.execute(
        "INSERT OR REPLACE INTO election_result(election_id,tally_json,tally_hash) VALUES(?,?,?)",
        (eid, json.dumps(tally), th),
    )
    conn.execute("UPDATE election SET status='completed' WHERE id=?", (eid,))
    log_event(conn, "tally_computed", {"election_id": eid, "tally_hash": th, "errors": errors}, eid)
    conn.commit(); conn.close()
    flash("Tally computed! Results are now public." + (f" ({errors} unreadable votes)" if errors else ""), "success")
    return redirect(url_for("results_detail", eid=eid))


# ══════════════════════════════════════════════════════════════════════════════
# TRUSTEE
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/trustee")
@login_required
@role_required("trustee")
def trustee_dashboard():
    u    = current_user()
    conn = get_db()
    eids = [r["election_id"] for r in conn.execute(
        "SELECT election_id FROM trustee_assignment WHERE trustee_id=?", (u["id"],)).fetchall()]
    elections = conn.execute(
        f"SELECT * FROM election WHERE id IN ({','.join('?'*len(eids))})", eids
    ).fetchall() if eids else []
    submitted_eids = {r["election_id"] for r in conn.execute(
        "SELECT election_id FROM trustee_submission WHERE trustee_id=?", (u["id"],)).fetchall()}
    conn.close()
    return render_template("trustee_dashboard.html", elections=elections, submitted_eids=submitted_eids)


@app.route("/trustee/share/<int:eid>")
@login_required
@role_required("trustee")
def trustee_share(eid):
    u    = current_user()
    conn = get_db()
    share = conn.execute(
        "SELECT * FROM trustee_share WHERE election_id=? AND trustee_id=?", (eid, u["id"])).fetchone()
    if not share: conn.close(); abort(404)
    conn.execute("UPDATE trustee_share SET acknowledged=1 WHERE id=?", (share["id"],))
    conn.commit()
    e = conn.execute("SELECT * FROM election WHERE id=?", (eid,)).fetchone()
    conn.close()
    return render_template("trustee_share.html", election=e, share=share)


@app.route("/trustee/submit/<int:eid>", methods=["GET", "POST"])
@login_required
@role_required("trustee")
def trustee_submit(eid):
    u    = current_user()
    conn = get_db()
    e    = conn.execute("SELECT * FROM election WHERE id=?", (eid,)).fetchone()
    if not e: conn.close(); abort(404)
    if e["status"] not in ("counting", "completed"):
        conn.close(); flash("Election must be closed before you can submit.", "warning")
        return redirect(url_for("trustee_dashboard"))
    share = conn.execute(
        "SELECT * FROM trustee_share WHERE election_id=? AND trustee_id=?", (eid, u["id"])).fetchone()
    if not share: conn.close(); abort(404)
    already = conn.execute(
        "SELECT * FROM trustee_submission WHERE election_id=? AND trustee_id=?", (eid, u["id"])).fetchone()
    total_submitted = conn.execute(
        "SELECT COUNT(*) FROM trustee_submission WHERE election_id=?", (eid,)).fetchone()[0]

    if request.method == "POST" and not already:
        conn.execute(
            "INSERT OR IGNORE INTO trustee_submission(election_id,trustee_id,share_x,share_y_hex) VALUES(?,?,?,?)",
            (eid, u["id"], share["share_x"], share["share_y_hex"]),
        )
        log_event(conn, "trustee_share_submitted",
                  {"trustee_id": u["id"], "election_id": eid, "share_x": share["share_x"]}, eid)
        conn.commit()
        total_submitted += 1
        flash(f"Share submitted! ({total_submitted}/{e['threshold']} required)", "success")
        conn.close()
        return redirect(url_for("trustee_dashboard"))

    conn.close()
    return render_template("trustee_submit.html",
                           election=e, share=share, already=already,
                           total_submitted=total_submitted)


@app.route("/profile")
@login_required
def profile():
    u    = current_user()
    conn = get_db()
    votes = conn.execute(
        "SELECT * FROM vote WHERE voter_id=? ORDER BY timestamp DESC", (u["id"],)).fetchall()
    elections = {v["election_id"]: conn.execute(
        "SELECT * FROM election WHERE id=?", (v["election_id"],)).fetchone() for v in votes}
    conn.close()
    return render_template("profile.html", user=u, votes=votes, elections=elections)


# ── Error handlers ────────────────────────────────────────────────────────────
@app.errorhandler(403)
def forbidden(e):  return render_template("error.html", code=403, msg="Access denied."), 403

@app.errorhandler(404)
def not_found(e):  return render_template("error.html", code=404, msg="Page not found."), 404
