import { Check, Circle, Sparkles } from 'lucide-react'

export type SkillWorkbenchStep = 1 | 2 | 3 | 4

const steps = [
  { number: 1, label: '定义目标', detail: '名称与用途' },
  { number: 2, label: '选择能力', detail: 'Action 与知识' },
  { number: 3, label: '生成 Skill', detail: '校验与产物' },
  { number: 4, label: '开始使用', detail: '复用与迭代' },
] as const

export function SkillProgress({
  current,
  compact = false,
}: {
  current: SkillWorkbenchStep
  compact?: boolean
}) {
  return (
    <nav className={`dw-skill-progress ${compact ? 'compact' : ''}`} aria-label="Skill 创建步骤">
      {steps.map((step, index) => {
        const done = step.number < current
        const active = step.number === current
        return (
          <div className={`dw-skill-progress-step ${done ? 'done' : ''} ${active ? 'active' : ''}`} key={step.number}>
            <span className="dw-skill-progress-marker">
              {done ? <Check size={13} strokeWidth={3} /> : active ? <Sparkles size={12} /> : <Circle size={9} />}
            </span>
            <span className="dw-skill-progress-copy">
              <strong>{step.number}. {step.label}</strong>
              {!compact && <small>{step.detail}</small>}
            </span>
            {index < steps.length - 1 && <i aria-hidden />}
          </div>
        )
      })}
    </nav>
  )
}
