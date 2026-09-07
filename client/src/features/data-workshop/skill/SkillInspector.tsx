import { AlertTriangle, CheckCircle2, History, PackageOpen } from 'lucide-react'
import { ArtifactPanel } from './ArtifactPanel'
import { HowToUse } from './HowToUse'
import type { SkillArtifact, SkillRevision, SkillSession } from './types'

export function SkillInspector({
  skillId,
  session,
  revisions,
}: {
  skillId: string
  session: SkillSession
  revisions: SkillRevision[]
}) {
  const artifact = session.artifact
  if (artifact) {
    return (
      <div className="dw-skill-inspector">
        <ArtifactPanel skillId={skillId} artifact={artifact} revisions={revisions} />
        <HowToUse ready={session.status === 'ready'} />
      </div>
    )
  }

  const failed = ['error', 'retryable', 'validation_failed', 'blocked_auth', 'blocked_config', 'cancelled'].includes(session.status)
  return (
    <aside className="dw-skill-inspector dw-skill-inspector-empty" aria-label="Skill 信息">
      <section className="dw-inspector-status">
        <div className={`dw-inspector-status-icon ${failed ? 'failed' : 'pending'}`}>
          {failed ? <AlertTriangle size={17} /> : <PackageOpen size={17} />}
        </div>
        <div>
          <span className="dw-eyebrow">{failed ? '需要处理' : '生成状态'}</span>
          <h2>{failed ? '本轮未完成' : '等待生成'}</h2>
          <p>{failed ? '历史记录已保留，修正上下文后可以重试。' : '开始生成后，产物与校验结果会显示在这里。'}</p>
        </div>
      </section>
      <HowToUse />
      <section className="dw-inspector-history">
        <div className="dw-inspector-heading"><span className="dw-eyebrow">记录</span><h2>历史状态</h2></div>
        {failed ? (
          <div className="dw-history-failure"><AlertTriangle size={14} /><span>失败记录已保留在对话中</span></div>
        ) : (
          <div className="dw-history-empty"><History size={15} /><span>完成第一轮生成后会显示版本历史</span></div>
        )}
      </section>
      {session.status === 'ready' && <div className="dw-ready-badge"><CheckCircle2 size={14} />已就绪</div>}
    </aside>
  )
}
