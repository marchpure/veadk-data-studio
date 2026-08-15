import { useState, useEffect } from 'react'
import { Loader2, MessageSquare } from 'lucide-react'
import { Button } from '../ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { ApiService } from '../../services/api'
import { useSlackConfig } from '../../hooks/useSlackConfig'
import { useAppConfig } from '../../hooks/useAppConfig'

type FrequencyType = 'daily' | 'weekly' | 'custom'

export interface ScheduleConfig {
  frequency: FrequencyType
  hour: string
  minute: string
  dayOfWeek: string
  customCron: string
  slackChannelId: string
}

interface ScheduleConfigPanelProps {
  config: ScheduleConfig
  onConfigChange: (config: ScheduleConfig) => void
  onCancel: () => void
  onSave: () => void
  isSaving: boolean
  existingScheduleId?: string | null
  instruction?: string
}

const DAYS_OF_WEEK = [
  { value: '0', label: 'Sun' },
  { value: '1', label: 'Mon' },
  { value: '2', label: 'Tue' },
  { value: '3', label: 'Wed' },
  { value: '4', label: 'Thu' },
  { value: '5', label: 'Fri' },
  { value: '6', label: 'Sat' },
]

export function ScheduleConfigPanel({
  config,
  onConfigChange,
  onCancel,
  onSave,
  isSaving,
  existingScheduleId,
  instruction,
}: ScheduleConfigPanelProps) {
  const { isSelfHosted } = useAppConfig()
  const { isConnected: isSlackConnected } = useSlackConfig(isSelfHosted)
  const [slackChannels, setSlackChannels] = useState<Array<{ id: string; name: string }>>([])
  const [loadingChannels, setLoadingChannels] = useState(false)

  useEffect(() => {
    if (isSlackConnected) {
      setLoadingChannels(true)
      ApiService.getSlackChannels()
        .then(channels => setSlackChannels(channels))
        .catch(err => console.error('Failed to load Slack channels:', err))
        .finally(() => setLoadingChannels(false))
    }
  }, [isSlackConnected])

  const hours = Array.from({ length: 24 }, (_, i) => i.toString())

  const updateConfig = (updates: Partial<ScheduleConfig>) => {
    onConfigChange({ ...config, ...updates })
  }

  return (
    <div className="px-6 pb-3">
      <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 bg-[#1f1f1f] border border-[#333] rounded-xl">
        <Select
          value={config.frequency}
          onValueChange={(v) => updateConfig({ frequency: v as FrequencyType })}
        >
          <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white text-xs h-8 w-24">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-[#2a2a2a] border-gray-600">
            <SelectItem value="daily" className="text-xs">Daily</SelectItem>
            <SelectItem value="weekly" className="text-xs">Weekly</SelectItem>
            <SelectItem value="custom" className="text-xs">Custom</SelectItem>
          </SelectContent>
        </Select>

        {config.frequency === 'weekly' && (
          <Select value={config.dayOfWeek} onValueChange={(v) => updateConfig({ dayOfWeek: v })}>
            <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white text-xs h-8 w-20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[#2a2a2a] border-gray-600">
              {DAYS_OF_WEEK.map((day) => (
                <SelectItem key={day.value} value={day.value} className="text-xs">{day.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {config.frequency !== 'custom' && (
          <Select value={config.hour} onValueChange={(v) => updateConfig({ hour: v })}>
            <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white text-xs h-8 w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[#2a2a2a] border-gray-600 max-h-48">
              {hours.map((h) => (
                <SelectItem key={h} value={h} className="text-xs">
                  {parseInt(h) === 0 ? '12 AM' : parseInt(h) < 12 ? `${h} AM` : parseInt(h) === 12 ? '12 PM' : `${parseInt(h) - 12} PM`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {config.frequency === 'custom' && (
          <input
            value={config.customCron}
            onChange={(e) => updateConfig({ customCron: e.target.value })}
            placeholder="0 9 * * *"
            className="bg-[#2a2a2a] border border-gray-600 rounded text-white text-xs h-8 px-2 font-mono w-28 focus:outline-none focus:ring-1 focus:ring-brand-orange/50"
          />
        )}

        {isSlackConnected && (
          <div className="flex items-center gap-1">
            <MessageSquare className="w-3.5 h-3.5 text-gray-400" />
            <Select
              value={config.slackChannelId || '_none'}
              onValueChange={(v) => updateConfig({ slackChannelId: v === '_none' ? '' : v })}
            >
              <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white text-xs h-8 w-32">
                <SelectValue placeholder={loadingChannels ? 'Loading...' : 'Channel'} />
              </SelectTrigger>
              <SelectContent className="bg-[#2a2a2a] border-gray-600 max-h-48">
                <SelectItem value="_none" className="text-xs">No channel</SelectItem>
                {slackChannels.filter(c => c.id?.trim()).map((channel) => (
                  <SelectItem key={channel.id} value={channel.id} className="text-xs">#{channel.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div className="flex-1" />

        <Button
          size="sm"
          variant="ghost"
          onClick={onCancel}
          disabled={isSaving}
          className="h-8 text-xs text-gray-400 hover:text-white"
        >
          Cancel
        </Button>
        <Button
          size="sm"
          variant="brand-primary"
          onClick={onSave}
          disabled={isSaving || !instruction?.trim()}
          className="h-8 text-xs"
        >
          {isSaving && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
          {existingScheduleId ? 'Update Schedule' : 'Save Schedule'}
        </Button>
      </div>
    </div>
  )
}
