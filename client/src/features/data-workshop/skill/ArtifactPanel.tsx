import { CheckCircle2, Download, FileCode2, FileText, GitCompare, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { apiFetch } from '../../../services/api'
import { skillApi } from './api'
import type { RevisionDiff, SkillArtifact, SkillRevision } from './types'

export function ArtifactPanel({
  skillId,
  artifact,
  revisions,
}: {
  skillId: string
  artifact: SkillArtifact
  revisions: SkillRevision[]
}) {
  const [selectedRevision, setSelectedRevision] = useState<SkillRevision | null>(null)
  const displayedArtifact = selectedRevision?.artifact || artifact
  const [preview, setPreview] = useState<string>('')
  const [previewType, setPreviewType] = useState('')
  const [error, setError] = useState('')
  const [diff, setDiff] = useState<RevisionDiff | null>(null)

  useEffect(() => {
    setSelectedRevision(null)
  }, [artifact.revision, skillId])

  useEffect(() => {
    let cancelled = false
    setPreview('')
    setError('')
    apiFetch(displayedArtifact.preview_url, { credentials: 'include' })
      .then(async response => {
        if (!response.ok) throw new Error('Artifact 预览加载失败')
        const contentType = response.headers.get('content-type') || 'text/plain'
        const content = await response.text()
        if (!cancelled) {
          setPreviewType(contentType)
          setPreview(content)
        }
      })
      .catch(reason => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : 'Artifact 预览加载失败')
      })
    return () => { cancelled = true }
  }, [displayedArtifact.preview_url])

  useEffect(() => {
    const previous = revisions.find(item => item.revision !== displayedArtifact.revision)
    if (!previous) {
      setDiff(null)
      return
    }
    let cancelled = false
    void skillApi.revisionDiff(skillId, previous.revision, displayedArtifact.revision).then(value => {
      if (!cancelled) setDiff(value)
    }).catch(() => {
      if (!cancelled) setDiff(null)
    })
    return () => { cancelled = true }
  }, [displayedArtifact.revision, revisions, skillId])

  const download = async () => {
    const response = await apiFetch(displayedArtifact.download_url, { credentials: 'include' })
    if (!response.ok) {
      setError('Artifact 下载失败')
      return
    }
    const blobUrl = URL.createObjectURL(await response.blob())
    const anchor = document.createElement('a')
    anchor.href = blobUrl
    anchor.download = `skill-${displayedArtifact.revision}.zip`
    anchor.click()
    URL.revokeObjectURL(blobUrl)
  }

  const files = Array.isArray(displayedArtifact.files) ? displayedArtifact.files : []
  const rawChecks = displayedArtifact.validation?.checks
  const checks = Array.isArray(rawChecks)
    ? rawChecks
    : Object.entries(rawChecks || {}).map(([name, ok]) => ({ name, ok, message: undefined }))
  const validationErrors = displayedArtifact.validation?.errors || []

  return (
    <aside className="dw-artifact-panel" aria-label="Artifact">
      <header>
        <div><span className="dw-eyebrow">Artifact</span><h2>产物</h2></div>
        <button className="dw-icon-button" type="button" onClick={() => void download()} title="下载 Artifact ZIP" aria-label="下载 Artifact ZIP">
          <Download size={17} />
        </button>
      </header>
      <section className="dw-artifact-revision">
        <span>当前 Revision</span><strong>{displayedArtifact.revision}</strong>
        <small>共 {revisions.length} 个 Revision</small>
      </section>
      <section className="dw-artifact-section">
        <h3><FileText size={14} />文件</h3>
        <div className="dw-file-tree">
          {(files.length ? files : [displayedArtifact.name || 'SKILL.md']).map(file => (
            <div key={file}><FileCode2 size={13} /><span>{file}</span></div>
          ))}
        </div>
      </section>
      <section className="dw-artifact-section">
        <h3><ShieldCheck size={14} />安全预览</h3>
        {error && <div className="dw-inline-error">{error}</div>}
        {!preview && !error && <div className="dw-artifact-loading">正在读取预览…</div>}
        {preview && previewType.includes('text/html') && (
          <iframe
            className="dw-artifact-frame"
            title="Artifact HTML 安全预览"
            sandbox=""
            srcDoc={preview}
          />
        )}
        {preview && !previewType.includes('text/html') && <pre className="dw-artifact-text">{preview}</pre>}
      </section>
      <section className="dw-artifact-section">
        <h3><GitCompare size={14} />Diff 与历史</h3>
        <div className="dw-revision-list">
          {revisions.map((revision, index) => (
            <button
              type="button"
              key={revision.revision}
              className={revision.revision === displayedArtifact.revision ? 'active' : ''}
              onClick={() => setSelectedRevision(revision.revision === artifact.revision ? null : revision)}
            >
              <CheckCircle2 size={13} />
              <span><strong>{revision.revision}</strong><small>{index === 0 ? '当前版本' : '历史版本'}</small></span>
            </button>
          ))}
        </div>
        {diff && (
          <div className="dw-artifact-diff">
            <strong>{diff.base} → {diff.target}</strong>
            <span>新增 {diff.files_added.length} · 移除 {diff.files_removed.length} · 元数据变更 {diff.metadata_changed.length}</span>
            {!!diff.text_diff.length && <pre>{diff.text_diff.join('\n')}</pre>}
          </div>
        )}
      </section>
      <section className="dw-artifact-section">
        <h3><ShieldCheck size={14} />校验摘要</h3>
        {!checks.length && <p>W5 未返回细项校验结果。</p>}
        {checks.map((check, index) => (
          <p key={`${check.name}-${index}`} className={check.ok ? 'passed' : 'failed'}>
            {check.ok ? '通过' : '失败'} · {check.name || check.message || `检查 ${index + 1}`}
          </p>
        ))}
        {validationErrors.map((message, index) => <p key={`${message}-${index}`} className="failed">失败 · {message}</p>)}
      </section>
    </aside>
  )
}
