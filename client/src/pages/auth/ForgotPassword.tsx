import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useStore } from '../../stores/useStore'

export default function ForgotPassword() {
  const navigate = useNavigate()
  const { forgotPassword, authError, setAuthError, isLoading } = useStore()

  const [email, setEmail] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setAuthError(null)

    try {
      await forgotPassword(email)
      // Redirect to check-email page
      navigate('/check-email', { state: { email, type: 'reset' } })
    } catch {
      // Error is already set in the store
    }
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
          <h1 className="text-2xl font-semibold text-gray-900 mb-2">Reset your password</h1>
          <p className="text-gray-500 mb-8">
            Enter your email and we'll send you a link to reset your password.
          </p>

          {/* Error message */}
          {authError && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-600">{authError}</p>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit}>
            {/* Email field */}
            <div className="mb-6">
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1.5">
                Email
              </label>
              <div className="flex items-center gap-3 py-3 px-4 border border-gray-200 rounded-md transition-all focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/10">
                <svg
                  className="flex-shrink-0 text-gray-400 w-5 h-5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <rect x="2" y="4" width="20" height="16" rx="2" />
                  <path d="M22 6L12 13L2 6" />
                </svg>
                <input
                  id="email"
                  type="email"
                  placeholder="yours@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
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
                  Sending...
                </>
              ) : (
                <>
                  Send reset link
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

          {/* Back to login link */}
          <p className="mt-8 text-center text-sm text-gray-500">
            Remember your password?{' '}
            <Link
              to="/login"
              className="font-medium text-blue-600 hover:text-blue-700 hover:underline"
            >
              Sign in
            </Link>
          </p>
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
