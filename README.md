# AI Requirements → System Design Agent

An AI-powered requirements engineering agent that transforms natural-language software requirements into structured requirements and high-level system architecture.

## Current Status

**MVP-2 — Requirements to High-Level System Design**

The application now implements the MVP-2 architecture pipeline with the following capabilities:

* Natural-language requirements input
* AI-powered requirements analysis
* Structured requirements artifacts using Pydantic
* Requirements refinement
* Requirements versioning
* Azure Blob Storage persistence
* High-level system architecture generation
* Structured architecture artifacts
* Architecture semantic validation
* Requirement-to-component traceability
* Requirement-to-interface traceability
* External dependency modeling
* Architecture versioning
* Graphviz architecture diagrams
* SVG diagram generation
* External dependencies represented in architecture diagrams
* Stronger failure handling around architecture generation and validation
* Azure Blob Storage for architecture artifacts
* MCP architecture adapter
* Automated tests
* mypy type checking
* Ruff linting
* GitHub Actions CI (`ruff` + `mypy --strict` + `pytest` on every push/PR)
* FastAPI web layer with Entra ID (Azure AD) bearer-token authentication
* Cosmos DB-backed session state for the web API (`CosmosSessionStore`)
* Requirements → architecture flow exposed over HTTP
  (`/requirements-runs` start/refine/accept, plus listing a caller's own
  sessions), mirroring the CLI's Accept/Refine loop, with per-user
  ownership enforcement
* A double-submit guard on `accept` — a transitional `"generating"` stage
  plus a Cosmos ETag/if-match condition on the upsert — so both a retried
  request and a genuinely concurrent one get an immediate `409` instead of
  racing (or re-running) the generation pipeline
* Interactive Swagger UI (`/docs`) and a device-code token-acquisition
  script (`scripts/get_dev_token.py`) for manual testing
* Graceful shutdown of both the Cosmos and Blob Storage clients on server stop

The architecture stage intentionally focuses on **logical, high-level system components**.

Detailed database schemas, detailed API specifications, deployment topology, networking, Kubernetes configuration, and implementation-specific infrastructure remain outside MVP-2 scope.

---

## Web API & Authentication

The project has been CLI + MCP-server only up to this point — there was no
HTTP API. A `app/web` FastAPI layer has been added as the foundation for a
future UI (or any other HTTP client) to drive the same requirements →
architecture pipeline, secured with Entra ID (Azure AD).

**What exists today:**

* `app/config.py` — a `Settings` singleton (`pydantic-settings`) for the web
  layer's own configuration (host/port/CORS, auth toggle, Entra ID tenant
  and client id, Cosmos DB connection).
* `app/security/auth.py` — Entra ID bearer-token validation:
  * `require_user` — a FastAPI dependency that validates the
    `Authorization: Bearer <token>` header against the tenant's published
    JWKS keys and attaches the decoded claims to `request.state.user`.
  * `current_claims` / `current_user_key` / `principal_of` — read the
    validated claims back out inside a route (`oid` is the stable id to key
    ownership off of).
* `app/infrastructure/session_store.py` — a `SessionRecord` (the web
  equivalent of the CLI's in-memory `DesignSession`/`ArchitectureSession`
  state) persisted in Cosmos DB via `CosmosSessionStore`. This store is
  **synchronous** (`azure.cosmos.CosmosClient`, not the `.aio` client) to
  match the rest of this project — `ArtifactStore` and both analyzers are
  synchronous too — so the routes that use it are plain `def`, not
  `async def`, and FastAPI runs them in a threadpool.
* `app/api/ownership.py` — per-user authorization for session records: a
  session is stamped with the Entra `oid` of whoever started it, and any
  request for a session that is missing *or* belongs to someone else gets
  an identical 404 (never a 403 — that would confirm the session id exists).
* `app/api/dependencies.py` — plain, override-friendly FastAPI dependencies
  (`get_session_store`, `get_artifact_store`, `get_requirements_analyzer`,
  `get_design_analyzer`, `get_diagram_generator`, `get_validator`) so tests
  can swap in fakes via `app.dependency_overrides` without needing real
  Azure credentials.
* `app/api/routes/requirements.py` — the requirements → architecture flow
  as HTTP endpoints, mirroring the CLI's "Accept / Refine" loop:
  * `POST /requirements-runs` — analyze the initial input, like the CLI's
    first `analyze()` call. Creates a session.
  * `GET /requirements-runs` — list the caller's own sessions, newest
    first (`SessionStore.list_for_owner`). Returns `[]` for an anonymous
    caller (or with `AUTH_ENABLED=false`) rather than every session anyone
    has ever created.
  * `GET /requirements-runs/{id}` — fetch the current state of a session
    (poll/resume).
  * `POST /requirements-runs/{id}/refine` — like choosing "2. Refine": bumps
    `requirements_version` and re-analyzes with the previous artifact as
    context. `409` unless the session is still in the `"requirements"` stage.
  * `POST /requirements-runs/{id}/accept` — like choosing "1. Accept":
    marks the session `"generating"` (see below), then generates,
    validates, diagrams, and persists the architecture via
    `ArchitectureSession`. `409` if there are no requirements yet or the
    session isn't in the `"requirements"` stage (already accepted, or a
    generation already in flight); `422` if generation/validation fails —
    the session reverts to `"requirements"` so accept can be retried, and
    its `error` field is set.

  **On double-submission:** `accept` upserts the session with
  `stage="generating"` *before* starting the expensive work (AI generation
  + validation + diagram render + two Blob writes), so a sequential retry
  gets an immediate `409` rather than re-running the whole pipeline. That
  upsert is also conditional on the record's Cosmos `_etag` — `SessionRecord`
  carries the `_etag` of whatever it was last read with
  (`CosmosSessionStore.get`/`create`/`upsert` all populate it), and
  `upsert()` passes it back as an if-match condition
  (`azure.core.MatchConditions.IfNotModified`). Two requests racing to
  `accept` the same session both read the same starting `_etag`, but only
  the first upsert wins; Cosmos rejects the second with a 412, which the
  store surfaces as `SessionConflictError` and the routes translate to a
  `409` (`_upsert_guarded` in `app/api/routes/requirements.py`) — so the
  race is fully closed, not just narrowed, without needing a lock or a
  separate reservation record. A record that's never round-tripped through
  Cosmos (`etag` still `None`) writes unconditionally, same as before this
  existed.
