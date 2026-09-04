import { ArrowRight, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ContextPicker } from './ContextPicker'
import type { SkillCatalog, SkillContextRef } from './types'

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
  }) => Promise<void>
  initialKnowledge?: SkillContextRef[]
}) {
  const [title, setTitle] = useState('')
  const [target, setTarget] = useState('')
  const [description, setDescription] = useState('')
  const [mcpRefs, setMcpRefs] = useState<SkillContextRef[]>([])
  const [knowledgeRefs, setKnowledgeRefs] = useState<SkillContextRef[]>(initialKnowledge)
  const normalizedTarget = target.trim().toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '')
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

  return (
    <div className="dw-new-skill">
      <header><span className="dw-new-icon"><Sparkles size={20} /></span><div><span className="dw-eyebrow">New Skill</span><h1>创建一个新的 Skill</h1><p>选择可见的数据能力与知识，再从同一工作台开始生成。</p></div></header>
      <div className="dw-new-fields">
        <label><span>Skill 名称</span><input value={title} onChange={event => setTitle(event.target.value)} placeholder="例如：周度营收复盘" /></label>
        <label><span>Target Skill</span><input value={target} onChange={event => setTarget(event.target.value)} placeholder="weekly-revenue-review" /><small>仅支持小写字母、数字和连字符</small></label>
        <label className="wide"><span>用途说明</span><textarea value={description} onChange={event => setDescription(event.target.value)} placeholder="这个 Skill 将帮助团队…" /></label>
      </div>
      <ContextPicker
        catalog={effectiveCatalog}
        selectedMcp={mcpRefs}
        selectedKnowledge={knowledgeRefs}
        onMcpChange={setMcpRefs}
        onKnowledgeChange={setKnowledgeRefs}
      />
      <footer>
        <p>创建后仍停留在 <code>/skill</code>，并自动开始第一段会话。</p>
        <button
          className="dw-button dw-button-primary"
          disabled={!title.trim() || !normalizedTarget || creating}
          onClick={() => void onCreate({
            title: title.trim(),
            target_skill: normalizedTarget,
            description: description.trim(),
            mcp_refs: mcpRefs,
            knowledge_refs: knowledgeRefs,
          })}
        >
          {creating ? '创建中…' : '创建并进入工作台'}<ArrowRight size={15} />
        </button>
      </footer>
    </div>
  )
}
