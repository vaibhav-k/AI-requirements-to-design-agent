# design-tools-service

The deterministic, LLM-free half of the AI Requirements → System Design
Agent's architecture-design capability: rendering a structured design as
an SVG diagram, and validating a structured design's semantic integrity.

This service is one of three that make up the whole system — see the
root `README.md` (two directories up) for the full picture, and
`backend/orchestrator/README.md`'s "Service Architecture" section for
exactly how a request reaches here.

## Why this is a separate service

Before the split, this logic
(`app.design.diagram.ArchitectureDiagramGenerator` and
`app.design.validator.ArchitectureValidator`) ran in-process inside the
orchestrator, alongside every Microsoft Agent Framework/Azure OpenAI
call. The orchestrator/tools-service split's whole point is keeping every
LLM call — and only LLM calls — in the orchestrator; this service has no
LLM dependency at all, no Azure OpenAI key, nothing non-deterministic.
Nothing here talks to MCP either — `backend/mcp-wrapper` is the only
thing that calls this service, over plain REST.

## Endpoints

* `POST /tools/diagrams/generate` — body: a `SystemDesignArtifact` (JSON).
  Returns `{"svg": "<svg>...</svg>"}` on success, or HTTP 422 with
  `{"detail": "..."}` if rendering fails.
* `POST /tools/designs/validate` — body: a `SystemDesignArtifact` (JSON).
  Returns `{"valid": true, "design": {...}}` on success, or HTTP 422 with
  `{"detail": "..."}` if validation fails.
* `GET /health` — liveness check, no auth, no dependencies.

## Project structure

```text
tools-service/
├── main.py                     # FastAPI app factory; mounts both routers + /health
├── src/
│   ├── domain/
│   │   ├── design.py            # DesignComponent/.../SystemDesignArtifact —
│   │   │                        # a deliberate, independent copy of the
│   │   │                        # orchestrator's app.domain.design models,
│   │   │                        # matching Parnell-AI-Persona-Agent's own
│   │   │                        # per-service duplicated domain models
│   │   │                        # rather than a shared package
│   │   └── errors.py            # DiagramGenerationError, ArchitectureValidationError
│   │
│   ├── infrastructure/
│   │   ├── diagram.py           # ArchitectureDiagramGenerator (moved from
│   │   │                        # app/design/diagram.py, imports rewritten)
│   │   ├── validator.py         # ArchitectureValidator (moved from
│   │   │                        # app/design/validator.py, imports rewritten)
│   │   ├── icons.py             # icon path resolution (moved as-is)
│   │   ├── icons/azure/*.png    # vendored Azure Architecture Icons (23 files)
│   │   └── config.py            # Settings (env prefix TOOLS_SERVICE_)
│   │
│   └── api/routes/
│       ├── diagrams.py          # POST /tools/diagrams/generate
│       └── validation.py        # POST /tools/designs/validate
│
├── tests/
└── requirements.txt
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

Graphviz's `dot` executable must be installed separately (the Python
`graphviz` package only wraps it):

```bash
# Linux
sudo apt-get update && sudo apt-get install graphviz

# macOS
brew install graphviz

# Windows: install Graphviz and ensure its bin/ directory is on PATH
```

Copy `.env.example` to `.env` if you need non-default host/port/log
level — none of the settings are required to run locally.

## Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8100 --reload
```

## Test

```bash
pytest -q
```
