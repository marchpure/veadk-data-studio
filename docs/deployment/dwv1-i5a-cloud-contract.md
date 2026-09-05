# DWV1 I5-A Cloud Contract

This contract is for the Data Studio deployment only. It does not modify or
copy OpenConnector or W5 source code.

## Runtime boundary

- One VeFaaS function serves the compiled client and FastAPI BFF.
- APIG owns the stable HTTPS origin and routes `/api/*` to the BFF.
- The browser receives only `dwv1_oidc_session`, a Secure, HttpOnly,
  SameSite=Strict cookie.
- W5 calls use the formal HTTPS runtime endpoint. The BFF never starts an
  AgentKit CLI subprocess.
- OpenConnector admin calls, OpenViking upstream calls, and W5 credentials are
  resolved server-side from the Data Studio KMS secret document.

## KMS secret fields

`DWV1_RUNTIME_SECRET_NAME` must refer to `dwv1/data-studio/dev`:

- `app_secret`
- `data_studio_oauth_client_secret`
- `broker_service_credential`
- `openconnector_admin_token`
- `openviking_api_key`
- `openviking_profile_key`

`DWV1_SKILL_AGENT_SECRET_NAME` must refer to `dwv1/skill-agent/dev`:

- `w5_runtime_api_key`

Secret values must never be committed, logged, returned by an API, or placed
in browser storage. `DWV1_ALLOW_ENV_SECRETS` remains false in cloud mode.

## OIDC binding

- UserPool: `f69c17b4-d030-43bc-b4a7-9cae0f6370c3`
- Client ID: a new Data Studio OAuth client, never the WorkBuddy client
- Callback: `<final-https-origin>/api/auth/external/callback`
- Required validation: RS256 signature, exact issuer, audience, expiry, nbf,
  subject, and `client_id` or `azp` equal to the Data Studio client ID
- Required identity: verified `sub`, group claim, and optional required group

## Persistent data boundary

PostgreSQL `postgres-ef669f38f7c6` may host a dedicated Data Studio database,
schema, and account. Data Studio migrations must not use OpenConnector tables.
The KMS `database_url` field supplies the async application URL and the
profile-store sync URL. The profile repository uses the same PostgreSQL
database and only the Data Studio-owned tables.

Required identifiers for the approved reuse plan:

- instance: `postgres-ef669f38f7c6`
- database: `data_studio_dev`
- schema: `data_studio`
- account: `data_studio_app`

The approved TOS bucket may be reused only with:

- `data-workshop/`
- `skill-artifacts/`

Lifecycle rules must not delete active skill artifacts.

## Fail-closed states

- Missing KMS field: `BLOCKED_CONFIG`
- Missing or invalid OIDC session: `401`
- Missing verified external subject/groups/token: `BLOCKED_AUTH`
- Missing W5 HTTPS endpoint or API key: `BLOCKED_CONFIG`
- Revoked, expired, replayed, cross-tenant, wrong-audience, wrong-issuer, or
  wrong-UserPool delegation: `404`
