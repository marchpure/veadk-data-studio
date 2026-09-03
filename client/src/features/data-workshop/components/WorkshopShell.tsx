import {
  BookOpen,
  ChevronDown,
  Database,
  Home,
  Menu,
  MessageSquareText,
  PanelLeftClose,
  Sparkles,
  X,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'

const primaryNav = [
  { label: '首页', path: '/home', icon: Home },
  { label: '连接', path: '/connections/overview', icon: Database },
  { label: '知识库', path: '/kb', icon: BookOpen },
  { label: 'Skill', path: '/skill', icon: Sparkles },
  { label: '最近会话', path: '/sessions', icon: MessageSquareText },
]

const connectionNav = [
  ['总览', '/connections/overview'],
  ['连接器', '/connections/providers/market'],
  ['Actions', '/connections/actions'],
  ['Trace', '/connections/trace'],
  ['访问权限', '/connections/access'],
  ['文档', '/connections/docs'],
]

export function WorkshopShell({ children }: { children: ReactNode }) {
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const inConnections = location.pathname.startsWith('/connections')

  return (
    <div className="dw-app">
      <header className="dw-mobile-header">
        <button aria-label="打开导航" onClick={() => setMobileOpen(true)}><Menu /></button>
        <span>Data Workshop</span>
      </header>
      <aside className={`dw-sidebar ${mobileOpen ? 'is-open' : ''}`}>
        <div className="dw-brand">
          <div className="dw-brand-mark">DW</div>
          <div><strong>Data Workshop</strong><span>数据工作坊</span></div>
          <button aria-label="关闭导航" className="dw-mobile-close" onClick={() => setMobileOpen(false)}><X /></button>
        </div>
        <nav className="dw-primary-nav" aria-label="一级导航">
          {primaryNav.map(({ label, path, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              className={({ isActive }) => isActive || (label === '连接' && inConnections) ? 'active' : ''}
              onClick={() => setMobileOpen(false)}
            >
              <Icon size={18} /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="dw-sidebar-footer">
          <div className="dw-avatar">林</div>
          <div><strong>林默</strong><span>数据平台管理员</span></div>
          <ChevronDown size={16} />
        </div>
      </aside>
      {mobileOpen && <button className="dw-backdrop" aria-label="关闭导航遮罩" onClick={() => setMobileOpen(false)} />}
      <main className="dw-main">
        {inConnections && (
          <div className="dw-subnav-wrap">
            <nav className="dw-subnav" aria-label="连接二级导航">
              {connectionNav.map(([label, path]) => (
                <NavLink key={path} to={path} className={({ isActive }) => isActive ? 'active' : ''}>
                  {label}
                </NavLink>
              ))}
            </nav>
            <PanelLeftClose size={17} aria-hidden />
          </div>
        )}
        <div className="dw-content">{children}</div>
      </main>
    </div>
  )
}
