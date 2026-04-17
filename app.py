"""
Check'd — AI-vetted product discovery.
Only real products, verified by AI before they go live.
Port 5567
"""

import os, json, sqlite3, uuid, re
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import anthropic

load_dotenv()

app = Flask(__name__)
DB = os.path.join(os.path.dirname(__file__), "data", "checkd.db")

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
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                tagline     TEXT NOT NULL,
                description TEXT NOT NULL,
                url         TEXT NOT NULL,
                category    TEXT NOT NULL,
                maker_name  TEXT NOT NULL,
                maker_email TEXT NOT NULL,
                status      TEXT DEFAULT 'pending',
                verdict     TEXT,
                verdict_reason TEXT,
                views       INTEGER DEFAULT 0,
                uses        INTEGER DEFAULT 0,
                submitted_at TEXT NOT NULL,
                approved_at  TEXT
            )
        """)
        conn.commit()

init_db()

# ── AI Validation ─────────────────────────────────────────────────────────────

VALIDATION_PROMPT = """You are the gatekeeper for Check'd — a product discovery platform that only lists real, working software products.

Evaluate this product submission:

Name: {name}
Tagline: {tagline}
Description: {description}
URL: {url}
Category: {category}

Your job: determine if this is a REAL, WORKING software product worth listing.

Approve if:
- It is a real working tool/app/software (not vaporware, not a landing page for something not built yet)
- It has a clear, genuine use case for real people
- It is not a blatant clone of something already famous with no differentiation
- It is not spam, adult content, or illegal

Reject if:
- It's a "coming soon" page or waitlist with no working product
- It's so vague it's impossible to tell what it does
- It's clearly AI-generated filler with no substance
- It's a duplicate submission

Respond in this exact JSON format:
{{
  "approved": true or false,
  "reason": "one sentence explaining why"
}}

Be fair but firm. Real builders deserve a real platform."""


def validate_with_ai(product):
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    prompt = VALIDATION_PROMPT.format(
        name=product["name"],
        tagline=product["tagline"],
        description=product["description"],
        url=product["url"],
        category=product["category"]
    )
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}]
    )
    text = msg.content[0].text.strip()
    # Extract JSON
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
        total = conn.execute("SELECT COUNT(*) FROM products WHERE status='approved'").fetchone()[0]
    return render_template("index.html", products=products, total=total)


@app.route("/submit", methods=["GET"])
def submit_page():
    return render_template("index.html", view="submit")


@app.route("/api/submit", methods=["POST"])
def api_submit():
    data = request.json
    required = ["name", "tagline", "description", "url", "category", "maker_name", "maker_email"]
    for field in required:
        if not data.get(field, "").strip():
            return jsonify({"error": f"Missing field: {field}"}), 400

    product_id = str(uuid.uuid4())[:8]

    # Run AI validation
    try:
        verdict = validate_with_ai(data)
    except Exception as e:
        return jsonify({"error": f"Validation error: {str(e)}"}), 500

    approved = verdict.get("approved", False)
    reason   = verdict.get("reason", "")
    status   = "approved" if approved else "rejected"
    now      = datetime.utcnow().isoformat()

    with get_db() as conn:
        conn.execute("""
            INSERT INTO products
            (id, name, tagline, description, url, category, maker_name, maker_email,
             status, verdict, verdict_reason, submitted_at, approved_at)
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
            status,
            "approved" if approved else "rejected",
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


@app.route("/api/view/<product_id>", methods=["POST"])
def track_view(product_id):
    with get_db() as conn:
        conn.execute("UPDATE products SET views = views + 1 WHERE id=?", (product_id,))
        conn.commit()
    return jsonify({"ok": True})


@app.route("/api/use/<product_id>", methods=["POST"])
def track_use(product_id):
    with get_db() as conn:
        conn.execute("UPDATE products SET uses = uses + 1 WHERE id=?", (product_id,))
        row = conn.execute("SELECT url FROM products WHERE id=?", (product_id,)).fetchone()
        conn.commit()
    url = row["url"] if row else "#"
    return jsonify({"url": url})


@app.route("/api/products")
def api_products():
    category = request.args.get("category", "")
    query = "SELECT * FROM products WHERE status='approved'"
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
