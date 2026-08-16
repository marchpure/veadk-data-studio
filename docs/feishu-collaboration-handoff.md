# Feishu Collaboration Owner handoff

Status: PARTIAL. This branch is ready for Integration Owner review as a Feishu-owned slice, but it is not complete until a real Feishu test app/group E2E and the final Integration Owner merge are finished.

## Scope

- Repo/worktree: `/Users/bytedance/byaan-team-feishu`
- Branch: `feature/team-feishu-integration`
- Current HEAD before this handoff update: `254982c Record Feishu probe and handoff status`
- Current merge-base with `integration/team-semantic-modeling` when checked: `31951211c1d9d923e45d8e044f5daf55fdbb0d5a`
- Current observed `integration/team-semantic-modeling` HEAD when checked: `4866e711470051134439e71b923d67d65b1c30f9`
- Shared dirty worktree `/Users/bytedance/byaan` was not used.
- Docker/self-hosted deployment, 8080 container replacement, and `byaan_data` were intentionally not touched by the Feishu Owner.
- `server/migrations/**` is not owned by this handoff round. Treat migration content on this branch as proposal/input for the Integration Owner, not as the final production Alembic linearization.

## Commit classification

### Feishu-owned functional commits after the current integration merge-base

- `036aee5 Audit malformed Feishu callback messages`
- `d24a83c Audit inactive Feishu callback messages`
- `c92ba66 Use stable Feishu request UUIDs for delivery`
- `0772477 Preflight Feishu credentials before websocket connect`
- `3e31561 Require Feishu private chat delivery targets`
- `ec97566 Validate Feishu delivery target shape`
- `c993182 Revalidate Feishu outbound targets before sending`
- `ea602c7 Audit unsupported Feishu callback events`
- `ada77dc Expose Feishu response refs in event audit`
- `d73f740 Refresh invalid Feishu tenant tokens`
- `44c1b57 Surface Feishu callback verification health`
- `c415638 Expand Feishu E2E evidence snapshot`
- `9d0ed26 Audit inactive Feishu callback dispatch races`
- `13c0bea Audit Feishu tenant token refresh`
- `094c118 Document Feishu integration slice mapping`
- `deb671e Redact Feishu E2E evidence refs`
- `254982c Record Feishu probe and handoff status`
- `f4bbee7 Allow retrying failed Feishu outbound sends`
- `5bf8880 Mark Feishu delivery reauth during event processing`
- `a19a5aa Skip Feishu delivery retry for reauth failures`
- `c50207b Retry transient Feishu response delivery failures`
- `05f2f9f Mark failed Feishu callback background events`
- `18867e7 Preaccept Feishu callback events before dispatch`
- `7bb5a82 Revalidate Feishu delivery target on resume`
- `78bbc9c Refresh Feishu collaboration handoff status`
- `b4d708c Guard Feishu agent LLM tenant at runtime`
- `5b2bf90 Allow mapped Feishu direct messages`
- `5c9d2b2 Coalesce concurrent Feishu websocket connects`
- `8fe568b Validate Feishu default LLM tenant scope`
- `7070f93 Document Feishu collaboration owner handoff`
- `0a942a7 Handle Feishu agent timeouts explicitly`
- `7272e18 Serialize Feishu followups against refreshed conversations`
- `d99a911 Revoke Feishu delivery targets on disconnect`
- `30e92e4 Surface Feishu event subscription readiness`
- `7a488b0 Harden Feishu outbound delivery safeguards`
- `12cba76 Add Feishu reauth and delivery reliability coverage`
- `531c34c Harden Feishu collaboration ownership flows`

Earlier Feishu slice commits on this branch also contain the original implementation and test coverage, including admin UI, WebSocket lifecycle, callback verification, identity mapping, delivery targets, event processing, Slack compatibility, and E2E evidence tooling. Review with `git log --oneline --no-merges integration/team-semantic-modeling..HEAD`.

### Merge commits to treat as integration history, not Feishu feature work

