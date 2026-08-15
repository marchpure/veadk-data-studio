import { useState, useRef } from 'react'
import { Button } from './ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog'
import { Loader2, ExternalLink, Copy, Check } from 'lucide-react'
import { openExternalUrl } from '../lib/tauri-api'
import { getCodexOAuthBaseUrl } from '../hooks/useCodexOAuthStatus'

interface CodexOAuthDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onTokensReceived?: (tokens: { access_token: string; refresh_token: string; expires_at: number }) => void
}

type OAuthStep = 'start' | 'device-code' | 'success' | 'error'

export function CodexOAuthDialog({ open, onOpenChange, onTokensReceived }: CodexOAuthDialogProps) {
  const [step, setStep] = useState<OAuthStep>('start')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')
  const [userCode, setUserCode] = useState('')
  const [verificationUrl, setVerificationUrl] = useState('')
  const [copied, setCopied] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const resetDialog = () => {
    abortRef.current?.abort()
    abortRef.current = null
    setStep('start')
    setError('')
    setUserCode('')
    setVerificationUrl('')
    setCopied(false)
  }

  const handleClose = (newOpen: boolean) => {
    if (!newOpen) {
      resetDialog()
    }
    onOpenChange(newOpen)
  }

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(userCode)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback handled by UI
    }
  }

  const openVerificationUrl = async () => {
    try {
      await openExternalUrl(verificationUrl)
    } catch {
      window.open(verificationUrl, '_blank')
    }
  }

  const startOAuth = async () => {
    setLoading(true)
    setError('')

    try {
      const apiBaseUrl = await getCodexOAuthBaseUrl()
      const response = await fetch(`${apiBaseUrl}/codex-oauth/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      const data = await response.json()
      if (!data.success) {
        setError(data.message || 'Failed to start authentication')
        setStep('error')
        return
      }

      const { session_id, verification_url, user_code } = data.data
      setUserCode(user_code)
      setVerificationUrl(verification_url)
      setStep('device-code')

      const abort = new AbortController()
      abortRef.current = abort

      try {
        const pollResponse = await fetch(`${apiBaseUrl}/codex-oauth/poll/${session_id}`, {
          signal: abort.signal
        })
        const pollData = await pollResponse.json()

        if (pollData.success) {
          setStep('success')
          onTokensReceived?.(pollData.data.tokens)
        } else {
          setError(pollData.message || 'Authentication failed')
          setStep('error')
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === 'AbortError') return
        throw err
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      const message = err instanceof Error ? err.message : 'Failed to start authentication'
      setError(message)
      setStep('error')
    } finally {
      setLoading(false)
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
              'Authenticate with OpenAI Codex'
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {step === 'start' && (
            <>
              <p className="text-sm text-gray-400">
                Connect your ChatGPT Plus or Pro subscription to use Codex models without separate API credits.
              </p>

              <div className="p-3 bg-[#1a1a1a] rounded-md border border-[#555555]">
                <p className="text-xs text-gray-500">
                  You'll receive a one-time code to enter on OpenAI's website.
                  After verifying, your account will be connected automatically.
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

          {step === 'device-code' && (
            <>
              <p className="text-sm text-gray-400">
                Enter this code on OpenAI's website to connect your account:
              </p>

              <div className="flex items-center justify-center gap-3 p-4 bg-[#1a1a1a] rounded-md border border-[#555555]">
                <span className="text-2xl font-mono font-bold text-white tracking-widest">
                  {userCode}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={copyCode}
                  className="border-[#555555] text-white hover:bg-[#3a3a3a] px-2"
                  title="Copy code"
                >
                  {copied ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                </Button>
              </div>

              <Button
                onClick={openVerificationUrl}
                className="w-full bg-brand-orange hover:bg-brand-orange/90 flex items-center justify-center gap-2"
              >
                <ExternalLink className="w-4 h-4" />
                Open OpenAI Verification Page
              </Button>

              <div className="flex items-center gap-2 justify-center text-sm text-gray-500">
                <Loader2 className="w-4 h-4 animate-spin" />
                Waiting for verification...
              </div>

              <div className="flex justify-end pt-2">
                <Button
                  variant="outline"
                  onClick={() => handleClose(false)}
                  className="border-[#555555] text-white hover:bg-[#3a3a3a]"
                >
                  Cancel
                </Button>
              </div>
            </>
          )}

          {step === 'success' && (
            <>
              <div className="p-4 bg-green-900/20 border border-green-500 rounded-md text-center">
                <Check className="w-12 h-12 text-green-400 mx-auto mb-3" />
                <p className="text-green-400 font-medium mb-2">
                  Successfully authenticated with OpenAI!
                </p>
                <p className="text-sm text-gray-400">
                  You can now use Codex models in Byaan via your ChatGPT subscription.
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
