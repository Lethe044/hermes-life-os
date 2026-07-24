# Contributing to Hermes Life OS

Thanks for considering a contribution! This project has a fairly heavy
test suite (136+ tests) and a strict "every code path has a test"
culture - that's intentional, and PRs are expected to follow it.

## Setup

```bash
git clone https://github.com/Lethe044/hermes-life-os.git
cd hermes-life-os
pip install -e ".[all,dev]"
```

This installs the package in editable mode with every optional
dependency (Anthropic, matplotlib) plus pytest, and gives you the
`hermes-life-os` / `hermes-life-os-dashboard` / `hermes-life-os-scheduler`
CLI commands pointed at your local checkout.

## Running the test suite

```bash
python -m pytest tests/ -v
```

All 136+ tests should pass before and after your change. If you add a
feature or fix a bug, add a test for it in the matching `tests/test_*.py`
file - PRs that add behavior without test coverage will be asked to add
it before merge.

Tests must not require a live LLM API key, a running Ollama server, or
any real network access. Mock the provider/client layer (see
`tests/test_llm_providers.py` for the pattern) rather than skipping
coverage for code that talks to an LLM.

## Code style

- Match the existing style in the file you're editing rather than
  introducing a new one.
- Keep functions focused - `demo/` is already split into focused modules
  (`storage.py`, `patterns.py`, `analytics.py`, `tools.py`,
  `notifications.py`, `scheduler.py`, `llm_providers.py`); new
  functionality should generally extend one of these or add a new
  module rather than growing `demo_life_os.py` further.
- No hard dependency on any single LLM provider - anything that calls an
  LLM should go through `llm_providers.get_client()`, not a
  provider-specific SDK call.

## Pull requests

1. Fork the repo and create a branch from `main`.
2. Make your change, with tests.
3. Run `python -m pytest tests/ -v` locally and confirm everything passes.
4. Open a PR describing what changed and why. Link any related issue.
5. CI (GitHub Actions) will run the same test suite automatically - it
   must be green before merge.

## Reporting bugs / requesting features

Please use the issue templates (Bug report / Feature request) rather
than a blank issue - they ask for the details that are almost always
needed to act on a report (steps to reproduce, provider/OS, logs).

## Questions

Open an issue - "question" is a fine reason to open one, it doesn't have
to be a bug or feature request.
