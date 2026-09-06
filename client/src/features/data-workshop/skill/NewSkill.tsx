import { ArrowRight, Save, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ContextPicker } from './ContextPicker'
import type { SkillCatalog, SkillContextRef, SkillCreateMode } from './types'

function normalizeTarget(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '')
}

function targetFromTitle(value: string) {
  const normalized = normalizeTarget(value)
  if (normalized) return normalized
  const encoded = Array.from(value.trim())
    .map(character => character.codePointAt(0)?.toString(36))
    .filter(Boolean)
    .join('-')
  return encoded ? `skill-${encoded}`.slice(0, 160).replace(/-+$/g, '') : ''
}

export function NewSkill({
  catalog,
  creating,
  onCreate,
  initialKnowledge = [],
}: {
  catalog: SkillCatalog | null
  creating: boolean
  onCreate: (value: {
    title: string
    target_skill: string
    description: string
    mcp_refs: SkillContextRef[]
    knowledge_refs: SkillContextRef[]
  }, mode: SkillCreateMode) => Promise<void>
  initialKnowledge?: SkillContextRef[]
}) {
  const [title, setTitle] = useState('')
  const [target, setTarget] = useState('')
  const [targetEdited, setTargetEdited] = useState(false)
  const [description, setDescription] = useState('')
  const [mcpRefs, setMcpRefs] = useState<SkillContextRef[]>([])
  const [knowledgeRefs, setKnowledgeRefs] = useState<SkillContextRef[]>(initialKnowledge)
  const generatedTarget = targetFromTitle(title)
  const normalizedTarget = normalizeTarget(targetEdited ? target : generatedTarget)
  const hasContext = mcpRefs.length + knowledgeRefs.length > 0
  const effectiveCatalog = catalog
    ? {
        ...catalog,
        knowledge_refs: [
          ...initialKnowledge,
          ...catalog.knowledge_refs.filter(item => !initialKnowledge.some(ref => ref.id === item.id)),
        ],
      }
    : catalog

  useEffect(() => {
    if (initialKnowledge.length) setKnowledgeRefs(initialKnowledge)
  }, [initialKnowledge])

  const submit = (mode: SkillCreateMode) => onCreate({
    title: title.trim(),
    target_skill: normalizedTarget,
    description: description.trim(),
    mcp_refs: mcpRefs,
    knowledge_refs: knowledgeRefs,
  }, mode)

  return (
    <div className="dw-new-skill">
      <header><span className="dw-new-icon"><Sparkles size={20} /></span><div><span className="dw-eyebrow">新建 Skill</span><h1>创建一个新的 Skill</h1><p>先保存草稿，准备好 Action 或知识后再开始生成。</p></div></header>
      <div className="dw-new-fields">
        <label><span>Skill 名称</span><input value={title} onChange={event => setTitle(event.target.value)} placeholder="例如：周度营收复盘" /></label>
        <label className="wide"><span>用途说明</span><textarea value={description} onChange={event => setDescription(event.target.value)} placeholder="这个 Skill 将帮助团队…" /></label>
        <details className="wide">
          <summary>高级设置</summary>
          <label>
            <span>目标标识</span>
            <input
              value={targetEdited ? target : generatedTarget}
              onChange={event => {
                setTargetEdited(true)
                setTarget(event.target.value)
              }}
              placeholder="weekly-revenue-review"
            />
            <small>默认根据名称生成；仅支持小写字母、数字和连字符</small>
          </label>
        </details>
      </div>
      <ContextPicker
        catalog={effectiveCatalog}
        selectedMcp={mcpRefs}
        selectedKnowledge={knowledgeRefs}
        onMcpChange={setMcpRefs}
        onKnowledgeChange={setKnowledgeRefs}
      />
      <footer>
        <p>{hasContext ? '保存后可以立即开始静态校验与生成。' : '至少选择一个 Action 或一个知识资源后才能开始生成。'}</p>
        <div className="dw-button-row">
          <button
            className="dw-button dw-button-secondary"
            disabled={!title.trim() || !normalizedTarget || creating}
            onClick={() => void submit('draft')}
          >
            <Save size={15} />{creating ? '保存中…' : '保存草稿'}
          </button>
          <button
            className="dw-button dw-button-primary"
            disabled={!title.trim() || !normalizedTarget || !hasContext || creating}
            onClick={() => void submit('generate')}
          >
            {creating ? '正在开始…' : '保存并开始生成'}<ArrowRight size={15} />
          </button>
        </div>
      </footer>
    </div>
  )
}