- `25bccb9 Merge branch 'integration/team-semantic-modeling' into feature/team-feishu-integration`
- `73f68f5 Merge branch 'integration/team-semantic-modeling' into feature/team-feishu-integration`
- Older merge commits are visible in branch history before the current merge-base audit. Do not continue merging every new integration commit; wait for the Integration Owner to freeze a base and perform one rebase/merge.

### Migration proposal / non-owner history

The branch diff against `integration/team-semantic-modeling` currently includes migration paths such as:

- `server/migrations/versions/add_collaboration_integration_tables.py`
- `server/migrations/versions/add_collaboration_event_trace_refs.py`
- source/semantic migration files from prior integration history

Do not accept these as final production migration ordering without Integration Owner review. Use `docs/feishu-collaboration-migration-proposal.md` as the intended schema/rollback contract.

## Integration-ready linear slice mapping

Do not merge `feature/team-feishu-integration` directly. The current branch diff against `integration/team-semantic-modeling` still contains non-Feishu Team/Data Modeling/Source/Semantic history. Integration Owner should freeze a target base, create a clean branch from that base, and replay only the Feishu-owned changes below.

### Feishu-owned paths to replay

- `server/collaboration/**`
- `server/routers/collaboration.py`
- `server/schemas/collaboration.py`
- `client/src/components/collaboration/FeishuIntegrationModal.tsx`
- `client/src/hooks/useFeishuIntegration.ts`
- `scripts/feishu_collaboration_e2e.py`
- `docs/feishu-collaboration-e2e.md`
- `docs/feishu-collaboration-handoff.md`
- `docs/feishu-collaboration-migration-proposal.md`
- `server/tests/test_collaboration_core.py`
- `server/tests/test_feishu_collaboration_api.py`
- `server/tests/test_feishu_event_slice.py`
- `server/tests/test_feishu_e2e_evidence.py`
- `server/tests/test_slack_compatibility_adapter.py`

### Mixed paths: replay only Feishu-owned hunks

- `client/src/services/api.ts`: keep only collaboration/Feishu client methods and types.
- `server/main.py`: keep only collaboration router wiring and Feishu WebSocket startup/shutdown auto-resume hooks.
- `server/models/__init__.py`: keep only collaboration model exports.
- `server/services/crypto_service.py`: keep only credential redaction/encryption behavior needed by collaboration configuration, if not already present on the frozen base.

### Exclude from the Feishu linear branch

- Data Modeling UI/API/history, including `client/src/features/data-modeling/**`, data-modeling E2E scripts, semantic modeling services, and semantic/source tests.
- Source/Semantic migration repair commits and files, including `37bfc8b`, `c212630`, and source/semantic migration changes.
- Global lint/dependency drift not required by Feishu, including `9ebd18f Remove stale ruff ignore`, `pyproject.toml`, `client/package.json`, and `client/pnpm-lock.yaml` unless the frozen base independently requires them.
- Docker/self-hosted launcher changes. The Feishu Owner did not validate or deploy 8080 from this branch.
- Public Alembic ordering from this branch. Use the migration proposal document and let Integration Owner create the final one-head migration on the frozen base.

### Original commits to review buckets

| Review bucket | Original commits / source material |
| --- | --- |
| A. Collaboration domain/models/services | `ada2ac0`, `238e47b`, `066b18a`, `23a83a5`, `3a2a0aa`, `c9d4074`, `85c631c`, `5b2bf90`, `8fe568b`, `b4d708c`, `7272e18`, `0a942a7`, `531c34c` |
| B. Feishu transport/auth/event/idempotency | `b7c4b85`, `4f26c44`, `1cc2302`, `7170335`, `0ef4e9f`, `41d8905`, `bce103c`, `30e92e4`, `5c9d2b2`, `7bb5a82`, `18867e7`, `05f2f9f`, `036aee5`, `d24a83c`, `0772477`, `ea602c7`, `d73f740`, `44c1b57`, `9d0ed26`, `13c0bea` |
| C. Agent mapping/reply/outbound send | `238e47b`, `067226f`, `7a488b0`, `d99a911`, `c50207b`, `a19a5aa`, `5bf8880`, `f4bbee7`, `c92ba66`, `3e31561`, `ec97566`, `c993182` |
| D. Admin UI/API | `406a77c`, `9c41674`, `046d4b7`, `505affb`, relevant hunks from `1cc2302`, `30e92e4`, `44c1b57` |
| E. Tests/evidence/tooling/docs | `4090369`, `505affb`, `7070f93`, `78bbc9c`, `c415638`, `13c0bea`, plus Feishu/Slack regression tests in the files listed above |
| F. Migration proposal / Integration Owner migration input | Schema intent from `b87909f`, `7170335`, `docs/feishu-collaboration-migration-proposal.md`; do not replay migration files verbatim without re-linearizing against the frozen base |

