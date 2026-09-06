import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type SVGProps,
} from 'react'
import {
  Link,
  NavLink,
  Navigate,
  useLocation,
  useNavigate,
} from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import { Toaster } from 'sonner'

import { openVikingApi } from './api'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from './components/ui/dialog'
import {
  AppConnectionProvider,
  type OpenVikingProfile,
} from './hooks/use-app-connection'
import i18n from './i18n'
import { getOpenVikingResourceRef, registerOpenVikingRoot } from './lib/ov-client/client'
import { ResourceContextTree } from './routes/resources/-components/context-tree'
import { FindPalette } from './routes/resources/-components/find-palette'
import { LazyFilePreview } from './routes/resources/-components/lazy-file-preview'
import { useInvalidateVikingFs } from './routes/resources/-hooks/viking-fm'
import {
  deleteFsResource,
  fetchFsStat,
} from './routes/resources/-lib/api'
import {
  ACTIVE_OPENVIKING_PROFILE_KEY,
} from './profile-selection'
import {
  fileNameFromUri,
  normalizeDirUri,
  parentUri,
} from './routes/resources/-lib/normalize'
import type { VikingFsEntry } from './routes/resources/-types/viking-fm'
import {
  AddResourceForm,
  ResourceUploadProvider,
} from './routes/resources/resource-upload'
import { RetrievalPage } from './routes/retrieval/route'
import { TasksRoute } from './routes/tasks/route'
import { WatchesRoute } from './routes/watches/route'
import './openviking.css'

type OpenVikingPage =
  | 'resources'
  | 'retrieval'
  | 'tasks'
  | 'watches'
  | 'settings'

const queryClient = new QueryClient()
const detailPages = new Set<OpenVikingPage>([
  'resources',
  'retrieval',
  'tasks',
  'watches',
  'settings',
])

export type OpenVikingCredentialPolicy = 'managed' | 'byok' | 'hybrid'

type KnowledgeRoute =
  | { kind: 'list' }
  | { kind: 'new' }
  | { kind: 'redirect'; to: string }
  | { kind: 'detail'; profileId: string; page: OpenVikingPage }

function parseKnowledgeRoute(pathname: string): KnowledgeRoute {
  const parts = pathname
    .replace(/^\/kb\/?/, '')
    .split('/')
    .filter(Boolean)
    .map((part) => decodeURIComponent(part))
  if (!parts.length) return { kind: 'list' }
  if (parts[0] === 'new' || parts[0] === 'connect') return { kind: 'new' }
  if (parts.length === 1) {
    return {
      kind: 'redirect',
      to: `/kb/${encodeURIComponent(parts[0])}/resources`,
    }
  }
  const page = parts[1] as OpenVikingPage
  if (!detailPages.has(page)) return { kind: 'list' }
  return { kind: 'detail', profileId: parts[0], page }
}

function credentialMode(profile: OpenVikingProfile): 'managed' | 'byok' {
  return profile.credential_mode === 'byok' ? 'byok' : 'managed'
}

function credentialModeLabel(profile: OpenVikingProfile): string {
  return credentialMode(profile) === 'managed'
    ? '平台托管凭据'
    : '自有 OpenViking 凭据'
}

function statusLabel(status: OpenVikingProfile['status']): string {
  return {
    pending: '待检查',
    ready: '可用',
    error: '连接异常',
  }[status]
}

function formatDate(value?: string | number | null): string {
  if (value === undefined || value === null || value === '') return '暂无记录'
  const date = new Date(
    typeof value === 'number' && value < 10_000_000_000
      ? value * 1000
      : value,
  )
  if (Number.isNaN(date.getTime())) return '暂无记录'
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function ResourcesIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path d="M3 4.25h5l1.45 1.6H17v9.9H3V4.25Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.45" />
      <path d="M6.25 9h7.5M6.25 12h5" stroke="currentColor" strokeLinecap="round" strokeWidth="1.3" />
    </svg>
  )
}

function ConnectionIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path d="M7.5 6.75 5.25 9a3 3 0 0 0 4.25 4.25l1.25-1.25m1.75 1.25L14.75 11A3 3 0 0 0 10.5 6.75L9.25 8" stroke="currentColor" strokeLinecap="round" strokeWidth="1.45" />
    </svg>
  )
}

function SearchIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <circle cx="8.6" cy="8.6" r="4.6" stroke="currentColor" strokeWidth="1.45" />
      <path d="m12.1 12.1 3.8 3.8" stroke="currentColor" strokeLinecap="round" strokeWidth="1.45" />
    </svg>
  )
}

function AddIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path d="M10 4v12M4 10h12" stroke="currentColor" strokeLinecap="round" strokeWidth="1.5" />
    </svg>
  )
}

function RefreshIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path d="M15.6 7.1A6 6 0 1 0 16 12" stroke="currentColor" strokeLinecap="round" strokeWidth="1.45" />
      <path d="M15.6 3.7v3.4h-3.4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.45" />
    </svg>
  )
}

function DeleteIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path d="M4.5 6h11M8 3.75h4M6.25 6l.65 10.25h6.2L13.75 6M8.25 8.5v5.25m3.5-5.25v5.25" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.35" />
    </svg>
  )
}

function ShieldIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path d="M10 2.75 16 5v4.4c0 3.7-2.25 6.25-6 7.85-3.75-1.6-6-4.15-6-7.85V5l6-2.25Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.4" />
      <path d="m7.25 9.9 1.75 1.75 3.75-4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.4" />
    </svg>
  )
}

function rootEntry(uri: string): VikingFsEntry {
  return {
    uri,
    name: fileNameFromUri(uri) || 'OpenViking',
    isDir: true,
    size: '',
    sizeBytes: null,
    modTime: '',
    modTimestamp: null,
    abstract: '',
    overview: '',
  }
}

function expandedAncestors(uri: string, rootUri: string): Set<string> {
  const root = normalizeDirUri(rootUri)
  const values = new Set<string>()
  let current = parentUri(uri)
  while (current.startsWith(root) && current !== root) {
    values.add(current)
    const next = parentUri(current)
    if (next === current) break
    current = next
  }
  return values
}

function ProfileForm({
  credentialPolicy,
  onCreated,
}: {
  credentialPolicy: OpenVikingCredentialPolicy
  onCreated: (profile: OpenVikingProfile) => void
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [mode, setMode] = useState<'managed' | 'byok'>(
    credentialPolicy === 'byok' ? 'byok' : 'managed',
  )
  const byokEnabled = credentialPolicy === 'byok' || credentialPolicy === 'hybrid'

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    setPending(true)
    setError('')
    const fields = new FormData(form)
    try {
      const input = {
        display_name: String(fields.get('display_name') || ''),
        workspace_uri: String(fields.get('workspace_uri') || ''),
        ...(mode === 'byok'
          ? {
              api_key: String(fields.get('api_key') || ''),
              base_url: String(fields.get('base_url') || ''),
              credential_mode: 'byok' as const,
            }
          : credentialPolicy === 'hybrid'
            ? { credential_mode: 'managed' as const }
            : {}),
      }
      const profile = await openVikingApi.createProfile(input)
      form.reset()
      if (credentialPolicy === 'managed') {
        onCreated(await openVikingApi.validateProfile(profile.profile_id))
      } else {
        onCreated(profile)
      }
    } catch (value) {
      setError(value instanceof Error ? value.message : '知识库创建失败')
    } finally {
      setPending(false)
    }
  }

  return (
    <form className="ov-profile-form" onSubmit={submit}>
      <div className="ov-profile-heading">
        <span className="ov-profile-heading-icon"><ShieldIcon /></span>
        <div>
          <h1>新建知识库</h1>
          <p>创建独立的 OpenViking Profile，资源和任务不会与其他知识库混用。</p>
        </div>
      </div>
      {credentialPolicy === 'hybrid' ? (
        <fieldset className="ov-credential-options">
          <legend>凭据模式</legend>
          <label>
            <input
              checked={mode === 'managed'}
              name="credential_mode"
              onChange={() => setMode('managed')}
              type="radio"
              value="managed"
            />
            <span><strong>平台托管凭据</strong><small>由平台安全提供 Endpoint 和 API Key。</small></span>
          </label>
          <label>
            <input
              checked={mode === 'byok'}
              name="credential_mode"
              onChange={() => setMode('byok')}
              type="radio"
              value="byok"
            />
            <span><strong>自有 OpenViking</strong><small>使用你自己的 Endpoint 和 API Key。</small></span>
          </label>
        </fieldset>
      ) : (
        <div className="ov-managed-credential">
          <ShieldIcon />
          <div>
            <strong>{credentialPolicy === 'managed' ? '平台托管凭据' : '自有 OpenViking 凭据'}</strong>
            <span>
              {credentialPolicy === 'managed'
                ? 'Endpoint 和 API Key 由平台安全托管，浏览器不会接触密钥。'
                : 'API Key 仅通过本次加密请求提交，保存后不会再次显示。'}
            </span>
          </div>
        </div>
      )}
      <div className="ov-form-grid">
        <label>
          知识库名称
          <input name="display_name" required placeholder="例如：产品文档库" />
        </label>
        <label>
          Workspace URI
          <input name="workspace_uri" required defaultValue="viking://resources/" />
        </label>
      </div>
      {byokEnabled && mode === 'byok' ? (
        <>
          <label>
            Base URL
            <input name="base_url" required type="url" placeholder="https://…" />
          </label>
          <label>
            API Key
            <input name="api_key" required type="password" autoComplete="new-password" />
          </label>
          <p className="ov-security-note">密钥只在本次 HTTPS 创建请求的请求体中提交；页面不会保存或回显。</p>
        </>
      ) : null}
      {error ? <p className="ov-form-error" role="alert">{error}</p> : null}
      <div className="ov-form-actions">
        <button className="ov-primary-button" disabled={pending} type="submit">
          {pending ? '正在创建…' : '创建知识库'}
        </button>
        <Link className="ov-secondary-link" to="/kb">取消</Link>
      </div>
    </form>
  )
}

