# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Grok2API is a FastAPI gateway that reverse-engineers Grok's web protocol and exposes it as
OpenAI-compatible (`/v1/*`) and Anthropic-compatible (`/v1/messages`) APIs. It manages a pool of
Grok accounts with tier-aware selection, load balancing, quota refresh, proxy/Cloudflare-clearance
handling, and local media caching. Python 3.13+, managed with `uv`.

## Commands

```bash
uv sync                                                                          # install/lock deps
uv run granian --interface asgi --host 0.0.0.0 --port 8000 --workers 1 app.main:app   # run (only way)
uv run ruff check .                                                              # lint
uv run ruff format .                                                             # format
docker compose up -d                                                             # run via Docker
```

- Running `python app/main.py` directly is intentionally disabled — always launch via `granian`.
- There is **no test suite** in this repo. `ruff` is the only configured dev tool. Despite the
  global TDD protocol, there is no test infrastructure to write against here unless you add it.
- Multi-worker: only the worker that wins an advisory file lock (`data/.scheduler.lock`) runs the
  heavy account-refresh scheduler; all workers run the lightweight directory-sync loop.

## Architecture: four layers

Code is split into four layers under `app/`, with a strict dependency direction
(`products → control → dataplane → platform`). Understanding this split is the key to navigating
the repo.

- **`app/products/`** — API surface. Translates external request/response formats. `openai/`
  (chat, responses, images, video), `anthropic/` (messages), `web/` (admin backend, WebUI chat /
  masonry / voice pages). Routers are wired in `app/main.py:create_app`.
- **`app/control/`** — control plane / slow path. Domain logic + persistent state. `account/`
  (repository backends, refresh scheduler, state machine), `model/` (the model registry),
  `proxy/` (egress pool + Cloudflare-clearance lifecycle).
- **`app/dataplane/`** — data plane / hot path. `account/` (`AccountDirectory`, an in-memory
  lock-minimal columnar table), `proxy/` (runtime selection), `reverse/` (the actual Grok protocol:
  planner, executor pipeline, `protocol/xai_*` serializers, `transport/` http/ws/grpc).
- **`app/platform/`** — cross-cutting infra. `config/` (config snapshot + backends), `storage/`
  (media cache), `auth/`, `logging/`, `tokens/` (tiktoken estimation), `runtime/`, `startup/`.

### Account: control vs dataplane split

This is the most important architectural concept. Accounts live in **two places**:

- **Control plane (`control/account/`)** owns the persistent `AccountRepository`
  (backends: `local` SQLite / `redis` / `mysql` / `postgresql`, chosen by `ACCOUNT_STORAGE`) and the
  heavy `AccountRefreshScheduler` that probes upstream quota.
- **Data plane (`dataplane/account/AccountDirectory`)** is an in-memory store optimized for the
  request hot path. It bootstraps a full snapshot at startup, then applies **revision-based
  incremental changesets** via `sync_if_changed()` — no lock held during selection scoring.

Writes go to the repository; the directory converges via the sync loop (adaptive interval: fast
after a change, backing off when idle). Account state transitions (active / failed / rate-limited)
flow through `control/account/state_machine.py` via feedback events.

### Model registry — single source of truth

All supported models are declared in one tuple: `app/control/model/registry.py:MODELS`. Each
`ModelSpec` carries `mode` (fast/auto/expert/heavy/...), `tier` (basic/super/heavy), `capability`
(chat/image/video), and `prefer_best`. **Add a new model here and nowhere else.** Tier gates which
account pool can serve it; `prefer_best=True` models reverse-select the pool (heavy → super → basic).

### Reverse pipeline

The reverse data plane runs a 7-step lifecycle (`dataplane/reverse/executor.py`):
`plan → account → proxy → serialize → execute → classify → feedback`. The planner
(`planner.py`) is a pure transform from `ModelSpec` + request → endpoint/transport/timeout; the
executor wires in account + proxy leases, the `protocol/xai_*` modules serialize the Grok payloads,
and `transport/` carries them over HTTP-SSE / WebSocket / gRPC-web.

### Configuration

Three-layer merge, lowest → highest priority (`platform/config/snapshot.py`):
1. `config.defaults.toml` — shipped defaults (read-only template).
2. Backend user overrides — `${DATA_DIR}/config.toml` or Redis; this is the hot-update target
   edited via the admin `/admin/config` page and applied without restart.
3. `GROK_*` env vars — always win (e.g. `GROK_APP_API_KEY` overrides `app.api_key`).

`.env` holds **startup-only** settings (storage backend DSNs, ports, data/log dirs); runtime
behavior (`features.*`, `proxy.*`, `account.refresh.*`, timeouts) lives in the config backend. The
config snapshot is re-checked cheaply on every request (one `stat()` or Redis `GET`).

### Auth scopes

- `/v1/*` → `app.api_key` (no extra auth if empty).
- `/admin/*` → `app.app_key` (default `grok2api`).
- `/webui/*` → `app.webui_enabled` + `app.webui_key` (disabled by default).

## Conventions

- All upstream/transport errors raise `AppError` subclasses (`platform/errors.py`); the global
  handler in `main.py` serializes them to OpenAI-style JSON. Raise these rather than returning ad-hoc
  error dicts.
- Logging uses `loguru` via `platform/logging/logger.py` with structured `key={}` placeholders —
  match that style (e.g. `logger.info("... pid={}", os.getpid())`).
- Async throughout; the HTTP transport uses `curl_cffi` (browser-impersonating TLS), not `requests`.
- Commit messages: Chinese body/subject, English conventional-commits prefix (`feat:`, `fix:`, ...).
