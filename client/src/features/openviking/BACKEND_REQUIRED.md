# OpenViking credential policy backend contract

Status: `BACKEND_REQUIRED=yes`

The frontend defaults to `managed` and does not infer credential behavior from
enterprise OIDC. Genuine BYOK and hybrid operation requires the backend changes
below.

## Configuration

Expose a non-secret effective policy:

```text
OPENVIKING_CREDENTIAL_POLICY=managed|byok|hybrid
```

`GET /api/app/config` should return
`openviking_credential_policy: "managed" | "byok" | "hybrid"`.

## Profile model and API

- Add `credential_mode` (`managed` or `byok`) to every Profile.
- Migrate existing Profiles forward compatibly. Determine the initial mode from
  server-owned evidence during migration; do not infer it in the browser.
- Profile list/create/update/validate responses may return
  `credential_mode`, `api_key_configured`, and a mask. They must never return
  the API Key or Base URL credentials.
- Return the Profile's display-safe `workspace_uri` and `last_validated_at`;
  the current `opaque-workspace` placeholder cannot satisfy the list view.
- `managed`: reject browser-supplied `base_url` and `api_key`; resolve both from
  server-managed secrets.
- `byok`: require an HTTPS Base URL and API Key on create. Preserve the existing
  SSRF checks and allowlist.
- `hybrid`: require an explicit Profile `credential_mode`, then apply the
  corresponding rule.
- Rotating a BYOK key must use an explicit HTTPS `POST` or `PATCH` request body.
  An omitted or empty key keeps the current encrypted key.
- The raw key must occur only in the one create/rotate request body. It must
  never enter a URL, response, browser storage, normal logs, or evidence.
- Keep the existing tenant/workspace/principal isolation. Deleting one Profile
  must delete only its ResourceRefs and must not affect other Profiles.
- Record and return a non-secret `last_validated_at` timestamp after each health
  check so the list can distinguish health-check time from update time.

Once the config field exists, the host should pass it to
`OpenVikingWorkspace.credentialPolicy`. Until then, managed mode remains the
safe default and the UI does not claim that BYOK succeeded.
