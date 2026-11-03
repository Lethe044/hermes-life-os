# Security Policy

Hermes Life OS keeps personal data (mood, sleep, meals, money, notes), so reports about
data exposure are taken seriously.

## Supported versions

Only the latest release on PyPI receives fixes. Please update before reporting.

## Reporting a vulnerability

Use GitHub's private reporting: open the **Security** tab of the repository and choose
**Report a vulnerability**. Please do not open a public issue for security problems.

Helpful details: the version (`pip show hermes-life-os`), what you did, what you expected and what
happened. Reports are acknowledged within a few days and fixed as quickly as the severity requires.

## What is in scope

- Reading or writing another profile's or user's data (multi-profile and multi-user modes)
- Weaknesses in encryption at rest (`crypto_store.py`) or in key handling
- The local REST API and the Slack, Telegram, Discord and WhatsApp bots accepting requests they should reject
- Path traversal in backup, restore, export or plugin loading

## Design notes

- Data lives in plain JSON files under `~/.hermes/life-os/` unless encryption at rest is turned on.
- The core runs locally. Network calls only happen for the LLM provider you configure and for the
  integrations you switch on yourself.
- The local REST API binds to `127.0.0.1` by default and needs a token.
