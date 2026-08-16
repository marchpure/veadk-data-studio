# Source/Evidence real Feishu Sheet + TOS E2E runbook

This runbook is intentionally credential-free. Do not paste secrets, tokens, object keys containing sensitive names, or Feishu URLs into git, logs, or handoff notes.

## Status

- Local contract E2E can run without external credentials.
- Real E2E is blocked until controlled non-production Feishu Sheet and TOS resources are explicitly provided.
- Skipped real E2E tests are not counted as passed completion evidence.

## Required permissions

### Feishu Sheet

- Non-production Feishu token with read access to one test spreadsheet.
- Scope: `sheets:spreadsheet:readonly`.
- The token holder must be able to read spreadsheet metadata, sheet list, and the configured value range.
- The test spreadsheet must contain a simple header row plus at least two numeric data rows.

### Volcengine TOS

- Non-production TOS bucket and one test object.
- Read-only access key or temporary credentials scoped to the test bucket/object.
- Object format must be one of CSV, XLSX, XLSM, JSON, JSONL, or Parquet for normalized Dataset verification.
- The object should contain a header plus at least two numeric data rows.

## Environment variables

Set names only; never commit or print values.

### Feishu Sheet

```bash
export BYAAN_REAL_FEISHU_ACCESS_TOKEN=
export BYAAN_REAL_FEISHU_REFRESH_TOKEN=   # optional; required only for refresh/reauth recovery checks
export BYAAN_REAL_FEISHU_SPREADSHEET_TOKEN=
export BYAAN_REAL_FEISHU_SHEET_ID=
export BYAAN_REAL_FEISHU_RANGE=
```

### TOS

```bash
export BYAAN_REAL_TOS_ENDPOINT=
export BYAAN_REAL_TOS_REGION=
export BYAAN_REAL_TOS_ACCESS_KEY_ID=
export BYAAN_REAL_TOS_SECRET_ACCESS_KEY=
export BYAAN_REAL_TOS_BUCKET=
export BYAAN_REAL_TOS_OBJECT_KEY=
```

## Resource preparation

1. Create a dedicated non-production Feishu spreadsheet.
2. Add a single sheet/range with stable headers, for example `region,target`.
3. Grant the OAuth subject read access.
4. Create a dedicated non-production TOS bucket/object.
5. Upload a simple object such as `region,revenue` CSV.
6. Grant read-only access only to that bucket/object where possible.
7. Confirm both resources can be safely updated and revoked during the test.

## Commands

Run local contract tests first:

```bash
/Users/bytedance/byaan/.venv/bin/python -m pytest \
  server/tests/test_source_connectors_api.py \
  server/tests/test_source_evidence_contract_fixtures.py \
  -q
```

Run real E2E only after all required `BYAAN_REAL_*` variables are present:

```bash
/Users/bytedance/byaan/.venv/bin/python -m pytest \
  server/tests/test_real_source_connector_e2e.py \
  -q -rs
```

## Expected real E2E result

- Feishu Sheet creates a `SourceConnection`, `SourceResource`, `SourceSnapshot`, `KnowledgeResource`, `EvidenceFragment`, and normalized Dataset projection.
- TOS object creates the same chain and projects the object to a normalized Dataset.
- Snapshot metadata, evidence locators, dataset projection manifests, error payloads, and raw storage URIs expose only `*:ref:<hash>` references for sensitive Feishu/TOS identifiers.
- No access token, refresh token, app secret, TOS key, full Feishu URL, bucket name, object key, or document/body text appears in API payloads or assertion output.

## Update, revoke, and recovery checks

After the basic real E2E passes:

1. Update the Feishu range and TOS object content.
2. Re-run the real E2E and verify a new `SourceSnapshot` is produced.
3. Re-run without changing content and verify same-content sync is idempotent.
4. Revoke Feishu access or expire the token in the controlled test setup.
5. Verify status becomes `reauthorization_required` and the previous successful snapshot remains available.
6. Remove TOS object permission or point to a missing controlled object.
7. Verify status becomes `permission_lost` or `source_unavailable` and previous successful snapshot remains available.
8. Restore permissions and verify sync can recover.

## Cleanup

1. Delete or archive the test Feishu spreadsheet.
2. Delete the TOS test object and bucket if no longer needed.
3. Revoke temporary TOS credentials.
4. Revoke Feishu test token/app grant if it was created only for this run.
5. Unset all `BYAAN_REAL_*` variables in the shell.
6. Do not copy secret-containing shell history or test output into docs.

## Rollback

This branch does not add public migrations. If the change must be rolled back before merge:

1. Revert the Source/Evidence code/test/docs commits from the source/evidence branch.
2. Remove generated local test datasets/storage under the test environment only.
3. Do not touch production/self-hosted Docker stacks or shared migrations as part of this runbook.
