# Feishu Collaboration E2E verification

This branch does not deploy or mutate the shared 8080 Team Version by itself.
After the Integration Owner replays the commits and deploys the Team branch, use
the evidence collector below to verify the real Feishu loop.

Safety defaults:

- default mode is read-only;
- secrets and tenant tokens are not printed;
- no message is sent unless `--send-test-message --chat-id <oc_xxx>` is passed;
- the script reads the configured Team database through `DATABASE_URL`.

Commands:

```bash
# Local callback + outbound contract acceptance. These commands do not connect
# to Feishu and do not require or print real chat ids.
PYTHONPATH=. uv run pytest \
  server/tests/test_feishu_simulator_contract.py \
  server/tests/test_feishu_outbound_sink_contract.py -q

# Read current installation, health, recent events, conversations, notebooks,
# response refs, external identities, and delivery targets.
DATABASE_URL=<team-db-url> APP_SECRET=<team-app-secret> \
  uv run python scripts/feishu_collaboration_e2e.py --snapshot

# List Bot-visible chats before choosing a test group. Output contains only
# chat_ref hashes and chat_type, not raw chat_id or group names.
DATABASE_URL=<team-db-url> APP_SECRET=<team-app-secret> \
  uv run python scripts/feishu_collaboration_e2e.py --list-chats

# Send a test message only after the owner provides an explicit known test
# chat_id out of band. Do not treat a chat_ref hash as send authorization.
DATABASE_URL=<team-db-url> APP_SECRET=<team-app-secret> \
  uv run python scripts/feishu_collaboration_e2e.py \
  --send-test-message --chat-id oc_xxx

# Capture evidence for a human-triggered @ / DM journey.
DATABASE_URL=<team-db-url> APP_SECRET=<team-app-secret> \
  uv run python scripts/feishu_collaboration_e2e.py --wait-new-event --timeout 180
```

Required final evidence:

- local simulator verifies signed/encrypted URL verification, replay rejection, message event normalization, duplicate event construction, out-of-order topic events, recalled/unknown events, and stale callback rejection;
- local outbound sink verifies redacted delivery refs, idempotency-key refs, ACK/final/follow-up delivery state, retry transitions, p2p/outbound send paths where covered by API/event contract tests, and no raw message text or Feishu target ids in recorded evidence;
- admin UI/API exposes not installed, admin authorization pending, installed/configured, target unbound/needs rebind, sending/success/failure, and needs reauth states; target binding uses the chat selector path and not manual chat id as the primary path;
- group first @ creates one completed event, one conversation, one Notebook, and response refs;
- same topic follow-up reuses the same conversation and Notebook;
- unowned group topic is ignored;
- DM creates an independent conversation and Notebook;
- replaying the same `event_id` remains duplicate/idempotent;
- `recent_external_identities` shows the Feishu sender mapped inside the same tenant without exposing raw full IDs;
- `recent_delivery_targets` shows the selected chat/topic target and whether it was explicitly verified;
- `--list-chats`, `snapshot`, and `wait-new-event` evidence expose only hash refs for chat/event/message/user/tenant/app identifiers and do not print group names or raw chat ids;
- `installation.callback` shows signed/encrypted URL verification status and timestamp without exposing verification token or encrypt key;
- `installation.event_subscription` shows whether `im.message.receive_v1` has been observed, with event ids shortened;
- container restart auto-resumes the active WebSocket and receives another message.