* `app/web/main.py` — the FastAPI app itself: CORS middleware, a public
  `/health` liveness probe, a `/me` endpoint that proves the auth wiring
  works end-to-end, a `lifespan` that starts the Cosmos session store and
  the Blob artifact store once at startup, and the `requirements` router
  registered with `dependencies=[Depends(require_user)]`.

**Graceful shutdown:** on `Ctrl+C`, a `--reload` restart, or a real
`SIGTERM`, the `lifespan`'s `finally` block closes both the Cosmos session
store and the Blob artifact store. Each store's `close()` is called
independently and any exception is caught and logged rather than
propagated — one store failing to close must not stop the other from
closing, or turn an ordinary shutdown into `Application shutdown failed.
Exiting.` the way an earlier version of this code did (it called
`.close()` on the synchronous `azure.cosmos.CosmosClient`, which — unlike
`azure.cosmos.aio.CosmosClient` — doesn't have that method; fixed in
`CosmosSessionStore.close()`, which is now a documented no-op). This gap
existed because none of the original web-API tests ever exercised
`lifespan` at all — they construct `TestClient(app)` and call `.get()`
directly, which skips startup/shutdown entirely (only the context-manager
form, `with TestClient(app) as client:`, runs it). `test_web_main.py` now
has two tests that use that form specifically to close this gap.

**Configuration** (see `.env.example`):

```env
AUTH_ENABLED=false          # true to require a valid Entra ID token
ENTRA_TENANT_ID=...
ENTRA_CLIENT_ID=...
ENTRA_API_SCOPE=access_as_user
HOST=0.0.0.0
PORT=8000
CORS_ALLOW_ORIGINS=http://localhost:5173,http://localhost:4173

# Session state for the /requirements-runs endpoints — the CLI doesn't need
# these, its session state lives only in the running process.
COSMOS_ENDPOINT=https://your-cosmos-account.documents.azure.com:443/
COSMOS_KEY=...
COSMOS_DATABASE=requirements-to-design
COSMOS_SESSIONS_CONTAINER=sessions
COSMOS_AUTH_MODE=key        # or "managed_identity"
```

With `AUTH_ENABLED=false` (the default) every route is reachable without a
token — local development and CI never need a real Entra ID tenant
configured. Set it to `true` plus the tenant/client id to require a valid
token on any router registered with `dependencies=[Depends(require_user)]`.
`COSMOS_ENDPOINT`/`COSMOS_KEY` are required to actually run the web API
(the `lifespan` calls `CosmosSessionStore.start()` on startup, which needs a
real Cosmos account), but are not needed to run the test suite — the
requirements-route tests inject fakes via `app.dependency_overrides` instead.

**Run it:**

```bash
python -m app.web.main
# or, with auto-reload:
uvicorn app.web.main:app --reload
```

```bash
curl http://localhost:8000/health
curl http://localhost:8000/me   # 401 once AUTH_ENABLED=true and no token is sent

# Requirements → architecture flow (add -H "Authorization: Bearer <token>" once AUTH_ENABLED=true)
curl -X POST http://localhost:8000/requirements-runs \
  -H "Content-Type: application/json" \
  -d '{"input": "Build a todo app for small teams."}'

curl -X POST http://localhost:8000/requirements-runs/<session_id>/refine \
  -H "Content-Type: application/json" \
  -d '{"input": "Add per-team task assignment."}'

curl -X POST http://localhost:8000/requirements-runs/<session_id>/accept

curl http://localhost:8000/requirements-runs/<session_id>

# List the caller's own sessions (returns [] when AUTH_ENABLED=false, since
# sessions created without auth are unowned — see "On double-submission" above)
curl http://localhost:8000/requirements-runs
```

**Try it in Swagger UI** — FastAPI generates an interactive docs page at
`http://127.0.0.1:8000/docs`; it's the easiest way to exercise these
endpoints by hand, no `curl`/PowerShell quoting involved at all:

1. **Start a run.** Expand `POST /requirements-runs`, click "Try it out",
   and replace the placeholder Request body with:

   ```json
   {
     "input": "Build a todo app for small teams."
   }
   ```

   Click "Execute". Copy the `session_id` out of the response body below —
   you'll need it for every call after this.

2. **Check the run.** Expand `GET /requirements-runs/{session_id}`, "Try it
   out", paste your `session_id` into the path parameter field, "Execute".
   You should get back the same record — `stage: "requirements"`, the
   parsed `requirements` object, etc.

3. **Refine it** (optional). Expand
   `POST /requirements-runs/{session_id}/refine`, "Try it out", paste the
   same `session_id`, and put something like this in the body:

   ```json
   {
     "input": "Add per-team task assignment and due dates."
   }
   ```

   Execute — `requirements_version` should bump to `2` and the requirements
   should reflect the new input layered on top of the old one.

4. **Accept it.** Expand `POST /requirements-runs/{session_id}/accept`,
   "Try it out", paste the `session_id` (no request body — it just acts on
   the existing requirements), Execute. This is the expensive call: it runs
   the design analyzer, validates the architecture, renders the diagram,
   and persists both to Blob Storage. On success `stage` flips to
   `"architecture"` and `design`/`design_blob`/`diagram_blob` are populated.
   Executing it a second time before the first finishes (or against an
   already-accepted session) returns `409` rather than running the pipeline
   again.

5. **List your sessions** (optional). Expand `GET /requirements-runs`, "Try
   it out", Execute — with `AUTH_ENABLED=true` and a real token supplied via
   Authorize (see below), this returns every session you've started, newest
   first. With `AUTH_ENABLED=false` it always returns `[]`, since sessions
   created without auth have no owner to list them by.

If `AUTH_ENABLED=true`, every one of these 401s with `"Missing bearer
token"` until you click the padlock/"Authorize" button near the top of the
page and paste in a real bearer token — Swagger UI doesn't mint one on its
own (see below). If you're just smoke-testing the flow itself, the fastest
path is flipping `AUTH_ENABLED=false` in `.env` and restarting the server,
then clicking through all four steps with no auth involved at all.

**Getting a bearer token for manual testing** (once `AUTH_ENABLED=true`):
`Invoke-RestMethod`/`curl`/Swagger UI's "Authorize" dialog all need a real
Entra ID access token — none of them can mint one for you. The quickest way
to get one without a frontend:

