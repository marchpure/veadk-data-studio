import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useStore } from '../../stores/useStore'

export default function ResetPassword() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const { resetPassword, authError, setAuthError, isLoading } = useStore()

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setAuthError(null)
    setLocalError(null)

    if (!token) {
      setLocalError('Invalid reset link. Please request a new password reset.')
      return
    }

    // Validate passwords match
    if (password !== confirmPassword) {
      setLocalError('Passwords do not match')
      return
    }

    // Validate password strength
    if (password.length < 8) {
      setLocalError('Password must be at least 8 characters')
      return
    }

    try {
      await resetPassword(token, password)
      setSuccess(true)
      // Redirect to login after 3 seconds
      setTimeout(() => {
        navigate('/login')
      }, 3000)
    } catch {
      // Error is already set in the store
    }
  }

  const displayError = localError || authError

  // No token provided
  if (!token) {
    return (
      <div className="flex min-h-screen w-full">
        <div className="flex-1 flex items-center justify-center p-8 bg-white">
          <div className="w-full max-w-[380px] text-center">
            <div className="mb-10">
              <span className="text-3xl font-bold text-gray-900 tracking-tight">Byaan</span>
            </div>
            <div className="text-6xl mb-6">:(</div>
            <h1 className="text-2xl font-semibold text-gray-900 mb-4">Invalid Reset Link</h1>
            <p className="text-gray-500 mb-8">
              This password reset link is invalid or has expired.
            </p>
            <Link
              to="/forgot-password"
              className="inline-flex items-center justify-center gap-2 py-3 px-6 bg-brand-orange border-none rounded-md text-base font-semibold text-white transition-all hover:bg-brand-orange-hover"
            >
              Request new link
            </Link>
          </div>
        </div>
        <div className="flex-1 hidden md:flex items-center justify-center p-8 bg-[#0f0f0f]">
          <div className="max-w-[500px] text-center">
            <p className="text-xs font-semibold tracking-[0.15em] text-brand-orange mb-6">
              AI-POWERED DATA ANALYTICS
            </p>
            <h1 className="text-5xl font-bold text-white leading-tight tracking-tight">
              Your data companion
              <br />
              for insights at scale
            </h1>
          </div>
        </div>
      </div>
    )
  }

  // Success state
  if (success) {
    return (
      <div className="flex min-h-screen w-full">
        <div className="flex-1 flex items-center justify-center p-8 bg-white">
          <div className="w-full max-w-[380px] text-center">
            <div className="mb-10">
              <span className="text-3xl font-bold text-gray-900 tracking-tight">Byaan</span>
            </div>
            <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-green-100 flex items-center justify-center">
              <svg className="w-8 h-8 text-green-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
            <h1 className="text-2xl font-semibold text-gray-900 mb-4">Password Reset!</h1>
            <p className="text-gray-500 mb-8">
              Your password has been successfully reset. Redirecting to login...
            </p>
            <Link
              to="/login"
              className="inline-flex items-center justify-center gap-2 py-3 px-6 bg-brand-orange border-none rounded-md text-base font-semibold text-white transition-all hover:bg-brand-orange-hover"
            >
              Sign in now
            </Link>
          </div>
        </div>
        <div className="flex-1 hidden md:flex items-center justify-center p-8 bg-[#0f0f0f]">
          <div className="max-w-[500px] text-center">
            <p className="text-xs font-semibold tracking-[0.15em] text-brand-orange mb-6">
              AI-POWERED DATA ANALYTICS
            </p>
            <h1 className="text-5xl font-bold text-white leading-tight tracking-tight">
              Your data companion
              <br />
              for insights at scale
            </h1>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen w-full">
      {/* Left side - Form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-white">
        <div className="w-full max-w-[380px]">
          {/* Logo */}
          <div className="mb-10">
            <span className="text-3xl font-bold text-gray-900 tracking-tight">Byaan</span>
          </div>

          {/* Header */}
          <h1 className="text-2xl font-semibold text-gray-900 mb-2">Set new password</h1>
          <p className="text-gray-500 mb-8">
            Enter your new password below.
          </p>

          {/* Error message */}
          {displayError && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-600">{displayError}</p>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit}>
            {/* Password field */}
            <div className="mb-4">
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1.5">
                New password
              </label>
              <div className="flex items-center gap-3 py-3 px-4 border border-gray-200 rounded-md transition-all focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/10">
                <svg
                  className="flex-shrink-0 text-gray-400 w-5 h-5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0110 0v4" />
                </svg>
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="At least 8 characters"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={isLoading}
                  className="flex-1 border-none outline-none text-[15px] text-gray-900 bg-transparent placeholder:text-gray-400"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  {showPassword ? (
                    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            {/* Confirm password field */}
            <div className="mb-6">
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 mb-1.5">
                Confirm password
              </label>
              <div className="flex items-center gap-3 py-3 px-4 border border-gray-200 rounded-md transition-all focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/10">
                <svg
                  className="flex-shrink-0 text-gray-400 w-5 h-5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0110 0v4" />
                </svg>
                <input
                  id="confirmPassword"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Confirm your password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  disabled={isLoading}
                  className="flex-1 border-none outline-none text-[15px] text-gray-900 bg-transparent placeholder:text-gray-400"
                />
              </div>
            </div>

            {/* Submit button */}
            <button
              type="submit"
              disabled={isLoading}
              className="flex items-center justify-center gap-2 w-full py-3 px-6 bg-brand-orange border-none rounded-md text-base font-semibold text-white cursor-pointer transition-all hover:bg-brand-orange-hover disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <>
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white"></div>
                  Resetting...
                </>
              ) : (
                <>
                  Reset password
                  <svg
                    className="flex-shrink-0"
                    viewBox="0 0 24 24"
                    width="20"
                    height="20"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </>
              )}
            </button>
          </form>
        </div>
      </div>

      {/* Right side - Branding */}
      <div className="flex-1 hidden md:flex items-center justify-center p-8 bg-[#0f0f0f]">
        <div className="max-w-[500px] text-center">
          <p className="text-xs font-semibold tracking-[0.15em] text-brand-orange mb-6">
            AI-POWERED DATA ANALYTICS
          </p>
          <h1 className="text-5xl font-bold text-white leading-tight tracking-tight">
            Your data companion
            <br />
            for insights at scale
          </h1>
        </div>
      </div>
    </div>
  )
}