The target clean branch should contain a small number of squashed or curated commits corresponding to these buckets, not the full historical commit stream.

## Implemented Feishu journeys and contracts

- Admin can configure Feishu App ID/App Secret, default LLM, optional callback verification token/encrypt key.
- App Secret, verification token, encrypt key, tenant token, and full upstream credential errors are not returned to the frontend.
- `default_llm_connection_id` is tenant-scoped at both configuration time and Agent runtime. Historical/manual cross-tenant LLM references fail before constructing an Agent request.
- WebSocket is the production ingress. `connection_mode=webhook` is rejected.
- WebSocket connect revalidates saved Feishu credentials before starting a consumer; reauth failures set `needs_reauth`, keep the installation inactive, and do not acquire/start a WebSocket consumer.
- Same-process concurrent WebSocket connect calls for one installation are coalesced so they cannot start duplicate consumers under the same DB lease owner.
- The old unauthenticated public-id injection route remains absent.
- Signed/encrypted callback route exists for URL verification and message callbacks, with token validation, signature/timestamp/nonce checks, AES-CBC decrypt, and replay rejection.
- Signed/encrypted URL verification success updates installation callback health (`url_verification=verified`, `last_url_verification_at`) and the Feishu admin UI displays that state.
- Signed/encrypted callbacks with unsupported event types ACK quickly, persist the event id/chat/operator when present, and mark the event `ignored_event_type` without dispatching Agent work.
- Signed/encrypted malformed message callbacks with missing required message/chat/sender identifiers ACK quickly, persist the event id, and mark the event `failed_terminal` without dispatching Agent work.
- Signed/encrypted message callbacks received while an installation is inactive ACK quickly, persist the event id/chat/sender, and mark the event `inactive` without dispatching Agent work.
- Signed/encrypted message callbacks that are preaccepted and then lose installation activeness before background dispatch are marked `inactive` instead of being left in `received`.
- Installation/health payloads expose required event subscription readiness for `im.message.receive_v1`; observed real events mark readiness.
- The E2E evidence collector now captures callback URL verification health, event subscription readiness, tenant-token expiry, recent identities, delivery targets, conversations, response refs, and events with sensitive values/Feishu identifiers represented as hash refs.
- Recent event audit payloads include response message refs/status/sequence for completed Agent and outbound sends without exposing message text or raw Agent output.
- Bot-visible chat listing is used before binding/sending in the product UI; the standalone evidence script's `--list-chats` mode prints only `chat_ref` hashes and chat types, not raw chat ids or group names.
- Delivery targets are explicit allow-list records for groups, topics, and private chats. Unbound targets do not run Agent.
- Delivery target shape is validated against Feishu chat metadata: `group` has no `root_id`, `topic_group` requires a root/topic id, and `p2p` cannot include a root id.
- Delivery targets can be bound, paused, resumed, unbound, and revoked on disconnect.
- Feishu external identities must be mapped to a Byaan tenant user before Agent access.
- Feishu direct messages require both a mapped Byaan identity and an enabled `p2p` delivery-target binding before Agent access.
- Event idempotency is persisted by `(installation_id, external_event_id)`.
- Conversation mapping keys include installation, chat, and normalized root id.
- Same-root follow-ups are serialized and refresh the conversation before Agent execution, so follow-ups reuse the Notebook created by the first event.
- Agent failures and timeouts return explicit user-facing failure messages and mark the event.
- Final replies include Notebook and Run references.
- Plain text message length is capped/truncated while preserving Byaan trace references.
- Feishu response delivery transient failures are retried before persisting/updating `ResponseRef`.
- Feishu response delivery reauth failures are not retried.
- Feishu delivery reauth failures during event processing deactivate the installation and mark it `needs_reauth`.
- Outbound sends require confirmation, enabled target, idempotency key, and reject obvious credential/token content before sending.
- Outbound sends revalidate that the target is still visible to the bot before sending; missing targets are marked `needs_rebind` without sending or creating a delivery event.
- Outbound sends can be retried with the same idempotency key after a terminal delivery failure; once delivery succeeds, the same key remains idempotent and does not send again.
- Outbound sends and Agent ACK/final replies include stable Feishu request UUIDs, reducing duplicate Feishu messages when upstream delivery succeeds but a local retry path replays the request.
- Feishu 429 responses are retried with bounded backoff.
- If a cached tenant token is rejected by a Feishu authenticated OpenAPI request, the process-local cache is cleared and the request is retried once with a fresh tenant token while preserving the same request body/UUID.
- Concurrent authenticated requests that all observe the same rejected cached tenant token share one replacement token fetch under the existing token lock; ordinary non-reauth 4xx failures do not trigger token refresh; if the single post-refresh retry still fails, the second Feishu API error is propagated without a third OpenAPI attempt.
- Reauth-class failures mark installation `needs_reauth` and deactivate it.
- Bot/chat access loss invalidates delivery targets.
- Slack compatibility adapter and regression path remain present.

