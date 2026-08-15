import { useEffect, useRef, useCallback } from 'react'
import { getGoogleClientId } from '@/lib/runtime-config'

interface GoogleSignInButtonProps {
  onSuccess: (credential: string) => void
  onError?: (error: string) => void
  disabled?: boolean
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string
            callback: (response: { credential?: string }) => void
            auto_select?: boolean
            cancel_on_tap_outside?: boolean
          }) => void
          renderButton: (
            element: HTMLElement,
            config: {
              type?: 'standard' | 'icon'
              theme?: 'outline' | 'filled_blue' | 'filled_black'
              size?: 'large' | 'medium' | 'small'
              text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin'
              shape?: 'rectangular' | 'pill' | 'circle' | 'square'
              width?: number
            }
          ) => void
          prompt: () => void
        }
      }
    }
  }
}

export default function GoogleSignInButton({ onSuccess, onError, disabled }: GoogleSignInButtonProps) {
  const buttonRef = useRef<HTMLDivElement>(null)
  const initialized = useRef(false)

  const handleCredentialResponse = useCallback(
    (response: { credential?: string }) => {
      if (response.credential) {
        onSuccess(response.credential)
      } else {
        onError?.('No credential received from Google')
      }
    },
    [onSuccess, onError]
  )

  useEffect(() => {
    const clientId = getGoogleClientId()
    if (!clientId) {
      onError?.('Google Client ID is not configured')
      return
    }

    const initializeGoogle = () => {
      if (!window.google || initialized.current) return

      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: handleCredentialResponse,
        auto_select: false,
        cancel_on_tap_outside: true,
      })

      if (buttonRef.current) {
        window.google.accounts.id.renderButton(buttonRef.current, {
          type: 'standard',
          theme: 'outline',
          size: 'large',
          text: 'continue_with',
          shape: 'rectangular',
          width: 380,
        })
      }

      initialized.current = true
    }

    if (window.google) {
      initializeGoogle()
    } else {
      const existingScript = document.querySelector<HTMLScriptElement>('script[data-google-identity-services="true"]')
      if (!existingScript) {
        const script = document.createElement('script')
        script.src = 'https://accounts.google.com/gsi/client'
        script.async = true
        script.defer = true
        script.dataset.googleIdentityServices = 'true'
        script.onerror = () => onError?.('Failed to load Google Sign-In')
        document.head.appendChild(script)
      }

      const checkGoogle = setInterval(() => {
        if (window.google) {
          clearInterval(checkGoogle)
          initializeGoogle()
        }
      }, 100)

      // Clean up interval after 10 seconds
      const timeout = setTimeout(() => {
        clearInterval(checkGoogle)
      }, 10000)

      return () => {
        clearInterval(checkGoogle)
        clearTimeout(timeout)
      }
    }
  }, [handleCredentialResponse, onError])

  return (
    <div
      ref={buttonRef}
      className={`google-signin-button flex justify-center ${disabled ? 'opacity-50 pointer-events-none' : ''}`}
    />
  )
}
