"""
Check'd — AI-vetted product discovery.
Only real products, verified by AI before they go live.
Port 5567
"""

import os, json, sqlite3, uuid, re, urllib.request
from datetime import datetime, timedelta
from urllib.parse import urlparse
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import anthropic

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'), override=True)

app = Flask(__name__)
DB      = os.path.join(os.path.dirname(__file__), "data", "checkd.db")
UPLOADS = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOADS, exist_ok=True)

ALLOWED_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
MAX_UPLOAD  = 5 * 1024 * 1024  # 5 MB

# ── Rate limits ───────────────────────────────────────────────────────────────
IP_LIMIT_PER_HOUR   = 5
EMAIL_LIMIT_PER_DAY = 10

# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id             TEXT PRIMARY KEY,
                name           TEXT NOT NULL,
                tagline        TEXT NOT NULL,
                description    TEXT NOT NULL,
                url            TEXT NOT NULL,
                domain         TEXT NOT NULL,
                category       TEXT NOT NULL,
                maker_name     TEXT NOT NULL,
                maker_email    TEXT NOT NULL,
                ip_address     TEXT,
                screenshot     TEXT,
                status         TEXT DEFAULT 'pending',
                verdict_reason TEXT,
                views          INTEGER DEFAULT 0,
                uses           INTEGER DEFAULT 0,
                submitted_at   TEXT NOT NULL,
                approved_at    TEXT
            )
        """)
        # Migrate older DBs that may be missing columns
        existing = [r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()]
        for col, defn in [
            ("domain",     "TEXT NOT NULL DEFAULT ''"),
            ("ip_address", "TEXT"),
            ("screenshot", "TEXT"),
        ]:
            if col not in existing:
                conn.execute(f"ALTER TABLE products ADD COLUMN {col} {defn}")
        conn.commit()

init_db()

# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_domain(url):
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        return host.lstrip("www.")
    except Exception:
        return url.lower()

def url_is_live(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Checkd-Bot/1.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status < 400
    except Exception:
        return False

def check_rate_limits(ip, email):
    """Returns (ok, reason) tuple."""
    with get_db() as conn:
        hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        day_ago  = (datetime.utcnow() - timedelta(hours=24)).isoformat()

        ip_count = conn.execute(
            "SELECT COUNT(*) FROM products WHERE ip_address=? AND submitted_at>?",
            (ip, hour_ago)
        ).fetchone()[0]
        if ip_count >= IP_LIMIT_PER_HOUR:
            return False, "Too many submissions from your network. Try again in an hour."

        email_count = conn.execute(
            "SELECT COUNT(*) FROM products WHERE maker_email=? AND submitted_at>?",
            (email.lower(), day_ago)
        ).fetchone()[0]
        if email_count >= EMAIL_LIMIT_PER_DAY:
            return False, "Too many submissions from this email today. Come back tomorrow."

    return True, ""

def check_duplicate(domain, url):
    """Returns (is_dupe, reason)."""
    with get_db() as conn:
        # Exact URL match
        row = conn.execute(
            "SELECT status FROM products WHERE url=?", (url,)
        ).fetchone()
        if row:
            if row["status"] == "approved":
                return True, "This product is already listed on Check'd."
            elif row["status"] == "pending":
                return True, "This product is already under review."
            else:
                return True, "This product was already submitted and didn't pass validation. Fix it substantially before resubmitting."

        # Same domain already approved
        row = conn.execute(
            "SELECT name FROM products WHERE domain=? AND status='approved'", (domain,)
        ).fetchone()
        if row:
            return True, f"A product from this domain is already listed ({row['name']}). One listing per product."

    return False, ""

# ── AI Validation ─────────────────────────────────────────────────────────────

VALIDATION_PROMPT = """You are the gatekeeper for Check'd — a product discovery platform that only lists real, working software products.

Evaluate this product submission:

Name: {name}
Tagline: {tagline}
Description: {description}
URL: {url}
Category: {category}
URL reachable: {url_live}

Your job: determine if this is a REAL, WORKING software product worth listing publicly.

Approve if:
- It is a real working tool/app/software (not vaporware, not a landing page for something not built yet)
- It has a clear, genuine use case for real people
- It is not a blatant clone of something famous with zero differentiation
- It is not spam, adult content, or illegal

Reject if:
- The URL is unreachable and description is vague
- It's a "coming soon" page or waitlist with no working product
- It's so vague it's impossible to tell what it does
- It's clearly AI-generated filler with no substance

Respond ONLY in this exact JSON format:
{{
  "approved": true or false,
  "reason": "one clear sentence explaining why"
}}

