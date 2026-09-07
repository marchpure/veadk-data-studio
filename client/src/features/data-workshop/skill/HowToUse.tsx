import { ArrowUpRight, BookOpen, MessageSquare, Play } from 'lucide-react'

export function HowToUse({ ready = false }: { ready?: boolean }) {
  return (
    <section className="dw-how-to-use" aria-labelledby="dw-how-to-use-title">
      <div className="dw-inspector-heading">
        <span className="dw-eyebrow">下一步</span>
        <h2 id="dw-how-to-use-title">如何使用</h2>
      </div>
      <p className="dw-how-to-use-intro">
        {ready ? 'Skill 已就绪，可以从一次真实问题开始。' : '完成生成后，这里会告诉你如何复用这个 Skill。'}
      </p>
      <ol>
        <li><span><Play size={13} /></span><div><strong>描述任务</strong><small>用自然语言告诉 Skill 你要完成什么。</small></div></li>
        <li><span><MessageSquare size={13} /></span><div><strong>继续对话</strong><small>根据结果追问、补充条件或生成新版本。</small></div></li>
        <li><span><BookOpen size={13} /></span><div><strong>保持上下文</strong><small>需要时添加 Action 或知识资源。</small></div></li>
      </ol>
      {ready && <a href="#skill-composer">开始一次对话 <ArrowUpRight size={13} /></a>}
    </section>
  )
}
