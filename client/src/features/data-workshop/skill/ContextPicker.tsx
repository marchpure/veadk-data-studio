import { BookOpen, Database } from 'lucide-react'
import { useState } from 'react'
import type { SkillCatalog, SkillContextRef } from './types'

export function ContextPicker({
  catalog,
  selectedMcp,
  selectedKnowledge,
  onMcpChange,
  onKnowledgeChange,
  initialOpen,
}: {
  catalog: SkillCatalog | null
  selectedMcp: SkillContextRef[]
  selectedKnowledge: SkillContextRef[]
  onMcpChange: (items: SkillContextRef[]) => void
  onKnowledgeChange: (items: SkillContextRef[]) => void
  initialOpen?: 'action' | 'knowledge'
}) {
  const [openSection, setOpenSection] = useState<'action' | 'knowledge' | null>(initialOpen || null)
  const toggle = (
    current: SkillContextRef[],
    item: SkillContextRef,
    update: (items: SkillContextRef[]) => void,
  ) => update(current.some(ref => ref.id === item.id) ? current.filter(ref => ref.id !== item.id) : [...current, item])

  return (
    <div className="dw-context-picker">
      <details
        open={openSection === 'action'}
        onToggle={event => {
          if (event.currentTarget.open) setOpenSection('action')
          else if (openSection === 'action') setOpenSection(null)
        }}
      >
        <summary><Database size={15} />添加 Action <span>{selectedMcp.length}</span></summary>
        <div className="dw-context-options">
          {!catalog?.connections.length && <p>当前没有可用的 Action。</p>}
          {catalog?.connections.map(connection => (
            <section key={connection.id}>
              <strong>{connection.name}</strong>
              {connection.actions.map(action => (
                <label key={`${connection.id}:${action.id}`}>
                  <input
                    type="checkbox"
                    checked={selectedMcp.some(item => item.id === action.id)}
                    onChange={() => toggle(selectedMcp, action, onMcpChange)}
                  />
                  <span>{action.name}</span>
                </label>
              ))}
            </section>
          ))}
        </div>
      </details>
      <details
        open={openSection === 'knowledge'}
        onToggle={event => {
          if (event.currentTarget.open) setOpenSection('knowledge')
          else if (openSection === 'knowledge') setOpenSection(null)
        }}
      >
        <summary><BookOpen size={15} />添加知识 <span>{selectedKnowledge.length}</span></summary>
        <div className="dw-context-options">
          {!catalog?.knowledge_refs.length && <p>当前没有可用的知识资源。</p>}
          {catalog?.knowledge_refs.map(resource => (
            <label key={resource.id}>
              <input
                type="checkbox"
                checked={selectedKnowledge.some(item => item.id === resource.id)}
                onChange={() => toggle(selectedKnowledge, resource, onKnowledgeChange)}
              />
              <span>
                <strong>{resource.name}</strong>
                <small>{String(resource.metadata.resource_type || '知识资源')}</small>
                {resource.metadata.summary ? <small>{String(resource.metadata.summary)}</small> : null}
              </span>
            </label>
          ))}
        </div>
      </details>
    </div>
  )
}
