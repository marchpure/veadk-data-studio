# Feishu collaboration migration proposal

Status: proposal for the Integration Owner. Do not treat this document as a finalized Alembic linearization.

Current branch already contains Feishu collaboration migration files from the earlier slice, but this round intentionally did not edit `server/migrations/**`. The Integration Owner should re-linearize against the authoritative Team/Data Modeling head before production deployment.

## Proposed tables

- `collaboration_installations`
  - Tenant-scoped installation records for Feishu/Slack-compatible collaboration channels.
  - Stores encrypted credentials only; App Secret, verification token, encrypt key, and tenant tokens must not be plaintext columns.
  - Required indexes: `tenant_id`, `platform`, `external_tenant_id`.
  - Required unique constraints: `public_id`; `(platform, external_tenant_id)`.

- `collaboration_conversations`
  - Maps `(installation_id, external_chat_id, normalized_root_id)` to one Byaan Notebook.
  - Required unique constraint: `(installation_id, external_chat_id, normalized_root_id)`.
  - Compatibility invariant: top-level Feishu group messages normalize to their own message id; thread follow-ups normalize to the Feishu root id; private chat uses the private root/message mapping.

- `collaboration_event_logs`
  - Persistent idempotency and audit state keyed by `(installation_id, external_event_id)`.
  - Trace refs: `conversation_id`, `notebook_id`, `run_id`.
  - Must not store raw message text or secrets.

- `collaboration_delivery_targets`
  - Explicitly authorized Feishu groups/topics/private targets.
  - Required unique constraint: `(installation_id, target_type, external_target_id, normalized_root_id)`.
  - `config_json.is_enabled=false` plus `is_verified=false` represents paused/unbound targets without deleting audit history.

- `external_identities`
  - Maps Feishu external user ids/union ids to Byaan tenant users.
  - Required unique constraint: `(installation_id, external_user_id)`.

- `collaboration_response_refs`
  - Stores sent Feishu message ids for ChannelResult/Renderer follow-up and outbound idempotency.

- `collaboration_leases`
  - DB lease for one active Feishu WebSocket consumer per installation.
  - Required index: `expires_at`.

## Compatibility and rollback

- Existing Slack tables, APIs, dependencies, and behavior are not removed.
- New columns referenced from schedules/skill suggestions should remain nullable so legacy rows continue to load.
- Downgrade must drop nullable FK columns before dropping collaboration tables.
- Do not hard-code an old `down_revision`; check the current authoritative Team Alembic head and resolve any multi-head state during integration.
- Rollback should remove only collaboration-owned tables/nullable FK columns and preserve existing User, Tenant, Notebook, Connection, Dataset, Source, Semantic Model, and Slack data.

## Integration-owner checklist

1. Rebase/merge the Feishu branch once onto the selected Team integration commit.
2. Re-run `alembic heads` and ensure there is one head.
3. Run upgrade from a copy of the current Team database.
4. Run downgrade to the direct previous revision.
5. Run upgrade to head again.
6. Verify existing Team data counts before/after upgrade/downgrade on a non-production copy.