```bash
python scripts/get_dev_token.py
```

This runs MSAL's device-code flow: it prints a URL and a code, you sign in
via a browser once, and it prints an access token you can paste into
Swagger UI's Authorize dialog (no `Bearer ` prefix — it adds that itself)
or use directly as `Authorization: Bearer <token>`. It's a manual-testing
helper, not part of the application — the equivalent of a real frontend
using MSAL.js to sign users in and attach a token to every request
automatically. If it fails, it recognizes the common Azure AD error codes
below and prints which setting fixes each one.

### Entra ID App Registration Setup

This app uses **one** app registration for both roles: it's the *client*
that requests a token (via `scripts/get_dev_token.py`, or eventually a real
frontend) **and** the *resource* (API) that validates it (`require_user` in
`app/security/auth.py`). That dual role is exactly why the settings below
are easy to get only half-right — a single-app setup needs configuration on
both the "client" and "resource" sides of the same registration, where a
typical SPA-plus-API setup would split those across two registrations.

1. **Register the app** (skip if you already have one): Azure Portal →
   Microsoft Entra ID → App registrations → New registration. Note the
   **Application (client) ID** and **Directory (tenant) ID** from its
   Overview page — these are `ENTRA_CLIENT_ID` and `ENTRA_TENANT_ID` in
   `.env`.

2. **Expose an API** (left sidebar, on the app registration):
   * Set an **Application ID URI** if none exists — the default
     `api://<client-id>` is fine.
   * **Add a scope** — name it to match `ENTRA_API_SCOPE` in `.env`
     (default `access_as_user`), give it an admin and user consent display
     name/description, leave state **Enabled**.

3. **Authentication** (left sidebar):
   * Under **Advanced settings**, set **"Allow public client flows"** to
     **Yes**. Device-code sign-in (what `get_dev_token.py` uses) and the
     Azure CLI's interactive login are both public-client flows — without
     this, Azure AD rejects them with `AADSTS7000218` because it expects a
     client secret that a public client never sends.

4. **API permissions** (left sidebar) — this is the step that's easy to
   miss because the app is authorizing itself:
   * **Add a permission** → **My APIs** → select this same app registration
     → **Delegated permissions** → check the scope you added in step 2 →
     **Add permissions**.
   * Click **Grant admin consent for `<tenant>`** (requires tenant admin
     rights). Without this, the first sign-in attempt fails with
     `AADSTS65001` ("consent required") — or, if you're not a tenant admin,
     you'd instead need to sign in interactively once and accept a consent
     prompt, which `get_dev_token.py`'s device-code flow does not present.

5. **Run the script**:

   ```bash
   python scripts/get_dev_token.py
   ```

   Sign in via the printed URL/code, and it prints an access token.

6. **Use the token**: set `AUTH_ENABLED=true` in `.env`, restart the web API
   (not just `--reload` — `.env` changes need a real restart), then either
   paste the token into Swagger UI's Authorize dialog at
   `http://127.0.0.1:8000/docs`, or send it directly:

   ```bash
   curl http://localhost:8000/me -H "Authorization: Bearer <token>"
   ```

**Troubleshooting by error code** (from either `get_dev_token.py` or
`az account get-access-token`):

| Code | Cause | Fix |
| --- | --- | --- |
| `AADSTS7000218` | App requires a client secret; device-code sends none | Step 3 — Allow public client flows → Yes |
| `AADSTS65001` | Nobody has consented to this scope yet | Step 4 — Add the permission and grant consent |
| `AADSTS500011` | `api://<client-id>` resource not found in tenant | Step 2 — set an Application ID URI |
| `AADSTS70011` | Requested scope not recognized | Step 2 — scope name must match `ENTRA_API_SCOPE` |
| `AADSTS90002` | Tenant not found | Double-check `ENTRA_TENANT_ID` against the Overview page |
| `AADSTS650057` | Azure CLI's own client isn't authorized for this resource | Only relevant to `az account get-access-token`, not `get_dev_token.py` — use the script instead, or authorize Azure CLI (`04b07795-8ddb-461a-bbee-02f9e1bf7b46`) under Expose an API → Authorized client applications |

### Next Development Steps

**Recently closed:**

* ~~Set up GitHub Actions CI~~ — `.github/workflows/ci.yml` now runs
  `ruff check`, `mypy .` (strict), and `pytest -v` on every push/PR,
  installing the `dot`/Graphviz system package the diagram tests need. An
  earlier revision of this README (and the MVP-2 checklist) had claimed
  this was already done when it wasn't; it's genuinely done now.
* ~~`GET /requirements-runs` — list a caller's own sessions~~ — implemented
  via `SessionStore.list_for_owner`, a cross-partition `owner_oid`-filtered
  Cosmos query (sessions are partitioned by their own id, not by owner —
  see the partition-key reasoning earlier in this doc). Returns `[]` for an
  anonymous caller rather than every session anyone has ever created.
* ~~Guard `accept` against double-submission~~ — narrowed at first (a
  transitional `"generating"` stage), then fully closed: see "On
  double-submission" above. Both the sequential-retry case (immediate
  `409`) and the genuinely concurrent case (Cosmos ETag/`if-match`
  conflict, surfaced as `409` too) are handled now.

**Still open, roughly in the order it'd make sense to tackle it:**

1. **A real frontend.** `scripts/get_dev_token.py` and Swagger UI are
   testing conveniences, not a product surface. A minimal frontend using
   MSAL.js to sign in and drive `/requirements-runs` (now including the
   list endpoint, so it has something to show on load) would replace
   both — and would be the point at which "Expose an API" needs a second,
   frontend-specific redirect URI/app registration rather than reusing the
   API's own client id the way the dev script does.
2. **Managed identity in production.** `COSMOS_AUTH_MODE=managed_identity`
   is already implemented in `CosmosSessionStore.start()` but never
   exercised — everything so far has run against `COSMOS_KEY`. Before this
   goes anywhere near production, switching to managed identity (and
   dropping the long-lived key entirely) is worth doing before it's a
   retrofit.
3. **Deployment.** No `Dockerfile`, no infrastructure-as-code, no target
   platform decided (Azure Container Apps vs. App Service vs. something
   else). Everything so far assumes `uvicorn` on a dev machine. CI now
   proves the code works; it doesn't yet ship anywhere.
