import * as React from 'react'

interface SwitchProps {
  id?: string
  checked?: boolean
  onCheckedChange?: (checked: boolean) => void
  disabled?: boolean
  className?: string
  size?: 'default' | 'sm'
  variant?: 'default' | 'destructive'
}

const trackSize = {
  default: 'h-5 w-9',
  sm: 'h-4 w-7',
}

const knobSize = {
  default: 'h-4 w-4',
  sm: 'h-3 w-3',
}

const knobTranslate = {
  default: 'translate-x-4',
  sm: 'translate-x-3',
}

const checkedBg = {
  default: 'bg-brand-orange',
  destructive: 'bg-red-500',
}

const Switch = React.forwardRef<HTMLButtonElement, SwitchProps>(
  ({ id, checked = false, onCheckedChange, disabled = false, className = '', size = 'default', variant = 'default', ...props }, ref) => {
    const handleClick = () => {
      if (!disabled && onCheckedChange) {
        onCheckedChange(!checked)
      }
    }

    return (
      <button
        ref={ref}
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={handleClick}
        className={`
          relative inline-flex ${trackSize[size]} shrink-0 cursor-pointer items-center rounded-full
          border-2 border-transparent transition-colors duration-200 ease-in-out
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-orange focus-visible:ring-offset-2 focus-visible:ring-offset-[#2a2a2a]
          disabled:cursor-not-allowed disabled:opacity-50
          ${checked ? checkedBg[variant] : 'bg-gray-600'}
          ${className}
        `}
        {...props}
      >
        <span
          className={`
            pointer-events-none inline-block ${knobSize[size]} transform rounded-full bg-white shadow-lg
            ring-0 transition duration-200 ease-in-out
            ${checked ? knobTranslate[size] : 'translate-x-0'}
          `}
        />
      </button>
    )
  }
)

Switch.displayName = 'Switch'

export { Switch }
