import { useState } from 'react'
import { Button } from './ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { Loader2, ExternalLink, Copy, Check } from 'lucide-react'
import { openExternalUrl } from '../lib/tauri-api'
import { getClaudeOAuthBaseUrl } from '../hooks/useClaudeOAuthStatus'

interface ClaudeOAuthDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}

type OAuthStep = 'start' | 'code' | 'success' | 'error'

export function ClaudeOAuthDialog({ open, onOpenChange, onSuccess }: ClaudeOAuthDialogProps) {
  const [step, setStep] = useState<OAuthStep>('start')
  const [authUrl, setAuthUrl] = useState<string>('')
  const [state, setState] = useState<string>('')
  const [code, setCode] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')
  const [copied, setCopied] = useState(false)

  const resetDialog = () => {
    setStep('start')
    setAuthUrl('')
    setState('')
    setCode('')
    setError('')
    setCopied(false)
  }

  const handleClose = (newOpen: boolean) => {
    if (!newOpen) {
      resetDialog()
    }
    onOpenChange(newOpen)
  }

  const startOAuth = async () => {
    setLoading(true)
    setError('')

    try {
      const apiBaseUrl = await getClaudeOAuthBaseUrl()
      const response = await fetch(`${apiBaseUrl}/claude-oauth/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      const data = await response.json()
      if (data.success) {
        setAuthUrl(data.data.auth_url)
        setState(data.data.state)
        setStep('code')
      } else {
        setError(data.message || 'Failed to start OAuth flow')
        setStep('error')
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to start OAuth flow'
      setError(message)
      setStep('error')
    } finally {
      setLoading(false)
    }
  }

  const exchangeCode = async () => {
    if (!code.trim()) {
      setError('Please enter the authorization code')
      return
    }

    setLoading(true)
    setError('')

    try {
      const apiBaseUrl = await getClaudeOAuthBaseUrl()
      const response = await fetch(`${apiBaseUrl}/claude-oauth/exchange`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: code.trim(),
          state: state
        })
      })
      const data = await response.json()

      if (data.success) {
        setStep('success')
        onSuccess?.()
      } else {
        setError(data.message || 'Failed to exchange code')
        setStep('error')
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to exchange code'
      setError(message)
      setStep('error')
    } finally {
      setLoading(false)
    }
  }

  const copyUrl = async () => {
    try {
      await navigator.clipboard.writeText(authUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback: select the text in a textarea
    }
  }

  const openAuthUrl = async () => {
    try {
      await openExternalUrl(authUrl)
    } catch (error) {
      console.error('Failed to open auth URL:', error)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg bg-[#2a2a2a] border-[#444444]">
        <DialogHeader>
          <DialogTitle className="text-white flex items-center gap-2">
            {step === 'success' ? (
              <>
                <Check className="w-5 h-5 text-green-400" />
                Authentication Successful
              </>
            ) : (
              'Authenticate with Claude Pro/Max'
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Step: Start */}
          {step === 'start' && (
            <>
              <p className="text-sm text-gray-400">
                Connect your Claude Pro or Max subscription to use Claude models without an API key.
                This uses the same authentication as Claude Code CLI.
              </p>

              <div className="p-3 bg-[#1a1a1a] rounded-md border border-[#555555]">
                <p className="text-xs text-gray-500">
                  You'll be redirected to claude.ai to authorize access. After authorizing,
                  copy the authorization code and paste it here.
                </p>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={() => handleClose(false)}
                  className="border-[#555555] text-white hover:bg-[#3a3a3a]"
                >
                  Cancel
                </Button>
                <Button
                  onClick={startOAuth}
                  disabled={loading}
                  className="bg-brand-orange hover:bg-brand-orange/90 flex items-center gap-2"
                >
                  {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                  Start Authentication
                </Button>
              </div>
            </>
          )}

          {/* Step: Enter Code */}
          {step === 'code' && (
            <>
              <p className="text-sm text-gray-400 mb-4">
                Click the button below to open the authorization page, then paste the code you receive.
              </p>

              {/* Auth URL Display */}
              <div className="space-y-2">
                <Label className="text-white text-sm">Authorization URL</Label>
                <div className="flex gap-2">
                  <div className="flex-1 p-3 bg-[#1a1a1a] rounded-md border border-[#555555] overflow-hidden">
                    <p className="text-xs text-blue-400 break-all line-clamp-2">
                      {authUrl}
                    </p>
                  </div>
                  <div className="flex flex-col gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={copyUrl}
                      className="border-[#555555] text-white hover:bg-[#3a3a3a] px-2"
                      title="Copy URL"
                    >
                      {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={openAuthUrl}
                      className="border-[#555555] text-white hover:bg-[#3a3a3a] px-2"
                      title="Open in browser"
                    >
                      <ExternalLink className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </div>

              {/* Code Input */}
              <div className="space-y-2">
                <Label htmlFor="auth-code" className="text-white">
                  Authorization Code
                </Label>
                <Input
                  id="auth-code"
                  type="text"
                  placeholder="Paste the authorization code here..."
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  className="bg-[#1a1a1a] border-[#555555] text-white"
                  autoFocus
                />
                <p className="text-xs text-gray-500">
                  After authorizing in your browser, copy the code and paste it above.
                </p>
              </div>

              {error && (
                <div className="p-3 bg-red-900/20 border border-red-500 rounded-md">
                  <p className="text-sm text-red-400">{error}</p>
                </div>
              )}

              <div className="flex justify-between gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={resetDialog}
                  disabled={loading}
                  className="border-[#555555] text-white hover:bg-[#3a3a3a]"
                >
                  Back
                </Button>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => handleClose(false)}
                    disabled={loading}
                    className="border-[#555555] text-white hover:bg-[#3a3a3a]"
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={exchangeCode}
                    disabled={loading || !code.trim()}
                    className="bg-brand-orange hover:bg-brand-orange/90 flex items-center gap-2"
                  >
                    {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                    Authenticate
                  </Button>
                </div>
              </div>
            </>
          )}

          {/* Step: Success */}
          {step === 'success' && (
            <>
              <div className="p-4 bg-green-900/20 border border-green-500 rounded-md text-center">
                <Check className="w-12 h-12 text-green-400 mx-auto mb-3" />
                <p className="text-green-400 font-medium mb-2">
                  Successfully authenticated with Claude!
                </p>
                <p className="text-sm text-gray-400">
                  You can now use Claude Pro/Max models in Byaan.
                </p>
              </div>

              <div className="flex justify-end pt-2">
                <Button
                  onClick={() => handleClose(false)}
                  className="bg-brand-orange hover:bg-brand-orange/90"
                >
                  Done
                </Button>
              </div>
            </>
          )}

          {/* Step: Error */}
          {step === 'error' && (
            <>
              <div className="p-4 bg-red-900/20 border border-red-500 rounded-md text-center">
                <p className="text-red-400 font-medium mb-2">
                  Authentication Failed
                </p>
                <p className="text-sm text-gray-400">
                  {error || 'An error occurred during authentication.'}
                </p>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={() => handleClose(false)}
                  className="border-[#555555] text-white hover:bg-[#3a3a3a]"
                >
                  Cancel
                </Button>
                <Button
                  onClick={() => {
                    resetDialog()
                    startOAuth()
                  }}
                  className="bg-brand-orange hover:bg-brand-orange/90"
                >
                  Try Again
                </Button>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
