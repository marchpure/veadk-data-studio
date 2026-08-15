import { useState, useEffect } from 'react'
import { Button } from '../ui/button'
import { Card } from '../ui/card'
import { Input } from '../ui/input'
import { Switch } from '../ui/switch'
import { Loader2, Trash2, Settings2, ChevronDown, ChevronRight, ExternalLink } from 'lucide-react'
import { GitHubService } from '../../services/github'

function SetupStepsAccordion({ callbackUrl }: { callbackUrl: string }) {
  const [expandedStep, setExpandedStep] = useState(0)

  const steps = [
    {
      id: 1,
      title: 'Create a GitHub OAuth App',
      content: (
        <ul className="space-y-2 text-sm text-gray-400">
          <li className="flex items-start gap-2">
            <span className="text-gray-500 mt-0.5">•</span>
            <span>
              Go to{' '}
              <a
                href="https://github.com/settings/developers"
                target="_blank"
                rel="noopener noreferrer"
                className="text-brand-orange hover:underline inline-flex items-center gap-1"
              >
                github.com/settings/developers
                <ExternalLink className="w-3 h-3" />
              </a>
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-gray-500 mt-0.5">•</span>
            <span>Click <strong className="text-gray-300">"New OAuth App"</strong></span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-gray-500 mt-0.5">•</span>
            <span>
              Set <strong className="text-gray-300">"Application name"</strong> to anything (e.g., "Byaan")
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-gray-500 mt-0.5">•</span>
            <span>
              Set <strong className="text-gray-300">"Homepage URL"</strong> to your app domain:
            </span>
          </li>
          <li className="ml-4">
            <code className="text-xs text-brand-orange bg-gray-800 px-2 py-1 rounded block break-all">
              {window.location.origin}
            </code>
          </li>
        </ul>
      ),
    },
    {
      id: 2,
      title: 'Set the Callback URL',
      content: (
        <ul className="space-y-2 text-sm text-gray-400">
          <li className="flex items-start gap-2">
            <span className="text-gray-500 mt-0.5">•</span>
            <span>
              Set <strong className="text-gray-300">"Authorization callback URL"</strong> to:
            </span>
          </li>
          <li className="ml-4">
            <code className="text-xs text-brand-orange bg-gray-800 px-2 py-1 rounded block break-all">
              {callbackUrl}
            </code>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-gray-500 mt-0.5">•</span>
            <span>Click <strong className="text-gray-300">"Register application"</strong></span>
          </li>
        </ul>
      ),
    },
    {
      id: 3,
      title: 'Enable Device Flow & Copy Client ID',
      content: (
        <ul className="space-y-2 text-sm text-gray-400">
          <li className="flex items-start gap-2">
            <span className="text-gray-500 mt-0.5">•</span>
            <span>
              On the app page, check <strong className="text-gray-300">"Enable Device Flow"</strong> under Device Flow settings and save
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-gray-500 mt-0.5">•</span>
            <span>
              Copy the <strong className="text-gray-300">"Client ID"</strong> and paste it in the field below
            </span>
          </li>
        </ul>
      ),
    },
  ]

  return (
    <div className="bg-[#0d0d0d] rounded-lg border border-gray-800 overflow-hidden mb-4">
      <h3 className="text-sm font-medium text-white px-4 py-3 border-b border-gray-800">
        Setup Guide
      </h3>
      <div className="divide-y divide-gray-800">
        {steps.map((step) => (
          <div key={step.id}>
            <button
              type="button"
              onClick={() => setExpandedStep(expandedStep === step.id ? 0 : step.id)}
              className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-gray-800/50 transition-colors"
            >
              {expandedStep === step.id ? (
                <ChevronDown className="w-4 h-4 text-brand-orange flex-shrink-0" />
              ) : (
                <ChevronRight className="w-4 h-4 text-gray-500 flex-shrink-0" />
              )}
              <span className="text-brand-orange font-mono text-sm w-4">{step.id}.</span>
              <span className={`text-sm ${expandedStep === step.id ? 'text-white' : 'text-gray-400'}`}>
                {step.title}
              </span>
            </button>
            {expandedStep === step.id && (
              <div className="px-4 pb-4 pl-14">
                {step.content}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

interface GitHubOAuthSettingsProps {
  onConfigChanged: () => void
}

export function GitHubOAuthSettings({ onConfigChanged }: GitHubOAuthSettingsProps) {
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [secretConfigured, setSecretConfigured] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const callbackUrl = `${window.location.origin}/api/github/oauth/callback`

  useEffect(() => {
    GitHubService.getOAuthSettings()
      .then((data) => {
        setClientId(data.client_id)
        setSecretConfigured(data.client_secret_configured)
        if (data.client_secret_configured) setExpanded(true)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    if (!clientId.trim() || !clientSecret.trim()) return
    setSaving(true)
    try {
      await GitHubService.saveOAuthSettings(clientId.trim(), clientSecret.trim())
      setSecretConfigured(true)
      setClientSecret('')
      onConfigChanged()
    } catch (err) {
      console.error('Failed to save OAuth config:', err)
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = async () => {
    setRemoving(true)
    try {
      await GitHubService.deleteOAuthSettings()
      setClientId('')
      setClientSecret('')
      setSecretConfigured(false)
      setExpanded(false)
      onConfigChanged()
    } catch (err) {
      console.error('Failed to remove OAuth config:', err)
    } finally {
      setRemoving(false)
    }
  }

  if (loading) {
    return (
      <Card className="bg-[#1a1a1a] border-gray-800 p-6 mb-8">
        <div className="flex items-center justify-center py-4">
          <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
        </div>
      </Card>
    )
  }

  return (
    <Card className="bg-[#1a1a1a] border-gray-800 p-6 mb-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Settings2 className="w-5 h-5 text-gray-400" />
          <div>
            <h3 className="text-white font-medium">Enable GitHub OAuth</h3>
            <p className="text-xs text-gray-500">
              Allow users to connect via OAuth instead of personal access tokens
            </p>
          </div>
        </div>
        <Switch
          checked={expanded}
          onCheckedChange={setExpanded}
        />
      </div>

      {expanded && (
        <div className="mt-5 pt-5 border-t border-gray-800">
          <SetupStepsAccordion callbackUrl={callbackUrl} />

          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Client ID</label>
              <Input
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                placeholder="Ov23li..."
                className="bg-[#111] border-gray-700 text-white text-sm"
              />
            </div>

            <div>
              <label className="text-xs text-gray-400 mb-1 block">
                Client Secret {secretConfigured && <span className="text-green-400 ml-1">(configured)</span>}
              </label>
              <Input
                type="password"
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
                placeholder={secretConfigured ? '••••••••••••••••' : 'Enter client secret'}
                className="bg-[#111] border-gray-700 text-white text-sm"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              {secretConfigured && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleRemove}
                  disabled={removing}
                  className="border-red-800 text-red-400 hover:bg-red-900/20"
                >
                  {removing ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Trash2 className="w-4 h-4 mr-1" />}
                  Remove
                </Button>
              )}
              <Button
                size="sm"
                onClick={handleSave}
                disabled={saving || !clientId.trim() || !clientSecret.trim()}
                className="bg-brand-orange hover:bg-brand-orange/90"
              >
                {saving && <Loader2 className="w-4 h-4 animate-spin mr-1" />}
                Save
              </Button>
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}