4. **Observability.** Logging today is `logging.basicConfig(level=INFO)`
   plus whatever the Azure SDKs emit on their own (as seen in the verbose
   Cosmos/Blob request logs during startup). No request tracing, no
   structured logs, no Application Insights — fine for one developer
   testing locally, not fine for anything with real traffic.
5. **Reconcile the CLI and web session models.** `app/session.py`'s
   `DesignSession` and `app/infrastructure/session_store.py`'s
   `SessionRecord` model largely the same lifecycle in parallel, with no
   shared code between them. That's been fine while they're this simple,
   but every future field (see items above) has to be added twice unless
   this gets unified at some point.
6. **Recover sessions stuck on `"generating"`.** If the process crashes
   between marking a session `"generating"` and either finishing or
   reverting it, that session is stuck — `refine` and `accept` both refuse
   anything not in `"requirements"` stage, with no path back. Not exercised
   by any test today; worth a TTL-based recovery or an admin unstick
   endpoint before this runs unattended for real users.

The pre-existing MVP-3/"Future" roadmap further down (architecture
refinement, version comparison, ADRs, deployment architecture generation,
etc.) is still the right next horizon for the *pipeline* itself — the list
above is specifically about hardening the *web API* built this round
before building further on top of it.

---

## Architecture

The project is implemented as a staged requirements-to-design pipeline:

```text
                         User / MCP Client
                                │
                                ▼
                   ┌─────────────────────────┐
                   │ Requirements Input      │
                   │ / MCP Adapter           │
                   └────────────┬────────────┘
                                │
                                ▼
                   ┌─────────────────────────┐
                   │ Requirements Analyzer   │
                   │                         │
                   │ Azure OpenAI            │
                   └────────────┬────────────┘
                                │
                                ▼
                   ┌─────────────────────────┐
                   │ RequirementsArtifact    │
                   └────────────┬────────────┘
                                │
                                ▼
                   ┌─────────────────────────┐
                   │ Azure Blob Storage      │
                   └────────────┬────────────┘
                                │
                       Requirements accepted
                                │
                                ▼
                   ┌─────────────────────────┐
                   │ System Design Analyzer  │
                   │                         │
                   │ Azure OpenAI            │
                   └────────────┬────────────┘
                                │
                                ▼
                   ┌─────────────────────────┐
                   │ SystemDesignArtifact    │
                   └────────────┬────────────┘
                                │
                                ▼
                   ┌─────────────────────────┐
                   │ Architecture Validator  │
                   │                         │
                   │ Semantic validation     │
                   └────────────┬────────────┘
                                │
                         Valid architecture
                                │
                   ┌────────────┴────────────┐
                   │                         │
                   ▼                         ▼
          ┌──────────────────┐      ┌─────────────────────┐
          │ JSON Artifact    │      │ Diagram Generator   │
          │                  │      │ Graphviz            │
          └────────┬─────────┘      └──────────┬──────────┘
                   │                           │
                   │                           ▼
                   │                          SVG
                   │                           │
                   └──────────────┬────────────┘
                                  ▼
                         Azure Blob Storage
```

The architecture validator runs before an architecture is persisted. Invalid architecture artifacts are rejected rather than silently stored.

The architecture diagram represents both internal components and explicitly modeled external dependencies.

---

## Project Structure

```text
requirements-agent/
├── app/
│   ├── main.py
│   ├── models.py
│   ├── analyzer.py
│   ├── session.py
│   ├── storage.py
│   ├── config.py
│   │
│   ├── design/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── analyzer.py
│   │   ├── validator.py
│   │   ├── diagram.py
│   │   └── session.py
│   │
│   ├── mcp/
│   │   ├── __init__.py
│   │   └── server.py
│   │
│   ├── security/
│   │   ├── __init__.py
│   │   └── auth.py
│   │
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   └── session_store.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── ownership.py
│   │   ├── dependencies.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── requirements.py
│   │
│   └── web/
│       ├── __init__.py
│       └── main.py
│
├── scripts/
│   └── get_dev_token.py
│
├── tests/
│   ├── test_analyzer.py
│   ├── test_storage.py
│   ├── test_refinement.py
│   ├── test_design_analyzer.py
│   ├── test_design_validator.py
│   ├── test_design_diagram.py
│   ├── test_design_storage.py
│   ├── test_mcp.py
│   ├── test_auth.py
│   ├── test_web_main.py
│   ├── test_session_store.py
│   └── test_requirements_routes.py
│
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── .env.example
├── .gitignore
├── pyproject.toml
├── requirements.txt
└── README.md
```

`.github/workflows/ci.yml` runs `ruff check`, `mypy .` (strict), and
`pytest -v` on every push/PR — a prior revision of this README (and the
MVP-2 checklist below) had claimed this existed before it actually did;
see "Next Development Steps" for that history.

---

# Implementation Progress

The MVP-2 implementation was completed in six incremental steps.

## 1. Fix Architecture Versioning

Architecture generation now treats each generated design as a versioned artifact.

The architecture session owns the design version and passes that version consistently to both JSON and SVG persistence.

Artifacts follow the structure:

```text
{environment}/{session-id}/design/
├── v1.json
├── v1.svg
├── v2.json
├── v2.svg
└── ...
```

Requirements and architecture versions are associated with the same session, providing a foundation for design evolution and future version comparison.

### Versioning principle

A new architecture generation creates a new version instead of overwriting the previous logical version.

```text
Requirements
     │
     ├── Design v1
     │      ├── v1.json
     │      └── v1.svg
     │
     └── Design v2
            ├── v2.json
            └── v2.svg
```

---

## 2. Add Architecture Semantic Validation

A dedicated architecture validation layer was added between AI generation and persistence.

```text
SystemDesignAnalyzer
        │
        ▼
SystemDesignArtifact
        │
        ▼
ArchitectureValidator
        │
        ├── valid ───────► persistence
        │
        └── invalid ─────► failure
```

Validation checks the semantic integrity of the generated architecture rather than relying only on Pydantic schema validation.

The validator can verify conditions such as:

* Component IDs are unique
* Interface IDs are unique
* Interface source components exist
* Interface target components exist
* External dependency IDs are unique
* Traceability references point to valid requirements
* Architecture relationships reference known entities
* Required architecture fields are populated

This provides a second validation boundary after structured AI output parsing.

---

