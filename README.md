<p align="center">
  <img src="static/logo.png" width="120" alt="Check'd logo"/>
</p>

# Check'd — AI-Vetted Product Discovery

> **Every listing verified. No noise.**

A product discovery platform where nothing goes live without Claude reviewing it first. Submit a product, get a verdict — real or reject — before it ever appears in the feed.

---

## What It Does

- **AI vetting** — every product submission runs through Claude before publishing
- **Structured verification** — name, URL, description, category, and image all validated
- **Reject filter** — duplicates, spam, affiliate traps, and vague listings don't make it through
- **Clean feed** — only Claude-approved products appear on the discovery page
- **Rate limiting** — 5 submissions per IP per hour, 10 per email per day

---

## How Verification Works

```
User submits product (name, URL, description, image, email)
  ↓ Claude reads the submission
  ↓ Validates: Is this a real product? Is the URL reachable? Is the description accurate?
  ↓ Verdict: APPROVE (published) or REJECT (with reason)
  ↓ Product appears in feed (or doesn't)
```

---

## Stack

Python · Flask · SQLite · Anthropic Claude · Vanilla JS · Railway

---

## Setup

```bash
git clone https://github.com/papjamzzz/checkd.git
cd checkd
cp .env.example .env
# Add ANTHROPIC_API_KEY to .env
python app.py
```

---

## Part of Creative Konsoles

Built by [Creative Konsoles](https://creativekonsoles.com) — tools built using thought.

**[creativekonsoles.com](https://creativekonsoles.com)** &nbsp;·&nbsp; support@creativekonsoles.com

<!-- repo maintenance: 2026-05-12 -->
