# Evaluation + Sharing Governance P0

Status: release-ready.

## Scope

This branch integrates the completed Data Studio and Dashboard P0 branches and adds Evaluation plus unified Sharing governance. It did not write to the upstream Data Studio or Dashboard worktrees.

## Upstream Heads

| Stream | Branch | Head |
| --- | --- | --- |
| Data Studio / Connector / Modeling | `veadk-data-studio/agent/data-studio-p0` | `9718bf6431c177c0b48e6fc21c36626a9057c47a` |
| Human/Agent Dashboard | `veadk-data-studio/agent/dashboard-human-agent-p0` | `d6c4c2ea1b602a2c6ee84902f457054b79947045` |
| Governance integration | `integration/evaluation-sharing-governance-p0` | release-ready at `28813672936f417c23cf2e9ada3b76af031055e9` before final handoff artifact commit |

## Execution Rules

- All writes happen only in `/Users/bytedance/worktrees/byaan-governance-integration-p0`.
- Upstream worktrees are read-only inputs.
- Dashboard will be merged with a normal non-force merge.
- Migration heads are resolved only in this integration branch, preserving upstream revisions.
- Evaluation and unified Sharing schema work starts only after the three-layer integration gate passes.

## Phase Plan

1. Integration preflight and immutable upstream head capture. Done.
2. Merge Dashboard branch and resolve shared entry points. Done.
3. Run migration, backend, frontend, MCP, and browser integration gates. Done.
4. Phase 0 Sharing security stopgap. Done.
5. Evaluation contract, runner, grader, feedback/advisor/promotion. Done.
6. Canonical Sharing foundation, REST/MCP/UI, legacy migration. Done.
7. Real 8080 release gate. Done.

## Final Release Gate

- Real runtime: `http://127.0.0.1:8080`
- Image: `byaan:selfhosted-governance-p0-2881367`
- Container: `byaan-governance-p0-2881367-8080`
- Migration head: `add_canonical_sharing_model (head)`
- Release gate script: `server/scripts/sharing_release_gate_8080.py`
- Result: `ok: true`
- Registered historical folder `b268fd5a-8bb4-4ee6-9447-03edc9c142f0` was cleaned during the gate.
