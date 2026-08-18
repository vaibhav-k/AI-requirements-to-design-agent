# AI Requirements → System Design Agent

An AI-powered requirements engineering agent that transforms natural-language software requirements into structured requirements and high-level system architecture.

## Current Status

**MVP-2 is complete; MVP-3 (Design Refinement) is in progress.**

MVP-2's full requirements→architecture pipeline shipped, and three of
MVP-3's six planned items are also already done — architecture
refinement, architecture version comparison, and the human approval
workflow. What's left to close out MVP-3: requirement-to-architecture
coverage analysis, architecture impact analysis, architecture decision
records (ADRs), and a unified architecture change history. See
"Roadmap" → "MVP-3 — Design Refinement" for the checklist and "Path to
MVP-3 Completion" (just below it) for concrete next steps on each
remaining item.

Separately from the MVP feature roadmap, a **Clean Architecture
migration is now complete** (all 8 of 8 slices done): the codebase has
been re-layered into Domain / Application / Infrastructure /
Presentation, requirements-analysis/system-design-generation/image-
classification/diagram-interpretation all now run on [Microsoft Agent
Framework](https://github.com/microsoft/agent-framework) instead of a
direct Azure OpenAI SDK call, every one of the three "strangler fig"
facade modules (`app/analyzer.py`, `app/design/analyzer.py`,
`app/vision.py`) that used to bridge old call sites onto that new code
has been deleted, requirements/design/session persistence sits behind
`ArtifactStorePort`/`SessionStorePort` (`app/application/ports.py`)
rather than every layer above storage depending on the concrete Blob/
Cosmos adapter classes directly, and architecture diagram rendering
sits behind `DiagramRendererPort` rather than
`app.design.session.ArchitectureSession` and its callers depending on
`ArchitectureDiagramGenerator`/Graphviz directly. This was an
architecture/tech initiative orthogonal to the MVP roadmap above — it
didn't add or change user-facing capability, and didn't block MVP-3
work landing in parallel. See "Clean Architecture Migration" under
"Next Steps" for the full plan and what each slice did.

Capabilities implemented so far:

* Natural-language requirements input
* AI-powered requirements analysis — now running on Microsoft Agent
  Framework behind a Clean Architecture layering (domain/application/
  infrastructure); see "Next Steps" → "Clean Architecture Migration"
* Structured requirements artifacts using Pydantic
* Requirements refinement
* Requirements versioning
* Azure Blob Storage persistence
* High-level system architecture generation — also now running on
  Microsoft Agent Framework; see "Next Steps" → "Clean Architecture
  Migration"
* Structured architecture artifacts
* Architecture semantic validation
* Requirement-to-component traceability
* Requirement-to-interface traceability
* External dependency modeling
* Architecture versioning
* Architecture refinement — an accepted architecture can be iterated on
  with new free-text input instead of only being generated once; see the
  "MCP" and endpoint sections below
* Architecture version comparison — client-side (frontend diff) and a
  backend-computed structured diff (`GET .../architecture/compare`)
* Human approval workflow — approve/reject decisions recorded against an
  architecture version, with a full decision history; see "Next Steps" →
  "Human Approval Workflow" below
* File upload for requirements input — PDF, DOCX, PNG, JPG, JPEG, and TXT
  files can be scanned for requirements text instead of (or alongside)
  typing it, via Azure AI Document Intelligence's `prebuilt-read` model;
  the original uploaded file is persisted in Blob Storage alongside the
  extracted-text artifact; see "Next Steps" → "File Upload for
  Requirements Scanning" below
* Image input classification — an uploaded PNG/JPG/JPEG is automatically
  classified as a document screenshot (processed as usual, above) or a
  system design/workflow diagram (redrawn directly into a structured,
  well-architected system design, jumping straight to the architecture
  stage); see "Next Steps" → "Image Input Classification" below
* Graphviz architecture diagrams
* SVG diagram generation
* External dependencies represented in architecture diagrams
* Domain-clustered diagram layout — components are grouped into labeled,
  dashed clusters by their `domain`, laid out left-to-right with
  right-angle edges, keeping related components visually together and
  edges short instead of scattered across the page; see "Next Steps" →
  "Architecture Diagram Clustering & Clutter Reduction" below
* Azure Architecture Icons on every diagram node — components and
  external dependencies render with a real, recognizable Azure service
  icon (Kubernetes, SQL Database, Key Vault, etc.) instead of a plain
  box, matched from the component's/dependency's name and
  responsibility/purpose text; see "Next Steps" → "Diagram Icons (Azure
  Architecture Icons)" below
* Overlap-free, non-floating edge labels — a named edge's text renders
  as its own reserved-space node directly on the connecting line,
  instead of an auto-placed label that could land on top of a
  neighboring node or float disconnected from its edge; see "Next
  Steps" → "Diagram Label Placement (No More Overlapping/Floating
  Text)" below
* Stronger failure handling around architecture generation and validation
* Azure Blob Storage for architecture artifacts
* MCP adapter covering the full requirements-to-architecture flow —
  `analyze_requirements`/`refine_requirements`,
  `generate_system_design`/`refine_architecture`/`validate_system_design`,
  `generate_architecture_diagram` — usable end to end through MCP alone;
  see the "MCP" section below
* Automated tests
* mypy type checking
* Ruff linting
* GitHub Actions CI (`ruff` + `mypy --strict` + `pytest` on every push/PR) —
  the workflow file (`.github/workflows/ci.yml`) is currently `.gitignore`d
  and runs locally/on-demand only, not on the actual GitHub remote yet; see
  the note in "Project Structure" for why
* FastAPI web layer with Entra ID (Azure AD) bearer-token authentication
* Role-based access control (RBAC) on top of that authentication — Entra
  ID App Roles (`User`/`Architect`/`Reviewer`/`Admin`) gate which actions a
  caller may perform (create/refine requirements, generate/refine an
  architecture, approve/reject one), with `Admin` additionally bypassing
  per-owner session isolation; see "Web API & Authentication" →
  "RBAC (Role-Based Access Control)" below
* Cosmos DB-backed session state for the web API (`CosmosSessionStore`)
* Requirements → architecture flow exposed over HTTP
  (`/requirements-runs` start/refine/accept/refine-architecture, plus
  listing a caller's own sessions), mirroring (and, for
  refine-architecture, extending beyond) the CLI's Accept/Refine loop, with
  per-user ownership enforcement
* A double-submit guard on both `accept` and `refine-architecture` — a
  transitional `"generating"` stage plus a Cosmos ETag/if-match condition
  on the upsert — so both a retried request and a genuinely concurrent one
  get an immediate `409` instead of racing (or re-running) the generation
  pipeline
* Interactive Swagger UI (`/docs`) and a device-code token-acquisition
  script (`scripts/get_dev_token.py`) for manual testing
