import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Plus, Search, Sparkles } from 'lucide-react'
import { ApiService } from '../../services/api'

type Skill = { id: string; name: string; description: string; skill_type: string; is_active: boolean }

export default function SkillListPage() {
  const [skills, setSkills] = useState<Skill[]>([])
  const [query, setQuery] = useState('')
  const [type, setType] = useState('all')
  useEffect(() => {
    ApiService.getCustomSkills().then(response => setSkills((response.data || []) as Skill[])).catch(() => setSkills([]))
  }, [])
  const filtered = useMemo(() => skills.filter(skill => `${skill.name} ${skill.description}`.toLowerCase().includes(query.toLowerCase()) && (type === 'all' || skill.skill_type === type)), [skills, query, type])
  return <div className="skill-creator-page">
    <header className="skill-creator-header"><div><p className="skill-eyebrow">DATA WORKSHOP</p><h1>Skills</h1><p>Build, validate, and revise skills with the current workspace context.</p></div><Link className="skill-primary" to="/skill/new"><Plus size={16} /> New skill</Link></header>
    <div className="skill-toolbar"><label><Search size={15} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search skills" /></label><select value={type} onChange={event => setType(event.target.value)}><option value="all">All types</option><option value="general">General</option><option value="slack_inbound">Slack inbound</option><option value="slack_outbound">Slack outbound</option></select></div>
    {filtered.length === 0 ? <div className="skill-empty"><Sparkles size={22} /><h2>{skills.length ? 'No matching skills' : 'No skills yet'}</h2><p>{skills.length ? 'Try another search or filter.' : 'Create a skill to start a guided workshop.'}</p>{!skills.length && <Link className="skill-secondary" to="/skill/new"><Plus size={15} /> Create skill</Link>}</div> : <div className="skill-cards">{filtered.map(skill => <Link className="skill-card" to={`/skill/${skill.id}`} key={skill.id}><div><span className="skill-status">{skill.is_active ? 'Active' : 'Paused'}</span><h2>{skill.name}</h2><p>{skill.description}</p></div><footer><span>{skill.skill_type}</span><ChevronRight size={16} /></footer></Link>)}</div>}
  </div>
}
