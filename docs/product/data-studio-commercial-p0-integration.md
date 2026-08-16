# Data Studio Commercial P0 Integration

CURRENT_PHASE: Phase 2 — latest Connector/Modeling `142837f` is merged and locally verified. Next: merge Dashboard `ef7ad32` while preserving Evaluation/Sharing.

## Immutable Inputs

| Stream | Branch | Input SHA | Status at capture |
| --- | --- | --- | --- |
| Connector / Modeling | `veadk-data-studio/agent/data-studio-p0` | `142837f7587dd1519d4287c1cb26c8e2840fc39a` | clean, pushed; documented `PARTIAL` / `8080_PARTIAL` |
| Dashboard | `veadk-data-studio/agent/dashboard-human-agent-p0` | `ef7ad32d031fcd5dea7102536720abd54b46ecdb` | clean, pushed; documented `DASHBOARD_BRANCH_READY_FOR_INTEGRATION / 8080_PENDING_INTEGRATION` |
| Evaluation / Sharing Governance | `veadk-data-studio/integration/evaluation-sharing-governance-p0` | `0c5b517381eedbc5c9a1181f82ab84d9965f2453` | clean, pushed; documented `RELEASE_READY` |

## Unified Branch

- Branch: `integration/data-studio-commercial-p0`
- Worktree: `/Users/bytedance/worktrees/byaan-commercial-integration-p0`
- Remote: `veadk-data-studio`
- Initial base: `0c5b517381eedbc5c9a1181f82ab84d9965f2453`
- Initial push: branch created and tracking `veadk-data-studio/integration/data-studio-commercial-p0`.

## Current 8080 Baseline

- Current URL: `http://127.0.0.1:8080`
- Current image: `byaan:selfhosted-governance-p0-2881367`
- Current container: `byaan-governance-p0-2881367-8080`
- Current `BYAAN_VERSION`: `governance-p0-2881367`
- Current migration: `add_canonical_sharing_model (head)`

This 8080 runtime is not the final commercial baseline. It predates the unified commercial branch and does not include latest Connector/Modeling `142837f` or Dashboard `ef7ad32`.

## Merge Plan

1. Merge latest Connector/Modeling input `142837f7587dd1519d4287c1cb26c8e2840fc39a`.
2. Merge latest Dashboard input `ef7ad32d031fcd5dea7102536720abd54b46ecdb`.
3. Preserve all Evaluation/Sharing Governance code and migrations from `0c5b517381eedbc5c9a1181f82ab84d9965f2453`.
4. Resolve shared files explicitly:
   - `server/main.py`
   - `server/models/__init__.py`
   - `server/auth/scopes.py`
   - `server/routers/folders.py`
   - `server/routers/exports.py`
   - `server/mcp/tools.py`
   - `server/mcp/tool_wrappers.py`
   - `server/tests/test_migration_chain_hardening.py`
   - `client/src/App.tsx`
   - `client/src/components/CollapsibleSidebar.tsx`
   - `client/src/services/api.ts`
   - `client/package.json`
   - `client/pnpm-lock.yaml`
5. Re-run migration, backend, frontend, browser, REST/MCP parity, and 8080 Release Gate from this branch. Historical outputs from the source branches are evidence inputs only, not final pass criteria.

## Known Starting Risks

- Connector/Modeling is intentionally not ready-complete: the source matrix records `0 ready / 14 beta / 26 planned / 0 blocked / 40 total`.
- The latest Dashboard branch includes post-governance browser/editor coverage commits that are not in the old Governance 8080 image.
- The merge must not let either source branch delete Evaluation/Sharing artifacts from the Governance branch.
- External credentials for several connector rows are unavailable; those rows must remain `beta` or `planned`, not be promoted to `ready`.

## 2026-08-17 03:18 CST - Connector / Modeling Merge

Merged input:

- `veadk-data-studio/agent/data-studio-p0`
- SHA: `142837f7587dd1519d4287c1cb26c8e2840fc39a`

Conflict resolution:

- `server/tests/test_migration_chain_hardening.py` was the only content conflict.
- Kept the commercial/governance final Alembic head assertion: `add_canonical_sharing_model`.
- Kept the Connector/Modeling migration chain assertion for `add_blocked_source_resource_status -> add_file_source_resource_type`.
- Preserved Dashboard, Evaluation, and Sharing migration lineage through `merge_ds_dash_20260816`, `add_evaluation_authoritative_model`, and `add_canonical_sharing_model`.

Evidence:

- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_migration_chain_hardening.py tests/test_data_studio_p0_source_matrix.py -q` -> `8 passed, 8 warnings`.
- `cd server && PYTHONPATH=..:tests uv run alembic heads` -> `add_canonical_sharing_model (head)`.
- `cd server && PYTHONPATH=..:tests uv run pytest tests/test_source_connectors_api.py::test_source_connection_browse_requires_authorization_without_fake_empty_success tests/test_multi_source_artifacts_api.py::test_source_processing_step_schema_is_typed_contract tests/test_multi_source_artifacts_api.py::test_web_source_blocks_private_urls tests/test_sources_overview_api.py::test_sources_overview_maps_blocked_and_needs_confirmation_to_product_states tests/test_data_studio_p0_source_matrix.py -q` -> `7 passed, 9 warnings`.
- `cd server && uv run ruff check models/source_resources.py routers/source_connections.py schemas/source_resources.py schemas/source_overview.py services/source_connections.py services/source_overview.py services/source_resources.py tests/test_multi_source_artifacts_api.py tests/test_source_connectors_api.py tests/test_sources_overview_api.py tests/test_data_studio_p0_source_matrix.py migrations/versions/add_blocked_source_resource_status.py scripts/generate_data_studio_p0_source_matrix.py tests/test_migration_chain_hardening.py` -> passed with the existing removed-rule warning.

Commercial readiness note:

- Connector/Modeling remains `PARTIAL`, not ready-complete. The merged source matrix still reports `0 ready / 14 beta / 26 planned / 0 blocked / 40 total`.