## Validation performed

Most recent selected backend regression:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_source_connector_migration_compat.py \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py \
  server/tests/test_source_connectors_api.py \
  server/tests/test_semantic_modeling_api.py \
  server/tests/test_web_source_adapter.py \
  server/tests/test_multi_source_artifacts_api.py -q
```

Result: `90 passed, 42 warnings`.

Recent Feishu/Collaboration focused regression:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result after latest Feishu Owner commits: `66 passed, 12 warnings`.

Latest focused regression after delivery reauth hardening:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `72 passed, 12 warnings`.

Latest focused regression after outbound retry hardening:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `73 passed, 12 warnings`.

Latest focused regression after malformed callback audit hardening:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `74 passed, 12 warnings`.

Latest focused regression after inactive callback audit hardening:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `75 passed, 12 warnings`.

Latest focused regression after stable Feishu request UUID delivery hardening:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `76 passed, 12 warnings`.

Latest focused regression after Feishu connect credential preflight:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `77 passed, 12 warnings`.

Latest focused regression after explicit private-chat delivery-target enforcement:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `77 passed, 12 warnings`.

Latest focused regression after delivery-target type/root validation:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `78 passed, 12 warnings`.

Latest focused regression after outbound target visibility preflight:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `79 passed, 12 warnings`.

Latest focused regression after unsupported Feishu callback event audit:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `80 passed, 12 warnings`.

Latest focused regression after response-ref audit metadata:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `80 passed, 12 warnings`.

Latest focused regression after invalid cached tenant-token refresh:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `81 passed, 12 warnings`.

Focused token-refresh regression:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py::test_feishu_authenticated_request_refreshes_invalid_cached_tenant_token_once \
  server/tests/test_collaboration_core.py::test_feishu_tenant_token_refresh_is_serialized \
  server/tests/test_collaboration_core.py::test_feishu_request_retries_rate_limit \
  server/tests/test_collaboration_core.py::test_feishu_send_text_message_retries_rate_limit_without_duplicate_payload -q
```

Result: `4 passed, 7 warnings`.

Latest token-refresh audit regression:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py::test_feishu_tenant_token_refresh_is_serialized \
  server/tests/test_collaboration_core.py::test_feishu_authenticated_request_refreshes_invalid_cached_tenant_token_once \
  server/tests/test_collaboration_core.py::test_feishu_authenticated_concurrent_invalid_cached_token_refreshes_once \
  server/tests/test_collaboration_core.py::test_feishu_authenticated_request_refresh_failure_is_not_retried_again \
  server/tests/test_collaboration_core.py::test_feishu_authenticated_request_does_not_refresh_for_non_reauth_4xx \
  server/tests/test_collaboration_core.py::test_feishu_request_retries_rate_limit \
  server/tests/test_collaboration_core.py::test_feishu_send_text_message_retries_rate_limit_without_duplicate_payload \
  server/tests/test_collaboration_core.py::test_feishu_send_text_message_includes_stable_request_uuid -q
