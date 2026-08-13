"""HTTP API layer for the requirements-to-design agent.

This package is new: everything else in the project is reachable only via
the CLI (``app/main.py``) or the MCP server (``app/mcp/server.py``). The web
layer exists so a future UI (or any other HTTP client) can drive the same
requirements → architecture pipeline behind Entra ID authentication.

Endpoint-by-endpoint wiring of the requirements/architecture pipeline is not
part of this first step — see the "Authentication" section of the README for
what is and isn't covered yet.
"""
