# Evaluation + Sharing Governance P0 Release Handoff

Status: not release-ready.

## Current State

The integration branch has been initialized from the Data Studio P0 head and pushed. Dashboard has not yet been merged into this branch, Evaluation/Sharing implementation has not started, and no 8080 release gate has been run for this integration branch.

## Immutable Inputs

- Data Studio head: `9718bf6431c177c0b48e6fc21c36626a9057c47a`
- Dashboard head: `d6c4c2ea1b602a2c6ee84902f457054b79947045`
- Integration branch: `integration/evaluation-sharing-governance-p0`

## Required Before Handoff

- Merge Dashboard and resolve shared files.
- Prove Alembic has a single head after merge.
- Run migration checks on fresh/existing SQLite and PostgreSQL-supported paths.
- Implement and test Sharing security stopgap.
- Implement Evaluation and canonical Sharing phases.
- Run backend/frontend/MCP/security/browser gates.
- Run or honestly block the real 8080 release gate.

Current handoff status: `NOT_READY`.
