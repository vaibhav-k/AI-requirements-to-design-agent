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
* GitHub Actions CI

The architecture stage intentionally focuses on **logical, high-level system components**.

Detailed database schemas, detailed API specifications, deployment topology, networking, Kubernetes configuration, and implementation-specific infrastructure remain outside MVP-2 scope.

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
│   │
│   ├── design/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── analyzer.py
│   │   ├── validator.py
│   │   ├── diagram.py
│   │   └── session.py
│   │
│   └── mcp/
│       ├── __init__.py
│       └── server.py
│
├── tests/
│   ├── test_analyzer.py
│   ├── test_storage.py
│   ├── test_refinement.py
│   ├── test_design_analyzer.py
│   ├── test_design_validator.py
│   ├── test_design_diagram.py
│   ├── test_design_storage.py
│   └── test_mcp.py
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