## 3. Add External Dependencies to the Diagram

External dependencies are modeled explicitly in the architecture artifact.

For example:

```text
┌──────────────────┐
│ Document Service │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Storage Service  │
└──────────────────┘
```

External dependencies are also represented visually in the generated Graphviz diagram.

This makes the diagram more useful for communicating system boundaries and dependencies to product owners, architects, and engineering teams.

---

## 4. Add Stronger Failure Handling

Architecture generation now treats failures explicitly rather than allowing invalid or incomplete results to be persisted.

The generation pipeline follows:

```text
AI generation
     │
     ▼
Structured parsing
     │
     ▼
Semantic validation
     │
     ├── failure ──► no artifact persistence
     │
     ▼
Diagram generation
     │
     ├── failure ──► generation failure
     │
     ▼
JSON + SVG persistence
```

The system distinguishes between:

* AI/API failures
* Structured output failures
* Semantic validation failures
* Diagram generation failures
* Storage failures

This prevents a partially generated architecture from being presented as a successful MVP-2 artifact.

---

## 5. Add Requirement Traceability

Architecture artifacts now support traceability from requirements into the generated design.

The goal is to make it possible to answer:

> Which architecture components implement this requirement?

and:

> Which requirements justify this component or interface?

The architecture model supports:

```text
Requirement
     │
     ▼
Component
     │
     ▼
Interface
```

This provides the foundation for future architecture impact analysis and requirement-to-design coverage reporting.

Traceability also gives the semantic validator enough information to detect invalid references.

---

## 6. Add MCP Adapter

An MCP adapter was added under:

```text
app/mcp/
├── __init__.py
└── server.py
```

The adapter provides an integration boundary for exposing requirements and system-design functionality to MCP-compatible clients.

The application therefore has two primary interaction paths:

```text
                 ┌──────────────────┐
                 │ Interactive CLI  │
                 └────────┬─────────┘
                          │
                          ▼
                 Requirements Agent
                          ▲
                          │
                 ┌────────┴─────────┐
                 │   MCP Adapter    │
                 └────────┬─────────┘
                          │
                          ▼
                    MCP Client
```

The MCP layer is intentionally kept as an adapter rather than embedding MCP-specific concerns throughout the requirements and architecture domain logic.

---

# MVP-1

MVP-1 converts natural-language requirements into a structured requirements artifact.

The artifact contains:

* Business goal
* Actors
* Functional requirements
* Non-functional requirements
* Data requirements
* Integration requirements
* Constraints
* Assumptions
* Open questions

Example:

```text
User input
    ↓
RequirementsAnalyzer
    ↓
RequirementsArtifact
    ↓
Azure Blob Storage
    ↓
requirements/v1.json
```

Requirements can be refined and re-analyzed. Each analysis creates a new version.

---

# MVP-2

MVP-2 consumes an accepted requirements artifact and generates a high-level system architecture.

```text
RequirementsArtifact
        │
        ▼
SystemDesignAnalyzer
        │
        ▼
SystemDesignArtifact
        │
        ▼
ArchitectureValidator
        │
        ├──────────────► design/v1.json
        │
        ▼
ArchitectureDiagramGenerator
        │
        ▼
      SVG
        │
        ▼
design/v1.svg
```

The generated architecture contains:

* Architecture summary
* Logical system components
* Component responsibilities
* Requirement-to-component traceability
* Component interfaces
* Requirement-to-interface traceability
* External dependencies
* Architecture assumptions
* Open architecture questions

---

## Architecture Artifact

A high-level architecture is represented using structured Pydantic models.

Conceptually:

```text
SystemDesignArtifact
│
├── architecture_summary
│
├── components
│   ├── id
│   ├── name
│   └── responsibility
│
├── interfaces
│   ├── id
│   ├── name
│   ├── purpose
│   ├── source_component
│   └── target_component
│
├── external_dependencies
│   ├── id
│   ├── name
│   └── purpose
│
├── assumptions
│
└── open_questions
```

The structured artifact is used as the single source of truth for validation, persistence, and diagram generation.

---

# Architecture Validation

Semantic validation is separate from schema validation.

Pydantic validates the shape of the generated artifact:

```text
SystemDesignArtifact
        │
        ▼
Pydantic validation
```

The architecture validator validates relationships and architectural consistency:

```text
SystemDesignArtifact
        │
        ▼
Semantic validation
        │
        ├── component references
        ├── interface references
        ├── dependency references
        └── traceability references
```

This separation allows the project to evolve its architecture rules without coupling them to the data model.

---

# Requirement Traceability

Requirement traceability connects the requirements artifact to the generated architecture.

The intended relationship is:

```text
REQ-001 ─────────► Component-A
   │
   └──────────────► Interface-001

REQ-002 ─────────► Component-B
   │
   └──────────────► Interface-002
```

This enables future features including:

* Requirement coverage analysis
* Architecture impact analysis
* Requirement-to-component reports
* Requirement-to-interface reports
* Architecture change impact analysis
* Traceability validation

---

# Architecture Diagrams

Architecture diagrams are generated using Graphviz.

The diagram generator converts:

* Components into nodes
* Component interfaces into edges
* External dependencies into dependency nodes
* Relationships into labeled connections

The output is SVG.

Example artifact set:

```text
design/
├── v1.json
└── v1.svg
```

Graphviz must be installed separately because the Python `graphviz` package invokes the Graphviz `dot` executable.

---

# Azure Blob Storage

Artifacts are stored by environment, session, artifact type, and version.

Example:

```text
{environment}/
└── {session-id}/
    ├── requirements/
    │   ├── v1.json
    │   └── v2.json
    │
    └── design/
        ├── v1.json
        ├── v1.svg
        ├── v2.json
        └── v2.svg
```

This provides a foundation for:

* Artifact history
* Version comparison
* Design evolution
* Future approval workflows
* Architecture change tracking

---

# Azure OpenAI

The application uses the Azure OpenAI v1 API through the OpenAI Python SDK.

The application expects an Azure OpenAI deployment name in `AZURE_OPENAI_MODEL`.

Example configuration:

```text
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/openai/v1/
AZURE_OPENAI_MODEL=<deployment-name>
```

Azure's v1 API uses the `/openai/v1/` endpoint and the deployed model name in the `model` parameter.

Structured outputs are represented using Pydantic models so the application receives validated requirements and architecture artifacts instead of relying on free-form JSON parsing.

