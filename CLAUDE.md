# Check'd — CLAUDE.md

## What This Is
AI-vetted product discovery platform. Rival to Product Hunt.
Every submission validated by Claude before going live.
No voting. No pay-to-play. Views + uses are the only metrics.

## Re-Entry
"Re-entry: checkd"

## Port
5567 (local) / Railway PORT (deployed)

## Stack
- Flask + SQLite
- Anthropic API (Claude) for validation
- Subdomain: checkd.creativekonsoles.com

## How Validation Works
On submit → POST /api/submit → validate_with_ai() → Claude checks:
- Is it a real, working product?
- Does it have a genuine use case?
- Is it original (not a vaporware clone)?
- Approved → status='approved', goes live instantly
- Rejected → status='rejected', maker told why

## Key Files
- app.py — Flask routes, AI validation, SQLite
- templates/index.html — Full UI (hero, product grid, submit modal, verdict screen)
- data/checkd.db — SQLite (gitignored)

## Status
Built 2026-04-17. Ready to deploy to Railway.

## Next Steps
- [ ] Deploy to Railway
- [ ] Set ANTHROPIC_API_KEY on Railway
- [ ] Add checkd.creativekonsoles.com subdomain
- [ ] Submit 5i and other CK products as seed listings
- [ ] Post on Reddit (r/SideProject, r/Entrepreneur) + Product Hunt comments
