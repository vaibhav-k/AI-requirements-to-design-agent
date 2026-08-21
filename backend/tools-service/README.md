# design-tools-service

The deterministic, LLM-free half of the AI Requirements → System Design
Agent's pipeline: rendering a structured design as an SVG diagram,
validating a structured design's semantic integrity, validating +
rendering a work breakdown's traceability into an import-ready CSV, and
rendering a technical design document into a downloadable `.docx` file
with the approved architecture diagram and a requirements traceability
appendix embedded.

This service is one of three that make up the whole system - see the
root `README.md` (two directories up) for the full picture, and
`backend/orchestrator/README.md`'s "Service Architecture" section for
exactly how a request reaches here.

## Why this is a separate service

Before the split, the diagram/validation logic
(`app.design.diagram.ArchitectureDiagramGenerator` and
`app.design.validator.ArchitectureValidator`) ran in-process inside the
orchestrator, alongside every Microsoft Agent Framework/Azure OpenAI
call. The orchestrator/tools-service split's whole point is keeping every
LLM call - and only LLM calls - in the orchestrator; this service has no
LLM dependency at all, no Azure OpenAI key, nothing non-deterministic.
The work-breakdown export/validation logic
(`src/infrastructure/work_breakdown_export.py`) and the technical-design
`.docx` renderer (`src/infrastructure/document_export.py`) never had an
in-process home to begin with - both were built directly here, since CSV
rendering, ID-traceability checking, and Word document assembly are all
just as deterministic as diagram rendering and design validation.
Nothing here talks to MCP either - `backend/mcp-wrapper` is the only
thing that calls this service, over plain REST.

## Endpoints

* `POST /tools/diagrams/generate` - body: a `SystemDesignArtifact` (JSON).
  Returns `{"svg": "<svg>...</svg>"}` on success, or HTTP 422 with
  `{"detail": "..."}` if rendering fails.
* `POST /tools/designs/validate` - body: a `SystemDesignArtifact` (JSON).
  Returns `{"valid": true, "design": {...}}` on success, or HTTP 422 with
  `{"detail": "..."}` if validation fails.
* `POST /tools/work-breakdown/export` - body: a `WorkBreakdownArtifact`
  plus the `RequirementsArtifact`/`SystemDesignArtifact` it was generated
  from (JSON - see `src/domain/work_breakdown.py`'s
  `WorkBreakdownExportRequest`). Returns a `WorkBreakdownExport` - the
  rendered CSV text plus feature/story/task counts, covered/unmapped/
  fabricated requirement and architecture IDs, and any ambiguities the
  agent flagged - on success, or HTTP 422 with `{"detail": "..."}` if a
  task has no traceability to any requirement or architecture ID at all
  (the one defect this endpoint treats as fatal rather than a warning).
* `POST /tools/technical-design/export` - body: a `TechnicalDesignArtifact`
  plus the `SystemDesignArtifact`/`RequirementsArtifact`/
  `WorkBreakdownArtifact` it was generated from (JSON - see
  `src/domain/technical_design.py`'s `TechnicalDesignExportRequest`).
  Returns a `TechnicalDesignExport` - the rendered `.docx` as base64 text
  (the MCP transport envelope's JSON has no binary type) plus heading/
  table counts, whether the architecture diagram was embedded, the byte
  count, and any warnings (e.g. a diagram render failure, which degrades
  to an omitted figure rather than failing the export) - on success, or
  HTTP 422 with `{"detail": "..."}` if the document has no sections at
  all (the one defect this endpoint treats as fatal).
* `GET /health` - liveness check, no auth, no dependencies.

## Project structure

```text
tools-service/
├── main.py                     # FastAPI app factory; mounts all four routers + /health
├── src/
│   ├── domain/
│   │   ├── design.py            # DesignComponent/.../SystemDesignArtifact -
│   │   │                        # a deliberate, independent copy of the
│   │   │                        # orchestrator's app.domain.design models,
│   │   │                        # matching Parnell-AI-Persona-Agent's own
│   │   │                        # per-service duplicated domain models
│   │   │                        # rather than a shared package
│   │   ├── requirements.py      # Requirement/.../RequirementsArtifact - same
│   │   │                        # deliberate duplication, of app.domain.requirements
│   │   ├── work_breakdown.py    # WorkBreakdownTask/.../WorkBreakdownExport -
│   │   │                        # same duplication, of app.domain.work_breakdown
│   │   ├── technical_design.py  # DesignSection/.../TechnicalDesignExport -
│   │   │                        # same duplication, of app.domain.technical_design
│   │   └── errors.py            # DiagramGenerationError, ArchitectureValidationError,
│   │                            # WorkBreakdownExportError, TechnicalDesignExportError
│   │
│   ├── infrastructure/
│   │   ├── diagram.py           # ArchitectureDiagramGenerator (moved from
│   │   │                        # app/design/diagram.py, imports rewritten) -
│   │   │                        # generate() renders SVG, generate_png()
│   │   │                        # renders the same diagram as PNG for
│   │   │                        # embedding in the exported .docx
│   │   ├── validator.py         # ArchitectureValidator (moved from
│   │   │                        # app/design/validator.py, imports rewritten)
│   │   ├── work_breakdown_export.py  # WorkBreakdownExporter - CSV rendering +
│   │   │                        # requirement/architecture ID traceability
│   │   │                        # validation; built here directly (see "Why
│   │   │                        # this is a separate service" above)
│   │   ├── document_export.py   # TechnicalDesignExporter - python-docx
│   │   │                        # rendering (outline numbering, a Word TOC
│   │   │                        # field, the embedded PNG diagram, tables,
│   │   │                        # and a requirements traceability
│   │   │                        # appendix); built here directly, same
│   │   │                        # reasoning as work_breakdown_export.py
│   │   ├── icons.py             # icon path resolution (moved as-is)
│   │   ├── icons/azure/*.png    # vendored Azure Architecture Icons (23 files)
│   │   └── config.py            # Settings (env prefix TOOLS_SERVICE_)
│   │
│   └── api/routes/
│       ├── diagrams.py          # POST /tools/diagrams/generate
│       ├── validation.py        # POST /tools/designs/validate
│       ├── work_breakdown.py    # POST /tools/work-breakdown/export
│       └── documents.py         # POST /tools/technical-design/export
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

`pip install -r requirements.txt` also installs `python-docx`, used only
by `document_export.py` for the technical-design `.docx` export - no
separate system package is needed for it, unlike Graphviz below.

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
level - none of the settings are required to run locally.

## Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8100 --reload
```

## Test

```bash
pytest -q
```