---

# Setup

## 1. Clone the repository

```bash
git clone https://github.com/vaibhav-k/AI-requirements-to-design-agent.git
cd AI-requirements-to-design-agent
```

## 2. Create a virtual environment

### Windows

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### Linux/macOS

```bash
python -m venv .venv
source .venv/bin/activate
```

## 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

## 4. Install Graphviz

The Python `graphviz` package requires the Graphviz executable (`dot`) to be installed separately.

### Windows

Install Graphviz and ensure its `bin` directory is on `PATH`.

Verify:

```powershell
dot -V
```

### Linux

```bash
sudo apt-get update
sudo apt-get install graphviz
```

### macOS

```bash
brew install graphviz
```

## 5. Configure environment variables

Copy:

```text
.env.example
```

to:

```text
.env
```

Then provide the required Azure credentials.

Do not commit `.env`.

---

# Environment Variables

Typical configuration:

```text
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/openai/v1/
AZURE_OPENAI_MODEL=<deployment-name>

AZURE_STORAGE_CONNECTION_STRING=<connection-string>
AZURE_STORAGE_CONTAINER=requirements
AZURE_STORAGE_ENVIRONMENT=dev
```

The exact variables used by the application should match `.env.example`.

---

# Run

This project has two separate entry points — they are not interchangeable,
and running the wrong one is the most common setup mistake:

* `app/main.py` — the interactive **CLI** (`python -m app.main`). This is a
  plain script, not a FastAPI app, so `uvicorn app.main:app` fails with
  `Attribute "app" not found in module "app.main"` — there is no `app`
  object there to serve.
* `app/web/main.py` — the **web API** (`python -m app.web.main` or
  `uvicorn app.web.main:app --reload`). This is the FastAPI app with the
  Entra ID-protected `/health`, `/me`, and `/requirements-runs` endpoints
  described above.

## CLI

Start the interactive CLI:

```bash
python -m app.main
```

Example:

```text
AI REQUIREMENTS → SYSTEM DESIGN AGENT — MVP-2

Describe what you want to build.

> I want to build a platform where users can upload
> documents and ask questions about them.
```

After requirements analysis:

```text
1. Accept
2. Refine
3. Exit
```

Selecting `Accept` triggers MVP-2:

```text
Requirements accepted.

Generating high-level system architecture...

Validating architecture...

Architecture generated.

Saved design:
  JSON: <session-id>/design/v1.json
  SVG:  <session-id>/design/v1.svg
```

If semantic validation fails, the architecture is not treated as a successful persisted design.

## Web API

Start the FastAPI web layer:

```bash
python -m app.web.main
```

or, with auto-reload during development:

```bash
uvicorn app.web.main:app --reload
```

Either way it listens on `http://localhost:8000` by default (`HOST`/`PORT`
in `.env`), and requires `COSMOS_ENDPOINT`/`COSMOS_KEY` to be set — the
`lifespan` starts the Cosmos session store on startup and the process will
fail to boot without a reachable Cosmos account. Verify it's up:

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl http://localhost:8000/me
# {"authenticated":false,"principal":"anonymous","oid":""}
# — until AUTH_ENABLED=true, /me never 401s; see Web API & Authentication above.

curl -X POST http://localhost:8000/requirements-runs \
  -H "Content-Type: application/json" \
  -d '{"input": "Build a todo app for small teams."}'
# {"session_id":"...","stage":"requirements","requirements_version":1,...}
```

See [Web API & Authentication](#web-api--authentication) above for the full
`/requirements-runs` flow (start/refine/accept), Entra ID configuration, and
Cosmos DB setup.

---

# MCP

The project includes an MCP adapter under:

```text
app/mcp/server.py
```

The MCP layer is an integration boundary around the existing application capabilities.

The architecture intentionally separates:

```text
MCP transport / protocol
        │
        ▼
Application services
        │
        ├── Requirements analysis
        ├── Requirements refinement
        └── System design generation
```

This prevents MCP-specific implementation details from leaking into the core requirements and design models.

The MCP adapter can subsequently be extended with additional tools for:

* Requirements analysis
* Requirements refinement
* Architecture generation
* Architecture validation
* Artifact retrieval
* Version comparison
* Traceability queries

---

# Quality Checks

Run mypy:

```bash
mypy .
```

Run Ruff:

```bash
ruff check .
```

Run tests:

```bash
pytest -v
```

Run everything locally:

```bash
mypy .
ruff check .
pytest -v
```

---

# Testing

Azure OpenAI calls should be mocked in unit tests.

The test suite covers:

* Requirements analysis
* Requirements refinement
* Requirements versioning
* Azure Blob persistence
* System design generation
* Architecture semantic validation
* Architecture versioning
* Requirement traceability
* External dependency modeling
* Architecture diagram generation
* Design artifact storage
* MCP adapter behavior
* Entra ID token validation and the `require_user` dependency
* Cosmos DB session store (`CosmosSessionStore`), including a regression
  test that specs its mocked client against the real synchronous
  `CosmosClient` API (a plain `MagicMock` would silently accept a call to
  a method that doesn't actually exist on it), `list_for_owner`'s
  cross-partition query and its `owner_oid`-required short-circuit, and
  the ETag optimistic-concurrency path (`upsert` writing unconditionally
  when a record has no `etag`, passing it as an if-match condition when it
  does, capturing the new `etag` Cosmos returns, and translating a 412 into
  `SessionConflictError`)
* The `/requirements-runs` start/list/refine/accept routes, via
  `app.dependency_overrides` — no real Azure credentials needed. This
  includes the double-submit guard end-to-end: a second `accept` call is
  rejected with `409` without ever touching the analyzer, a losing
  concurrent write (`SessionConflictError`) on either `refine` or `accept`
  surfaces as `409` too, and a failed generation reverts the session back
  to `"requirements"` rather than leaving it stuck
* The FastAPI `lifespan`'s startup and graceful shutdown, exercised via
  `with TestClient(app) as client:` (the context-manager form is required
  for lifespan to run at all — a bare `TestClient(app)` skips it)

The Graphviz diagram test requires the `dot` executable.

---

# Failure Handling

The application follows a fail-before-persist model for generated architecture artifacts.

```text
Generate
   │
   ▼
Parse
   │
   ▼
