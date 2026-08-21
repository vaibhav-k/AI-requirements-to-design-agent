# Frontend

React + Vite + TypeScript app for the requirements → architecture agent.

See [`backend/orchestrator/README.md`](../backend/orchestrator/README.md#frontend)
- its "Frontend" section covers what this app does (including the
"Task Planning" tab added for the Work Breakdown Agent - generate,
refine, and export a CSV work breakdown once an architecture is
approved - and the "Technical Design" tab added for the Technical
Writer Agent - generate, refine, and export a `.docx` technical design
document once a work breakdown exists), how to run it, and how to set
up the Entra ID app registration it needs for sign-in. The root
[`README.md`](../README.md)
has the whole-repo picture; this app is the fourth top-level piece,
alongside the three `backend/` services, even though it isn't a
separate deployable "service" the way they are (see the root README's
"Services" section).

Quick start:

```bash
npm install
cp .env.example .env   # fill in the values, see root README
npm run dev
```