```

Result: `8 passed, 7 warnings`.

Real Feishu credential-safe probe:

```bash
PYTHONPATH=. uv run python - <<'PY'
# Uses FEISHU_APP_ID and FEISHU_APP_SECRET from the local environment.
# Prints only hashes/counts and never sends a message.
PY
```

Result: `real_probe=ok`, bot hash `c931743116df`, tenant hash `3dae29e673cf`, `visible_chat_count=7`, `sent_message=no`.

Latest real Feishu credential-safe probe:

```bash
PYTHONPATH=. uv run python - <<'PY'
# Uses FEISHU_APP_ID and FEISHU_APP_SECRET from the local environment.
# Prints only hash refs/counts and never sends a message.
PY
```

Result: `ok=true`, `bot_ref=bot_c931743116df`, `tenant_ref=tenant_3dae29e673cf`, `visible_chat_count=7`, `tenant_token_expires_at_present=true`, `sent_message=no`.

Latest focused regression after callback URL verification health:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `81 passed, 12 warnings`.

Focused callback/API regression:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_feishu_collaboration_api.py::test_feishu_signed_encrypted_callback_url_verification \
  server/tests/test_feishu_collaboration_api.py::test_feishu_callback_rejects_unsigned_or_unencrypted_public_id_injection \
  server/tests/test_feishu_collaboration_api.py::test_feishu_signed_callback_message_acknowledges_and_dispatches_event -q
```

Result: `3 passed, 7 warnings`.

Latest Feishu/Collaboration focused regression after token-refresh audit:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `85 passed, 12 warnings`.

Latest E2E evidence redaction regression:

```bash
PYTHONPATH=. uv run pytest server/tests/test_feishu_e2e_evidence.py -q
```

Result: `2 passed, 7 warnings`.

Latest Feishu/Collaboration focused regression after E2E evidence redaction:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_collaboration_core.py \
  server/tests/test_feishu_event_slice.py \
  server/tests/test_feishu_collaboration_api.py \
  server/tests/test_feishu_e2e_evidence.py \
  server/tests/test_slack_compatibility_adapter.py -q
```

Result: `86 passed, 12 warnings`.

Latest E2E evidence snapshot regression:

```bash
PYTHONPATH=. uv run pytest server/tests/test_feishu_e2e_evidence.py -q
```

Result: `1 passed, 7 warnings`.

Latest callback inactive-race regression:

```bash
PYTHONPATH=. uv run pytest \
  server/tests/test_feishu_collaboration_api.py::test_feishu_callback_background_inactive_race_marks_preaccepted_event_terminal \
  server/tests/test_feishu_collaboration_api.py::test_feishu_signed_callback_background_failure_marks_preaccepted_event \
  server/tests/test_feishu_collaboration_api.py::test_feishu_signed_callback_message_acknowledges_and_dispatches_event -q
```

Result: `3 passed, 7 warnings`.

Lint/checks:

```bash
uv run ruff check server/collaboration/channel_agent_service.py server/tests/test_feishu_event_slice.py
uv run ruff check server/collaboration/feishu/event_processor.py server/tests/test_feishu_event_slice.py
uv run ruff check server/collaboration/feishu/transport.py server/tests/test_collaboration_core.py
uv run ruff check server/collaboration/installation_service.py server/tests/test_feishu_collaboration_api.py
uv run ruff check server/collaboration/feishu/client.py server/tests/test_collaboration_core.py docs/feishu-collaboration-handoff.md
uv run ruff check server/routers/collaboration.py server/tests/test_feishu_collaboration_api.py
uv run ruff check scripts/feishu_collaboration_e2e.py server/tests/test_feishu_e2e_evidence.py docs/feishu-collaboration-e2e.md docs/feishu-collaboration-handoff.md
uv run ruff check server/routers/collaboration.py server/tests/test_feishu_collaboration_api.py docs/feishu-collaboration-handoff.md
git diff --check
```

Result: passed.

Frontend validation was run after the Feishu UI changes:

```bash
cd client
./node_modules/.bin/eslint src/components/collaboration/FeishuIntegrationModal.tsx \
  src/hooks/useFeishuIntegration.ts src/services/api.ts --quiet
