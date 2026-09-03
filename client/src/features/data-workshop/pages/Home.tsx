import { ArrowRight, BookOpenCheck, Database, KeyRound, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'

const steps = [
  { title: '准备数据', body: '创建并验证数据库或 API 连接', to: '/connections/providers/market', icon: Database },
  { title: '配置访问权限', body: '决定谁可以在连接上执行哪些 Actions', to: '/connections/access', icon: KeyRound },
  { title: '查看接入文档', body: '使用 MCP、HTTP API 或 SDK 接入', to: '/connections/docs', icon: BookOpenCheck },
  { title: '生成 Skill', body: '把已授权的数据能力沉淀为业务技能', to: '/skill', icon: Sparkles },
]

export function WorkshopHome() {
  return (
    <div className="dw-page">
      <div className="dw-page-heading">
        <div><span className="dw-eyebrow">工作台</span><h1>数据能力，从连接到 Skill</h1></div>
        <p>沿着一条清晰的路径完成数据准备、授权和安全接入。</p>
      </div>
      <section className="dw-journey" aria-label="首页旅程">
        {steps.map(({ title, body, to, icon: Icon }, index) => (
          <Link to={to} key={title} className="dw-journey-step">
            <div className="dw-step-index">{String(index + 1).padStart(2, '0')}</div>
            <Icon size={22} />
            <strong>{title}</strong>
            <span>{body}</span>
            <ArrowRight size={17} className="dw-step-arrow" />
          </Link>
        ))}
      </section>
      <section className="dw-summary-band">
        <div><span>连接</span><strong>由 OpenConnector 实时提供</strong></div>
        <div><span>权限模型</span><strong>Connection + Subject + Role</strong></div>
        <div><span>用户接入</span><strong>OAuth / JWT</strong></div>
      </section>
    </div>
  )
}
