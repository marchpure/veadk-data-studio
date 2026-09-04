# DWV1 W6 OpenViking migration mapping

Source commits are read-only snapshots from `/Users/bytedance/veadk-python-research`.

| Donor capability/file | Target module | Adaptation | Evidence |
| --- | --- | --- | --- |
| `frontend/server/extensions/openviking/service.py` (`d203bfb`) | `server/services/openviking_service.py` | Encrypted profile/BFF boundary, hosted upstream proxy, allow-listed fs/content/search/task/watch operations, task history, idempotent writes, recursive redaction, file and connection-resource imports. | `tests/test_openviking_bff.py` (4 passed); compileall |
| `frontend/server/extensions/openviking/routes.py` (`d203bfb`) | `server/routers/openviking.py` | FastAPI router under target `/api`, `AuthContext` scopes, standardized response envelope, profile lifecycle and connection-resource import endpoint. | `tests/test_openviking_bff.py`; compileall |
| `frontend/src/extensions/openviking/OpenVikingWorkspace.tsx` (`d203bfb`) | `client/src/pages/OpenVikingPage.tsx` | React Router/Layout adaptation with structured resource/retrieval/task/watch panels; operation calls remain BFF-backed and no browser API key. | `client` typecheck/build; browser screenshots |
| donor `openviking.css` | `client/src/pages/openviking.css` | Isolated target stylesheet with responsive 1440/1280/390 layout. | browser screenshots |
| donor `KnowledgeSourceRef` / `ResourceRef` contracts | `skill-context` response and operation payloads | Target keeps profile/resource identities as opaque context data and does not convert profiles into connections. | BFF ref validation/redaction tests; browser screenshots |
| donor isolation `knowledge_workspace/*` | target BFF route boundary | Target already owns connection/source resources; only the OpenViking profile/resource boundary is added, avoiding cross-domain route ownership. | route inventory |

## Verification status

The encryption key is task-local configuration. Hosted live E2E requires an approved hosted base URL and API key injected through the runtime secret source; no local OpenViking server is started. This run completed migration, static verification, and browser shell verification; hosted live E2E remains explicitly unexecuted because no approved base URL was present.

## Browser Evidence

- Preview: `http://localhost:5173/kb/connect`
- 1440x900: `/tmp/dwv1-openviking-1440x900-current.png`
- 1280x800: `/tmp/dwv1-openviking-1280x800-current.png`
- 390x844: `/tmp/dwv1-openviking-390x844-current.png`
- Lazy chunk: `client/dist/assets/OpenVikingPage-*.js`
