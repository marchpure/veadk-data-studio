# DWV1 W6 OpenViking migration mapping

Source commits are read-only snapshots from `/Users/bytedance/veadk-python-research`.

| Donor capability/file | Target module | Adaptation | Evidence |
| --- | --- | --- | --- |
| `frontend/server/extensions/openviking/service.py` (`d203bfb`) | `server/services/openviking_service.py` | Encrypted profile/BFF boundary, hosted upstream proxy, opaque profile-scoped ResourceRef, allow-listed fs/content/search/task/watch operations, task history, idempotent writes, recursive redaction, two-stage file/text imports, URL SSRF protection. | `tests/test_openviking_bff.py` (6 passed); hosted journey |
| `frontend/server/extensions/openviking/routes.py` (`d203bfb`) | `server/routers/openviking.py` | FastAPI router under target `/api`, `AuthContext` scopes, standardized response envelope, profile lifecycle, resolve/read, and connection-resource import endpoints. | `tests/test_openviking_bff.py`; compileall |
| `frontend/src/extensions/openviking/OpenVikingWorkspace.tsx` (`d203bfb`) | `client/src/pages/OpenVikingPage.tsx` | React Router/Layout adaptation with structured resource/retrieval/task/watch panels; operation calls remain BFF-backed and no browser API key. | `client` typecheck/build; browser screenshots |
| donor `openviking.css` | `client/src/pages/openviking.css` | Isolated target stylesheet with responsive 1440/1280/390 layout. | browser screenshots |
| donor `KnowledgeSourceRef` / `ResourceRef` contracts | `skill-context` response and operation payloads | Target keeps profile/resource identities as opaque context data and does not convert profiles into connections. | BFF ref validation/redaction tests; browser screenshots |
| donor isolation `knowledge_workspace/*` | target BFF route boundary | Target already owns connection/source resources; only the OpenViking profile/resource boundary is added, avoiding cross-domain route ownership. | route inventory |

## Verification status

The encryption key is task-local configuration. Hosted live E2E used the approved hosted base URL and an API key injected through `OPENVIKING_E2E_API_KEY`; no local OpenViking server was started. The browser used only the target BFF and did not receive the API key.

## Browser Evidence

- Preview: `http://127.0.0.1:5182/kb`
- Connect 1440x900: `/tmp/dwv1-w6-desktop-1440x900.png`
- Connect 1280x800: `/tmp/dwv1-w6-laptop-1280x800.png`
- Connect 390x844: `/tmp/dwv1-w6-mobile-390x844.png`
- Resources 1440x900: `/tmp/dwv1-w6-resource-desktop-1440x900.png`
- Resources 1280x800: `/tmp/dwv1-w6-resource-laptop-1280x800.png`
- Resources 390x844: `/tmp/dwv1-w6-resource-mobile-390x844.png`
- Lazy chunk: `client/dist/assets/OpenVikingPage-*.js`
