import { BookOpen, Database } from 'lucide-react'
import type { SkillCatalog, SkillContextRef } from './types'

export function ContextPicker({
  catalog,
  selectedMcp,
  selectedKnowledge,
  onMcpChange,
  onKnowledgeChange,
}: {
  catalog: SkillCatalog | null
  selectedMcp: SkillContextRef[]
  selectedKnowledge: SkillContextRef[]
  onMcpChange: (items: SkillContextRef[]) => void
  onKnowledgeChange: (items: SkillContextRef[]) => void
}) {
  const toggle = (
    current: SkillContextRef[],
    item: SkillContextRef,
    update: (items: SkillContextRef[]) => void,
  ) => update(current.some(ref => ref.id === item.id) ? current.filter(ref => ref.id !== item.id) : [...current, item])

  return (
    <div className="dw-context-picker">
      <details>
        <summary><Database size={15} />Connection Actions <span>{selectedMcp.length}</span></summary>
        <div className="dw-context-options">
          {!catalog?.connections.length && <p>当前没有可用的 Connection Action。</p>}
          {catalog?.connections.map(connection => (
            <section key={connection.id}>
              <strong>{connection.name}</strong><small>{connection.provider}</small>
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
      <details>
        <summary><BookOpen size={15} />Knowledge ResourceRefs <span>{selectedKnowledge.length}</span></summary>
        <div className="dw-context-options">
          {!catalog?.knowledge_refs.length && <p>当前没有可用的 OpenViking ResourceRef。</p>}
          {catalog?.knowledge_refs.map(resource => (
            <label key={resource.id}>
              <input
                type="checkbox"
                checked={selectedKnowledge.some(item => item.id === resource.id)}
                onChange={() => toggle(selectedKnowledge, resource, onKnowledgeChange)}
              />
              <span>{resource.name}<small>{resource.id}</small></span>
            </label>
          ))}
        </div>
      </details>
    </div>
  )
}
