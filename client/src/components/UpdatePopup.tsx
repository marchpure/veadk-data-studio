import React, { useState, useEffect } from 'react';
import { Download, X, Loader2 } from 'lucide-react';

interface UpdatePopupProps {
  isOpen: boolean;
  version: string;
  notes?: string;
  downloading: boolean;
  onInstall: () => void;
  onDismiss: () => void;
}

export const UpdatePopup: React.FC<UpdatePopupProps> = ({
  isOpen,
  version,
  downloading,
  onInstall,
  onDismiss,
}) => {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (isOpen) {
      // Trigger slide-in animation
      setIsVisible(true);
    } else {
      setIsVisible(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[10000] pointer-events-none">
      <div className="pointer-events-auto">
        <div
          className={`
            transform transition-all duration-300 ease-out
            ${isVisible ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0'}
          `}
        >
          <div className="bg-[#1a1a1a] border border-gray-800 rounded-lg shadow-lg p-4 min-w-[320px] max-w-[380px]">
            <div className="flex items-start gap-3">
              {/* Update Icon */}
              <div className="flex-shrink-0 mt-0.5">
                <Download className="w-5 h-5 text-orange-500" />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white mb-2.5">
                  New update <span className="font-semibold text-orange-500">v{version}</span> available
                </p>

                {/* Action Button */}
                {downloading ? (
                  <div className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded bg-gray-700 text-gray-300">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Installing...</span>
                  </div>
                ) : (
                  <button
                    onClick={onInstall}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded transition-colors bg-orange-600 hover:bg-orange-700 text-white"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Update Now</span>
                  </button>
                )}
              </div>

              {/* Close Button - Hidden when downloading */}
              {!downloading && (
                <button
                  onClick={onDismiss}
                  className="flex-shrink-0 text-gray-400 hover:text-white transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
