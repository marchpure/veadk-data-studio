import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Loader2, ArrowDownToLine, ArrowUpFromLine } from 'lucide-react'
import type { CustomSkill, CreateCustomSkillData } from '@/stores/slices/contextSlice'

type SlackSkillType = 'slack_inbound' | 'slack_outbound'

interface SlackSkillModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (data: Omit<CreateCustomSkillData, 'skill_type' | 'scope'>) => Promise<void>
  editingSkill?: CustomSkill | null
  skillType: SlackSkillType
}

const SKILL_CONFIG = {
  slack_inbound: {
    title: 'Inbound Skill',
    icon: ArrowDownToLine,
    description: 'Inbound skills enrich questions with context before the AI processes them. Add data sources, example queries, and formatting guidelines.',
    namePlaceholder: 'e.g., Sales Context',
    descriptionPlaceholder: 'Adds context for sales team Slack questions',
    instructionsPlaceholder: `DATA SOURCES TO USE:
- Primary: sales_pipeline database
- Reference: customer_info table

EXAMPLE QUESTIONS:
- "What's our Q1 revenue?"
- "Show top 10 customers by sales"

CONTEXT TO ADD:
- Always include date ranges when relevant
- Reference company fiscal year (Jan-Dec)`,
  },
  slack_outbound: {
    title: 'Outbound Skill',
    icon: ArrowUpFromLine,
    description: 'Outbound skills transform AI responses before posting to Slack. Add formatting rules, tone guidelines, and content filters.',
    namePlaceholder: 'e.g., Slack Formatter',
    descriptionPlaceholder: 'Formats responses for Slack posting',
    instructionsPlaceholder: `FORMATTING RULES:
- Use Slack markdown (*bold*, _italic_, \`code\`)
- Keep responses under 2000 characters
- Use bullet points for lists

TONE GUIDELINES:
- Professional but friendly
- Avoid technical jargon
- Include relevant emojis sparingly

CONTENT FILTERS:
- Never include raw SQL in responses
- Summarize large data sets`,
  },
}

export function SlackSkillModal({ isOpen, onClose, onSave, editingSkill, skillType }: SlackSkillModalProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [instructions, setInstructions] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const config = SKILL_CONFIG[skillType]
  const Icon = config.icon

  useEffect(() => {
    if (editingSkill) {
      setName(editingSkill.name ?? '')
      setDescription(editingSkill.description ?? '')
      setInstructions(editingSkill.instructions ?? '')
    } else {
      setName('')
      setDescription('')
      setInstructions('')
    }
    setError(null)
  }, [editingSkill, isOpen])

  const isValid = name?.trim() && description?.trim() && instructions?.trim()

  async function handleSave() {
    if (!isValid) return

    setIsSaving(true)
    setError(null)

    try {
      await onSave({
        name: name.trim(),
        description: description.trim(),
        instructions: instructions.trim(),
      })
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save skill')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="bg-[#0d0d0d] border-gray-800 max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-white flex items-center gap-2">
            <Icon className="w-5 h-5 text-brand-orange" />
            {editingSkill ? `Edit ${config.title}` : `Create ${config.title}`}
          </DialogTitle>
        </DialogHeader>

        <p className="text-sm text-gray-400 -mt-2">
          {config.description}
        </p>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-300">Skill Name</label>
            <Input
              placeholder={config.namePlaceholder}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="bg-[#1a1a1a] border-gray-700 text-white"
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-300">Description</label>
            <Input
              placeholder={config.descriptionPlaceholder}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="bg-[#1a1a1a] border-gray-700 text-white"
            />
            <p className="text-xs text-gray-500">
              Brief description of what this skill does
            </p>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-300">Instructions</label>
            <textarea
              placeholder={config.instructionsPlaceholder}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={10}
              className="w-full px-3 py-2 bg-[#1a1a1a] border border-gray-700 rounded-md text-white text-sm placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-orange resize-y"
            />
            <p className="text-xs text-gray-500">
              Detailed instructions the AI will follow. Markdown is supported.
            </p>
          </div>

          {error && (
            <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-md">
              <p className="text-sm text-red-400">{error}</p>
            </div>
          )}

          <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-md">
            <p className="text-xs text-blue-400">
              This skill will be shared with your team and applied to all Slack interactions.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={onClose}
            disabled={isSaving}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={!isValid || isSaving}
            className="bg-brand-orange hover:bg-brand-orange/90"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              editingSkill ? 'Save Changes' : 'Create Skill'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