Validate
   │
   ├── invalid ──► fail
   │
   ▼
Generate diagram
   │
   ├── failure ──► fail
   │
   ▼
Persist JSON
   │
   ▼
Persist SVG
```

The system should not report an architecture as successfully generated when validation or required artifact generation fails.

---

# Security

Never commit:

* Azure OpenAI API keys
* Azure Storage connection strings
* Access tokens
* `.env`
* Other credentials

Use `.env.example` for configuration documentation.

If a credential is accidentally committed, rotate it immediately.

---

# MVP Checklist

## MVP-1 — Requirements Analysis

* [x] Natural-language requirements input
* [x] Structured requirements
* [x] Requirements refinement
* [x] Requirements versioning
* [x] Azure Blob persistence
* [x] Pydantic validation
* [x] Automated tests

## MVP-2 — System Design

* [x] High-level architecture model
* [x] AI architecture generation
* [x] Structured architecture artifacts
* [x] Architecture versioning
* [x] Architecture semantic validation
* [x] Requirement-to-component traceability
* [x] Requirement-to-interface traceability
* [x] External dependency modeling
* [x] External dependencies in diagrams
* [x] Graphviz diagram generation
* [x] SVG generation
* [x] Azure Blob persistence
* [x] Stronger failure handling
* [x] Automated tests
* [x] mypy
* [x] Ruff
* [x] GitHub Actions CI
* [x] MCP adapter

## Web API (post-MVP-2, pre-MVP-3)

* [x] FastAPI web layer
* [x] Entra ID (Azure AD) bearer-token authentication, opt-in via `AUTH_ENABLED`
* [x] Cosmos DB-backed session store
* [x] Requirements → architecture flow over HTTP (start/refine/accept)
* [x] `GET /requirements-runs` — list a caller's own sessions
* [x] Per-user session ownership (404-never-403)
* [x] Double-submit guard on `accept` (`"generating"` stage + Cosmos
      ETag/`if-match` optimistic concurrency)
* [x] Graceful shutdown of Cosmos + Blob clients
* [x] Device-code token acquisition script for manual testing
* [ ] Frontend / UI

---

# Roadmap

## MVP-3 — Design Refinement

Planned:

* [ ] Architecture refinement
* [ ] Architecture version comparison
* [ ] Requirement-to-component coverage analysis
* [ ] Requirement-to-interface coverage analysis
* [ ] Architecture impact analysis
* [ ] Architecture decision records
* [ ] Human approval workflow
* [ ] Architecture change history

## Future

* [ ] Detailed API design
* [ ] Data model generation
* [ ] Sequence diagrams
* [ ] Deployment architecture
* [ ] Infrastructure-as-code generation
* [ ] Advanced architecture validation
* [ ] Cost analysis
* [ ] Scalability analysis
* [ ] Security architecture analysis
* [ ] Architecture governance rules

---

# Design Philosophy

The project follows several principles:

### Requirements before design

Architecture generation begins only after requirements have been analyzed and accepted.

### Structured AI output

AI output is represented through Pydantic models rather than free-form JSON.

### Validate before persistence

Generated architecture is semantically validated before being stored.

### Technology-neutral MVP-2 architecture

The architecture describes logical components and relationships rather than prematurely selecting implementation technologies.

### Version everything

Requirements and architecture artifacts are persisted as versioned artifacts.

### Traceability

Architecture decisions should be connected back to the requirements that justify them.

### Adapter-based integrations

External protocols such as MCP remain at the application boundary rather than becoming dependencies throughout the core domain.

### Human-readable artifacts

JSON provides machine-readable architecture data while SVG provides a human-readable architecture diagram.

---

# MVP-2 End-to-End Flow

```text
Natural Language
      │
      ▼
Requirements Analyzer
      │
      ▼
RequirementsArtifact
      │
      ▼
Requirements Validation
      │
      ▼
Requirements Accepted
      │
      ▼
System Design Analyzer
      │
      ▼
SystemDesignArtifact
      │
      ▼
Semantic Architecture Validation
      │
      ├───────────────┐
      │               │
      ▼               ▼
 Traceability     Dependency
 Validation       Validation
      │               │
      └───────┬───────┘
              ▼
       Valid Architecture
              │
       ┌──────┴──────┐
       ▼             ▼
   JSON Artifact   Graphviz
       │             │
       │             ▼
       │            SVG
       │             │
       └──────┬──────┘
              ▼
       Azure Blob Storage
              │
              ▼
        Versioned Design
```

The result is a requirements-to-architecture pipeline that is structured, validated, traceable, versioned, persistable, diagrammable, and accessible through both the CLI and MCP integration boundary.

# Next Steps

The next development phase should focus on moving from **MVP-2 architecture generation** toward a more complete, traceable, and refinement-oriented system design workflow.

## 1. Architecture Refinement

Allow users to refine an existing architecture without regenerating the entire design from scratch.

```text
Existing Architecture
        │
        ▼
Refinement Request
        │
        ▼
System Design Analyzer
        │
        ▼
Architecture Validator
        │
        ▼
New Architecture Version
```

Planned capabilities:

* Modify individual components
* Add or remove components
* Modify interfaces
* Modify external dependencies
* Preserve unaffected architecture decisions
* Generate a new architecture version
* Validate the complete resulting architecture

---

## 2. Architecture Version Comparison

Add structured comparison between architecture versions.

Example:

```text
Design v1
   │
   │ compare
   ▼
Design v2
```

The comparison should identify:

* Added components
* Removed components
* Changed responsibilities
* Added interfaces
* Removed interfaces
* Changed interfaces
* Added external dependencies
* Removed external dependencies
* Changed traceability
* Changed assumptions
* Resolved or newly introduced questions

Example output:

```text
Architecture Changes: v1 → v2

Components
  + DocumentProcessor
  - LegacyProcessor

Interfaces
  + DocumentProcessor → SearchService

External Dependencies
  + Object Storage

Traceability
  REQ-004: SearchService added
```

---

## 3. Requirement-to-Architecture Coverage

Build a formal coverage report showing whether every requirement is represented in the architecture.

```text
Requirements
     │
     ▼
Traceability Graph
     │
     ▼
Coverage Analysis
```

The system should identify:

* Fully covered requirements
* Partially covered requirements
* Uncovered requirements
* Components without requirement justification
* Interfaces without requirement justification

Example:

```text
Architecture Coverage