Be fair but firm. Real builders deserve a real platform."""


def validate_with_ai(product, url_live):
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    prompt = VALIDATION_PROMPT.format(
        name=product["name"],
        tagline=product["tagline"],
        description=product["description"],
        url=product["url"],
        category=product["category"],
        url_live="YES — site responded" if url_live else "NO — could not reach URL"
    )
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}]
    )
    text = msg.content[0].text.strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {"approved": False, "reason": "Could not parse AI response."}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM products WHERE status='approved'"
        ).fetchone()[0]
    return render_template("index.html", total=total)


@app.route("/products")
def products_page():
    category = request.args.get("category", "")
    query  = "SELECT * FROM products WHERE status='approved'"
    params = []
    if category:
        query += " AND category=?"
        params.append(category)
    query += " ORDER BY approved_at DESC"
    with get_db() as conn:
        products = conn.execute(query, params).fetchall()
        total    = conn.execute("SELECT COUNT(*) FROM products WHERE status='approved'").fetchone()[0]
    return render_template("products.html", products=products, total=total, active_category=category)


@app.route("/api/submit", methods=["POST"])
def api_submit():
    if request.content_type and 'multipart' in request.content_type:
        data = request.form.to_dict()
        screenshot_file = request.files.get('screenshot')
    else:
        data = request.json or {}
        screenshot_file = None

    required = ["name", "tagline", "description", "url", "category", "maker_name", "maker_email"]
    for field in required:
        if not data.get(field, "").strip():
            return jsonify({"error": f"Missing: {field}"}), 400

    url    = data["url"].strip()
    domain = extract_domain(url)
    ip     = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    email  = data["maker_email"].strip().lower()

    # 1. Rate limit check
    ok, reason = check_rate_limits(ip, email)
    if not ok:
        return jsonify({"error": reason, "rate_limited": True}), 429

    # 2. Duplicate check
    is_dupe, reason = check_duplicate(domain, url)
    if is_dupe:
        return jsonify({"error": reason, "duplicate": True}), 409

    # 3. Save screenshot
    screenshot_path = None
    if screenshot_file and screenshot_file.filename:
        ext = os.path.splitext(screenshot_file.filename)[1].lower()
        if ext not in ALLOWED_EXT:
            return jsonify({"error": "Screenshot must be PNG, JPG, GIF, or WebP"}), 400
        screenshot_file.seek(0, 2)
        size = screenshot_file.tell()
        screenshot_file.seek(0)
        if size > MAX_UPLOAD:
            return jsonify({"error": "Screenshot must be under 5MB"}), 400
        fname = str(uuid.uuid4())[:8] + ext
        screenshot_file.save(os.path.join(UPLOADS, fname))
        screenshot_path = f"/static/uploads/{fname}"

    product_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()

    # 4. URL live check
    url_live = url_is_live(url)

    # 5. AI validation
    try:
        verdict = validate_with_ai(data, url_live)
    except Exception as e:
        return jsonify({"error": f"Validation error: {str(e)}"}), 500

    approved = verdict.get("approved", False)
    reason   = verdict.get("reason", "")
    status   = "approved" if approved else "rejected"

    with get_db() as conn:
        conn.execute("""
            INSERT INTO products
            (id, name, tagline, description, url, domain, category, maker_name, maker_email,
             ip_address, screenshot, status, verdict_reason, submitted_at, approved_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            product_id,
            data["name"].strip(),
            data["tagline"].strip(),
            data["description"].strip(),
            url, domain,
            data["category"].strip(),
            data["maker_name"].strip(),
            email,
            ip,
            screenshot_path,
            status, reason,
            now,
            now if approved else None
        ))
        conn.commit()

    return jsonify({
        "approved": approved,
        "reason": reason,
        "id": product_id if approved else None
    })


@app.route("/guide")
def guide():
    return render_template("guide.html")

@app.route("/support")
def support():
    return render_template("support.html")

@app.route("/api/use/<product_id>", methods=["POST"])
def track_use(product_id):
    with get_db() as conn:
        conn.execute("UPDATE products SET uses = uses + 1 WHERE id=?", (product_id,))
        row = conn.execute("SELECT url FROM products WHERE id=?", (product_id,)).fetchone()
        conn.commit()
    return jsonify({"url": row["url"] if row else "#"})


@app.route("/api/products")
def api_products():
    category = request.args.get("category", "")
    query  = "SELECT * FROM products WHERE status='approved'"
    params = []
    if category:
        query += " AND category=?"
        params.append(category)
    query += " ORDER BY approved_at DESC"
    with get_db() as conn:
        products = [dict(r) for r in conn.execute(query, params).fetchall()]
    return jsonify(products)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5567))
    app.run(host="0.0.0.0", port=port, debug=False)
