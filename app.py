"""
Check'd — AI-vetted product discovery.
Only real products, verified by AI before they go live.
Port 5567
"""

import os, json, sqlite3, uuid, re, urllib.request
from datetime import datetime
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
                category       TEXT NOT NULL,
                maker_name     TEXT NOT NULL,
                maker_email    TEXT NOT NULL,
                screenshot     TEXT,
                status         TEXT DEFAULT 'pending',
                verdict_reason TEXT,
                views          INTEGER DEFAULT 0,
                uses           INTEGER DEFAULT 0,
                submitted_at   TEXT NOT NULL,
                approved_at    TEXT
            )
        """)
        conn.commit()

init_db()

# ── URL reachability check ────────────────────────────────────────────────────

def url_is_live(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Checkd-Bot/1.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status < 400
    except Exception:
        return False

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
        products = conn.execute(
            "SELECT * FROM products WHERE status='approved' ORDER BY approved_at DESC"
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM products WHERE status='approved'"
        ).fetchone()[0]
    return render_template("index.html", products=products, total=total)


@app.route("/api/submit", methods=["POST"])
def api_submit():
    # Handle multipart (screenshot) or JSON
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

    # Save screenshot if provided
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

    # 1. Check URL is live
    url_live = url_is_live(data["url"].strip())

    # 2. AI validation (includes url_live signal)
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
            (id, name, tagline, description, url, category, maker_name, maker_email,
             screenshot, status, verdict_reason, submitted_at, approved_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            product_id,
            data["name"].strip(),
            data["tagline"].strip(),
            data["description"].strip(),
            data["url"].strip(),
            data["category"].strip(),
            data["maker_name"].strip(),
            data["maker_email"].strip(),
            screenshot_path,
            status,
            reason,
            now,
            now if approved else None
        ))
        conn.commit()

    return jsonify({
        "approved": approved,
        "reason": reason,
        "id": product_id if approved else None
    })


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
