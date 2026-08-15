import { Link, useLocation } from 'react-router-dom'

export default function CheckEmail() {
  const location = useLocation()
  const email = location.state?.email || ''

  return (
    <div className="flex min-h-screen w-full">
      {/* Left side - Content */}
      <div className="flex-1 flex items-center justify-center p-8 bg-white">
        <div className="w-full max-w-[380px] text-center">
          {/* Logo */}
          <div className="mb-10">
            <span className="text-3xl font-bold text-gray-900 tracking-tight">Byaan</span>
          </div>

          {/* Email icon */}
          <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-blue-100 flex items-center justify-center">
            <svg className="w-10 h-10 text-blue-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="2" y="4" width="20" height="16" rx="2" />
              <path d="M22 6L12 13L2 6" />
            </svg>
          </div>

          {/* Header */}
          <h1 className="text-2xl font-semibold text-gray-900 mb-4">Check your email</h1>
          <p className="text-gray-500 mb-2">We've sent a password reset link to:</p>
          {email && (
            <p className="text-gray-900 font-medium mb-6">{email}</p>
          )}

          {/* Instructions */}
          <div className="bg-gray-50 rounded-lg p-4 mb-8 text-left">
            <p className="text-sm font-medium text-gray-700 mb-3">Next steps:</p>
            <ol className="text-sm text-gray-600 space-y-2">
              <li className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-gray-200 text-gray-600 text-xs flex items-center justify-center font-medium">1</span>
                <span>Open your email inbox</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-gray-200 text-gray-600 text-xs flex items-center justify-center font-medium">2</span>
                <span>Click the "Reset Password" button</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-gray-200 text-gray-600 text-xs flex items-center justify-center font-medium">3</span>
                <span>Set your new password</span>
              </li>
            </ol>
          </div>

          {/* Didn't receive email */}
          <div className="text-sm text-gray-500 mb-6">
            <p className="mb-2">Didn't receive the email?</p>
            <ul className="text-left list-disc list-inside space-y-1">
              <li>Check your spam or junk folder</li>
              <li>Make sure the email address is correct</li>
              <li>Wait a few minutes and check again</li>
            </ul>
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-3">
            <Link
              to="/forgot-password"
              className="inline-flex items-center justify-center gap-2 py-3 px-6 bg-brand-orange border-none rounded-md text-base font-semibold text-white transition-all hover:bg-brand-orange-hover"
            >
              Try again
            </Link>
            <Link
              to="/login"
              className="inline-flex items-center justify-center gap-2 py-3 px-6 bg-white border border-gray-200 rounded-md text-base font-semibold text-gray-700 transition-all hover:bg-gray-50"
            >
              Back to login
            </Link>
          </div>
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
