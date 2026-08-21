# design-tools-wrapper (mcp-wrapper)

A thin internal MCP gateway sitting between `backend/orchestrator` and
`backend/tools-service`. It exposes tools-service's four REST endpoints
as MCP tools and does nothing else - no business logic, no state, no LLM
calls.

This service is one of three that make up the whole system - see the
root `README.md` (two directories up) for the full picture, and
`backend/orchestrator/README.md`'s "Service Architecture" section for
exactly how a request flows through here.

## Why an MCP gateway instead of a direct REST call

The orchestrator reaches every deterministic tool it depends on over
MCP, not raw HTTP - matching Parnell-AI-Persona-Agent's own
orchestrator/mcp-wrapper/tools-service pattern, which this project's
split mirrors. `app.infrastructure.tools_client.McpToolsClient` (in
`backend/orchestrator`) is the only orchestrator code that knows this
gateway exists.

## Tools exposed

All four tools live on one `FastMCP` server named `"design-tools"`,
mounted at `/mcp/design-tools`:

* `generate_architecture_diagram_tool(design_json: str) -> str`
* `validate_system_design_tool(design_json: str) -> str`
* `export_work_breakdown_tool(breakdown_json: str, requirements_json: str, design_json: str) -> str`
  - its request body is three artifacts, not one, since tools-service
  needs the requirements/architecture the breakdown claims to trace back
  to in order to catch a fabricated or uncovered ID.
* `export_technical_design_tool(document_json: str, design_json: str, requirements_json: str, work_breakdown_json: str) -> str`
  - four artifacts: the document itself, plus the design (embedded
  diagram), requirements, and work breakdown (both referenced by the
  rendered document's traceability appendix).

Every tool returns a JSON envelope,
`{"ok": bool, "status_code": int, "body": {...}}` - this wrapper's tools
never raise on a tools-service-level 4xx/5xx (an invalid diagram spec, a
failed validation, an untraceable work item) since that's an expected
outcome, not a transport failure. See `src/design_tools_wrapper/application
/tool_calls.py`'s module docstring for the full rationale, and
`app.infrastructure.tools_client.McpToolsClient` (in
`backend/orchestrator`) for the caller-side half of this contract.

## Project structure

```text
mcp-wrapper/
├── combined_main.py             # Starlette app mounting the design-tools
│                                 # FastMCP server via streamable_http_app();
│                                 # entry point: `python combined_main.py`
├── src/design_tools_wrapper/
│   ├── api/mcp_tools/
│   │   └── registry.py          # FastMCP instance + the four @mcp.tool() functions
│   ├── application/
│   │   └── tool_calls.py        # httpx translation layer: deserialize,
│   │                             # POST to tools-service, wrap in envelope
│   │                             # (export_work_breakdown assembles a
│   │                             # three-artifact payload, export_technical_design
│   │                             # a four-artifact payload; the other two
│   │                             # each POST a single already-JSON artifact)
│   └── infrastructure/
│       └── config.py            # Settings (env prefix DESIGN_TOOLS_WRAPPER_,
│                                 # WRAPPERS_GATEWAY_ for combined_main.py)
├── tests/
└── requirements.txt
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

Copy `.env.example` to `.env` if you need non-default settings - the
one you're most likely to change is `DESIGN_TOOLS_WRAPPER_TOOLS_SERVICE_BASE_URL`
if `backend/tools-service` isn't running at the default
`http://localhost:8100`.

## Run

```bash
python combined_main.py
```

The gateway listens on `:8200` by default (`WRAPPERS_GATEWAY_HOST`/
`WRAPPERS_GATEWAY_PORT`), serving the design-tools MCP endpoint at
`/mcp/design-tools`.

## Test

```bash
pytest -q
```