REQ-001   ✓ Covered
REQ-002   ✓ Covered
REQ-003   ⚠ Partial
REQ-004   ✗ Uncovered
```

This will make the traceability model useful for architecture review rather than merely storing references.

---

## 4. Architecture Impact Analysis

Determine what architecture elements are affected when a requirement changes.

```text
Requirement Change
        │
        ▼
Traceability Graph
        │
        ▼
Affected Components
        │
        ▼
Affected Interfaces
        │
        ▼
Affected Dependencies
```

Example:

```text
REQ-007 changed
     │
     ├── Component: SearchService
     ├── Component: DocumentProcessor
     ├── Interface: Search API
     └── Dependency: Search Provider
```

This provides the foundation for intelligent architecture evolution.

---

## 5. Architecture Decision Records

Introduce Architecture Decision Records (ADRs) to capture important architectural choices.

Each ADR should contain:

* Decision ID
* Title
* Context
* Decision
* Alternatives considered
* Rationale
* Consequences
* Related requirements
* Related components
* Status

Example:

```text
ADR-001

Decision:
Use an asynchronous document-processing component.

Rationale:
Large document processing should not block user requests.

Related requirements:
REQ-003
REQ-006

Related components:
DocumentProcessor
QueryService
```

---

## 6. Human Approval Workflow

Introduce explicit architecture approval states.

```text
Generated
    │
    ▼
Validated
    │
    ▼
Under Review
    │
    ├── Reject ─────► Refinement
    │
    ▼
Approved
```

Possible states:

```text
draft
validated
review
approved
rejected
superseded
```

Only approved architectures should optionally become the baseline for downstream engineering workflows.

---

## 7. MCP Tool Expansion

Expand the MCP adapter beyond the initial integration boundary.

Potential MCP tools:

```text
analyze_requirements
refine_requirements
generate_architecture
validate_architecture
get_architecture
compare_architectures
get_traceability
analyze_impact
refine_architecture
approve_architecture
```

The goal is to make the requirements-to-design workflow usable by MCP-compatible AI clients while keeping the underlying application services independent of MCP.

---

## 8. Detailed API Design

After the high-level architecture is stable, introduce a separate design stage for API contracts.

```text
High-Level Architecture
          │
          ▼
API Design
          │
          ├── Endpoints
          ├── Operations
          ├── Request models
          ├── Response models
          └── Error contracts
```

This should remain separate from MVP-2 so that the high-level architecture does not become unnecessarily implementation-specific.

---

## 9. Data Model Generation

Add a data-model design stage after architecture approval.

Potential outputs:

* Entities
* Relationships
* Attributes
* Constraints
* Data ownership
* Data lifecycle
* Retention requirements

The system should distinguish conceptual data modeling from physical database implementation.

---

## 10. Sequence Diagrams

Generate sequence diagrams from requirements and architecture.

```text
Actor
  │
  ▼
Component A
  │
  ▼
Component B
  │
  ▼
External Dependency
```

Potential scenarios:

* Primary user workflow
* Authentication
* Document upload
* Processing
* Search/query
* External service interaction
* Failure scenarios

Graphviz or another diagram format can be used depending on the final representation requirements.

---

## 11. Architecture Validation Rules

Expand semantic validation into configurable architecture governance rules.

Examples:

* Every functional requirement must have architectural coverage
* Every interface must reference valid components
* Every component should have a responsibility
* Every external dependency should have a purpose
* No orphan components
* No orphan interfaces
* No duplicate identifiers
* No invalid traceability references
* Required requirements should not remain uncovered
* Architecture should not introduce unsupported infrastructure

Eventually these rules could be represented as:

```text
ArchitectureRule
├── id
├── severity
├── description
├── validation
└── remediation
```

---

## 12. Architecture Quality Analysis

Introduce non-functional architecture analysis for:

* Scalability
* Reliability
* Security
* Performance
* Availability
* Maintainability
* Observability
* Cost

The system could produce an architecture review such as:

```text
Architecture Quality Review

Scalability       ✓ Good
Reliability       ⚠ Review
Security          ⚠ Review
Performance       ✓ Good
Observability     ✗ Missing
Cost              ⚠ Unknown
```

---

## 13. Deployment Architecture

Only after the logical architecture is stable should the project move toward deployment architecture.

Potential outputs:

```text
Logical Architecture
        │
        ▼
Deployment Architecture
        │
        ├── Compute
        ├── Networking
        ├── Storage
        ├── Identity
        ├── Observability
        └── External services
```

This stage can eventually support cloud-specific architectures, but should remain separate from the technology-neutral MVP-2 design.

---

## 14. Infrastructure-as-Code Generation

A later stage can transform an approved deployment architecture into infrastructure-as-code.

Potential targets:

* Terraform
* Bicep
* CloudFormation
* Kubernetes manifests

This should only operate from an **approved deployment architecture**, rather than directly from raw natural-language requirements.

---

## 15. Cost and Scalability Analysis

Add architecture-level estimation and trade-off analysis.

Potential output:

```text
Architecture Assessment

Estimated scale:
  100k users
  10k requests/minute

Primary bottleneck:
  Document processing

Scaling strategy:
  Horizontal worker scaling

Cost risk:
  External AI processing

Recommendation:
  Introduce asynchronous processing
```

The system should clearly distinguish estimates from verified infrastructure pricing.

---

# Recommended Implementation Order

The recommended roadmap is:

```text
MVP-2
  │
  ├── ✓ Versioning
  ├── ✓ Semantic validation
  ├── ✓ External dependencies
  ├── ✓ Failure handling
  ├── ✓ Requirement traceability
  └── ✓ MCP adapter
       │
       ▼
MVP-3
  │
  ├── Architecture refinement
  ├── Version comparison
  ├── Coverage analysis
  ├── Impact analysis
  ├── ADRs
  └── Human approval
       │
       ▼
MVP-4
  │
  ├── API design
  ├── Data modeling
  ├── Sequence diagrams
  └── Architecture quality analysis
       │
       ▼
MVP-5
  │
  ├── Deployment architecture
  ├── IaC generation
  ├── Cost analysis
  └── Scalability analysis
```

The immediate priority should be **Architecture Refinement + Version Comparison + Traceability Coverage**, because these features build directly on the MVP-2 foundation without prematurely expanding into implementation-specific design.
