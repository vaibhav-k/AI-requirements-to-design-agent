# AI Requirements → System Design Agent

An AI-powered requirements engineering agent that transforms natural-
language software requirements into structured requirements and a
high-level system architecture, complete with a rendered SVG diagram.

This repository is three independently deployable services rather than
one monolith - see `backend/orchestrator/README.md`'s "Service
Architecture" section for the full rationale and request-flow diagram.
This file is the whole-repo map; each service's own `README.md` has its
setup/run/test instructions.

## Services

* **`backend/orchestrator/`** - owns all state and every LLM call.
  FastAPI web API, an interactive CLI, Azure Blob/Cosmos persistence,
  Microsoft Agent Framework-backed requirements/design/work-breakdown
  generation, and an external MCP server exposing the whole pipeline
  (requirements → architecture → work breakdown) to outside clients (an
  IDE assistant, another agent). This is the service end users and
  external MCP clients actually talk to.
* **`backend/tools-service/`** - the deterministic, LLM-free logic that
  used to run in-process on the orchestrator (Graphviz-based diagram
  rendering, design validation), plus the work-breakdown CSV
  export/traceability validator, which never had an in-process home to
  begin with - it was built directly here since it's equally LLM-free.
  Plain FastAPI REST, no MCP awareness, no LLM dependency.
* **`backend/mcp-wrapper/`** - a thin internal MCP gateway between the
  orchestrator and tools-service. Translates three MCP tool calls
  (`generate_architecture_diagram_tool`, `validate_system_design_tool`,
  `export_work_breakdown_tool`) into plain REST calls against
  tools-service. Nothing outside this repository talks to it.
