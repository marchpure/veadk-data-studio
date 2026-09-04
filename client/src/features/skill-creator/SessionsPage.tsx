import { useEffect, useState } from 'react'
import { ChevronRight, History, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { skillCreatorApi, type SkillSession } from './api'

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SkillSession[]>([])
  useEffect(() => { skillCreatorApi.listSessions().then(result => setSessions(result.items)).catch(() => setSessions([])) }, [])
  return <div className="skill-creator-page"><header className="skill-creator-header"><div><p className="skill-eyebrow">DATA WORKSHOP</p><h1>Sessions</h1><p>Resume context, events, and revisions from the server.</p></div><Link className="skill-secondary" to="/skill/new"><Plus size={15} /> New session</Link></header>{sessions.length === 0 ? <div className="skill-empty"><History size={22} /><h2>No recent sessions</h2><p>Sessions appear here after you start a workshop.</p></div> : <div className="session-list">{sessions.map(item => <Link className="session-row" to={`/skill/${item.skill_id || 'new'}?session=${item.id}`} key={item.id}><div><strong>{item.target || 'Untitled skill'}</strong><p>{item.messages.at(-1)?.content || 'No messages yet'}</p></div><span>{item.status}<ChevronRight size={16} /></span></Link>)}</div>}</div>
}
