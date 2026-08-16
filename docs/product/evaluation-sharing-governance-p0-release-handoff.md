# Evaluation + Sharing Governance P0 Release Handoff

Status: release-ready.

## Final State

Governance Integration P0 is complete on branch `integration/evaluation-sharing-governance-p0`.

The branch integrates the Data Studio and Human/Agent Dashboard P0 streams, implements Evaluation governance and canonical Sharing, preserves additive migrations, and has passed the final real `127.0.0.1:8080` Release Gate.

## Immutable Inputs

- Data Studio head: `9718bf6431c177c0b48e6fc21c36626a9057c47a`
- Dashboard head: `d6c4c2ea1b602a2c6ee84902f457054b79947045`
- Integration branch: `integration/evaluation-sharing-governance-p0`
- Latest pushed implementation commit before release-gate artifact commit: `28813672936f417c23cf2e9ada3b76af031055e9`
- Current 8080 image used for Release Gate: `byaan:selfhosted-governance-p0-2881367`
- Current 8080 container after Release Gate: `byaan-governance-p0-2881367-8080`

## Completed Scope

- Three-layer integration gate after merging the Dashboard stream.
- Phase 0 Sharing security stopgap: secret redaction, object authorization, viewer-session binding, structured dashboard query filtering, and error/log/audit redaction.
- Phase 1 Evaluation authoritative model and additive migration.
- Phase 2 Evaluation runner lease, resumability, artifacts, gate summary, and promotion blocking.
- Phase 3 Evaluation REST APIs for runner, promotion, feedback-to-case, advisor draft compatibility, and read surfaces.
- Phase 3/4 Evaluation MCP wrappers, shared serializers, Human UI workspace, advisor lifecycle, and browser/MCP parity smoke.
- Phase 5 canonical Sharing model/service, folder dashboard compatibility, worker-backed notebook compatibility, folder notebook compatibility, REST/MCP read surface, and local canonical Sharing smoke.
- Migration bridge for inherited self-hosted databases carrying `merge_ds_dash_20260816`.
- Canonical Sharing timestamp compatibility with PostgreSQL `TIMESTAMP WITHOUT TIME ZONE`.
- Final real 8080 Release Gate and cleanup of the previously registered test folder.

## Release Gate Evidence

- Local focused Sharing/security suite: `39 passed, 9 warnings`.
- Local canonical Sharing smoke: `ok: true`, covering `folder_notebook`, `html_notebook_share`, `json_notebook_share`, password rotation, canonical evidence, legacy redaction, and revocation.
- Alembic head: `add_canonical_sharing_model (head)`.
- Real 8080 container Alembic current: `add_canonical_sharing_model (head)`.
- Real 8080 unauthenticated `GET /api/sharing/grants`: `401`, proving the route is mounted and protected.
- Real 8080 login with `admin@example.com / password`: `200`.
- Real 8080 release gate script:
  - command: `BASE_URL=http://127.0.0.1:8080 CONTAINER=byaan-governance-p0-2881367-8080 RUN_ID=2881367 PYTHONPATH=. uv run python server/scripts/sharing_release_gate_8080.py`
  - result: `ok: true`
  - verified canonical folder notebook surface: `folder_notebook`
  - verified canonical folder dashboard surface: `folder_dashboard`
  - verified folder notebook canonical revoke status: `revoked`
  - verified worker-backed notebook sharing gate: `403` / `External sharing is not available in this deployment mode`
  - deleted temporary release-gate folder and notebook
  - cleaned registered historical folder `b268fd5a-8bb4-4ee6-9447-03edc9c142f0`
- Recent 8080 logs contain no `Traceback`, `ERROR`, `500`, `invalid input`, `offset-naive`, or `offset-aware` matches.

## Runtime Notes

- The previous 8080 container `byaan-governance-p0-976c5cf-8080` was stopped for the final Release Gate.
- The new 8080 container keeps the existing persistent volume `byaan_data_studio_p0_9718bf6_8080`.
- Runtime environment includes `APP_MODE=self-hosted`, `BYAAN_VERSION=governance-p0-2881367`, `FRONTEND_URL=http://127.0.0.1:8080`, and `PUBLIC_BASE_URL=http://127.0.0.1:8080`.
- The self-hosted runtime intentionally has external sharing disabled; worker-backed notebook sharing returning 403 is expected and verified.

## Residual Risk

- Existing frontend CSS/chunk warnings remain pre-existing and were present across prior gates.
- The Release Gate directly seeds a minimal dashboard row in the current 8080 container database because the legacy dashboard version creation path does not expose a simple public REST API. The temporary fixture is deleted by the script.

Current handoff status: `RELEASE_READY`.
