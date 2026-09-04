import { Clock3, Plus, Search, Sparkles } from 'lucide-react'
import type { WorkshopSkill } from './types'

const statusLabel: Record<string, string> = {
  draft: '草稿',
  idle: '待开始',
  running: '生成中',
  ready: '已就绪',
  blocked_auth: '待授权',
  blocked_config: '待配置',
  validation_failed: '校验失败',
  cancelled: '已停止',
  retryable: '可重试',
  error: '失败',
}

function formatTime(value?: string | null) {
  if (!value) return '刚刚'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date)
}

export function SkillRail({
  skills,
  selectedId,
  search,
  loading,
  onSearch,
  onNew,
  onSelect,
}: {
  skills: WorkshopSkill[]
  selectedId: string | null
  search: string
  loading: boolean
  onSearch: (value: string) => void
  onNew: () => void
  onSelect: (id: string) => void
}) {
  return (
    <aside className="dw-skill-rail" aria-label="Skill 工作栏">
      <header>
        <div><span className="dw-eyebrow">工作台</span><strong>我的 Skill</strong></div>
        <button className="dw-skill-new" type="button" onClick={onNew}><Plus size={16} />新建 Skill</button>
      </header>
      <label className="dw-skill-search">
        <Search size={15} aria-hidden />
        <span className="sr-only">搜索 Skill</span>
        <input value={search} onChange={event => onSearch(event.target.value)} placeholder="搜索 Skill" />
      </label>
      <div className="dw-skill-list">
        {loading && <div className="dw-skill-rail-empty">正在加载…</div>}
        {!loading && !skills.length && (
          <div className="dw-skill-rail-empty"><Sparkles size={18} /><span>还没有 Skill</span></div>
        )}
        {skills.map(skill => (
          <button
            type="button"
            key={skill.id}
            className={selectedId === skill.id ? 'active' : ''}
            onClick={() => onSelect(skill.id)}
          >
            <span className="dw-skill-item-head">
              <strong>{skill.title}</strong>
              <span className={`dw-skill-dot ${skill.status}`} aria-label={statusLabel[skill.status] || skill.status} />
            </span>
            <span className="dw-skill-target">{skill.target_skill}</span>
            <span className="dw-skill-time"><Clock3 size={11} />{formatTime(skill.updated_at)}</span>
          </button>
        ))}
      </div>
    </aside>
  )
}