* Graceful shutdown of both the Cosmos and Blob Storage clients on server stop
* A React + Vite + TypeScript frontend (`frontend/`) built as a chat-first
  artifact explorer: sign in (or run anonymously against
  `AUTH_ENABLED=false`), a Conversation panel driving
  start/refine/accept/refine-architecture/approve/reject with explicit
  Loading/Processing/Ready/Error states plus an approval-status pill, and
  a Requirements/Architecture artifact panel with version switching,
  side-by-side version compare, and an interactive
  (zoom/pan/click-to-inspect) diagram viewer — see the Frontend section
  below

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
* `app/infrastructure/session_store.py` — a `SessionRecord`
  (`app/domain/session.py`; the web equivalent of the CLI's in-memory
  `DesignSession`/`ArchitectureSession` state) persisted in Cosmos DB via
  `CosmosSessionStore`, the concrete
  `app.application.ports.SessionStorePort` implementation. This store is
  **synchronous** (`azure.cosmos.CosmosClient`, not the `.aio` client) to
  match the rest of this project — `app/infrastructure/artifact_store.py`'s
  `ArtifactStore` and every use case are synchronous or sync-bridged too —
  so the routes that use it are plain `def`, not `async def`, and FastAPI
  runs them in a threadpool.
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
    first (`SessionStorePort.list_for_owner`). Returns `[]` for an anonymous
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
  * `POST /requirements-runs/{id}/refine-architecture` — the architecture
    analogue of `refine`: bumps `design_version` and re-generates with the
    previous design as context (`GenerateSystemDesignUseCase.execute`'s
    `previous_design`/`refinement_input`), preserving components,
    interfaces, and external dependencies that are still valid rather than
    regenerating from scratch. Unlike `refine`, this is only valid *after*
    `accept` — `409` unless the session is already in the `"architecture"`
    stage — and it can be called repeatedly, each call producing a new
    design version on top of the last. `422` if generation/validation
    fails — the session reverts to `"architecture"` (not `"requirements"`;
    the previous design is still valid and still what's persisted) so
    refinement can be retried, and its `error` field is set.
  * `POST /requirements-runs/{id}/approve` / `POST /requirements-runs/{id}/reject`
    — record an approve/reject decision against the *current*
    `design_version`, with an optional free-text `reason`. `409` unless the
    session is in the `"architecture"` stage. Neither is one-shot: calling
    either again appends another entry to `approval_history` rather than
    erroring, and `reject` deliberately leaves `stage` and the persisted
    design untouched (it's a human judgment call, not a generation
    failure) so `refine-architecture` still works immediately afterward —
    the intended loop is reject → refine → re-approve. `approval_status`
    resets to `"pending"` every time `design_version` changes (on `accept`
    and on every `refine-architecture`), so a decision never silently
    carries over to a design it wasn't actually made against.

  **On double-submission:** `accept` and `refine-architecture` both upsert
  the session with `stage="generating"` *before* starting the expensive work
  (AI generation + validation + diagram render + two Blob writes), so a
  sequential retry (or a concurrent second call to either route) gets an
  immediate `409` rather than re-running the whole pipeline. That
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
* `app/api/routes/artifacts.py` — read-only access to *historical* artifact
  content, as a separate router from `requirements.py` (which only ever
  tracks a session's *current* state). Blob names in `ArtifactStore` are
  already deterministic and version-embedded
  (`{env}/{session_id}/requirements/v{n}.json`,
  `{env}/{session_id}/design/v{n}.json`/`.svg`), and design blobs are
  written with `overwrite=False`, so every version ever persisted was
  already sitting in Blob Storage — this router just exposes it:
  * `GET /requirements-runs/{id}/requirements/versions` — the list of
    requirements version numbers that exist for this session, ascending.
  * `GET /requirements-runs/{id}/requirements/{version}` — that version's
    `RequirementsArtifact`, unwrapped from the stored envelope.
  * `GET /requirements-runs/{id}/architecture/versions` — same, for design
    versions.
  * `GET /requirements-runs/{id}/architecture/{version}` — that version's
    `SystemDesignArtifact`.
  * `GET /requirements-runs/{id}/architecture/{version}/diagram` — that
    version's persisted Graphviz SVG, as `image/svg+xml`.

  Every route runs the same ownership check as `requirements.py`
  (`load_owned` — 404, never 403, for a session that's missing or belongs
  to someone else) before touching Blob Storage. A missing version (never
  persisted, or since deleted) is a 404; a blob that fails to parse as the
  expected model is a 500 rather than a silently wrong 200.
* `app/web/main.py` — the FastAPI app itself: CORS middleware, a public
  `/health` liveness probe, a `/me` endpoint that proves the auth wiring
  works end-to-end, a `lifespan` that starts the Cosmos session store and
  the Blob artifact store once at startup, and the `requirements` and
  `artifacts` routers registered with `dependencies=[Depends(require_user)]`.

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

curl -X POST http://localhost:8000/requirements-runs/<session_id>/refine-architecture \
  -H "Content-Type: application/json" \
  -d '{"input": "Add a notifications component for due-date reminders."}'

curl http://localhost:8000/requirements-runs/<session_id>

# List the caller's own sessions (returns [] when AUTH_ENABLED=false, since
# sessions created without auth are unowned — see "On double-submission" above)
curl http://localhost:8000/requirements-runs

# Start (or refine) a run from an uploaded document instead of typed text —
# see "Next Steps" → "File Upload for Requirements Scanning" below.
# "notes" is optional free text appended after the extracted document text.
curl -X POST http://localhost:8000/requirements-runs/upload \
  -F "file=@spec.pdf" \
  -F "notes=Focus on the payments section."

curl -X POST http://localhost:8000/requirements-runs/<session_id>/refine/upload \
  -F "file=@updated-spec.docx"

# Download the original uploaded file behind the current requirements
# version (404 if that version came from typed text instead)
curl http://localhost:8000/requirements-runs/<session_id>/source-file -o downloaded
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

5. **Refine the architecture** (optional). Expand
   `POST /requirements-runs/{session_id}/refine-architecture`, "Try it
   out", paste the same `session_id`, and put something like this in the
   body:

   ```json
   {
     "input": "Add a notifications component for due-date reminders."
   }
   ```

   Execute — `design_version` should bump to `2`, `stage` stays
   `"architecture"`, and the new `design` should reflect the requested
   change while keeping the previous components/interfaces intact. This
   can be called again on the result to layer further changes on top; it
   only 409s if the session isn't in the `"architecture"` stage yet, or a
   refine/accept is already in flight.

6. **List your sessions** (optional). Expand `GET /requirements-runs`, "Try
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

---

### RBAC (Role-Based Access Control)

Authentication (above) establishes *that* a caller is a valid user in the
tenant. RBAC is the layer on top: *which actions* that caller may perform,
based on Entra ID **App Roles** assigned to them. It's implemented
entirely in `app/security/auth.py` (`require_role`, `roles_of`) and
`app/api/ownership.py` (`is_admin`) — see those modules' docstrings for the
mechanics; this section is the setup + permission matrix.

**Roles:**

| Role | Can do |
| --- | --- |
| `User` | Create and refine requirements on their own sessions (`POST /requirements-runs`, `.../refine`, and their `/upload` siblings) |
| `Architect` | Generate and refine an architecture on their own sessions (`POST .../accept`, `.../refine-architecture`) |
| `Reviewer` | Approve or reject an architecture on their own sessions (`POST .../approve`, `.../reject`) |
| `Admin` | Everything above, on **every** session regardless of owner — passes every `require_role` check automatically and bypasses the ownership check in `app/api/ownership.py` entirely |

Renaming a session (`POST .../rename`, setting the display label the UI
shows in the sessions pane) is open to any of `User`/`Architect`/`Reviewer`
on their own sessions (`Admin` on any session) — the same "any functional
role, own session" shape as the read routes below, since it's a metadata
edit rather than a stage-advancing action tied to one role.

Every read route (`GET /requirements-runs`, `GET .../{id}`, and the whole
`app/api/routes/artifacts.py` router — version history, architecture
content, diagrams) accepts any of `User`/`Architect`/`Reviewer` (`Admin`
implicit). Ownership is a separate, narrower question than the role check:
a `User` can only create/refine requirements on sessions *they* own; an
`Architect`/`Reviewer` likewise can only act on their own sessions — RBAC
here gates *which actions* a role may perform, not whose sessions it can
see, except for `Admin`, which is explicitly cross-user by design
("Admins can manage users and access across the system"). Since `GET
/requirements-runs` returns every session for an `Admin` rather than only
their own (`list_all` vs. `list_for_owner`, see
`app/infrastructure/session_store.py`), `RequirementsRunView` includes
`owner_name` so the frontend's sessions pane can label whose session is
whose when it isn't the signed-in caller's own — see `Sidebar.tsx`.

A caller with **no App Role assigned at all** — including one with a
perfectly valid, correctly-issued token — gets **403 on every route**,
including read routes. This is a deliberate choice: authentication alone
doesn't grant access to anything, only a role does. If you enable
`AUTH_ENABLED=true` and start getting 403s with a message like "This
action requires one of these roles: ...", the fix is almost always "this
user needs an app role assignment" (step 4 below), not a code change.

RBAC is a no-op — every `require_role` check passes and ownership is
skipped — whenever `AUTH_ENABLED=false`, exactly like `require_user`: local
development and CI never need roles (or a real Entra ID tenant) configured.

**Setup, on top of the app registration from the previous section:**

1. **Define the App Roles** — on the app registration, left sidebar → **App
   roles** → **Create app role**, once for each of `User`, `Architect`,
   `Reviewer`, `Admin`:
   * **Display name**: whatever's readable (e.g. "Requirements Author").
   * **Allowed member types**: **Users/Groups** (this project reads roles
     off user tokens, not app-to-app/client-credential tokens).
   * **Value**: must be exactly `User`, `Architect`, `Reviewer`, or
     `Admin` — this is the literal string `roles_of` matches against the
     token's `roles` claim, not the display name.
   * **Description**: whatever's useful for whoever assigns it later.
   * Leave **Enabled** checked.

2. **Assign roles to users** — Azure Portal → **Enterprise applications** →
   this app (**not** "App registrations" — role *assignment* happens on
   the enterprise application object even though the roles themselves were
   *defined* on the registration) → **Users and groups** → **Add
   user/group** → pick a user → pick one of the roles from step 1 → assign.
   A user can hold more than one role (e.g. both `User` and `Architect`);
   assign each separately.

3. **Nothing else changes** — the same access token `get_dev_token.py`
   already knows how to acquire (or a real frontend's MSAL sign-in) now
   carries a `roles` claim listing whatever was assigned in step 2; no new
   scope, permission, or `.env` variable is needed for RBAC itself.

**Checking what roles landed in a token:** `GET /me` (`app/web/main.py`'s
`whoami`) echoes back `roles` alongside the existing `authenticated`/
`principal`/`oid` fields — `curl http://localhost:8000/me -H "Authorization:
Bearer <token>"` is the quickest way to confirm an assignment actually took
effect, without needing to decode the JWT by hand. The frontend uses this
same endpoint (`useCurrentUser.ts`) to grey out actions the signed-in
user's role doesn't permit — see "Frontend" below.

**A role change doesn't retroactively update an already-issued token** —
MSAL/the OAuth flow bakes the `roles` claim in at token issuance, so after
assigning yourself a new role in step 2 above, sign out and sign back in
(not just wait for silent refresh) to get a token that reflects it.

**What was considered and deliberately left out:**

* **Entra ID security groups instead of App Roles** — groups would reuse
  directory groups you might already have, but need either the `groups`
  claim (which has a size limit and "group overage" fallback requiring a
  Microsoft Graph call to resolve) or a separate app-defined mapping from
  group ID to role name. App Roles surface directly as role *names* in the
  `roles` claim with no size limit or extra API call, and are the approach
  Microsoft's own docs recommend for API authorization — simpler for a
  project this size.
* **No role hierarchy beyond `Admin`** — `User`/`Architect`/`Reviewer` are
  independent grants, not tiers (an `Architect` cannot also approve without
  also being assigned `Reviewer`). Only `Admin` is a superset, and that's
  a deliberate single special case (`require_role` checks for it
  explicitly) rather than a general tier system, since the three
  functional roles don't have a natural ordering — an `Architect` isn't
  "more" than a `Reviewer`, just different.
* **No cross-user access for `Architect`/`Reviewer` on sessions they don't
  own** — only `Admin` bypasses ownership. In this project's model each
  session has a single owner throughout its lifecycle; if a workflow needs
  a different Architect/Reviewer than whoever created the session, sharing
  a session across owners is a separate, unimplemented feature (a "team"
  or "collaborators" concept), not something RBAC alone should silently
  enable.

---

## Frontend

`frontend/` is a React + Vite + TypeScript app built as a chat-first
artifact explorer, not an artifact generator: it renders exactly what the
backend has persisted for a session and its accompanying versions, and
never fabricates requirements, architecture, IDs, diagrams, or version
history of its own. It replaces Swagger UI and `scripts/get_dev_token.py`
as the way to actually *use* the API day to day — those remain useful for
quick manual API testing, but aren't a product surface.

**Layout — three connected areas:**

* **Sidebar** (`Sidebar.tsx`) — the caller's own sessions
  (`GET /requirements-runs`) plus "New session". Each session can be
  renamed inline (the pencil button next to it) — `POST .../rename`, greyed
  out with a tooltip the same way Send/Accept/Approve are when the signed-in
  caller holds none of `User`/`Architect`/`Reviewer` (`Admin` implicit; see
  the README's RBAC section). A session's own generated name falls back to
  a shortened `session_id` until it's renamed. For an `Admin` — the only
  caller `GET /requirements-runs` ever returns *other* people's sessions to
  — each entry also shows who started it (`owner_name`, or "unowned" for a
  session created before ownership tracking existed, or while
  `AUTH_ENABLED` was off, which genuinely has no owner to report); for
  anyone else every session shown is already their own, so this is never
  displayed. The
  pane itself is resizable (drag its right edge) and collapsible (the `«`
  toggle in its header, `»` to bring it back) — purely a client-side layout
  preference, persisted in `localStorage`, with no effect on what data is
  fetched or shown once expanded. The conversation/artifact split in the
  Workspace area is resizable the same way (drag the handle between them).
* **Conversation** (`Workspace.tsx` + `Conversation.tsx`) — the AI
  interaction layer. Starting a session, refining requirements, accepting
  them to generate an architecture, refining that architecture, and
  approving/rejecting it are all driven from here as a chat transcript;
  every entry reflects something the backend actually did (a persisted
  requirements/design summary, a recorded decision, or a real error),
  never fabricated conversational filler. A status pill shows **Loading**
  (fetching an existing session), **Processing** (a
  refine/accept/refine-architecture/approve/reject request is in flight —
  each backend call is a single synchronous request, so this spans the
  whole wait rather than faking granular progress), **Ready**, or
  **Error**. Once a session reaches the `"architecture"` stage: further
  chat input is routed to `POST .../refine-architecture` instead of
  `refine` — `Workspace.tsx`'s `handleSend` branches on `run.stage` the
  same way it already branched on "no session yet" vs. "requirements
  stage" — and an approval-status pill (**Pending approval**, **Approved**,
  or **Rejected**) plus **Approve**/**Reject** buttons appear alongside
  "Accept & generate architecture". Both `.../accept` and
  `.../refine-architecture` failures are read directly off the backend's
  error text to tell an architecture *validation* failure
  (`DesignGenerationWorkflowError`'s "Architecture validation failed: ...")
  from a generation failure, rather than guessing. A session stuck in the
  transient `"generating"` stage (a refine/accept already in flight) still
  has chat input rejected client-side with an explanatory message rather
  than silently hitting the backend's `409` — see the "Recover sessions
  stuck on `generating`" limitation above, which this doesn't solve.
  While the session is still in (or hasn't yet reached) the requirements
  stage, a **Scan a file** button sits alongside Send: it opens a file
  picker restricted to the supported extensions
  (`.txt`/`.pdf`/`.docx`/`.png`/`.jpg`/`.jpeg`), and whatever's currently
  typed in the textarea is sent along as optional notes appended to the
  extracted text (`POST .../upload` / `POST .../refine/upload` — see "Next
  Steps" → "File Upload for Requirements Scanning" below). A dashed
  **Source: `<filename>`** pill appears next to the status pill whenever
  the current requirements version came from an uploaded file rather than
  typed text. Send/Scan a file/Accept/Approve/Reject are each greyed out
  (with a tooltip naming the missing role, e.g. "Requires the Architect
  role.") rather than hidden, whenever the signed-in caller's Entra ID App
  Role doesn't permit that specific action — see `useCurrentUser.ts`
  (fetches `GET /me`'s `roles`) and `permissions.ts`. This is a UI
  convenience only, not the enforcement: the backend's own `require_role`
  is what actually decides, so a role revoked after the page loaded (or
  simply not yet reflected in a stale fetch) still gets caught server-side
  — surfaced as "You don't have permission to do this: ..." rather than
  the raw backend detail alone, distinct from "You're not signed in.
  Sign in above and try again." for a 401 (no token at all) — see
  `Workspace.tsx`'s `friendlyErrorMessage`.
* **Artifacts** (`ArtifactPanel.tsx`) — tabs for Requirements and
  Architecture, each backed by `app/api/routes/artifacts.py`:
  * `RequirementsView.tsx` — summary, business goal, actors,
    functional/non-functional requirements, data/integration requirements,
    constraints, assumptions, and open questions, with IDs, for the
    selected version.
  * `ArchitectureView.tsx` — components, interfaces, external dependencies,
    open questions, and a requirement-traceability section built purely
    from each component's/interface's own `requirement_ids` (never
    invented), plus `DiagramViewer.tsx` rendering the persisted Graphviz SVG
    with wheel-to-zoom, drag-to-pan, and click-to-inspect (clicking a node
    reads its Graphviz `<title>`, which is the component id, and
    highlights the matching entry in the list above).
  * `VersionBar.tsx` — switch which persisted version is shown, and
    optionally pick a second version to compare against.
  * When a compare version is selected, both views switch to a
    side-by-side field diff (`lib/diff.ts`'s `diffByKey`/`diffStringList` +
    `DiffList.tsx`) — added/removed/changed entries are tagged and shown
    before/after, for every list field on both artifacts.

**Other pieces:**

* Sign-in via MSAL (`@azure/msal-browser` + `@azure/msal-react`), or an
  explicit "Continue without signing in" path for a backend running with
  `AUTH_ENABLED=false`.
* A typed API client (`src/api.ts`) that acquires a token silently per
  request (falling back to a popup only when `acquireTokenSilent` needs
  interaction) and surfaces the backend's `detail` message on any error.
* Visual style deliberately borrows the *restraint* of a clean,
  chat-first, whitespace-generous layout — not a literal skin of any
  particular product's brand colors or typography.

The sidebar polls `GET /requirements-runs` every 5 seconds (in addition to
refetching immediately whenever this tab itself starts a session) so a
session's stage — including one another tab, or another user entirely for
an Admin, is actively generating — updates without needing to switch away
and back. This is a live *view* of whatever stage the backend actually
reports; it doesn't do anything about a session that's genuinely stuck
(see "Recover sessions stuck on `generating`" below) — a truly wedged
record just keeps polling back as `"generating"` forever, the same as
before, only without needing a manual refresh to see that it's still stuck.

**What's deliberately not covered yet:** automatically recovering a session
stuck on `"generating"` (see "Recover sessions stuck on `generating`"
below — the sidebar polling above surfaces that state live, it doesn't fix
it), and any automated frontend tests.

### Running it locally

```bash
cd frontend
npm install
cp .env.example .env   # then fill in the values — see below
npm run dev
```

By default this runs on `http://localhost:5173`, which is already in the
backend's `CORS_ALLOW_ORIGINS` default (`app/config.py`) — no CORS
configuration needed for local dev as long as you haven't changed either
side's default port.

If you just want to click around without setting up sign-in yet, leave
`.env` unfilled (or don't create it) and run the backend with
`AUTH_ENABLED=false` (the default) — the app detects that Entra isn't
configured and offers "Continue without signing in" instead of gating on
sign-in.

### Frontend: Entra ID App Registration

The frontend needs its **own** app registration — separate from the
backend API's — because a single-page app is a public client (no client
secret, ever) that authenticates *end users*, while the existing
registration doubles as both a client and the resource API it's requesting
a token for (see the backend's Entra ID section above for why that one
works differently). Reusing the API's client id here wouldn't work: its
redirect URIs and platform type are configured for the device-code flow,
not a browser sign-in redirect.

1. **Register a new app**: Azure Portal → Microsoft Entra ID → App
   registrations → New registration. Give it a distinct name (e.g.
   `requirements-agent-frontend`) so it's not confused with the API
   registration. Same tenant as the backend.

2. **Platform configuration** (Authentication, left sidebar):
   * **Add a platform** → **Single-page application**.
   * **Redirect URI**: `http://localhost:5173` for local dev (Vite's
     default port — matches `VITE_ENTRA_CLIENT_ID`'s redirect target). Add
     `http://localhost:4173` too if you'll also test against `vite preview`.
   * Leave "Allow public client flows" alone — that setting is for the
     device-code flow the backend's registration uses, not the
     authorization-code-with-PKCE flow MSAL uses for SPAs.

3. **API permissions** (left sidebar) — this is what actually lets a
   frontend-issued token be used against the backend API:
   * **Add a permission** → **My APIs** → select the **backend's** app
     registration (not this one) → **Delegated permissions** → check the
     scope it exposes (`ENTRA_API_SCOPE`, default `access_as_user`) →
     **Add permissions**.
   * **Grant admin consent** for the tenant, same as the backend's setup —
     without it, sign-in succeeds but the token request for that scope
     fails with `AADSTS65001`.

4. **Note the Application (client) ID** from this new registration's
   Overview page, and the API's own client id (from the backend's
   registration) to build the scope URI.

5. **Fill in `frontend/.env`**:

   ```dotenv
   VITE_ENTRA_TENANT_ID=<same tenant id as the backend's ENTRA_TENANT_ID>
   VITE_ENTRA_CLIENT_ID=<this new frontend app registration's client id>
   VITE_API_SCOPE=api://<backend api's client id>/access_as_user
   VITE_API_BASE_URL=http://localhost:8000
   ```

6. Restart `npm run dev` (Vite only reads `.env` at startup) and set
   `AUTH_ENABLED=true` on the backend, then restart it too. "Sign in" in
   the frontend should now complete a full round trip.

### Next Development Steps

**Recently closed:**

* ~~Set up GitHub Actions CI~~ — `.github/workflows/ci.yml` now runs
  `ruff check`, `mypy .` (strict), and `pytest -v` on every push/PR,
  installing the `dot`/Graphviz system package the diagram tests need. An
  earlier revision of this README (and the MVP-2 checklist) had claimed
  this was already done when it wasn't; it's genuinely done now.
* ~~`GET /requirements-runs` — list a caller's own sessions~~ — implemented
  via `SessionStorePort.list_for_owner`, a cross-partition `owner_oid`-filtered
  Cosmos query (sessions are partitioned by their own id, not by owner —
  see the partition-key reasoning earlier in this doc). Returns `[]` for an
  anonymous caller rather than every session anyone has ever created.
* ~~Guard `accept` against double-submission~~ — narrowed at first (a
  transitional `"generating"` stage), then fully closed: see "On
  double-submission" above. Both the sequential-retry case (immediate
  `409`) and the genuinely concurrent case (Cosmos ETag/`if-match`
  conflict, surfaced as `409` too) are handled now.
* ~~A real frontend~~ — a first pass, not the final word: React + Vite +
  TypeScript, MSAL sign-in (or anonymous mode against
  `AUTH_ENABLED=false`), covering
  start/list/refine/accept/refine-architecture end to end.
* ~~Frontend: fetch actual artifact content~~ — `app/api/routes/artifacts.py`
  now exposes version lists and content (JSON + SVG) for both requirements
  and architecture, and the frontend was rebuilt around it into the
  chat-first workspace described in the Frontend section above: version
  switching, side-by-side compare, and an interactive (zoom/pan/inspect)
  diagram viewer. See "What's deliberately not covered yet" in that section
  for what's still missing — mainly automated frontend tests.

**Still open, roughly in the order it'd make sense to tackle it:**

1. **Frontend automated tests.** Nothing here yet — no Vitest/React
   Testing Library setup, no component or `api.ts` tests. The backend's
   testing bar (see "Testing" below) hasn't been applied to `frontend/` at
   all yet.
2. **Managed identity in production.** `COSMOS_AUTH_MODE=managed_identity`
   is already implemented in `CosmosSessionStore.start()` but never
   exercised — everything so far has run against `COSMOS_KEY`. Before this
   goes anywhere near production, switching to managed identity (and
   dropping the long-lived key entirely) is worth doing before it's a
   retrofit.
3. **Deployment.** No `Dockerfile`, no infrastructure-as-code, no target
   platform decided (Azure Container Apps vs. App Service vs. something
   else). Everything so far assumes `uvicorn` on a dev machine (and now
   `npm run dev` for the frontend). CI now proves the backend works; it
   doesn't yet ship anywhere.
4. **Observability.** Logging today is `logging.basicConfig(level=INFO)`
   plus whatever the Azure SDKs emit on their own (as seen in the verbose
   Cosmos/Blob request logs during startup). No request tracing, no
   structured logs, no Application Insights — fine for one developer
   testing locally, not fine for anything with real traffic.
5. **Reconcile the CLI and web session models.** `app/session.py`'s
   `DesignSession` and `app/domain/session.py`'s
   `SessionRecord` model largely the same lifecycle in parallel, with no
   shared code between them. That's been fine while they're this simple,
   but every future field (see items above) has to be added twice unless
   this gets unified at some point.
6. **Recover sessions stuck on `"generating"`.** If the process crashes
   between marking a session `"generating"` and either finishing or
   reverting it, that session is stuck — `refine`, `accept`, and
   `refine-architecture` each refuse to run against a session already in
   `"generating"`, with no path back. Not exercised by any test today;
   worth a TTL-based recovery or an admin unstick endpoint before this runs
   unattended for real users. The frontend's Conversation view has no
   polling loop for this today either — see "What's deliberately not
   covered yet" in the Frontend section.

The pre-existing MVP-3/"Future" roadmap further down (coverage analysis,
impact analysis, ADRs, deployment architecture generation, etc. —
architecture refinement, version comparison, and the human approval
workflow are now implemented, see the "MCP" and endpoint sections above)
is still the right next horizon for the *pipeline* itself — the list
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
                   │ Microsoft Agent         │
                   │ Framework (Azure        │
                   │ OpenAI) — see "Clean    │
                   │ Architecture Migration" │
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
                   │ Microsoft Agent         │
                   │ Framework (Azure        │
                   │ OpenAI) — see "Clean    │
                   │ Architecture Migration" │
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

The diagram above already reflects all eight slices of what is now a
completed architectural migration — see "Clean Architecture Migration"
(in "Next Steps," below "Roadmap") for the full plan, rationale, and
what each slice did. In short: requirements analysis, system-design
generation, and image classification/diagram-image interpretation all
now run on Microsoft Agent Framework instead of a direct Azure OpenAI
SDK call, the code behind each is now layered as Domain → Application →
Infrastructure rather than one flat module apiece, the architecture/
design bounded context's entities (`SystemDesignArtifact` and friends)
live in `app/domain/design.py` alongside the requirements bounded
context's `app/domain/requirements.py` and the run entity in
`app/domain/session.py`, all five re-export/facade shims that used to
bridge old call sites onto that new code
(`app/models.py`/`app/design/models.py`/`app/analyzer.py`/
`app/design/analyzer.py`/`app/vision.py`) have been deleted — every
call site now either imports the domain entities directly or
constructs its use case via `app/infrastructure/composition.py` (see
`app/api/dependencies.py`, `app/mcp/server.py`, `app/main.py`) —
requirements/design/session persistence sits behind
`ArtifactStorePort`/`SessionStorePort` rather than every layer above
storage depending on the concrete Blob (`app/infrastructure
/artifact_store.py`) / Cosmos (`app/infrastructure/session_store.py`)
adapter classes directly, and the Diagram Generator box now sits
behind `DiagramRendererPort` rather than
`app.design.session.ArchitectureSession` and its callers (`app/main.py`,
`app/api/dependencies.py`, `app/mcp/server.py`) depending on
`ArchitectureDiagramGenerator`/Graphviz directly. The Architecture
Validator box remains a plain concrete dependency, not behind a port —
it's pure in-process validation logic with no external service or
library it needs to be abstracted away from, unlike every other box
this migration touched.

---

## Project Structure

```text
requirements-agent/
├── app/
│   ├── main.py
│   ├── session.py
│   ├── config.py
│   ├── ingestion.py
│   │
│   ├── domain/                       # Clean Architecture: entities, zero I/O
│   │   ├── __init__.py
│   │   ├── requirements.py           # Requirement/Actor/.../RequirementsArtifact
│   │   ├── design.py                 # DesignComponent/.../SystemDesignArtifact
│   │   ├── vision.py                 # ImageClassification
│   │   └── session.py                # SessionRecord
│   │
│   ├── application/                  # Clean Architecture: use cases + ports
│   │   ├── __init__.py
│   │   ├── ports.py                  # RequirementsAgentPort/SystemDesignAgentPort/
│   │   │                             # ImageClassifierPort/DiagramImageInterpreterPort/
│   │   │                             # ArtifactStorePort/SessionStorePort/
│   │   │                             # DiagramRendererPort
│   │   ├── errors.py                 # DesignGenerationError/ImageClassificationError/
│   │   │                             # DiagramInterpretationError/
│   │   │                             # ArtifactVersionConflict/SessionConflictError/
│   │   │                             # DiagramGenerationError
│   │   └── use_cases/
│   │       ├── __init__.py
│   │       ├── analyze_requirements.py
│   │       ├── generate_system_design.py
│   │       ├── classify_image.py
│   │       └── interpret_diagram_image.py
│   │
│   ├── design/
│   │   ├── __init__.py
│   │   ├── validator.py
│   │   ├── diagram.py                # ArchitectureDiagramGenerator — concrete
│   │   │                             # DiagramRendererPort
│   │   ├── comparison.py
│   │   ├── icons.py
│   │   ├── icons/
│   │   │   └── azure/
│   │   │       ├── NOTICE.md
│   │   │       └── *.png  (23 vendored Azure Architecture Icons)
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
│   │   ├── session_store.py   # CosmosSessionStore — concrete SessionStorePort
│   │   ├── artifact_store.py  # ArtifactStore — concrete ArtifactStorePort
│   │   ├── composition.py   # composition root — builds each *UseCase
│   │   │                    # wired to a real Microsoft Agent Framework
│   │   │                    # adapter, reading AZURE_OPENAI_* once here
│   │   ├── sync_bridge.py   # run_sync() — bridges a use case's async
│   │   │                    # execute() into a sync call for the CLI/MCP/
│   │   │                    # sync FastAPI routes
│   │   └── agents/
│   │       ├── __init__.py
│   │       ├── requirements_agent.py    # Microsoft Agent Framework adapter
│   │       ├── system_design_agent.py   # Microsoft Agent Framework adapter
│   │       ├── image_classifier_agent.py          # Microsoft Agent Framework adapter
│   │       ├── diagram_image_interpreter_agent.py # Microsoft Agent Framework adapter
│   │       └── vision_support.py    # shared image-Content-part helper
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── ownership.py
│   │   ├── dependencies.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── requirements.py
│   │       └── artifacts.py
│   │
│   └── web/
│       ├── __init__.py
│       └── main.py
│
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── App.css
│   │   ├── index.css
│   │   ├── authConfig.ts
│   │   ├── api.ts
│   │   ├── types.ts
│   │   ├── lib/
│   │   │   └── diff.ts
│   │   ├── hooks/
│   │   │   └── useVersionedArtifact.ts
│   │   └── components/
│   │       ├── Sidebar.tsx
│   │       ├── Workspace.tsx
│   │       ├── Conversation.tsx
│   │       ├── ArtifactPanel.tsx
│   │       ├── RequirementsView.tsx
│   │       ├── ArchitectureView.tsx
│   │       ├── DiagramViewer.tsx
│   │       ├── VersionBar.tsx
│   │       ├── DiffList.tsx
│   │       └── ErrorBanner.tsx
│   ├── .env.example
│   ├── package.json
│   └── vite.config.ts
│
├── scripts/
│   └── get_dev_token.py
│
├── tests/
│   ├── test_analyze_requirements_use_case.py
│   ├── test_infrastructure_requirements_agent.py
│   ├── test_artifact_store.py
│   ├── test_refinement.py
│   ├── test_ingestion.py
│   ├── test_generate_system_design_use_case.py
│   ├── test_infrastructure_system_design_agent.py
│   ├── test_classify_image_use_case.py
│   ├── test_interpret_diagram_image_use_case.py
│   ├── test_infrastructure_image_classifier_agent.py
│   ├── test_infrastructure_diagram_image_interpreter_agent.py
│   ├── test_infrastructure_vision_support.py
│   ├── test_infrastructure_sync_bridge.py
│   ├── test_design_validator.py
│   ├── test_design_diagram.py
│   ├── test_design_storage.py
│   ├── test_design_comparison.py
│   ├── test_design_icons.py
│   ├── test_mcp.py
│   ├── test_auth.py
│   ├── test_rbac.py
│   ├── test_ownership.py
│   ├── test_web_main.py
│   ├── test_session_store.py
│   ├── test_requirements_routes.py
│   └── test_artifacts_routes.py
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
`pytest -v` on every push/PR — but it's currently listed in `.gitignore`
(temporarily, while Azure AI Foundry access for CI's own Azure OpenAI
credentials gets sorted out), so it exists on disk and runs fine locally
but isn't tracked in git or active on the GitHub remote yet. Remove that
`.gitignore` line (and commit the workflow file) once that's resolved. A
prior revision of this README (and the MVP-2 checklist below) had claimed
CI was fully set up before either of these gaps were closed; see "Next
Development Steps" for that history.

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

Requirements and architecture versions are associated with the same session. `app/api/routes/artifacts.py` exposes that version history over HTTP, and the frontend's `VersionBar`/`DiffList` components use it to switch between versions and show a side-by-side field diff — see the Frontend section above.

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
GenerateSystemDesignUseCase
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
AnalyzeRequirementsUseCase
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
GenerateSystemDesignUseCase
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

Architecture diagrams are generated using Graphviz (`app/design/diagram.py`,
`ArchitectureDiagramGenerator`).

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

**Layout, current state — see "Architecture Diagram Clustering & Clutter
Reduction" and "Diagram Icons (Azure Architecture Icons)" below for the
full history and reasoning; summarized here:**

* Every component renders as a small icon (see "Diagram Icons" below)
  above an `{id}\n{name}` caption (e.g. `C-001` / `User Interaction
  Component`) — the full responsibility/purpose text is left out on
  purpose, since it's already shown in the Requirements/Architecture
  text panel (and in the frontend's `ArchitectureView.tsx`). It's still
  attached to each node/edge as a Graphviz `tooltip`, which renders as a
  native browser hover tooltip (`xlink:title`) without touching the
  node's own `<title>` — the frontend's `DiagramViewer.tsx`
  click-to-inspect depends on that `<title>` staying exactly the
  component id.
* Components are grouped into one dashed, labeled cluster per
  `DesignComponent.domain`, laid out left-to-right (`rankdir="LR"`) with
  no fixed page size — a design can be as wide/tall as its actual
  content needs; the frontend's `DiagramViewer` zoom/pan handles the
  rest. Within a domain's cluster, components stack in a single column
  (chained top-to-bottom by ordinary directed edges, not a
  `rank=same` grid) — see "Architecture Diagram Clustering & Clutter
  Reduction" for why a `rank=same` grid isn't used here.
* Edges route as straight, right-angle lines (`splines="ortho"`) rather
  than curved splines. A named edge (an interface, or the first "used
  by" edge into a given dependency) is split into two edges through an
  intermediate borderless `shape="plaintext"` label node
  (`_add_labeled_edge` in `app/design/diagram.py`) rather than carrying
  the name as a plain Graphviz `xlabel` — see "Diagram Label Placement
  (No More Overlapping/Floating Text)" below for why. Naming is
  suppressed above `ArchitectureDiagramGenerator.MAX_LABELED_EDGES`
  total edges to avoid cluttering a dense diagram with dozens of small
  text strings (in which case it's a single plain edge, no label node);
  full detail remains available via each edge's tooltip regardless.
* Component-to-external-dependency ("used by") edges are dashed and
  dependency-colored, visually distinct from interface edges at a glance
  rather than only distinguishable by reading their labels; only the
  first edge into a given dependency repeats its name as a label.

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

Artifact history and version comparison are already exposed and used —
see `app/api/routes/artifacts.py` and the Frontend section above. This
also provides a foundation for:

* Design evolution
* Future approval workflows
* Architecture change tracking

Every save goes through `ArtifactStore._upload`
(`app/infrastructure/artifact_store.py`), which
logs the resulting blob path after a successful upload — one `logger.info`
call covers every artifact type (requirements JSON, design JSON, diagram
SVG, uploaded source files) since they all funnel through this one method:

```text
Artifact saved to Azure Blob Storage: container=requirements blob=dev/<session-id>/design/v2.svg url=https://<account>.blob.core.windows.net/requirements/dev/<session-id>/design/v2.svg
```

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

# Optional — only required for scanning PDF/DOCX/PNG/JPG/JPEG files for
# requirements (typed-text input keeps working without these; see "Next
# Steps" → "File Upload for Requirements Scanning")
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://<resource>.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=<key>
```

The web API additionally reads `AUTH_ENABLED`, `ENTRA_TENANT_ID`,
`ENTRA_CLIENT_ID`, `ENTRA_API_SCOPE`, `HOST`, `PORT`,
`CORS_ALLOW_ORIGINS`, and the `COSMOS_*` session-store variables — see
"Web API & Authentication" above for those, rather than repeating them
here. The exact variables used by the application should match `.env.example`.

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
        ├── System design generation
        └── System design refinement
```

This prevents MCP-specific implementation details from leaking into the core requirements and design models.

**Tools exposed today**, covering the full requirements-to-architecture
flow end to end through MCP alone (no need to call the analyzers directly
outside it):

* `analyze_requirements(user_input)` — the entry point: free-text input in,
  a structured `RequirementsArtifact` JSON out.
* `refine_requirements(user_input, requirements_json)` — re-analyzes with
  the previous artifact as context, same as the CLI's/web API's "Refine"
  step.
* `generate_system_design(requirements_json)` — generates a
  `SystemDesignArtifact` from an accepted requirements artifact.
* `refine_architecture(user_input, requirements_json, design_json)` —
  re-generates with the previous design as context, same as the web API's
  `refine-architecture` endpoint: still-valid components, interfaces, and
  external dependencies are preserved rather than the architecture being
  regenerated from scratch.
* `validate_system_design(design_json)` — runs the same semantic
  `ArchitectureValidator` used before persistence.
* `generate_architecture_diagram(design_json)` — validates, then renders
  the SVG diagram (same `ArchitectureDiagramGenerator` as the web API).
* Resources: `requirements://schema` and `design://schema` — the JSON
  Schema for each artifact type, so a client can introspect the shape it's
  working with.

This layer is deliberately stateless — every tool takes and returns JSON
directly, with no session, persistence, or versioning of its own (that's
`ArtifactStorePort`/`SessionStorePort`'s job on the web API side). The MCP adapter
can subsequently be extended with additional tools for:

* Artifact retrieval — reading already-persisted versions (mirroring
  `app/api/routes/artifacts.py`) rather than only operating on JSON the
  caller already has in hand.
* Version comparison — the backend-computed structured diff itself now
  exists as a web API route (`GET .../architecture/compare`, see "Next
  Steps" → "Architecture Version Comparison"); it just isn't exposed as an
  MCP tool yet, since MCP tools here are stateless and this reads
  already-persisted versions the same way "Artifact retrieval" above
  would.
* Traceability queries — answering "which components/interfaces implement
  requirement X" as a dedicated tool instead of requiring the caller to
  walk `requirement_ids` themselves.

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

If `mypy . --strict` fails with something like `Type statement is only
supported in Python 3.12 and greater` pointing at a file under
`numpy/__init__.pyi`, that's not a bug in this project's code — this
project has no dependency on numpy at all, direct or transitive.
`openai`'s package internals do a `TYPE_CHECKING`-guarded `import numpy`
(for optional embedding helpers this project doesn't use), so if numpy
merely happens to be *installed somewhere in the same environment* mypy
runs in (e.g. a shared venv that also has data-science tooling), mypy
will try to resolve and fully parse whatever numpy stub is sitting
there — and some numpy versions' stubs use newer syntax than this
project's `python_version = "3.11"` mypy target supports, which is a
hard parse error that aborts the whole run. `pyproject.toml` already
has a `[[tool.mypy.overrides]]` entry with `module = ["numpy",
"numpy.*"]` and `follow_imports = "skip"` to prevent this — if you hit
it anyway, confirm you're on the version of `pyproject.toml` that
includes it (this was added alongside the Microsoft Agent Framework
migration, see "Next Steps" → "Clean Architecture Migration").

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
* The `/requirements-runs` start/list/refine/accept/refine-architecture
  routes, via `app.dependency_overrides` — no real Azure credentials
  needed. This includes the double-submit guard end-to-end: a second
  `accept` or `refine-architecture` call is rejected with `409` without
  ever touching the analyzer, a losing concurrent write
  (`SessionConflictError`) on `refine` or `accept` surfaces as `409` too,
  a failed `accept` reverts the session back to `"requirements"`, and a
  failed `refine-architecture` reverts it back to `"architecture"` (not
  `"requirements"` — the previous design is still valid) rather than
  leaving it stuck
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
* [x] Read-only artifact-history endpoints (`app/api/routes/artifacts.py`)
      — version lists and content (JSON + SVG) for both requirements and
      architecture
* [x] Frontend / UI — chat-first workspace (Conversation + Requirements +
      Architecture), version switching, side-by-side version compare, and
      an interactive diagram viewer; see the Frontend section above for
      what's still missing (mainly automated frontend tests)

---

# Roadmap

## MVP-3 — Design Refinement

Planned:

* [x] Architecture refinement — `POST .../refine-architecture` (web API) and
      `refine_architecture` (MCP); see the endpoint and "MCP" sections above
* [x] Architecture version comparison — both client-side, in the frontend
      (`VersionBar`/`DiffList` fetch two persisted versions via
      `app/api/routes/artifacts.py` and diff them in the browser), and now
      backend-computed (`GET .../architecture/compare`,
      `app/design/comparison.py`) for any client that wants the diff
      without fetching both full artifacts itself — see "Next Steps" →
      "Architecture Version Comparison" below
* [ ] Requirement-to-component coverage analysis
* [ ] Requirement-to-interface coverage analysis
* [ ] Architecture impact analysis
* [ ] Architecture decision records
* [x] Human approval workflow — `POST .../approve`/`POST .../reject`
      (web API only, no MCP tool yet); see "Next Steps" → "Human Approval
      Workflow" below for what shipped vs. what was deliberately left out
* [ ] Architecture change history — partially covered today by
      `GET .../architecture/compare` (diff between two versions) and
      `SessionRecord.approval_history` (who approved/rejected which
      version and when); what's still missing is a single endpoint that
      merges both into one chronological timeline per session, so a
      caller isn't stitching two separate history sources together

## Path to MVP-3 Completion

Recommended order for the four remaining checklist items above, each
building on the last (coverage needs the existing traceability graph;
impact analysis reuses coverage's dependency graph; ADRs and change
history are independent and can slot in anywhere once the others land):

1. **Requirement-to-architecture coverage analysis** (see "Next Steps" →
   "Requirement-to-Architecture Coverage" below for the full spec).
   Concretely: add `app/design/coverage.py` with a
   `compute_coverage(design) -> CoverageReport` function that walks the
   existing `traces` on each `DesignComponent`/`ComponentInterface`
   against `RequirementsArtifact.requirements`, classifying each
   requirement `covered` / `partial` / `uncovered` and flagging any
   component/interface with an empty `traces` list. Expose it as
   `GET /requirements-runs/{id}/architecture/coverage` (web API,
   mirroring `app/design/comparison.py` + its route) and as a
   `get_architecture_coverage` MCP tool (stateless — takes a
   `RequirementsArtifact` + `SystemDesignArtifact`, same pattern as
   `validate_system_design`). Add `tests/test_design_coverage.py`.
2. **Architecture impact analysis** (see "Next Steps" → "Architecture
   Impact Analysis" below). Concretely: add
   `app/design/impact.py` with `compute_impact(design, requirement_id)
   -> ImpactReport`, reusing the same traceability graph coverage
   analysis builds — this is the reason coverage should land first.
   Expose as `GET .../architecture/impact?requirement_id=...` and an
   `analyze_impact` MCP tool (the one MCP gap called out in the "MCP
   Tool Expansion" section below that has no other blocker).
3. **Architecture Decision Records** (see "Next Steps" → "Architecture
   Decision Records" below). Concretely: add an `ArchitectureDecisionRecord`
   Pydantic model (`app/domain/design.py`), persist it the same way as
   other artifacts (`ArtifactStore.save_adr`/`get_adr`, versioned per
   session like design JSON/SVG), and add
   `POST`/`GET /requirements-runs/{id}/architecture/decisions` routes.
   No MCP tool needed yet — start web-API-only, same call this project
   made for the human approval workflow.
4. **Architecture change history** — once coverage/impact/ADRs exist,
   add one `GET .../architecture/history` endpoint that merges
   `list_design_versions`, `approval_history`, and (once step 3 lands)
   ADR entries into a single chronological feed; this is largely
   aggregation over data that already exists rather than new analysis.

Each item should ship with: a stateless pure-function core (testable
without Azure credentials, matching `validator.py`/`comparison.py`'s
style), a web API route, automated tests, and a README update to this
file's "Next Steps" and "MVP Checklist" sections marking it done — the
same pattern used for every completed MVP-3 item so far.

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

## Clean Architecture Migration

**Complete — 8 of 8 slices done.** A separate initiative (not part
of the MVP-3 feature checklist above) that re-layered the backend as Clean
Architecture and moved the project's AI calls onto [Microsoft Agent
Framework](https://github.com/microsoft/agent-framework) — Microsoft's
unified successor to Semantic Kernel and AutoGen, combining Semantic
Kernel's enterprise features (typed, session-based state; middleware;
telemetry) with AutoGen's simpler multi-agent abstractions.

Why both changes together: adopting Agent Framework means every
LLM-calling module needs to change anyway, which is the natural moment
to also stop depending directly on `openai`/`agent_framework`/
`azure.storage.blob`/etc. from the same modules that hold business
logic, and instead depend on an abstraction it owns.

**Target layering** (Clean Architecture / the Dependency Rule — inner
layers never import outer ones):

```text
app/domain/            Entities & value objects. Zero I/O, zero framework
                        deps beyond Pydantic. E.g. RequirementsArtifact.

app/application/       Use cases + ports (Protocols). Depends only on
                        domain. Defines the *shape* infrastructure must
                        implement (e.g. RequirementsAgentPort) without
                        importing any concrete SDK.

app/infrastructure/    Concrete adapters implementing application ports:
                        Microsoft Agent Framework agents, Azure Blob
                        Storage, Cosmos DB, Graphviz, Azure Document
                        Intelligence. Depends on application + domain.

app/api/, app/web/,    Presentation. FastAPI routes, the CLI, and the
app/main.py, app/mcp/  MCP server — construct use cases (wired to real
                        infrastructure adapters) and call them. Depends
                        on application + domain; talks to infrastructure
                        only through application's ports.
```

**Slice 1 (done) — Requirements analysis, end to end:**

* `app/domain/requirements.py` — `Requirement`, `Actor`, `Assumption`,
  `OpenQuestion`, `RequirementsArtifact`, `StoredArtifact`, moved out of
  `app/models.py` verbatim. `app/models.py` became a deprecated
  re-export shim at this point (still used by most of the codebase at
  the time) so this slice didn't require updating every importer at
  once — that migration happened in a later slice (see Slice 5 below),
  and `app/models.py` no longer exists.
* `app/application/ports.py` — `RequirementsAgentPort`, a `Protocol`
  with one method (`analyze`). `app/application/use_cases
  /analyze_requirements.py` — `AnalyzeRequirementsUseCase`, pure
  orchestration against that port, no knowledge of Azure or Agent
  Framework.
* `app/infrastructure/agents/requirements_agent.py` —
  `AgentFrameworkRequirementsAgent`, a `RequirementsAgentPort`
  implementation backed by a Microsoft Agent Framework `Agent`. This
  replaces the direct `openai.OpenAI().responses.parse(...,
  text_format=RequirementsArtifact)` call the project used before.
  Structured output uses `ChatOptions(response_format=RequirementsArtifact)`
  passed to `Agent.run(...)`, reading the parsed instance off
  `AgentResponse.value` — see that module's docstring for wiring notes,
  including why `agent_framework.openai.OpenAIChatClient` is used
  rather than an `AzureOpenAIChatClient` (removed upstream; current
  Microsoft guidance routes Azure OpenAI through the OpenAI-provider
  client with an explicit `base_url`/`azure_endpoint`).
* `app/analyzer.py`'s `RequirementsAnalyzer` is now a **backward-compatible
  facade** over the above — a "strangler fig" seam so the many existing
  synchronous call sites (`app/main.py`, `app/session.py`,
  `app/api/dependencies.py`, `app/mcp/server.py`) didn't all need to
  change in this slice. It gained an `analyze_async` method for
  `async def` callers — `Agent.run` is async, and `asyncio.run()`
  cannot nest inside an already-running event loop, so the two `async
  def` upload routes (`start_run_from_upload`/`refine_run_from_upload`
  in `app/api/routes/requirements.py`) now call `analyze_async`
  directly while the two sync routes (`start_run`/`refine_run`, which
  FastAPI runs in a worker thread) keep calling the sync `analyze`.
* New dependencies: `agent-framework-core==1.14.0` and
  `agent-framework-openai==1.13.0` — pinned individually rather than
  the `agent-framework` meta-package, which pulls in ~30 optional
  provider integrations (Anthropic, Bedrock, Gemini, Redis, ...) this
  project doesn't use.
* New tests: `tests/test_analyze_requirements_use_case.py` (use case
  against a fake port), `tests/test_infrastructure_requirements_agent.py`
  (the Agent Framework adapter, with the underlying `Agent`/
  `OpenAIChatClient` faked out — no real network call, no Azure
  credentials needed), and `tests/test_analyzer.py`/`tests/test_mcp.py`
  updated to inject a fake `RequirementsAgentPort` instead of mocking
  the old raw OpenAI client shape.

**Slice 2 (done) — System design generation/refinement, end to end:**

* `app/application/ports.py` gained `SystemDesignAgentPort` (method
  `generate`), the design-generation analogue of `RequirementsAgentPort`.
  Its `SystemDesignArtifact` parameter/return type came from
  `app.design.models` rather than `app.domain` at this point — documented
  inline in `ports.py` as a deliberate, temporary compromise rather than
  an oversight, resolved two slices later once `app.domain.design`
  existed (see Slice 4 below).
* `app/application/errors.py` (new) — `DesignGenerationError`, moved
  out of `app/design/analyzer.py` so both the application and
  infrastructure layers can raise/import it without a circular
  dependency back into the presentation-facing facade module.
* `app/application/use_cases/generate_system_design.py` —
  `GenerateSystemDesignUseCase`, pure orchestration against
  `SystemDesignAgentPort`, mirroring `AnalyzeRequirementsUseCase`.
* `app/infrastructure/agents/system_design_agent.py` —
  `AgentFrameworkSystemDesignAgent`, replacing the direct
  `openai.OpenAI().responses.parse(..., text_format=SystemDesignArtifact)`
  call with a Microsoft Agent Framework `Agent`, same wiring as Slice 1's
  requirements agent (`OpenAIChatClient` + `base_url` routing +
  `ChatOptions(response_format=...)`). The full architecture-generation
  prompt (domain clustering instructions, the external-dependency/
  interface constraint, etc.) moved here verbatim from the old
  `SystemDesignAnalyzer._build_prompt`.
* `app/design/analyzer.py`'s `SystemDesignAnalyzer` is now a
  backward-compatible facade, same strangler-fig shape as
  `app/analyzer.py`'s `RequirementsAnalyzer` — sync `analyze()` (used by
  every current call site: `app/main.py`, `app/design/session.py`,
  `app/mcp/server.py`, and the web API's `accept_run`/
  `refine_architecture` routes, all of which are sync `def`s) plus an
  `analyze_async()` for symmetry, even though no `async def` caller
  needs it yet.
* New tests: `tests/test_generate_system_design_use_case.py`,
  `tests/test_infrastructure_system_design_agent.py` (includes the
  interface-vs-external-dependency prompt regression test, moved here
  from `tests/test_design_analyzer.py` along with the prompt itself),
  and `tests/test_design_analyzer.py`/`tests/test_mcp.py` updated to
  inject a fake `SystemDesignAgentPort`.

**Slice 3 (done) — Image classification & diagram-image interpretation,
end to end:**

* `app/domain/vision.py` — `ImageClassification`, moved out of
  `app/vision.py` verbatim, the same "pure entity, zero I/O" home
  `app.domain.requirements` already gives Slice 1's entities.
* `app/application/errors.py` gained `ImageClassificationError` and
  `DiagramInterpretationError`, moved out of `app/vision.py` for the same
  reason Slice 2 moved `DesignGenerationError` out of
  `app/design/analyzer.py`.
* `app/application/ports.py` gained `ImageClassifierPort` (method
  `classify`) and `DiagramImageInterpreterPort` (method `interpret`).
  `app/application/use_cases/classify_image.py` —
  `ClassifyImageUseCase` — and `app/application/use_cases
  /interpret_diagram_image.py` — `InterpretDiagramImageUseCase` — are
  pure orchestration against those ports, mirroring Slices 1–2's use
  cases.
* `app/infrastructure/agents/image_classifier_agent.py` —
  `AgentFrameworkImageClassifierAgent` — and `app/infrastructure/agents
  /diagram_image_interpreter_agent.py` —
  `AgentFrameworkDiagramImageInterpreterAgent` — replace the direct
  `openai.OpenAI().responses.parse(...)` calls (with `input_text`/
  `input_image` content parts) the project used before. This slice
  needed one thing Slices 1–2 didn't: multimodal input. Microsoft Agent
  Framework represents that as an `agent_framework.Message(role="user",
  contents=[...])` mixing a `Content.from_text(...)` prompt part with a
  `Content.from_data(...)` image part, passed to `Agent.run(...)`
  directly in place of a plain string prompt — see either adapter's
  docstring, and the shared `app/infrastructure/agents
  /vision_support.py` helper (`image_content`) that builds the image
  `Content` part from an upload's raw bytes and filename extension
  (factored out once, used by both adapters, rather than duplicated).
* `app/vision.py`'s `ImageInputClassifier`/`DiagramImageInterpreter` are
  now backward-compatible facades, same strangler-fig shape as
  `app/analyzer.py`/`app/design/analyzer.py` — each gained an
  `..._async` method (`classify_async`/`interpret_async`) for `async
  def` callers. This one mattered immediately, not just for symmetry:
  `app/api/routes/requirements.py`'s `_resolve_image_upload` (itself
  `async def`, invoked via `await` from the already-running-on-the-
  event-loop upload routes) previously called the old classes' sync
  `classify`/`interpret` directly — harmless when they wrapped a
  blocking-but-not-loop-touching `openai.OpenAI()` call, but exactly the
  Slice 1 `asyncio.run()`-inside-a-running-loop crash waiting to happen
  once `interpret`/`classify` became `asyncio.run()`-bridged sync
  facades over an async `Agent.run`. Caught before shipping (see Slice
  1's own writeup of the same bug class) — `_resolve_image_upload` now
  calls `classify_async`/`interpret_async` instead.
* New tests: `tests/test_classify_image_use_case.py`,
  `tests/test_interpret_diagram_image_use_case.py`,
  `tests/test_infrastructure_image_classifier_agent.py`,
  `tests/test_infrastructure_diagram_image_interpreter_agent.py`
  (Agent Framework adapters with the underlying `Agent`/
  `OpenAIChatClient` faked out — no real network call, no Azure
  credentials needed), `tests/test_infrastructure_vision_support.py`
  (the shared image-`Content` helper's extension-to-MIME-type mapping),
  `tests/test_vision.py` (new — the facade classes had no dedicated test
  file before this slice), and `tests/test_requirements_routes.py`'s
  `fakes()` fixture updated to wire `classify_async`/`interpret_async`
  the same way it already wired `analyze_async` in Slice 1.

**Slice 4 (done) — Move `app/design/models.py` into `app/domain/`:**

* `app/domain/design.py` (new) — `DesignComponent`, `DesignInterface`,
  `ExternalDependency`, `DesignAssumption`, `DesignQuestion`,
  `SystemDesignArtifact`, `ApprovalDecision`, moved out of
  `app/design/models.py` verbatim — the architecture/design bounded
  context's own home, alongside Slice 1's
  `app.domain.requirements`. `app/design/models.py` became a deprecated
  re-export shim at this point, the same "strangler fig" shape
  `app/models.py` used for `app.domain.requirements` — every existing
  importer kept working unchanged without needing to change in this
  same slice.
* `app/application/ports.py`, `app/application/use_cases
  /generate_system_design.py`, `app/application/use_cases
  /interpret_diagram_image.py`, `app/infrastructure/agents
  /system_design_agent.py`, and `app/infrastructure/agents
  /diagram_image_interpreter_agent.py` — the five application/
  infrastructure-layer modules introduced by Slices 2–3 that needed
  `SystemDesignArtifact` — started importing it from `app.domain.design`
  directly instead of through the `app.design.models` shim at this
  point, resolving `ports.py`'s previous "deliberate, temporary
  compromise" comment (importing a not-yet-domain module from the
  application layer). No other importer was touched in this slice —
  updating every remaining call site happened in Slice 5 below.
* No test or behavior changes: this slice was a pure move-plus-shim, and
  the existing suite already covered it transitively.

**Slice 5 (done) — Migrate every remaining importer off `app/models.py`
and `app/design/models.py`, then delete both shims:**

* Every one of the ~20 remaining importers of `app.models`/
  `app.design.models` — `app/api/routes/artifacts.py`,
  `app/api/routes/requirements.py`, `app/design/analyzer.py`,
  `app/design/comparison.py`, `app/design/diagram.py`,
  `app/design/session.py`, `app/design/validator.py`,
  `app/infrastructure/session_store.py`, `app/main.py`,
  `app/mcp/server.py`, `app/session.py`, `app/storage.py`,
  `app/vision.py`, and every test file that imported either shim —
  switched to importing `RequirementsArtifact`/`StoredArtifact`
  directly from `app.domain.requirements` and
  `SystemDesignArtifact`/`DesignComponent`/etc. directly from
  `app.domain.design`. Two importers used relative imports
  (`app/design/session.py`'s `from ..models import ...`/
  `from .models import ...` and `app/session.py`'s `from .models
  import ...`) rather than the absolute `from app.models import ...`
  form the rest of the codebase used — easy to miss with a naive
  text search, caught by actually running the test suite after the
  shims were deleted (`ModuleNotFoundError: No module named
  'app.models'`) rather than trusting the grep alone.
* `app/models.py` and `app/design/models.py` — deleted. Every entity
  either module ever defined now has exactly one home
  (`app.domain.requirements` or `app.domain.design`), with no
  re-export indirection left anywhere in the codebase.
* No behavior change — this was a mechanical import-path migration.
  Every existing test kept its own assertions unchanged; only their
  `import` lines moved. `python3 -m ruff check --select I --fix .` was
  run once at the end to re-sort import blocks disturbed by the module
  path change, rather than hand-fixing each file's import ordering.
* Verified the shims were actually gone from every layer, not just
  "probably fine": grepped for `app.models`/`app.design.models` (and
  their relative-import spellings) across `app/` and `tests/` after
  the edits, found zero remaining references outside historical
  docstring mentions (`app/domain/requirements.py`/`app/domain
  /design.py` note, in past tense, that the shims used to exist), then
  ran the full `pytest`/`ruff`/`mypy --strict`/`pyright` suite clean.

**Slice 6 (done) — Migrate `app/analyzer.py`/`app/design/analyzer.py`/
`app/vision.py`'s call sites onto their use cases directly, then delete
all three facade modules:**

* `app/infrastructure/composition.py` (new) — the composition root each
  facade's own `__init__` used to be. Four functions
  (`build_requirements_use_case`/`build_system_design_use_case`/
  `build_image_classifier_use_case`/`build_diagram_interpreter_use_case`),
  each reading `AZURE_OPENAI_API_KEY`/`AZURE_OPENAI_ENDPOINT`/
  `AZURE_OPENAI_MODEL` from the environment (via the same
  "require this var or raise" helper, defined once instead of copy-pasted
  three times across the old facades) and returning a ready-to-use
  `AnalyzeRequirementsUseCase`/`GenerateSystemDesignUseCase`/
  `ClassifyImageUseCase`/`InterpretDiagramImageUseCase` wired to a real
  `AgentFrameworkXAgent` adapter. `app/api/dependencies.py`,
  `app/mcp/server.py`, and `app/main.py` each call into this module now
  instead of constructing a facade class.
* `app/infrastructure/sync_bridge.py` (new) — `run_sync(coro, *,
  caller)`, the one remaining piece every facade duplicated: the
  `asyncio.get_running_loop()` guard (raising a clear `RuntimeError`
  instead of `asyncio.run()`'s confusing nested-loop crash) plus the
  `asyncio.run(...)` call itself. Every use case now exposes exactly one
  method, async `execute(...)` — no more sync/async method pairs to keep
  in sync per facade — and a caller that isn't itself `async` reaches it
  through this one bridge function instead.
* `app/session.py`'s `DesignSession` and `app/design/session.py`'s
  `ArchitectureSession` — previously typed against the facade classes
  (`RequirementsAnalyzer`/`SystemDesignAnalyzer`) — now type against
  `AnalyzeRequirementsUseCase`/`GenerateSystemDesignUseCase` directly,
  and their own `analyze()`/`generate()` methods (still synchronous, by
  design — the CLI and the sync FastAPI routes that construct them have
  no event loop of their own) call the use case's `execute()` through
  `run_sync` internally instead of a facade's own `analyze()`.
* `app/api/dependencies.py` — `get_requirements_analyzer`/
  `get_design_analyzer`/`get_image_classifier`/`get_diagram_interpreter`
  keep their names (so `app.dependency_overrides` call sites in tests
  didn't need to change) but now return the real use case, built by
  `app.infrastructure.composition`, instead of constructing a facade.
  `ArchitectureGenerationDependencies`/`RequirementsUploadDependencies`/
  `ImageUploadDependencies` retyped their analyzer/classifier/interpreter
  fields to the corresponding use case type.
* `app/api/routes/requirements.py` — the two sync routes (`start_run`/
  `refine_run`) now call `run_sync(analyzer.execute(...), caller=...)`
  instead of the facade's sync `analyze()`; the already-`async def`
  routes/helpers (`start_run_from_upload`/`refine_run_from_upload`/
  `_resolve_image_upload`) now `await analyzer.execute(...)` /
  `await classifier.execute(...)` / `await diagram_interpreter.execute(
  ...)` directly instead of the facades' `..._async` methods.
  `accept_run`/`refine_architecture` needed no change beyond the
  dependency's new type — they already just passed `deps.analyzer`
  through to `ArchitectureSession`, which does its own sync-bridging
  internally.
* `app/mcp/server.py` — its module-level `_requirements_analyzer`/
  `_design_analyzer` singletons are now built by
  `app.infrastructure.composition` instead of constructing a facade
  directly, and every tool function calls `run_sync(..._analyzer.execute(
  ...), caller=...)` instead of the facade's sync `analyze()`.
* `DesignGenerationError`/`ImageClassificationError`/
  `DiagramInterpretationError`/`ImageClassification` — every importer
  that used to pull these off the facade modules' re-exports
  (`app/design/analyzer.py`'s `__all__`, `app/vision.py`'s `__all__`)
  now imports them from their real homes,
  `app.application.errors`/`app.domain.vision`, directly.
* `app/analyzer.py`, `app/design/analyzer.py`, and `app/vision.py` —
  deleted. Every call site now depends on `app.application.use_cases.*`
  + `app.infrastructure.composition` instead of a facade.
* Tests: `tests/test_analyzer.py`, `tests/test_design_analyzer.py`, and
  `tests/test_vision.py` were deleted rather than updated — each only
  exercised the deleted facade's own sync/async-bridging behavior around
  a fake port, which `tests/test_analyze_requirements_use_case.py`/
  `tests/test_generate_system_design_use_case.py`/
  `tests/test_classify_image_use_case.py`/
  `tests/test_interpret_diagram_image_use_case.py` already cover at the
  use-case level. The sync-bridging behavior itself moved to
  `tests/test_infrastructure_sync_bridge.py` (new) — `run_sync`'s
  happy path and its running-event-loop guard, tested once instead of
  once per facade. `tests/test_refinement.py` and `tests/test_mcp.py`
  were updated in place (mock/fake `.analyze`/`._use_case.agent` access
  renamed to `.execute`/`.agent`) since they test real collaborators
  (`DesignSession`, the MCP tool functions) that still exist.
  `tests/test_requirements_routes.py`'s and `tests/test_rbac.py`'s
  `fakes()` fixtures collapsed each service's `.analyze`/`.analyze_async`
  (or `.classify`/`.classify_async`, `.interpret`/`.interpret_async`)
  mock-method pair down to a single `AsyncMock`-backed `.execute` — every
  test that configured `.analyze.return_value`/`.side_effect` etc. was
  updated to configure `.execute` instead (mechanical rename, no
  assertion logic changed, since the parameter names on `execute` match
  the old `analyze`/`classify`/`interpret` methods exactly).
* Verified with the same rigor as Slice 5: grepped for
  `app.analyzer`/`app.design.analyzer`/`app.vision` (and relative-import
  spellings) across `app/` and `tests/` after the edits, confirmed the
  only remaining hits are historical, past-tense docstring/comment
  mentions (e.g. `app/infrastructure/agents/vision_support.py` noting
  what `app.vision._data_url` used to do), then ran the full
  `pytest`/`ruff`/`mypy --strict`/`pyright` suite clean.

**What's temporarily duplicated/deprecated on purpose** (strangler fig,
not sloppiness — each would have been removed in a later slice once
nothing imported the old path): nothing, as of Slice 6 — the last three
facade modules (`app/analyzer.py`, `app/design/analyzer.py`,
`app/vision.py`) were deleted in that slice. Slices 7 and 8 were pure
new-abstraction work (ports for storage/diagram rendering), not
strangler-fig cleanup.

**Slice 7 (done) — Ports + adapters for storage:**

* `app/application/ports.py` gained `ArtifactStorePort` (every method
  `app/infrastructure/artifact_store.py`'s `ArtifactStore` exposes:
  `save`, the requirements/design version listing and JSON/SVG getters,
  `save_design_json`/`save_design_svg`, both `delete_design_*` methods,
  `save_source_file`/`get_source_file`, and `close`) and
  `SessionStorePort` (`create`/`get`/`upsert`/`list_for_owner`/`list_all`
  — the same shape the `SessionStore` `Protocol` that used to live in
  `app/infrastructure/session_store.py` already had, moved rather than
  redesigned). Both are synchronous, like every other port so far —
  nothing in this project's call sites needs an async storage call badly
  enough to justify it, and both concrete adapters already wrap
  synchronous SDKs.
* `app/domain/session.py` (new) — `SessionRecord`, moved out of
  `app/infrastructure/session_store.py` verbatim. One honest compromise
  documented inline rather than hidden: `SessionRecord.etag` (a Cosmos
  optimistic-concurrency token) and `to_item()` (a Cosmos document
  serializer) are infrastructure-flavored fields on an otherwise-pure
  domain entity. They stayed rather than being split into a separate
  infrastructure-only wrapper type, because splitting them would mean
  either every route also imports an infrastructure-only type just to
  thread a value it never reads, or `SessionStorePort` doing that
  threading itself — neither reads as clearer than accepting one
  concurrency-token field as domain-adjacent plumbing (see the module's
  own docstring for the fuller version of this reasoning).
* `app/application/errors.py` gained `ArtifactVersionConflict` (moved out
  of `app/storage.py`) and `SessionConflictError` (moved out of
  `app/infrastructure/session_store.py`), the same "error types live in
  `app.application`, not on the infrastructure module that used to raise
  them" pattern every prior slice's error types already followed.
* `app/storage.py` moved, verbatim aside from its imports, to
  `app/infrastructure/artifact_store.py` — `ArtifactStore` is now the
  concrete `ArtifactStorePort` implementation, sitting next to
  `app/infrastructure/session_store.py`'s `CosmosSessionStore` (the
  concrete `SessionStorePort` implementation) rather than at the top
  level of `app/`. `app/infrastructure/session_store.py` itself shrank to
  just `CosmosSessionStore` — its module docstring explains why the
  entity and port/error types it used to define all moved out.
* Every presentation-layer call site that used to type a parameter as
  the concrete `ArtifactStore`/`SessionStore` now types it as
  `ArtifactStorePort`/`SessionStorePort` instead:
  `app/api/dependencies.py` (`get_artifact_store`/`get_session_store`
  and all three dependency-bundle dataclasses), `app/api/ownership.py`
  (`load_owned`), `app/api/routes/requirements.py`,
  `app/api/routes/artifacts.py`, `app/session.py`'s `DesignSession`, and
  `app/design/session.py`'s `ArchitectureSession` (whose own narrow,
  locally-defined `DesignStore` `Protocol` — a strict subset of
  `ArtifactStorePort` — was deleted in favor of depending on the real
  port directly, once one existed to depend on). `app/web/main.py`,
  `app/main.py`, and `app/mcp/server.py` construct the concrete
  `ArtifactStore`/`CosmosSessionStore` adapters at their own composition
  roots exactly as before — only the *type* other layers see changed,
  not who constructs the real thing.
* Also fixed in this slice, found while sweeping for staleness rather
  than being this slice's main goal: `app/application/use_cases
  /classify_image.py` gained back the "document vs. diagram" module
  docstring that used to live on the now-deleted `app/vision.py` — Slice
  6 deleted that file without migrating its most useful piece of
  documentation, leaving `ClassifyImageUseCase`/
  `InterpretDiagramImageUseCase` with a one-line docstring apiece and no
  explanation of the wider problem they solve together.
* Tests: `tests/test_storage.py` renamed to `tests/test_artifact_store.py`
  (matching `tests/test_session_store.py`'s naming for the storage
  adapter it now sits beside) and its `@patch("app.storage...")` targets
  updated to `app.infrastructure.artifact_store`.
  `tests/test_design_storage.py`, `tests/test_session_store.py`,
  `tests/test_artifacts_routes.py`, `tests/test_ownership.py`,
  `tests/test_rbac.py`, and `tests/test_requirements_routes.py` had their
  `SessionRecord`/`SessionConflictError` imports switched from
  `app.infrastructure.session_store` to `app.domain.session`/
  `app.application.errors` respectively — no assertion logic changed,
  since these are the same classes at new import paths.
* Verified the same way as Slices 5–6: grepped for `app.storage`/
  `from app.infrastructure.session_store import` (beyond
  `CosmosSessionStore`) across `app/` and `tests/` after the edits,
  confirmed zero remaining hits, then ran the full
  `pytest`/`ruff`/`mypy --strict`/`pyright` suite clean.

**Slice 8 (done) — Diagram generation as a port:**

* `app/application/ports.py` gained `DiagramRendererPort` (one method,
  `generate(design: SystemDesignArtifact) -> str`). Unlike every other
  port added in this migration, its concrete implementation
  (`app.design.diagram.ArchitectureDiagramGenerator`) isn't built via
  `app/infrastructure/composition.py` — rendering needs no credentials
  or environment configuration to wire up, so each call site
  (`app/main.py`, `app/api/dependencies.py`, `app/mcp/server.py`)
  keeps constructing `ArchitectureDiagramGenerator()` directly, same as
  before. The port exists so `app.design.session.ArchitectureSession`
  (and anything else that renders a design) depends on "something that
  can render a design" rather than on Graphviz specifically — not to
  hide how the real one gets built.
* `app/application/errors.py` gained `DiagramGenerationError`, moved
  out of `app/design/diagram.py` (previously defined and raised in the
  same module) so it lives alongside every other application-layer
  error type rather than being the one exception a presentation-layer
  caller (`app/main.py`) had to reach into `app.design.diagram` for.
* `app/design/diagram.py` — `ArchitectureDiagramGenerator`'s class
  docstring now states it's the concrete `DiagramRendererPort`
  implementation, satisfied structurally (no inheritance).
* `app/design/session.py` — `ArchitectureSession.__init__`'s
  `diagram_generator` parameter retyped from `ArchitectureDiagramGenerator`
  to `DiagramRendererPort`; the now-unused concrete import was dropped.
* `app/api/dependencies.py` — `get_diagram_generator` retyped to return
  `DiagramRendererPort`; both dependency-bundle dataclasses
  (`ArchitectureGenerationDependencies`, `ImageUploadDependencies`) and
  their `Depends(...)` parameters retyped from
  `ArchitectureDiagramGenerator` to `DiagramRendererPort`.
* `app/main.py` — `DiagramGenerationError` now imported from
  `app.application.errors` alongside `DesignGenerationError`, instead of
  from `app.design.diagram`.
* No test changes were needed: every existing test that exercises a
  diagram generator does so through a `MagicMock()` dependency override
  (`tests/test_requirements_routes.py`, `tests/test_rbac.py`,
  `tests/test_artifacts_routes.py`) or the real
  `ArchitectureDiagramGenerator` directly
  (`tests/test_design_diagram.py`) — neither cares about the type
  annotation on the parameter it's satisfying, so retyping call sites
  to the port didn't require touching either.
* Verified the same way as every prior slice: grepped for
  `DiagramGenerationError` across `app/` and confirmed the only
  remaining references are its new home
  (`app/application/errors.py`) and its one still-valid import
  (`app/main.py`), then ran the full
  `pytest`/`ruff`/`mypy --strict`/`pyright` suite clean.

This closes out the Clean Architecture migration — all 8 planned slices
are done. Each shipped the same way: real code backed by a verified
library API (not just documentation — Microsoft's own docs disagreed
with each other about `agent_framework` class names across pages during
this migration; the installed package was checked directly with
`python -c "import agent_framework; ..."` to confirm), full test
coverage with fakes at the port boundary (no real network calls in unit
tests), a green `pytest`/`ruff`/`mypy --strict`/`pyright` run, and this
README updated in the same round — not deferred to "later."

---

## 1. Architecture Refinement

**Done.** Users can refine an existing architecture without regenerating
the entire design from scratch, via `POST .../refine-architecture` (web
API) or `refine_architecture` (MCP) — see those sections above for the
full contract. Implementation:

```text
Existing Architecture (+ Requirements)
        │
        ▼
Refinement Request (free-text)
        │
        ▼
System Design Analyzer
  (GenerateSystemDesignUseCase.execute,
   previous_design + refinement_input)
        │
        ▼
Architecture Validator
        │
        ▼
New Architecture Version (design_version + 1)
```

Capabilities:

* Modify individual components — the refinement prompt instructs the model
  to preserve still-valid components/interfaces/dependencies and prefer
  adjusting over wholesale regeneration, so IDs stay stable across a
  refinement wherever possible.
* Add or remove components
* Modify interfaces
* Modify external dependencies
* Preserve unaffected architecture decisions (best-effort, prompt-driven —
  not structurally enforced; see "What's deliberately not covered yet"
  below)
* Generate a new architecture version — `ArchitectureSession.generate`
  accepts a `version` to continue from, so each refinement bumps
  `design_version` rather than restarting it at 1
* Validate the complete resulting architecture — the same
  `ArchitectureValidator` used on the initial `accept`, not a partial or
  incremental check

**What's deliberately not covered yet:** the "preserve unaffected
decisions" behavior is entirely prompt-driven (the model is instructed not
to silently remove or rename existing IDs) rather than structurally
enforced — there's no diff/merge step confirming the previous
architecture's untouched parts survived byte-for-byte. A refinement can
still be rejected by `ArchitectureValidator` after generation (e.g. if the
model breaks a reference), in which case the session reverts to the
previous, still-valid `"architecture"` stage rather than corrupting it —
but nothing here guarantees minimal-diff output beyond what the prompt
asks for.

---

## 2. Architecture Version Comparison

**Done**, on both sides now:

* **Frontend (client-side).** Pick two persisted versions (via
  `app/api/routes/artifacts.py`) and `VersionBar`/`DiffList` render a
  side-by-side added/removed/changed field diff for every list field on
  both artifacts, computed in the browser (`frontend/src/lib/diff.ts`'s
  `diffByKey`). Unchanged since this was first written; still what the
  frontend itself uses.
* **Backend (structured, any client).**
  `GET /requirements-runs/{id}/architecture/compare?from={v}&to={v}`
  (`app/api/routes/artifacts.py`'s `compare_architecture_versions`,
  comparison logic in `app/design/comparison.py`) computes the same kind
  of id-keyed added/removed/changed/unchanged diff server-side, over
  `components`, `interfaces`, `external_dependencies`, `assumptions`, and
  `open_questions`, plus a before/after `architecture_summary` with a
  `architecture_summary_changed` flag — as a typed `ArchitectureComparison`
  response any client (an MCP client, a script, a different UI) can
  consume without re-implementing the comparison itself, no full-artifact
  fetch-and-diff round trip required. 404s if either version isn't stored
  for the session, the same way `GET .../architecture/{version}` does.

```text
Design v1 ──┐
            │  GET .../architecture/compare?from=1&to=2
Design v2 ──┘         │
                       ▼
         ArchitectureComparison
           (added/removed/changed/unchanged
            per field, id-keyed)
```

Example response shape:

```json
{
  "from_version": 1,
  "to_version": 2,
  "architecture_summary_changed": true,
  "from_architecture_summary": "...",
  "to_architecture_summary": "...",
  "components": {
    "added": [{"id": "C-003", "name": "DocumentProcessor", "...": "..."}],
    "removed": [{"id": "C-002", "name": "LegacyProcessor", "...": "..."}],
    "changed": [{"before": {"...": "..."}, "after": {"...": "..."}}],
    "unchanged": ["..."]
  },
  "interfaces": {"added": [], "removed": [], "changed": [], "unchanged": ["..."]},
  "external_dependencies": {"added": ["..."], "removed": [], "changed": [], "unchanged": []},
  "assumptions": {"added": [], "removed": [], "changed": [], "unchanged": ["..."]},
  "open_questions": {"added": [], "removed": [], "changed": [], "unchanged": ["..."]}
}
```

**What this doesn't do:** equality is purely structural (byte-for-byte
field comparison, mirroring the frontend's own `diffByKey`/JSON-stringify
approach) — it has no notion of a "renamed" component, which shows up as a
remove-plus-add pair rather than a rename, and there's no separate
requirement-traceability-specific view (that's `requirement_ids` fields
inside each added/removed/changed component/interface, not surfaced as
its own top-level diff section). Not wired into the frontend or MCP yet
either — the frontend still uses its own client-side diff, and there's no
`compare_architectures` MCP tool (see the "MCP Tool Expansion" section).

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

**Done**, in a simpler shape than originally sketched below (kept for
context on what was considered and why the simpler version was chosen).

Implemented:

* `SessionRecord.approval_status` — `"pending"` | `"approved"` |
  `"rejected"`, only meaningful once `stage == "architecture"`. Reset to
  `"pending"` every time `design_version` changes (on `accept` and on
  every `refine-architecture`), so a stale decision from a *previous*
  design version is never misread as covering the current one.
* `SessionRecord.approval_history` — an `ApprovalDecision` (`decision`,
  `architecture_version`, `reason`, `decided_by`, `decided_at`) appended
  on every decision, oldest first. Append-only: a later refinement resets
  `approval_status` but never rewrites or removes history, so the full
  reject → refine → approve trail survives.
* `POST /requirements-runs/{id}/approve` / `POST .../reject` — record a
  decision against the *current* architecture version, both accepting an
  optional free-text `reason`. Valid only once `stage == "architecture"`.
  Both are re-callable — approve again after a reject (or to record a
  second reviewer's sign-off), or reject after an approve — each call
  appends a new history entry rather than erroring on a second decision.
* Rejection is deliberately **not** a dead end: unlike a failed
  `accept`/`refine-architecture` (which reverts `stage`), `reject` leaves
  `stage` and the persisted design untouched — it's a human judgment call,
  not a generation failure — so `refine-architecture` still works
  immediately afterward. The intended loop is reject → refine → re-approve.
* Frontend: an approval-status pill next to the conversation status pill,
  and Approve/Reject buttons alongside "Accept & generate architecture"
  once a session reaches the architecture stage (`Conversation.tsx`,
  wired up in `Workspace.tsx`'s `handleApprove`/`handleReject`).

What was considered and deliberately left out, to keep the first version
small:

* **No `draft`/`validated`/`review`/`superseded` states** — `stage` (from
  the existing requirements→architecture flow) already distinguishes
  "not generated yet" from "generated"; layering a second, largely
  redundant state machine on top wasn't worth the complexity for what's
  fundamentally a yes/no decision per design version.
* **No MCP tool.** MCP tools here are stateless (see the "MCP" section) —
  approving/rejecting mutates a persisted `SessionRecord`, which the MCP
  layer has no access to today (same gap as `get_architecture`/
  `compare_architectures`, not something specific to approval).
* **No enforcement anywhere else in the system** — an "approved" status
  doesn't currently gate anything (there's no downstream consumer yet to
  gate). It's a recorded decision, not (yet) a permission check.

---

## File Upload for Requirements Scanning

**Done.**

Lets requirements come from an uploaded document — PDF, DOCX, PNG, JPG,
JPEG, or TXT — instead of only typed free text.

Implemented:

* `app/ingestion.py` — `RequirementsDocumentExtractor.extract(filename,
  content: bytes) -> str`. `.txt` is decoded directly (UTF-8); every other
  supported format (PDF/DOCX/PNG/JPG/JPEG) is routed through Azure AI
  Document Intelligence's `prebuilt-read` model — one shared OCR +
  layout-aware extraction path instead of a separate library per format
  (`pypdf`, `python-docx`, `pytesseract`, ...). Whatever text comes out
  feeds into `AnalyzeRequirementsUseCase.execute()` exactly like typed
  input — the rest of the requirements pipeline doesn't know or care
  whether its input was typed or extracted from a document.
* The Document Intelligence client is built **lazily**, on first actual
  use — unlike `AZURE_OPENAI_*`, which
  `app/infrastructure/composition.py` requires eagerly whenever one of
  its `build_*_use_case` functions runs (at composition-root call time,
  not at import time — see "Clean Architecture Migration" → Slice 6).
  File upload is optional and additive: a deployment that
  only ever uses typed text input must keep working without
  `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`/`AZURE_DOCUMENT_INTELLIGENCE_KEY`
  configured at all.
* `POST /requirements-runs/upload` / `POST .../{id}/refine/upload` — sibling
  multipart routes to the existing JSON-body `POST /requirements-runs` /
  `POST .../{id}/refine`. Separate routes rather than an optional field on
  the existing ones, because FastAPI can't mix a JSON body with
  `UploadFile`/`Form` multipart parsing on one route. Both accept an
  optional `notes` form field, appended after the extracted document text
  before analysis. `refine/upload` is only valid in `STAGE_REQUIREMENTS`,
  same as the typed-text `refine` route.
* The original uploaded file is persisted, not just its extracted text:
  `ArtifactStore.save_source_file`/`get_source_file` (blob name
  `v{version}_source{ext}`, listed by prefix since the extension varies
  per upload) store it in Blob Storage alongside the existing
  requirements/design artifacts. `GET /requirements-runs/{id}/source-file`
  downloads it back; 404s if the current requirements version came from
  typed text instead. `SessionRecord.source_filename` (reset to `None` on
  a typed-text `refine`, so it never misdescribes a later version) tracks
  which version, if any, came from a file.
* Frontend: a **Scan a file** button next to Send, shown while the session
  is still in (or hasn't reached) the requirements stage, opening a
  file picker restricted to the supported extensions. Whatever's typed in
  the textarea at the time is sent as `notes`. A dashed **Source:
  `<filename>`** pill next to the status pill shows when the current
  version came from a file.

What was considered and deliberately left out:

* **One shared extraction service instead of per-format libraries** — the
  user's explicit direction ("use Azure AI Document Intelligence wherever
  possible") was extended from images (what the original question asked
  about) to PDF and DOCX too, since `prebuilt-read` handles all of them
  uniformly and a single service is simpler to operate and reason about
  than `pypdf` + `python-docx` + `pytesseract` each with their own failure
  modes.
* **No MCP tool.** Same reasoning as the human approval workflow above:
  MCP tools here are stateless (no `session_id`-based blob access), so a
  file-scanning MCP tool would need a different shape entirely (raw file
  bytes/base64 in the request, mirroring `analyze_requirements`'s
  stateless design) rather than reusing the web API's session-based
  upload routes as-is. Left for a future MCP tool if a client actually
  needs it.
* **Legacy binary `.doc` is not supported** — only `.docx`. If your
  Document Intelligence resource is pinned to an older API version that
  doesn't yet accept `.docx` as an input format, DOCX extraction fails
  with a clear `DocumentExtractionError`; convert to PDF first as a
  workaround.

---

## Image Input Classification

**Done.**

An uploaded PNG/JPG/JPEG could mean two very different things: a
screenshot/photo of *text* meant to be read (requirements notes, a spec,
a whiteboard of bullet points), or a photo/screenshot of a *system
design or workflow diagram* — boxes and arrows depicting components and
data flow — meant to be understood structurally rather than read as
prose. Running OCR + requirements analysis on the latter would, at best,
transcribe box labels as if they were requirements text. This feature
classifies every uploaded image first and routes it accordingly:

* A **document** screenshot → processed exactly as before (OCR via
  Document Intelligence → `AnalyzeRequirementsUseCase`).
* A **diagram** → redrawn directly into a clean, well-architected system
  design and dropped straight into the architecture stage, skipping
  typed/extracted requirements text entirely.

Implemented:

* `ClassifyImageUseCase.execute(content, filename) -> ImageClassification`
  (`kind: "document" | "diagram"` plus a one-sentence `reasoning`) and
  `InterpretDiagramImageUseCase.execute(...) -> SystemDesignArtifact`
  against the same vision-capable `AZURE_OPENAI_MODEL` deployment every
  other use case already requires — no new environment variable. As of
  Clean Architecture Migration Slice 6 (see "Next Steps" → "Clean
  Architecture Migration"), both are pure orchestration against
  `ImageClassifierPort`/`DiagramImageInterpreterPort`, implemented by
  Microsoft Agent Framework `Agent`s
  (`app/infrastructure/agents/image_classifier_agent.py` /
  `diagram_image_interpreter_agent.py`) rather than a direct Azure
  OpenAI Responses API call — multimodal input goes through an
  `agent_framework.Message` mixing a text `Content` part with an image
  `Content` part, instead of `input_text`/`input_image` Responses API
  content items. `InterpretDiagramImageUseCase` reuses the exact
  `SystemDesignArtifact` schema `GenerateSystemDesignUseCase` produces
  from text, so an image-derived design is indistinguishable downstream
  (validation, diagram rendering, versioning, refinement, approval) from
  a text-derived one. It also supports refinement: passing the session's
  `previous_design` treats a later diagram upload as amending that
  design rather than replacing it outright, mirroring
  `GenerateSystemDesignUseCase.execute`'s "preserve what's still valid"
  contract.
* `app/ingestion.py` — `is_image_filename()` identifies which uploads
  (`.png`/`.jpg`/`.jpeg`) are eligible for classification before falling
  into the existing extraction path.
* `app/design/session.py` — `ArchitectureSession.generate()` was split
  into `generate()` (analyze requirements text → design) and
  `generate_from_design()` (validate → render → persist), so a
  diagram-derived design can go through the exact same
  validate/render/persist tail as a text-derived one without a parallel,
  divergent copy of that logic.
* `POST /requirements-runs/upload` / `POST .../{id}/refine/upload` — the
  same upload routes from "File Upload for Requirements Scanning" above
  now branch on `is_image_filename()`. A classified `"document"` image
  proceeds through the pre-existing OCR pipeline unchanged. A classified
  `"diagram"` image skips straight to `ArchitectureSession
  .generate_from_design()`: the session's `stage` jumps directly to
  `architecture`, `approval_status` resets to `pending`, and a stub
  `RequirementsArtifact` (empty requirement lists, a summary noting the
  session started from a diagram upload) backfills the requirements slot
  so every existing reviewer-facing view that expects a
  `RequirementsArtifact` still has one to show. `refine/upload`'s
  existing `STAGE_REQUIREMENTS`-only gate runs *before* classification,
  so a diagram uploaded against a session already past that stage still
  gets the same 409 as a document upload would, rather than silently
  reclassifying an already-generated architecture.
* Classification/interpretation failures (`ImageClassificationError`,
  `DiagramInterpretationError` — e.g. Azure OpenAI is unreachable, or
  returns no parsed output) surface as `422`, matching how
  `DocumentExtractionError` is already handled for the document path.

What was considered and deliberately left out:

* **A user-facing override to force one classification or the other** —
  left out for now since the classifier's system prompt is deliberately
  conservative (text with a few incidental boxes/icons still counts as
  `"document"`); revisit if misclassifications turn out to be common in
  practice.
* **Multi-image uploads treated as one diagram** — each upload is
  classified and interpreted independently, same granularity as the
  existing single-file document upload routes.

---

## Architecture Diagram Clustering & Clutter Reduction

**Done.**

Diagrams for any design with more than a handful of components and
interfaces used to render as a "hairball": long, curved edges crossing
the whole page, no visual grouping between related components, and
inline edge-label text scattered everywhere. Root cause: every component
was forced into one flat, page-wide grid (to keep the whole diagram on
one printed page), and every real interface/dependency edge was drawn
with `constraint="false"` so it couldn't influence where its endpoints
landed — so two closely related components could land in unrelated
grid cells, and the edge between them had to arc across the entire page
to connect them.

Implemented, in order of impact:

* **Domain clustering** — `DesignComponent` gained an optional `domain`
  field (a short group/category name, e.g. "Client & Identity", "Data
  Platform"); `GenerateSystemDesignUseCase` and
  `InterpretDiagramImageUseCase` both prompt for it now — the latter
  reading it directly off any visible grouping/labeled sections in an uploaded
  diagram image, or inferring a small number of sensible domains when
  the image has none. `ArchitectureDiagramGenerator` renders each domain
  as its own labeled Graphviz cluster, so related components stay
  visually together and most real edges stay short. A blank `domain`
  (older designs, or anything constructing a `DesignComponent` directly)
  falls back to a single "Other Components" cluster rather than
  erroring.
* **No forced one-page layout** — the fixed `size`/`ratio="compress"`
  graph attributes are gone. The frontend's `DiagramViewer` already
  supports zoom/pan, so letting Graphviz size the SVG to its actual
  content produces straighter edges at the cost of not fitting on one
  unscaled printed page.
* **Real edges allowed to influence layout, within a domain** — an
  interface between two components in the *same* domain is no longer
  forced to `constraint="false"`; a cross-domain interface still is
  (letting it pull on rank assignment would fight the cluster
  boundaries instead of just being drawn as a longer arrow between two
  independently-laid-out groups).
* **Inline edge labels suppressed past a threshold** — above
  `ArchitectureDiagramGenerator.MAX_LABELED_EDGES` (24) total real
  edges, every edge's name is dropped from the rendered label text.
  Full detail remains available via each edge's `tooltip` (shown on
  hover), which the frontend already relies on.
* **Deduplicated dependency fan-in labels** — a dependency used by
  several components previously repeated its own name as the label on
  every incoming edge. Now only the first edge shows the name inline;
  the rest carry the same tooltip but no repeated label text.

What was discovered and worked around along the way:

* **A real `dot` crash, not just a design smell.** The first clustering
  implementation nested `rank=same` "row grid" subgraphs inside each
  domain's Graphviz cluster (to bound a domain's width). That
  combination — `rank=same` inside a cluster, on a graph with enough
  edges crossing between clusters — reliably crashes the installed
  Graphviz `dot` build (2.43.0) with `class2.c:148: merge_chain:
  Assertion 'ED_to_virt(e) == NULL' failed`, confirmed via local
  reproduction at roughly 40+ components / 60+ interfaces across
  several domains — well within what a real generated architecture can
  reach. The fix was to lay out each domain's components as a single
  top-to-bottom column instead (chained with ordinary directed
  invisible edges, not same-rank/"flat" ones), which doesn't trigger the
  bug at any tested scale (stress-tested up to 200 components / 300
  interfaces without a crash) and, as a side benefit, more closely
  matches how a typical hand-drawn reference architecture diagram
  stacks a section's components in a single column anyway.
* **Row-order pinning was dropped.** An earlier version of the (now
  removed) row-grid pinned left-to-right order within a row using
  invisible same-rank edges; that specific construct — a "flat" edge
  between same-rank nodes inside a cluster — turned out to be the
  crash trigger by itself, independent of the grid or clustering per
  se. Since the column layout replacing it has no same-rank grouping
  at all, there's nothing left to pin, and the cost of the earlier
  cosmetic guarantee (nodes always exactly in source order) is gone
  along with it — Graphviz's own layout decides top-to-bottom order,
  which in practice still tracks input order closely.
* **External dependencies are not clustered per-domain** — a dependency
  is often used by components across several domains (see
  `used_by_components`), so it has no single natural "home" domain.
  They get their own dedicated cluster instead, using the same column
  layout as domain clusters.

Later, to match a specific reference Azure architecture diagram style
requested directly (client apps → load balancer → AKS cluster →
databases, dashed VNet boundary), the layout changed again on top of the
column-per-cluster foundation above:

* **`rankdir="LR"`** — diagrams now flow left-to-right instead of
  top-to-bottom, matching how most hand-drawn/reference cloud
  architecture diagrams are read. The column-layout crash fix above was
  re-verified at scale (up to 20 domains / 300 interfaces) under `LR`
  before shipping it — the crash was tied to `rank=same` inside a
  cluster, not to `rankdir`, so switching direction didn't reopen it.
* **`splines="ortho"`** — edges are straight lines with right angles
  instead of curved splines, again matching the reference style. This
  has one non-obvious consequence: `dot` doesn't position a plain
  `label=` correctly on an orthogonal edge, so every edge's name moved
  to `xlabel=` instead (see "Diagram Icons" below for a similar
  Graphviz-quirk story on the node side).
* **Real Azure service icons per node** — see "Diagram Icons (Azure
  Architecture Icons)" directly below.

---

## Diagram Label Placement (No More Overlapping/Floating Text)

**Done.**

**Problem:** a real generated diagram was reported with two distinct
text-placement defects: an edge's name (`xlabel`) rendered directly on
top of a neighboring node's icon/caption, and — separately — another
edge's name rendered visibly disconnected from the line it named,
floating with no visual tie to its edge. Both trace back to `xlabel`
being Graphviz's "exterior label" — auto-placed near an edge without
reserving any layout space for it, unlike a real node.

**Investigation and rejected fix:** Graphviz's own `forcelabels` graph
attribute defaults to `true`, which places every `xlabel` "even if
there is some overlap with nodes or other labels" (straight from its
docs) — the direct cause of the overlap defect. Setting
`forcelabels="false"` looked like the obvious fix (`dot` drops a
conflicting label instead of forcing an overlapping placement), and
combined with the edge attribute `decorate="true"` (draws a connector
line from a placed label back to its edge) it also solved the floating
defect — confirmed visually against several reproduction diagrams,
including a scaled-up one matching the density of the originally
reported case. It was ultimately **rejected**, though: with
`rankdir="LR"` (required for this diagram's left-to-right flow), the
project's installed Graphviz version (`dot` 2.42/2.43) drops *every*
exterior label with `forcelabels="false"` set — reproduced down to a
trivial two-node, one-edge diagram with the entire canvas empty, so
it's a real layout-engine limitation tied to `rankdir="LR"`, not an
actual spacing/overlap problem (increasing `nodesep`/`ranksep` had zero
effect). Shipping it would have silently emptied every edge label on
every diagram.

**Fix actually shipped:** `ArchitectureDiagramGenerator._add_labeled_edge`
(`app/design/diagram.py`) splits a named edge into two:
`source -> label node -> target`, where the label node is a borderless,
fill-less `shape="plaintext"` node whose only content is the edge's
name. Because it's a real node, Graphviz's core layout — not the
exterior-label heuristic — reserves genuine rank/column space for it
and guarantees no other node overlaps it, exactly like every
component/dependency icon node already gets. It still visibly sits *on*
the connecting line (it has a real inbound and outbound edge segment
either side of it), so it reads unambiguously as that interface's name
rather than a floating annotation — no `decorate` trick needed. An
unnamed edge (name suppressed past `MAX_LABELED_EDGES`, or a dependency
edge past the first into a shared dependency) still renders as a single
plain edge, unchanged. See `_add_labeled_edge`'s docstring for the full
investigation, and `test_diagram_labeled_interface_uses_a_label_node_not_an_xlabel`
in `tests/test_design_diagram.py` for the regression test.

As a side effect, this also fixed a hidden reliability issue the
`forcelabels`/`xlabel` approach never surfaced clearly: on denser
diagrams, `dot`'s exterior-label placement can silently drop a
majority of labels even when `forcelabels="true"` finds no fully clear
spot for them (it just overlaps instead). The label-node approach never
drops a name — every interface/dependency name that should be shown is
shown, every time.

---

## Diagram Icons (Azure Architecture Icons)

**Done.**

Nodes used to render as plain boxes with just an id/name label — clear,
but nothing like a real architecture diagram, where every component is
instantly recognizable by its cloud service icon (the AKS logo, a SQL
Database cylinder, the Key Vault key, and so on). `ArchitectureDiagramGenerator`
now renders every component and external dependency with a real Azure
Architecture Icon above its `{id}\n{name}` caption.

**Where the icons came from.** Rather than add a heavyweight runtime
dependency, a curated set of ~23 PNGs was vendored directly into the
repo under `app/design/icons/azure/`, sourced once from the MIT-licensed
`diagrams` Python package's bundled icon resources (it ships Microsoft's
official Azure Architecture Icons under `resources/azure/...`). `diagrams`
itself was installed only temporarily to copy the files out — it is
**not** a project dependency and does not appear in `requirements.txt`.
Each file was renamed to a short, stable slug (e.g. `key-vault.png`,
`kubernetes.png`) decoupled from `diagrams`' internal path layout, so the
icon set can be swapped for a different source later without touching
`app/design/icons.py`. Full provenance and the slug → original-path
mapping is documented in `app/design/icons/azure/NOTICE.md`.

**How a component/dependency picks its icon.** `app/design/icons.py`
matches a component's `name` and `responsibility` (or a dependency's
`name` and `purpose`) against an ordered keyword table
(`_KEYWORD_ICON_MAP`), falling back to a generic "service"/"external
dependency" icon when nothing matches — every node gets *some* icon
rather than mixing icon and plain-box nodes in one diagram. Two real
mismatches were found via visual inspection of rendered test diagrams
(not caught by unit tests alone) and fixed by (a) checking a node's
`name` against every keyword in a first full pass before ever looking at
its responsibility/purpose text, and (b) reordering the keyword table so
specific multi-word phrases are checked before generic single-word
fallbacks:

* An external dependency named "Key Vault" with purpose "Secret
  storage." rendered with a generic blob-storage icon, because the
  generic keyword `"storage"` matched inside the purpose text before the
  more specific `"key vault"`/`"secret"` keywords were ever reached.
* A component named "CI/CD Pipeline" with a responsibility mentioning
  "container images" rendered with a generic container icon instead of
  the pipeline icon, for the same reason (`"container"` matched before
  `"pipeline"`).

Both are now locked in as regression tests in `tests/test_design_icons.py`.

**Two Graphviz rendering quirks found and fixed along the way:**

* **Image + label overlap on `shape="none"` nodes.** Setting both
  `image=` and `label=` on a plain `shape="none"` node does not reserve
  separate vertical space for the two — the caption text renders
  overlapping the icon regardless of `labelloc`, in this Graphviz build.
  Fixed by switching every node to an HTML-like label (`label="<<TABLE>
  ...</TABLE>>"`): one table row holds the icon (`<IMG SRC=...>`), a
  second row holds the `{id}\n{name}` caption, which lays out correctly.
  Confirmed visually by rendering generated SVGs to PNG with `cairosvg`
  and inspecting them directly.
* **Local file paths don't survive into a browser-rendered SVG.**
  Graphviz's SVG output references a node's icon by its literal
  filesystem path (`xlink:href="/abs/path/icon.png"`), which resolves
  fine when `dot` renders it locally but fails once that same SVG is
  stored as an artifact and rendered client-side in the frontend's
  `DiagramViewer.tsx` — the browser has no access to the backend's
  filesystem. Fixed with a post-processing step
  (`_inline_local_images`) that replaces every such
  `xlink:href`/`href` attribute pointing at a local `.png` with a
  base64 `data:image/png;base64,...` URI read from disk at generation
  time, making the SVG fully self-contained.

---

## 7. MCP Tool Expansion

Expand the MCP adapter beyond the initial integration boundary.

Potential MCP tools:

```text
analyze_requirements        ✓ done — see the "MCP" section above
refine_requirements          ✓ done — see the "MCP" section above
generate_architecture        ✓ done, as generate_system_design
validate_architecture        ✓ done, as validate_system_design
refine_architecture          ✓ done — see the "MCP" section above
get_architecture
compare_architectures
get_traceability
analyze_impact
approve_architecture
```

`analyze_requirements`/`refine_requirements` closed the biggest gap in the
original list: previously the MCP layer could only generate/validate/
diagram an architecture from a `RequirementsArtifact` a caller already
had — there was no MCP tool to actually *produce* one from natural
language, so an MCP client needed something outside MCP entirely just to
get started. The requirements-to-architecture flow is now usable through
MCP alone, end to end. `refine_architecture` closed the next gap: an
accepted architecture no longer has to be regenerated from scratch (or
edited outside the tool entirely) to apply a change — see the web API's
`POST .../refine-architecture` and `GenerateSystemDesignUseCase.execute`'s
`previous_design`/`refinement_input` parameters.

`get_architecture`, `compare_architectures`, and `get_traceability` remain
open — these would read from what's already persisted (mirroring
`app/api/routes/artifacts.py`) rather than only operating on JSON the
caller already has, which is what the stateless tools above still require.
`approve_architecture` is the same kind of gap now, not a missing
capability: the approval workflow itself exists (`POST .../approve`/
`POST .../reject`, see "Next Steps" → "Human Approval Workflow"), it's
just a `SessionRecord` mutation the stateless MCP layer has no path to
today. `analyze_impact` is the one tool here that still depends on a
capability that doesn't exist yet anywhere in the application (impact
analysis — see the Roadmap section below), not just on MCP wiring.

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
  ├── ✓ Architecture refinement
  ├── ✓ Version comparison
  ├── Coverage analysis          ← next up
  ├── Impact analysis
  ├── ADRs
  ├── Change history
  └── ✓ Human approval
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

MVP-2 is done, and MVP-3 is now three-sixths complete (refinement,
version comparison, human approval). The immediate priority is
**requirement-to-architecture coverage analysis**, followed by
**impact analysis** (which reuses coverage's traceability graph) and
then **ADRs** — see "Roadmap" → "Path to MVP-3 Completion" above for
concrete implementation steps for each. Architecture quality analysis,
deployment architecture, and IaC generation remain deliberately last —
they depend on implementation-specific decisions this project has
stayed technology-neutral about so far (see "Design Philosophy" →
"Technology-neutral MVP-2 architecture" below).