* **`frontend/`** - the React + Vite + TypeScript web UI, a fourth
  top-level directory alongside the three `backend/` services above
  (not itself an independently deployable service - it's a browser app
  that talks only to `backend/orchestrator`'s web API). Covers
  requirements → architecture → Task Planning (Work Breakdown Agent)
  end to end: create/refine/accept requirements, refine/approve
  architecture, then generate/refine/export a CSV work breakdown once
  architecture is approved. See `backend/orchestrator/README.md`'s
  "Frontend" section for the full component breakdown, and
  `frontend/README.md` for how to run it.

```text
                     ┌─────────────────────┐
  End user (browser) │      frontend/      │  React web UI - talks only to
  ──────────────────►│                     │  backend/orchestrator's web API
                      └──────────┬──────────┘
                                 │ HTTPS (fetch, bearer token)
                                 ▼
                     ┌─────────────────────┐
  IDE assistant /  ─► │ backend/orchestrator │  owns state + every LLM call
  other MCP client    │                      │
                       └──────────┬───────────┘
                                 │ mcp.client.streamable_http
                                 │ + mcp.ClientSession
                                 ▼
                     ┌─────────────────────┐
                     │ backend/mcp-wrapper  │  MCP gateway, zero business logic
                     └──────────┬───────────┘
                                 │ httpx (plain REST)
                                 ▼
                     ┌─────────────────────┐
                     │ backend/tools-service│  deterministic, zero LLM calls
                     └─────────────────────┘
```

## Local development

All three services are needed for the full requirements-to-diagram flow
to work end to end (the orchestrator alone can still run and serve
`/health`, `/me`, and text-only requirements analysis - diagram
generation, design validation, and work-breakdown CSV export are the
three capabilities that need tools-service/mcp-wrapper up). Each runs as
a plain local process - no
Docker involved - start them in this order, since each depends on the
one before it being reachable:

1. `backend/tools-service/README.md` - start this first; nothing else
   works without it.
2. `backend/mcp-wrapper/README.md` - needs tools-service reachable at
   the URL its `.env` points at (default `http://localhost:8100`).
3. `backend/orchestrator/README.md` - needs the mcp-wrapper's gateway
   reachable at the URL its `.env`'s `DESIGN_TOOLS_MCP_URL` points at
   (default `http://localhost:8200/mcp/design-tools`), plus its own
   Azure OpenAI/Blob/Cosmos configuration.
4. `frontend/README.md` - optional, only needed if you want the web UI
   rather than driving `backend/orchestrator`'s API/CLI directly; needs
   the orchestrator's web API reachable (default `http://localhost:8000`).

## Environment variables

Each service has its own `.env.example` - copy it to `.env` inside that
service's directory, not at the repo root; there is no shared/root-level
`.env`. The two settings that connect the services to each other:

* `backend/orchestrator/.env` → `DESIGN_TOOLS_MCP_URL` - where the
  orchestrator finds the mcp-wrapper gateway.
* `backend/mcp-wrapper/.env` → `DESIGN_TOOLS_WRAPPER_TOOLS_SERVICE_BASE_URL`
  - where the mcp-wrapper finds tools-service.

## Static analysis / IDE setup

**Never run mypy, Pyright/Pylance, pytest, or a SonarQube/SonarLint scan
across the whole repo root in one shot** (`mypy .` from here, a bare
`pytest` from here, or opening this folder as a single VS Code workspace
with Pylance's default "analyze the whole open folder" behavior). Each
service deliberately reuses generic top-level package names -
`backend/orchestrator` imports as `app`, `backend/tools-service` and
`backend/mcp-wrapper` both import as `src`, and **all three name their
test package `tests`** - because each is meant to be treated as its own
independent Python project with its own virtualenv, never merged into
one. Point a whole-repo tool at all of them at once and you get exactly
the collision this section exists to head off:

```text
error: Duplicate module named "app" (also at ".\app\__init__.py")
```

or, from pytest specifically (each service's `tests/` is its own
`__init__.py`-marked package literally named `tests`, so collecting more
than one service's `tests/` in the same run collides the same way):

```text
ModuleNotFoundError: No module named 'tests.test_analyze_requirements_use_case'
```

(the mypy error above is from the still-present, superseded root-level
`app/` colliding with `backend/orchestrator/app/` - see "Migration note"
below; delete that old tree and the identical thing still happens
between `backend/tools-service/src` and `backend/mcp-wrapper/src`,
because they share that generic name by the same design. The pytest
error isn't about a leftover directory at all - it happens between the
three *current, correct* `backend/*/tests/` packages every time, purely
because pytest was invoked from a directory that can see more than one
of them.) None of this means the code has real type, lint, or test
failures - each service is clean under mypy/ruff/pytest run scoped to
just that service's own directory; it's purely a "which project does
this file belong to" ambiguity that only appears when a tool's search
path spans more than one service.

**Fix - always scope the tool to one service directory:**

* CLI: `cd backend/orchestrator && mypy app` (each service's own
  `.venv`/`requirements.txt` already has `mypy`/`ruff` pinned - see that
  service's README for setup). Same for `backend/tools-service` and
  `backend/mcp-wrapper`, using `src` as mypy's target there instead of
  `app`. Never pass more than one service's directory in the same
  invocation.
* pytest: `cd backend/orchestrator && pytest -q`, and likewise `cd
  backend/tools-service && pytest -q` / `cd backend/mcp-wrapper &&
  pytest -q` - always `cd` into the one service first rather than
  running `pytest backend/orchestrator/tests backend/tools-service/tests`
  (or a bare `pytest`/`pytest backend`) from the repo root, even though
  that looks like it should just run "more tests." A `--rootdir` flag
  alone doesn't fix it - the collision is each service's `tests/`
  package sharing the literal name `tests`, not pytest's notion of a
  root directory. If you want a single command that runs all three
  suites, run them as three separate `pytest` invocations in sequence
  (e.g. a small shell loop or three CI steps) rather than one combined
  invocation.
* VS Code / Pylance: open `ai-requirements-to-design-agent.code-workspace`
  (in this directory) instead of opening the repo root as a plain
  folder. It defines the four projects (`orchestrator`, `tools-service`,
  `mcp-wrapper`, `frontend`) as separate top-level workspace folders, so
  Pylance starts one isolated language server per folder - each only
  ever sees its own project, so the collision can't occur. Each backend
  folder also carries its own `.vscode/settings.json` pointing at that
  service's own `.venv`, so the right interpreter (and the right
  installed packages) get picked up automatically per folder too.
* SonarQube/SonarLint: each backend service has its own
  `sonar-project.properties` for the same reason - run `sonar-scanner`
  from inside that service's directory, or bind SonarLint to each folder
  separately in connected mode, rather than scanning the repo root as
  one project.

## Migration note

This three-service layout replaced a single-process FastAPI monolith.
The old top-level `app/`, `tests/`, `scripts/`, `requirements.txt`, and
`pyproject.toml` (everything that used to sit directly under the repo
root) are superseded by `backend/orchestrator/`, which now holds all of
that code (with `app/design/diagram.py`, `app/design/validator.py`,
`app/design/icons.py`, and the vendored Azure icons moved out to
`backend/tools-service` - see `backend/orchestrator/README.md`'s
"Service Architecture" section for exactly what moved and why). Those
old root-level paths can be deleted once you've confirmed
`backend/orchestrator/` has everything you need; nothing in this new
layout still reads from them.
