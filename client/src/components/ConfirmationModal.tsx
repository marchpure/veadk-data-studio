import React from 'react'
import { Loader2, Trash2 } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog'
import { Button } from './ui/button'

interface ConfirmationModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  message: React.ReactNode
  confirmText?: string
  cancelText?: string
  type?: 'danger' | 'warning' | 'info'
  loading?: boolean
}

export const ConfirmationModal: React.FC<ConfirmationModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  type = 'danger',
  loading = false
}) => {
  const handleConfirm = () => {
    if (!loading) {
      onConfirm()
    }
  }

  const getButtonStyles = () => {
    switch (type) {
      case 'danger':
        return 'bg-red-800 hover:bg-red-900'
      case 'warning':
        return 'bg-yellow-600 hover:bg-yellow-700'
      case 'info':
        return 'bg-blue-600 hover:bg-blue-700'
    }
  }

  const buttonStyles = getButtonStyles()

  return (
    <Dialog open={isOpen} onOpenChange={(open) => {
      if (!open && loading) return
      if (!open) onClose()
    }}>
      <DialogContent className="max-w-md bg-[#2a2a2a] border-[#444444]">
        <DialogHeader>
          <DialogTitle className="text-white">{title}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <p className="text-sm text-[#aaaaaa]">
            {message}
          </p>

          <div className="flex justify-end gap-2 mt-6">
            <Button
              variant="outline"
              onClick={onClose}
              disabled={loading}
              className="border-[#555555] text-white hover:bg-[#3a3a3a]"
            >
              {cancelText}
            </Button>
            <Button
              onClick={handleConfirm}
              disabled={loading}
              className={`${
                loading
                  ? 'bg-gray-500 cursor-not-allowed'
                  : buttonStyles
              } text-white flex items-center gap-2`}
            >
              {loading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : type === 'danger' ? (
                <Trash2 className="mr-2 h-4 w-4" />
              ) : null}
              {loading ? 'Deleting...' : confirmText}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}