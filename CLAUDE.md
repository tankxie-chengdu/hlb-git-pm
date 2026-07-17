# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A scheduled Git commit reporting daemon. It scans Git repositories (local paths or GitHub org via GitHub App), collects daily commits, optionally analyzes them with an LLM, renders a markdown/HTML report, and sends it via email. No web server, no database — purely a batch processor.

## Commands

**Run tests:**
```bash
python -m pytest
# or
python -m unittest discover
```

**Run a single test file:**
```bash
python -m pytest tests/test_config.py
```

**One-shot execution (dry run, no email sent):**
```bash
python -m app --config config.toml --once --dry-run
```

**One-shot for a specific date:**
```bash
python -m app --config config.toml --once --date 2025-01-15
```

**Continuous scheduler mode:**
```bash
python -m app --config config.toml
```

**Docker:**
```bash
docker build -t git-daily-report .
docker run -d --name git-daily-report --restart unless-stopped \
  -v "$PWD/config.toml:/app/config.toml:ro" \
  -v "$PWD/.data:/app/.data" \
  --env-file .env git-daily-report
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

## Architecture

The processing pipeline in `app/main.py`:
1. `run_once()` — orchestrates the full flow for a single date
2. Discover repos (static config + GitHub App auto-discovery via `app/github_app.py`)
3. Clone/fetch and scan each repo for commits in the date range (`app/git_service.py`)
4. Optionally call an OpenAI-compatible LLM for analysis (`app/ai.py`)
5. Render markdown + HTML (`app/report.py`)
6. Send email via SMTP (`app/emailer.py`)

`run_scheduler()` in `app/main.py` loops forever, calculating the next run time using `zoneinfo` + the configured `run_at` time.

**Key design choices:**
- Config is loaded into frozen dataclasses (`app/config.py`); env vars are injected via `${VAR_NAME}` syntax at load time.
- Git operations never raise — they return error strings embedded in `RepositoryReport`, so one failing repo doesn't block the email.
- AI analysis degrades gracefully: if disabled or the API call fails, a rule-based fallback summary is used instead.
- GitHub App auth uses short-lived JWT → installation token flow (`app/github_app.py`). Git clone auth uses a temporary `GIT_ASKPASS` shell script.

**Data flow through models (`app/models.py`):**
- `Commit` — one commit (repo, SHA, author, timestamp, subject, diff stats)
- `RepositoryReport` — all commits for one repo on a given day, plus optional error string
- `DailyReport` — aggregates all `RepositoryReport`s, holds AI analysis text, exposes computed totals

## Configuration

Copy `config.example.toml` to `config.toml` (gitignored). Key sections:
- Root: `timezone`, `run_at`, `workspace` (where repos are cloned), `subject_prefix`
- `[[repositories]]`: static repo list; each entry has `name`, `branch`, and either `path` (local) or `url` (clone)
- `[github]`: GitHub App credentials for org-wide repo discovery
- `[email]`: SMTP settings; `recipients` is a list
- `[ai]`: LLM settings; `base_url` + `api_key` + `model`; set `enabled = false` to skip

Sensitive values should use `${ENV_VAR}` placeholders and be supplied via environment or `.env` file.
