# CLAUDE.md

This file provides guidance for working with the HLB Git PM repository.

## Project overview

HLB Git PM is a FastAPI + Vue application that discovers private GitHub repositories through a GitHub App, maintains local Git mirrors, calculates commit and contributor metrics, optionally calls an OpenAI-compatible AI service, renders Markdown/HTML reports, and sends them by SMTP. The web UI and APScheduler run from the same `run.py` process.

## Commands

```bash
# Backend tests
python3 -m pytest

# Frontend build
cd frontend && npm ci && npm run build

# Local server and scheduler
python3 run.py --config config.toml --verbose

# Docker image (choose the target server architecture)
docker buildx build --platform linux/amd64 -t hlb-git-pm:latest --load .
```

`config.toml`, `secrets/`, and `.data/` are local deployment state and must not be committed or copied into an image. Use `config.example.toml` as the template and inject API/SMTP credentials through environment variables.

## Architecture

- `app/main.py`: report orchestration, scanning, AI analysis, rendering, and email delivery.
- `app/git_service.py`: Git mirror clone/fetch and batched `git log --numstat` parsing.
- `app/github_app.py`: GitHub App JWT, installation token, and repository discovery.
- `app/ai.py`: OpenAI-compatible requests, structured parsing, fallbacks, and yearly project-batch analysis.
- `app/report.py`: Markdown and HTML report templates.
- `web/app.py`: FastAPI application, API routers, database initialization, and frontend SPA serving.
- `web/api/`: authenticated API endpoints for repositories, reports, members, recipients, schedules, and settings.
- `scheduler/engine.py`: database-backed APScheduler jobs. Run only one scheduler replica.
- `frontend/src/`: Vue 3 + Element Plus frontend; production assets are built into `frontend/dist`.
- `tests/`: backend unit and integration tests.

## Data and deployment

The default SQLite database, Git mirrors, report files, and snapshots live under `.data/`. Persist this directory when running Docker. A single container is the supported deployment shape because the scheduler and SQLite state are local to the process and volume.

Mount these files/directories into a container:

```text
/app/config.toml       read-only configuration
/app/secrets/          read-only GitHub App private key
/app/.data/            read-write database, mirrors, and reports
```

Put the container behind HTTPS and do not expose the internal port directly to the public Internet. Set `JWT_SECRET_KEY` and replace the seeded development admin password before production use.

## Configuration

- Root settings: `timezone`, `run_at`, `workspace`, `db_path`.
- `[github]`: organization, App ID, installation ID, and private key path.
- `[ai]`: OpenAI-compatible `base_url`, API key, model, timeout, commit sample size, and yearly batch size.
- `[email]`: SMTP host, port, TLS/SSL mode, sender, and recipients.
- `${ENV_VAR}` placeholders are expanded while loading TOML.

## Engineering notes

- Empty `branch` means all refs (`git log --all`).
- GitHub App tokens use HTTPS authentication; a local mirror is reused when available.
- AI failures degrade to a rule-based summary and are recorded as a warning in the report workflow.
- Yearly reports call AI once per project batch and then once for the global synthesis.
- Keep historical investigation notes under `docs/archive/` and one-off scripts under `tools/archive/`; do not add dated process reports to the repository root.
