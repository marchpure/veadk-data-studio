import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Zap, ArrowDownToLine, ArrowUpFromLine, Plus, Edit2, Trash2, Loader2, Users, CheckCircle } from 'lucide-react'
import { useSlackSkills } from '@/hooks/useSlackSkills'
import { SlackSkillModal } from './SlackSkillModal'
import type { CustomSkill, CreateCustomSkillData } from '@/stores/slices/contextSlice'
import { useStore } from '@/stores/useStore'

interface SlackSkillsSectionProps {
  isSlackConnected: boolean
}

export function SlackSkillsSection({ isSlackConnected }: SlackSkillsSectionProps) {
  const {
    inboundSkill,
    outboundSkill,
    createInboundSkill,
    createOutboundSkill,
    updateSkill,
    deleteSkill,
    isLoading,
  } = useSlackSkills()

  const [modalOpen, setModalOpen] = useState(false)
  const [modalType, setModalType] = useState<'slack_inbound' | 'slack_outbound'>('slack_inbound')
  const [editingSkill, setEditingSkill] = useState<CustomSkill | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const user = useStore(state => state.user)

  if (!isSlackConnected) return null

  function openCreateModal(type: 'slack_inbound' | 'slack_outbound') {
    setModalType(type)
    setEditingSkill(null)
    setModalOpen(true)
  }

  function openEditModal(skill: CustomSkill) {
    setModalType(skill.skill_type as 'slack_inbound' | 'slack_outbound')
    setEditingSkill(skill)
    setModalOpen(true)
  }

  async function handleSave(data: Omit<CreateCustomSkillData, 'skill_type' | 'scope'>) {
    if (editingSkill) {
      await updateSkill(editingSkill.id, data)
    } else if (modalType === 'slack_inbound') {
      await createInboundSkill(data)
    } else {
      await createOutboundSkill(data)
    }
  }

  async function handleDelete(skill: CustomSkill) {
    if (!window.confirm(`Delete "${skill.name}"? This cannot be undone.`)) return
    setDeletingId(skill.id)
    try {
      await deleteSkill(skill.id)
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="mt-6 pt-6 border-t border-gray-800">
      <div className="flex items-center gap-3 mb-4">
        <Zap className="w-5 h-5 text-brand-orange" />
        <div>
          <h3 className="text-sm font-medium text-white">Slack Skills</h3>
          <p className="text-xs text-gray-400">
            Customize how Byaan processes and responds to Slack messages
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 text-brand-orange animate-spin" />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          <SkillCard
            title="Inbound Skill"
            description="Enriches questions BEFORE sending to AI"
            icon={ArrowDownToLine}
            skill={inboundSkill}
            isOwner={inboundSkill?.created_by === user?.id}
            isDeleting={deletingId === inboundSkill?.id}
            onAdd={() => openCreateModal('slack_inbound')}
            onEdit={() => inboundSkill && openEditModal(inboundSkill)}
            onDelete={() => inboundSkill && handleDelete(inboundSkill)}
          />
          <SkillCard
            title="Outbound Skill"
            description="Transforms responses BEFORE posting to Slack"
            icon={ArrowUpFromLine}
            skill={outboundSkill}
            isOwner={outboundSkill?.created_by === user?.id}
            isDeleting={deletingId === outboundSkill?.id}
            onAdd={() => openCreateModal('slack_outbound')}
            onEdit={() => outboundSkill && openEditModal(outboundSkill)}
            onDelete={() => outboundSkill && handleDelete(outboundSkill)}
          />
        </div>
      )}

      <SlackSkillModal
        isOpen={modalOpen}
        onClose={() => {
          setModalOpen(false)
          setEditingSkill(null)
        }}
        onSave={handleSave}
        editingSkill={editingSkill}
        skillType={modalType}
      />
    </div>
  )
}

interface SkillCardProps {
  title: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  skill?: CustomSkill
  isOwner: boolean
  isDeleting: boolean
  onAdd: () => void
  onEdit: () => void
  onDelete: () => void
}

function SkillCard({ title, description, icon: Icon, skill, isOwner, isDeleting, onAdd, onEdit, onDelete }: SkillCardProps) {
  return (
    <div className="bg-[#1a1a1a] border border-gray-800 rounded-lg p-4">
      <div className="flex items-start gap-3 mb-3">
        <div className="w-8 h-8 rounded-lg bg-brand-orange/10 flex items-center justify-center flex-shrink-0">
          <Icon className="w-4 h-4 text-brand-orange" />
        </div>
        <div className="min-w-0">
          <h4 className="text-sm font-medium text-white">{title}</h4>
          <p className="text-xs text-gray-500">{description}</p>
        </div>
      </div>

      {skill ? (
        <div className="space-y-3">
          <div className="bg-[#0d0d0d] rounded-lg p-3 border border-gray-800">
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle className="w-3.5 h-3.5 text-green-400" />
              <span className="text-sm font-medium text-white">{skill.name}</span>
            </div>
            <p className="text-xs text-gray-400 line-clamp-2">{skill.description}</p>
            <div className="flex items-center gap-2 mt-2">
              <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-500/10 text-green-400 border border-green-500/20">
                <Users className="w-2.5 h-2.5" /> Team shared
              </span>
              {!isOwner && skill.created_by_name && (
                <span className="text-[10px] text-gray-500">
                  by {skill.created_by_name}
                </span>
              )}
            </div>
          </div>

          {isOwner && (
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={onEdit}
                className="text-xs border-gray-700 hover:bg-gray-800 flex-1"
              >
                <Edit2 className="w-3 h-3 mr-1.5" /> Edit
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={onDelete}
                disabled={isDeleting}
                className="text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10"
              >
                {isDeleting ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Trash2 className="w-3 h-3" />
                )}
              </Button>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-2">
          <p className="text-xs text-gray-500 mb-3">Not configured</p>
          <Button
            size="sm"
            variant="outline"
            onClick={onAdd}
            className="border-gray-700 hover:bg-gray-800"
          >
            <Plus className="w-3 h-3 mr-1.5" /> Add Skill
          </Button>
        </div>
      )}
    </div>
  )
}
