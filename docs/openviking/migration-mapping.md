# DWV1 W6 OpenViking migration mapping

Frozen sources were read from `/Users/bytedance/veadk-python-research` without
modifying that repository:

- Primary: `d203bfb89a36baa908d0e60ef49f6175dd623942`
- Isolation: `7ab6a8697a04cbbfdea7f88aaa27d6c117663fc2`

| Donor file or capability | Target file or module | Adaptation reason | Test evidence |
| --- | --- | --- | --- |
| `frontend/src/extensions/openviking/**` (165 source files) | `client/src/features/openviking/**` | Preserve the frozen workspace, generated SDK, UI primitives, hooks, localization, and isolated styles as one module. | 29 Vitest files, 129 tests |
| `OpenVikingWorkspace.tsx` | `features/openviking/OpenVikingWorkspace.tsx`, `pages/OpenVikingPage.tsx` | Adapt to target React Router and Layout; retain Resources, Retrieval, Tasks, Watches, and Connection pages. | Browser route, navigation, and refresh journey |
| `ResourceContextTree` and resource APIs | `OpenVikingWorkspace.tsx`, `routes/resources/**`, `lib/ov-client/client.ts` | Translate hosted URIs to opaque BFF references and preserve resource display URIs. | Live tree (48 nodes after restart), `fs_stat`, browser tree |
| `LazyFilePreview` and file preview | `routes/resources/-components/lazy-file-preview.tsx`, `file-preview.tsx` | Read through the BFF reference endpoint; no browser upload path dependency. | Live `resource/read` 200 and browser marker preview |
| `AddResourceForm` and import hooks | `routes/resources/-components/add-resource-page.tsx`, `resource-upload.ts`, BFF upload/text/connection routes | Keep donor import UX while adapting multipart upload and target Source Resource lookup. | Live text, URL, TXT, Markdown, PDF, CSV, JSON, XLSX, and Connection imports |
| `RetrievalPage` and retrieval library | `routes/retrieval/**`, `lib/retrieval.ts` | Keep find/search/grep/glob UX; map `target_uri` to signed refs and allow all donor request fields. | Browser live find/search/grep/glob all HTTP 200 |
| `TasksRoute` and task normalization | `routes/tasks/**` | Preserve hosted task status, detail, failure, and retry UI. | 26 hosted tasks rendered; completed and failed states; retry request reached hosted service |
| `WatchesRoute` and watch API | `routes/watches/**` | Preserve create, list, pause/resume, trigger, history, and delete operations through BFF item routes. | Live create/list/update/trigger/delete |
| `KnowledgeSourceRef` / `ResourceRef` | `contracts.ts`, `lib/ov-client/client.ts`, `openviking_service.py` | Profile-bound HMAC capabilities replace raw URIs. Global hosted search results can only obtain refs from trusted BFF responses. | Ref tamper, cross-profile, unsigned-ref, and global-context tests |
| Donor profile selection | `profile-selection.ts`, `OpenVikingWorkspace.tsx`, `api.ts` | Adapt profile CRUD to target standard envelopes; keep Pending/Ready/Error and never prefill credentials. | Live create/edit/validate/restart/revoke and wrong-key 401 |
| Donor BFF service | `server/services/openviking_service.py` | AES-GCM credentials, tenant/workspace/principal isolation, recursive redaction, idempotency, URL validation, hosted error mapping. | 18 service tests plus hosted fail-closed checks |
| Donor extension routes | `server/routers/openviking.py` | Mount under `/api/knowledge/openviking`, use target `AuthContext`, scopes, database session, and response envelope. | 4 router tests |
| Isolation registration | `App.tsx`, `vite.config.ts`, `tsconfig.app.json`, `vitest.config.ts` | Lazy route entry, donor aliases, dedicated production JS/CSS chunks. | `OpenVikingPage-CrEsKhVt.js` and `OpenVikingPage-0mDA1AqO.css` |
| Responsive workspace styles | `openviking.css`, `components/Layout.tsx` | Keep the target sidebar on desktop and release its width to the OpenViking mobile navigation at 760px. | 1440x900, 1280x800, 390x844; zero horizontal overflow |

## Security boundary

- OpenViking is hosted; no OpenViking server is deployed by this change.
- The API key is injected into the BFF, encrypted at rest, masked in responses,
  and absent from browser storage and repository evidence.
- Profiles remain OpenViking profiles. Target Connections are import-only source
  records and are narrowed server-side before import.
- Skill Context receives only a profile ID and signed `ResourceRef`; raw hosted
  URIs cannot be submitted by the browser.

## Verification

- Backend: 22 tests passed.
- Frontend: 29 files, 129 tests passed.
- TypeScript, production build, Python compile, diff check, and secret scan passed.
- OpenViking lint: 0 errors and 9 retained donor hook/refresh warnings.
- Hosted task retry was exercised against a real failed historical task. The
  approved hosted service rejected reindex with HTTP 502 because the original
  resource no longer exists; the UI and BFF retry path were exercised without
  fabricating a successful task.
