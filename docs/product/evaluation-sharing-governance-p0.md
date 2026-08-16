# Evaluation + Sharing Governance P0

Status: integration worktree initialized.

## Scope

This branch integrates the completed Data Studio and Dashboard P0 branches before adding Evaluation and unified Sharing governance. It must not write to the upstream Data Studio or Dashboard worktrees.

## Upstream Heads

| Stream | Branch | Head |
| --- | --- | --- |
| Data Studio / Connector / Modeling | `veadk-data-studio/agent/data-studio-p0` | `9718bf6431c177c0b48e6fc21c36626a9057c47a` |
| Human/Agent Dashboard | `veadk-data-studio/agent/dashboard-human-agent-p0` | `d6c4c2ea1b602a2c6ee84902f457054b79947045` |
| Governance integration | `integration/evaluation-sharing-governance-p0` | initialized from Data Studio head |

## Execution Rules

- All writes happen only in `/Users/bytedance/worktrees/byaan-governance-integration-p0`.
- Upstream worktrees are read-only inputs.
- Dashboard will be merged with a normal non-force merge.
- Migration heads are resolved only in this integration branch, preserving upstream revisions.
- Evaluation and unified Sharing schema work starts only after the three-layer integration gate passes.

## Phase Plan

1. Integration preflight and immutable upstream head capture.
2. Merge Dashboard branch and resolve shared entry points.
3. Run migration, backend, frontend, MCP, and browser integration gates.
4. Phase 0 Sharing security stopgap.
5. Evaluation contract, runner, grader, feedback/advisor/promotion.
6. Canonical Sharing foundation, REST/MCP/UI, legacy migration.
7. Real 8080 release gate or honest blocked handoff.