function ProfileSettings({
  profile,
  onProfilesChanged,
  onRevoke,
}: {
  profile: OpenVikingProfile
  onProfilesChanged: () => Promise<void>
  onRevoke: (profile: OpenVikingProfile) => void
}) {
  const [editing, setEditing] = useState(false)
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')

  async function validate() {
    setPending(true)
    setMessage('')
    try {
      await openVikingApi.validateProfile(profile.profile_id)
      setMessage(`${profile.display_name} 连接正常。`)
      await onProfilesChanged()
    } catch (value) {
      setMessage(value instanceof Error ? value.message : '连接检查失败')
      await onProfilesChanged()
    } finally {
      setPending(false)
    }
  }

  async function update(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const fields = new FormData(form)
    const apiKey = String(fields.get('api_key') || '').trim()
    const baseUrl = String(fields.get('base_url') || '').trim()
    setPending(true)
    setMessage('')
    try {
      await openVikingApi.updateProfile(profile.profile_id, {
        display_name: String(fields.get('display_name') || ''),
        ...(credentialMode(profile) === 'byok'
          ? {
              ...(baseUrl ? { base_url: baseUrl } : {}),
              ...(apiKey ? { api_key: apiKey } : {}),
            }
          : {}),
      })
      form.reset()
      setEditing(false)
      setMessage('设置已保存，请重新检查连接。')
      await onProfilesChanged()
    } catch (value) {
      setMessage(value instanceof Error ? value.message : '设置保存失败')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="ov-connection-page">
      <section className="ov-settings-card">
        <div>
          <h2>连接设置</h2>
          <p>管理显示名称、检查连接，并查看当前凭据模式。</p>
        </div>
        <dl className="ov-profile-metadata">
          <div><dt>状态</dt><dd>{statusLabel(profile.status)}</dd></div>
          <div><dt>凭据模式</dt><dd>{credentialModeLabel(profile)}</dd></div>
          <div><dt>Workspace URI</dt><dd>{profile.workspace_uri}</dd></div>
          <div><dt>最近更新时间</dt><dd>{formatDate(profile.updated_at)}</dd></div>
        </dl>
        <div className="ov-profile-actions">
          <button type="button" onClick={() => setEditing(true)}>编辑</button>
          <button type="button" disabled={pending} onClick={() => void validate()}>
            <RefreshIcon />
            {pending ? '检查中…' : '检查连接'}
          </button>
        </div>
      </section>
      {message ? <p className="ov-form-error" role="status">{message}</p> : null}
      {editing ? (
        <form className="ov-profile-form" onSubmit={update}>
          <div className="ov-profile-heading">
            <span className="ov-profile-heading-icon"><ShieldIcon /></span>
            <div><h2>编辑知识库</h2><p>{credentialModeLabel(profile)}</p></div>
          </div>
          <div className="ov-form-grid">
            <label>知识库名称<input name="display_name" required defaultValue={profile.display_name} /></label>
            <label>Workspace URI<input readOnly value={profile.workspace_uri} /></label>
          </div>
          {credentialMode(profile) === 'byok' ? (
            <>
              <label>Base URL<input name="base_url" type="url" placeholder="保留当前地址" /></label>
              <label>轮换 API Key<input name="api_key" type="password" autoComplete="new-password" /></label>
              <p className="ov-security-note">留空表示保留原密钥；填写后仅通过本次 HTTPS 请求体轮换。</p>
            </>
          ) : <p className="ov-security-note">平台托管模式不允许浏览器提交 Endpoint 或 API Key。</p>}
          <div className="ov-form-actions">
            <button className="ov-primary-button" disabled={pending} type="submit">保存设置</button>
            <button type="button" onClick={() => setEditing(false)}>取消</button>
          </div>
        </form>
      ) : null}
      <section className="ov-danger-zone">
        <div><h2>删除知识库</h2><p>删除后，此知识库签发的 ResourceRef 将失效。</p></div>
        <button className="ov-danger-button" type="button" onClick={() => onRevoke(profile)}>
          <DeleteIcon />
          删除知识库
        </button>
      </section>
    </div>
  )
}

function ResourceWorkspace({ rootUri, profileId }: { rootUri: string; profileId: string }) {
  const navigate = useNavigate()
  const normalizedRoot = normalizeDirUri(rootUri)
  const [searchOpen, setSearchOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [selectedFile, setSelectedFile] = useState<VikingFsEntry>(() =>
    rootEntry(normalizedRoot),
  )
  const [expandedUris, setExpandedUris] = useState<Set<string>>(new Set())
  const { invalidateList, invalidatePreview, invalidateTree } =
    useInvalidateVikingFs()
  const [deleting, setDeleting] = useState(false)
  const [addingToSkill, setAddingToSkill] = useState(false)
  const [contextError, setContextError] = useState('')

  useEffect(() => {
    setSelectedFile(rootEntry(normalizedRoot))
    setExpandedUris(new Set())
  }, [normalizedRoot])

  useEffect(() => {
    const open = () => setAddOpen(true)
    window.addEventListener('openviking:add-resource', open)
    return () => window.removeEventListener('openviking:add-resource', open)
  }, [])

  const openUri = useCallback(
    async (uri: string) => {
      const entry = await fetchFsStat(uri, { throwOnError: true })
      setSelectedFile(entry)
      setExpandedUris((current) => {
        const next = new Set(current)
        for (const ancestor of expandedAncestors(entry.uri, normalizedRoot)) {
          next.add(ancestor)
        }
        if (entry.isDir) next.add(normalizeDirUri(entry.uri))
        return next
      })
    },
    [normalizedRoot],
  )

  const refresh = useCallback(async () => {
    await Promise.all([
      invalidateList(),
      invalidatePreview(selectedFile.uri),
    ])
  }, [invalidateList, invalidatePreview, selectedFile.uri])

  const deleteSelected = useCallback(async () => {
    if (selectedFile.uri === normalizedRoot) return
    if (!window.confirm(`Delete ${selectedFile.name}? This cannot be undone.`)) {
      return
    }
    setDeleting(true)
    try {
      await deleteFsResource(selectedFile.uri, selectedFile.isDir)
      setSelectedFile(rootEntry(normalizedRoot))
      setExpandedUris(new Set())
      await Promise.all([
        invalidateList(),
        invalidateTree(),
        invalidatePreview(selectedFile.uri),
      ])
    } finally {
      setDeleting(false)
    }
  }, [
    invalidateList,
    invalidatePreview,
    invalidateTree,
    normalizedRoot,
    selectedFile,
  ])

  const addSelectedToSkill = useCallback(async () => {
    if (selectedFile.isDir || selectedFile.uri === normalizedRoot) return
    const resourceRef = selectedFile.resourceRef || getOpenVikingResourceRef(selectedFile.uri)
    if (!resourceRef) {
      setContextError('请刷新资源树后再加入 Skill 上下文。')
      return
    }
    setAddingToSkill(true)
    setContextError('')
    try {
      const authorized = await openVikingApi.authorizeSkillContext(profileId, resourceRef)
      navigate(`/skill?mode=new&profile_ref=${encodeURIComponent(authorized.profile_ref)}&resource_ref=${encodeURIComponent(authorized.resource_ref)}`)
    } catch (value) {
      setContextError(value instanceof Error ? value.message : '该资源当前不可加入 Skill 上下文')
    } finally {
      setAddingToSkill(false)
    }
  }, [navigate, normalizedRoot, profileId, selectedFile])

  return (
    <ResourceUploadProvider>
      <div className="ov-resource-workbench">
        <section
          className="ov-context-explorer"
          aria-label="OpenViking context tree"
        >
          <header className="ov-context-header">
            <div className="ov-context-title">
              <span className="ov-context-glyph"><ResourcesIcon /></span>
              <span>资源目录</span>
            </div>
            <div className="ov-icon-actions">
              <button type="button" title="搜索资源" aria-label="搜索资源" onClick={() => setSearchOpen(true)}>
                <SearchIcon />
              </button>
              <button type="button" title="导入资源" aria-label="导入资源" onClick={() => setAddOpen(true)}>
                <AddIcon />
              </button>
              <button type="button" title="刷新资源" aria-label="刷新资源" onClick={() => void refresh()}>
                <RefreshIcon />
              </button>
            </div>
          </header>
          <div className="ov-context-scope" title="Workspace">当前知识库</div>
          <div className="ov-context-tree-scroll">
            <ResourceContextTree
              expandedUris={expandedUris}
              onExpandedUrisChange={setExpandedUris}
              onSelect={setSelectedFile}
              rootUri={normalizedRoot}
              selectedUri={selectedFile.uri}
            />
          </div>
        </section>
        <section className="ov-resource-preview" aria-label="资源预览">
          {contextError ? <div className="error" role="alert">{contextError}</div> : null}
          {selectedFile.uri !== normalizedRoot ? (
            <div className="ov-resource-preview-actions">
              {!selectedFile.isDir ? (
                <button
                  className="ov-primary-button"
                  type="button"
                  disabled={addingToSkill}
                  onClick={() => void addSelectedToSkill()}
                >
                  {addingToSkill ? '加入中…' : '加入 Skill 上下文'}
                </button>
              ) : null}
              <button
                className="ov-danger-button"
                type="button"
                disabled={deleting}
                onClick={() => void deleteSelected()}
              >
                <DeleteIcon />
                {deleting ? '正在删除…' : '删除资源'}
              </button>
            </div>
          ) : null}
          <LazyFilePreview
            file={selectedFile}
            onClose={() => setSelectedFile(rootEntry(normalizedRoot))}
            onNavigate={(uri) => void openUri(uri)}
            showCloseButton={false}
          />
        </section>
      </div>
      <FindPalette
        open={searchOpen}
        scopeUri={normalizedRoot}
        onClose={() => setSearchOpen(false)}
        onNavigate={(uri) => void openUri(uri)}
        onNavigateDir={(uri) => void openUri(uri)}
      />
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="ov-import-dialog sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>导入资源</DialogTitle>
            <DialogDescription>添加文件、文本、远程来源或已授权连接资源。</DialogDescription>
          </DialogHeader>
          <AddResourceForm
            onCompleted={() => {
              setAddOpen(false)
              void refresh()
            }}
          />
        </DialogContent>
      </Dialog>
    </ResourceUploadProvider>
  )
}

function KnowledgeBaseList({
  onProfilesChanged,
  onRevoke,
  profiles,
}: {
  onProfilesChanged: () => Promise<void>
  onRevoke: (profile: OpenVikingProfile) => void
  profiles: OpenVikingProfile[]
}) {
  const [message, setMessage] = useState('')
  const [validatingId, setValidatingId] = useState('')

  async function validate(profile: OpenVikingProfile) {
    setValidatingId(profile.profile_id)
    setMessage('')
    try {
      await openVikingApi.validateProfile(profile.profile_id)
      setMessage(`${profile.display_name} 连接正常。`)
      await onProfilesChanged()
    } catch (value) {
      setMessage(value instanceof Error ? value.message : '连接检查失败')
      await onProfilesChanged()
    } finally {
      setValidatingId('')
    }
  }

  return (
    <div className="ov-kb-page">
      <header className="ov-kb-heading">
        <div>
          <span>DATA WORKSHOP · KNOWLEDGE</span>
          <h1>知识库</h1>
          <p>每个知识库拥有独立的 Profile、资源、检索、任务和定时同步状态。</p>
        </div>
        <Link className="ov-primary-link" to="/kb/new">
          <AddIcon />
          新建知识库
        </Link>
      </header>
      {message ? <p className="ov-inline-message" role="status">{message}</p> : null}
      {profiles.length ? (
        <section className="ov-kb-grid" aria-label="知识库列表">
          {profiles.map((profile) => (
            <article className="ov-kb-card" key={profile.profile_id}>
              <div className="ov-kb-card-head">
                <div className="ov-kb-card-icon"><ResourcesIcon /></div>
                <span className={`ov-status is-${profile.status}`}>
                  <span />
                  {statusLabel(profile.status)}
                </span>
              </div>
              <h2>{profile.display_name}</h2>
              <dl>
                <div><dt>凭据模式</dt><dd>{credentialModeLabel(profile)}</dd></div>
                <div><dt>Workspace URI</dt><dd>{profile.workspace_uri}</dd></div>
                <div><dt>最近健康检查</dt><dd>{formatDate(profile.last_validated_at)}</dd></div>
                <div><dt>最近更新</dt><dd>{formatDate(profile.updated_at)}</dd></div>
              </dl>
              <div className="ov-kb-card-actions">
                <Link
                  aria-label={`进入 ${profile.display_name}`}
                  className="ov-primary-link"
                  to={`/kb/${encodeURIComponent(profile.profile_id)}/resources`}
                >
                  进入详情
                </Link>
                <button
                  disabled={validatingId === profile.profile_id}
                  onClick={() => void validate(profile)}
                  type="button"
                >
                  {validatingId === profile.profile_id ? '检查中…' : '检查连接'}
                </button>
                <Link to={`/kb/${encodeURIComponent(profile.profile_id)}/settings`}>编辑</Link>
                <button
                  className="is-danger"
                  onClick={() => onRevoke(profile)}
                  type="button"
                >
                  删除
                </button>
              </div>
            </article>
          ))}
        </section>
      ) : (
        <section className="ov-kb-empty">
          <ResourcesIcon />
          <h2>还没有知识库</h2>
          <p>创建第一个知识库，开始导入和检索团队知识。</p>
          <Link className="ov-primary-link" to="/kb/new">新建知识库</Link>
        </section>
      )}
    </div>
  )
}

function KnowledgeBaseHeader({
  page,
  profile,
}: {
  page: OpenVikingPage
  profile: OpenVikingProfile
}) {
  const items: Array<[OpenVikingPage, string]> = [
    ['resources', '资源'],
    ['retrieval', '检索'],
    ['tasks', '任务'],
    ['watches', '定时同步'],
    ['settings', '设置'],
  ]
  const base = `/kb/${encodeURIComponent(profile.profile_id)}`
  return (
    <>
      <header className="ov-detail-heading">
        <div className="ov-breadcrumbs">
          <Link to="/kb">知识库</Link>
          <span>/</span>
          <span>{profile.display_name}</span>
        </div>
        <div className="ov-detail-title">
          <div>
            <h1>{profile.display_name}</h1>
            <p>{profile.workspace_uri}</p>
          </div>
          <span className={`ov-status is-${profile.status}`}>
            <span />
            {statusLabel(profile.status)}
          </span>
        </div>
      </header>
      <nav className="ov-detail-nav" aria-label="知识库二级导航">
        {items.map(([id, label]) => (
          <NavLink className={page === id ? 'is-active' : ''} key={id} to={`${base}/${id}`}>
            {label}
          </NavLink>
        ))}
      </nav>
    </>
  )
}

export function OpenVikingWorkspace({
  connectOnly = false,
  credentialPolicy = 'managed',
}: {
  connectOnly?: boolean
  credentialPolicy?: OpenVikingCredentialPolicy
}) {
  const location = useLocation()
  const navigate = useNavigate()
  const route = useMemo(
    () => connectOnly ? ({ kind: 'new' } as const) : parseKnowledgeRoute(location.pathname),
    [connectOnly, location.pathname],
  )
  const [profiles, setProfiles] = useState<OpenVikingProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const routeProfile = useMemo(
    () => route.kind === 'detail'
      ? profiles.find((profile) => profile.profile_id === route.profileId) ?? null
      : null,
    [profiles, route],
  )
  const activeProfile =
    routeProfile?.status === 'ready' ? routeProfile : null

  useEffect(() => {
    if (!routeProfile) return
    window.localStorage.setItem(
      ACTIVE_OPENVIKING_PROFILE_KEY,
      routeProfile.profile_id,
    )
    if (activeProfile) {
      registerOpenVikingRoot(
        'viking://',
        activeProfile.root_resource_ref,
        activeProfile.profile_id,
      )
      registerOpenVikingRoot(
        'viking://workspace/',
        activeProfile.root_resource_ref,
        activeProfile.profile_id,
      )
    }
  }, [activeProfile, routeProfile])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const values = await openVikingApi.listProfiles()
      setProfiles(values)
      const stored = window.localStorage.getItem(ACTIVE_OPENVIKING_PROFILE_KEY)
      if (stored && !values.some((profile) => profile.profile_id === stored)) {
        window.localStorage.removeItem(ACTIVE_OPENVIKING_PROFILE_KEY)
      }
    } catch (value) {
      setError(value instanceof Error ? value.message : '知识库加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const handleCreated = useCallback((profile: OpenVikingProfile) => {
    setProfiles((current) => [
      profile,
      ...current.filter((item) => item.profile_id !== profile.profile_id),
    ])
    window.localStorage.setItem(
      ACTIVE_OPENVIKING_PROFILE_KEY,
      profile.profile_id,
    )
    navigate(`/kb/${encodeURIComponent(profile.profile_id)}/resources`, {
      replace: true,
    })
  }, [navigate])

  const handleRevoke = useCallback(async (profile: OpenVikingProfile) => {
    if (!window.confirm(`删除知识库“${profile.display_name}”？此操作不可撤销。`)) return
    try {
      await openVikingApi.revokeProfile(profile.profile_id)
      if (route.kind === 'detail' && route.profileId === profile.profile_id) {
        navigate('/kb', { replace: true })
      }
      await load()
    } catch (value) {
      setError(value instanceof Error ? value.message : '知识库删除失败')
    }
  }, [load, navigate, route])

  if (route.kind === 'redirect') return <Navigate replace to={route.to} />

  return (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={queryClient}>
        <AppConnectionProvider profile={activeProfile}>
          <div className="openviking-studio">
            <section className="main-shell">
              <main className="main openviking-main">
                {error ? <div className="error" role="alert">{error}</div> : null}
                {loading ? (
                  <div className="ov-loading" role="status">正在加载知识库…</div>
                ) : route.kind === 'list' ? (
                  <KnowledgeBaseList
                    onProfilesChanged={load}
                    onRevoke={(profile) => void handleRevoke(profile)}
                    profiles={profiles}
                  />
                ) : route.kind === 'new' ? (
                  <div className="ov-kb-form-page">
                    <ProfileForm
                      credentialPolicy={credentialPolicy}
                      onCreated={handleCreated}
                    />
                  </div>
                ) : !routeProfile ? (
                  <div className="ov-disconnected">
                    <ConnectionIcon />
                    <h1>知识库不存在</h1>
                    <Link to="/kb">返回知识库列表</Link>
                  </div>
                ) : (
                  <div className="ov-profile-detail">
                    <KnowledgeBaseHeader page={route.page} profile={routeProfile} />
                    {route.page !== 'settings' && !activeProfile ? (
                      <div className="ov-disconnected">
                        <ConnectionIcon />
                        <h2>请先完成连接检查</h2>
                        <p>只有状态可用的知识库可以访问资源、检索、任务和定时同步。</p>
                        <Link to={`/kb/${encodeURIComponent(routeProfile.profile_id)}/settings`}>
                          打开连接设置
                        </Link>
                      </div>
                    ) : route.page === 'resources' && activeProfile ? (
                      <ResourceWorkspace rootUri="viking://workspace/" profileId={activeProfile.profile_id} />
                    ) : route.page === 'retrieval' ? (
                      <div className="ov-page-scroll"><div className="ov-page-content"><RetrievalPage /></div></div>
                    ) : route.page === 'tasks' ? (
                      <div className="ov-page-scroll"><div className="ov-page-content"><TasksRoute /></div></div>
                    ) : route.page === 'watches' ? (
                      <div className="ov-page-scroll"><div className="ov-page-content"><WatchesRoute /></div></div>
                    ) : (
                      <div className="ov-page-scroll">
                        <ProfileSettings
                          onProfilesChanged={load}
                          onRevoke={(profile) => void handleRevoke(profile)}
                          profile={routeProfile}
                        />
                      </div>
                    )}
                  </div>
                )}
              </main>
            </section>
          </div>
          <Toaster richColors position="bottom-right" />
        </AppConnectionProvider>
      </QueryClientProvider>
    </I18nextProvider>
  )
}
