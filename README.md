# Check'd — AI-Vetted Product Discovery

**Every listing verified by Claude before it goes live. Signal over noise.**

Check'd is a curated product discovery platform where AI acts as the quality gate. No junk, no spam, no affiliate-stuffed roundups. Every product that appears has been reviewed by Claude against a set of criteria before it's published.

---

## How It Works

1. **Submit** — anyone can submit a product via the submission form
2. **AI review** — Claude evaluates the product against quality criteria: legitimacy, usefulness, clarity, no spam signals
3. **Publish or reject** — approved products go live; rejected ones get a reason
4. **Discover** — clean, searchable directory of products that passed the bar

## Stack

```
Python · Flask · Claude (Anthropic) · SQLite · Vanilla JS
Railway
```

## Run Locally

```bash
pip install -r requirements.txt
cp .env.example .env  # add ANTHROPIC_API_KEY
python app.py
```

---

*A Creative Konsoles project.*