./node_modules/.bin/eslint src/components/collaboration/FeishuIntegrationModal.tsx src/services/api.ts --quiet
./node_modules/.bin/tsc -b
./node_modules/.bin/vite build
```

Result: latest eslint/typecheck passed for touched Feishu UI/API files. Earlier full Vite build passed with pre-existing CSS/chunk/Browserslist warnings.

## Real Feishu E2E status

PARTIAL: real Feishu Probe is available, but the true receive/reply E2E is still blocked by the lack of an explicitly authorized test group/private chat target.

`FEISHU_APP_ID` and `FEISHU_APP_SECRET` were present locally and a safe real Probe plus chat-list count succeeded without sending any message. No explicit test group/private chat target was provided, and this handoff round did not send a message to any visible-but-unknown chat. The evidence tooling now prints only hash refs for Feishu chat/event/message/user/tenant/app identifiers and does not print group names or raw chat ids. Therefore the following remain unverified in production reality:

- real app install/authorization;
- real URL verification initiated from Feishu developer console;
- real WebSocket delivery of `im.message.receive_v1`;
- real group `@Byaan -> Agent -> Reply`;
- real same-topic follow-up in Feishu UI;
- real private chat loop;
- real event replay from Feishu retry behavior;
- real token invalidation;
- real bot removed from group / permission revoked;
- real outbound message to selected test group.

Do not report this integration as complete based only on contract tests or probe tests.

## Required environment variables / secrets

Names only; never commit or print values:

- `DATABASE_URL`
- `APP_SECRET`
- `ENCRYPTION_KEY`, if the deployment uses an explicit encryption key instead of deriving from `APP_SECRET`
- `FEISHU_APP_ID` and `FEISHU_APP_SECRET`, only for local credential-safe probe tooling; production configuration should be stored through the admin UI encrypted credentials path
- Feishu app id and secret supplied through the admin UI or local secure configuration
- Feishu callback verification token, if callback verification is tested
- Feishu encrypt key, if callback verification is tested

## Current completion audit

This audit is based on the current worktree and external state at this handoff point. Treat unverified items as incomplete.

| Requirement | Status | Evidence / next action |
| --- | --- | --- |
| Token-refresh fix committed and clean | Done | `13c0bea`, `254982c`, worktree clean before this update; token-focused regression `8 passed`. |
| Feishu-owned slice mapped for review | Done as handoff material | `Integration-ready linear slice mapping` section above. |
| Clean branch from frozen integration base exists | Pending | Integration Owner has not provided a frozen base; do not create the final `feature/feishu-collaboration-integration-ready` branch yet. |
| Source/Semantic/Data Modeling history excluded from final branch | Pending final branch | Exclusion list above identifies paths/commits to omit; final proof requires the clean branch diff. |
| Public Alembic one-head migration | Pending Integration Owner | This branch contains proposal material only; final migration must be re-linearized on the frozen base. |
| Credential-safe real Probe | Done | Latest probe: `ok=true`, `visible_chat_count=7`, `sent_message=no`; no raw chat ids/group names printed. |
| Local event/webhook simulator | Done in Feishu owner branch | `server/collaboration/feishu/simulator.py` plus `server/tests/test_feishu_simulator_contract.py`; covers signed/encrypted challenge, replay rejection, message event, out-of-order, recalled, unknown, and stale callbacks. |
| Local outbound sink/test transport | Done in Feishu owner branch | `FeishuOutboundSink` plus `server/tests/test_feishu_outbound_sink_contract.py`; covers redacted delivery refs, idempotency-key refs, ACK/final/follow-up retry transitions, and API outbound idempotency without contacting Feishu. |
| Admin UI/API status coverage | Partially done in Feishu owner branch | Installation/health expose `admin_state`; delivery targets expose `status`/redacted `last_error`; UI target binding uses selector-derived `topic_group` for root_id. Final browser proof remains pending Integration Owner deployment. |
| Explicit real test group/private chat authorization | Blocked on owner/user | No authorized target has been provided. |
| Real `@Bot -> Agent -> Reply` E2E | Blocked on authorized target and isolated deployment | Not attempted; do not claim complete. |
| Follow-up, replay, outbound, reauth, target revoke, restart evidence | Blocked on authorized target and isolated deployment | Contract tests exist, but real E2E evidence is still missing. |
| Slack compatibility | Done for current slice | Latest focused Feishu/Collaboration regression includes `server/tests/test_slack_compatibility_adapter.py`: `86 passed, 12 warnings`. |
| Integration Owner merge/deploy complete | Pending Integration Owner | Requires frozen base, clean branch, one-head migration, isolated deployment, and real E2E. |

Current status labels:

- CODE COMPLETE: partial Feishu-owned slice only; not final integration complete.
- CREDENTIAL PROBE PASSED: yes.
- TARGET AUTHORIZATION BLOCKED: yes.
- REAL MESSAGE E2E BLOCKED: yes.
- INTEGRATION PENDING: yes.
- DEPLOYMENT PENDING: yes.

## Real E2E evidence collection

Use `docs/feishu-collaboration-e2e.md` and `scripts/feishu_collaboration_e2e.py` after Integration Owner deployment. The script defaults to read-only snapshot mode and will not send a message unless explicitly asked with `--send-test-message --chat-id`.

Minimum evidence to attach before marking complete:

- desensitized test group identifier;
- desensitized event id / message id;
- Byaan Agent Run id;
- Notebook id;
- first group question result;
- same-topic follow-up reusing Notebook;
- private chat result;
- idempotent replay result;
- outbound send result;
- restart/auto-resume result.
- callback URL verification health and event subscription readiness from the E2E evidence snapshot.

## Suggested one-time Integration Owner merge plan

1. Freeze the target Team/Data Modeling integration commit.
2. Rebase or merge this branch once onto that commit; do not keep chasing every integration push.
3. Re-linearize Alembic using `docs/feishu-collaboration-migration-proposal.md`; ensure one Alembic head.
4. Run upgrade/downgrade/upgrade on a Team database copy and compare counts for User, Tenant, Notebook, Connection, Dataset/Source, Semantic Model, Slack, and collaboration tables.
5. Deploy to an isolated self-hosted Team instance.
6. Configure a real Feishu test app and explicit test group.
7. Run the real E2E checklist above.
8. Only after real E2E passes, deploy or promote to the 8080 Team Version according to the Integration Owner rollout plan.

## Integration Owner handoff package

Provide or verify these artifacts when ownership transfers:

1. Frozen Team/Data Modeling base commit and the clean Feishu integration branch HEAD.
2. Original commit to review-bucket mapping from this document.
3. Final one-head Alembic revision generated from the migration proposal, including upgrade/downgrade/upgrade output.
4. Environment variable names only, with secret values supplied out of band.
5. Real E2E evidence produced by `scripts/feishu_collaboration_e2e.py` plus human-observed Feishu first-question/follow-up/private-chat results.
6. Slack compatibility regression output.
7. 8080 deployment record: image tag/ID, container ID, preserved volume, rollback image tag, and restart/auto-resume proof.

Rollback plan:

1. Disable or disconnect the Feishu installation from the admin UI/API; this should stop processing new events and release/expire the WebSocket lease.
2. Stop the Feishu WebSocket consumer process/container if the deployment does not release cleanly.
3. Revert to the recorded rollback image tag while preserving `byaan_data` and the existing Team database.
4. Keep collaboration audit/event/response-ref rows for forensics; do not delete Slack tables or existing Team data.
5. If the final migration must be rolled back, use the Integration Owner's one-head downgrade path and verify User, Tenant, Notebook, Connection, Dataset/Source, Semantic Model, and Slack counts before/after.
