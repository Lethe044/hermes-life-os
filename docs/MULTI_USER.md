# Multi-user Hermes

Hermes already isolates data per *profile* (`storage.set_active_profile`).
Multi-user support builds on top of that: a registry (`demo/users.py`)
that maps a **person** to their own profile via their own personal API
key, so a household or small team can share one running instance (the
local REST API, and the Slack bot) without a shared secret or separate
processes per person.

## When you need this vs. plain profiles

- **Just you, switching contexts** (work self vs. personal, or testing):
  `--profile work` / `LIFE_OS_PROFILE=work` is all you need - no
  registry required.
- **Multiple people, one shared server/bot**: use the user registry
  below so each person authenticates as themselves and never sees
  anyone else's data, even by accident.

## Setting up users

```bash
python demo/users.py add alex --profile alex --role owner
# Created user 'alex' (profile: alex, role: owner)
# API key (save this now - it will not be shown again):
#   hlo_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

python demo/users.py add sam --profile sam
python demo/users.py list
python demo/users.py rotate alex     # issues a new key, invalidates the old one
python demo/users.py remove sam
```

Each user's API key is stored only as a salted PBKDF2 hash in
`~/.hermes/life-os/users.json` - the plaintext key is shown exactly once,
at creation/rotation time, exactly like a GitHub personal access token.

## Local REST API

```bash
pip install "hermes-life-os[api]"
hermes-life-os-api
```

`LIFE_OS_API_KEY` is no longer strictly required - the server starts as
long as *either* it's set *or* at least one user is registered. Each
request is authenticated independently against whichever key it sends,
and automatically operates on that key's own profile:

```bash
curl -H "X-API-Key: <alex's key>" http://127.0.0.1:8765/api/health
# {"status": "ok", "profile": "alex", "user": "alex"}

curl -H "X-API-Key: <sam's key>" http://127.0.0.1:8765/api/health
# {"status": "ok", "profile": "sam", "user": "sam"}
```

A legacy single `LIFE_OS_API_KEY` (if set) keeps working exactly as
before, mapped to `--profile`/`LIFE_OS_PROFILE` - the two mechanisms can
run side by side, so migrating to multi-user is opt-in and non-breaking.

## Slack bot

```bash
pip install "hermes-life-os[slack]"
python demo/users.py link alex slack U0123ABC   # alex's Slack user ID
python demo/users.py link sam   slack U0456DEF
set SLACK_BOT_TOKEN=xoxb-...
set SLACK_APP_TOKEN=xapp-...
python demo/slack_bot.py
```

Every direct message to the bot is resolved to a linked user (via their
Slack user ID) and routed to that user's own profile automatically - see
`demo/slack_bot.py`'s docstring for full setup and how to find a user's
Slack ID. Messages from an unlinked Slack user are politely declined
rather than silently falling back to anyone else's data.

## Security notes

- The registry only controls *routing* (which profile a request lands
  on) - it doesn't add encryption of its own. Combine with
  `LIFE_OS_ENCRYPTION_KEY` (see the main README) if you also want data
  at rest encrypted per profile.
- Roles (`owner` vs `member`) are recorded but not yet enforced anywhere
  in the API - today every authenticated user has full read/write access
  to their *own* profile only, never anyone else's. Role-based
  permissions beyond that (e.g. an owner managing other users' access
  through the API itself, not just the CLI) are tracked as a future
  enhancement - see the Roadmap section of the README.
- `python demo/users.py rotate <user>` immediately invalidates that
  user's old key - use it right away if a key leaks.
