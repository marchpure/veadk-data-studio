import React, { useState, useEffect } from 'react';
import { useStore } from '@/stores/useStore';
import { FileText, Edit2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export const InstructionsEditor: React.FC = () => {
  const { globalInstructions, updateInstructions, resetInstructionsToDefault } = useStore();
  const [isEditing, setIsEditing] = useState(false);
  const [content, setContent] = useState(globalInstructions);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setContent(globalInstructions);
  }, [globalInstructions]);

  const handleStartEditing = () => {
    setIsEditing(true);
    setError(null);
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);

    try {
      await updateInstructions(content);

      setTimeout(() => {
        setIsSaving(false);
        setIsEditing(false);
      }, 500);
    } catch (err) {
      setIsSaving(false);
      setError('Failed to save instructions. Please try again.');
      console.error('Error saving instructions:', err);
    }
  };

  const handleReset = async () => {
    if (!confirm('Are you sure you want to reset to default instructions? This cannot be undone.')) {
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      await resetInstructionsToDefault();

      setTimeout(() => {
        setIsSaving(false);
        setIsEditing(false);
      }, 500);
    } catch (err) {
      setIsSaving(false);
      setError('Failed to reset instructions. Please try again.');
      console.error('Error resetting instructions:', err);
    }
  };

  const handleCancel = () => {
    setContent(globalInstructions);
    setIsEditing(false);
    setError(null);
  };

  const charCount = content.length;

  return (
    <div className="space-y-4 relative pb-20">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-brand-orange/10 flex items-center justify-center">
          <FileText className="w-5 h-5 text-brand-orange" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white">Instructions</h3>
          <p className="text-xs text-gray-400">
            Your instructions and AI-remembered preferences, shared across all notebooks
          </p>
        </div>
      </div>

      <Card className="p-3 bg-blue-500/5 border-blue-500/20">
        <p className="text-xs text-blue-400">
          This is a shared space — you can write instructions here, and the AI also updates it to remember your preferences, patterns, and corrections across conversations.
        </p>
      </Card>

      {isEditing ? (
        <div className="space-y-3">
          <Card className="p-4 bg-[#0d0d0d] border-gray-800">
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="w-full h-[500px] bg-transparent text-sm text-gray-300 font-mono focus:outline-none resize-none custom-scrollbar"
              placeholder="# Instructions&#10;&#10;Write your instructions in Markdown format...&#10;&#10;## Example Section&#10;- Point 1&#10;- Point 2"
              autoFocus
            />
          </Card>

          <div className="flex items-center justify-between text-xs text-gray-500">
            <span>Supports Markdown formatting</span>
            <span>{charCount.toLocaleString()} characters</span>
          </div>
        </div>
      ) : (
        <Card
          onClick={handleStartEditing}
          className="p-6 bg-[#1a1a1a] border-gray-800 hover:border-gray-700 transition-colors cursor-pointer group relative"
        >
          <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
            <div className="flex items-center gap-1.5 px-2 py-1 bg-[#2a2a2a] border border-gray-700 rounded text-xs text-gray-400">
              <Edit2 className="w-3 h-3" />
              Click to edit
            </div>
          </div>

          <div className="prose prose-sm prose-invert max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h1: ({ children }) => (
                  <h1 className="text-xl font-bold text-white mb-4 mt-0">{children}</h1>
                ),
                h2: ({ children }) => (
                  <h2 className="text-lg font-semibold text-white mb-3 mt-6 first:mt-0">{children}</h2>
                ),
                h3: ({ children }) => (
                  <h3 className="text-base font-semibold text-white mb-2 mt-4">{children}</h3>
                ),
                p: ({ children }) => (
                  <p className="text-sm text-gray-300 mb-3 leading-relaxed">{children}</p>
                ),
                ul: ({ children }) => (
                  <ul className="list-disc list-outside text-sm text-gray-300 mb-3 space-y-1 pl-5">
                    {children}
                  </ul>
                ),
                ol: ({ children }) => (
                  <ol className="list-decimal list-outside text-sm text-gray-300 mb-3 space-y-1 pl-5">
                    {children}
                  </ol>
                ),
                li: ({ children }) => (
                  <li className="text-sm text-gray-300 ml-2">{children}</li>
                ),
                code: ({ children, className }) => {
                  const isInline = !className;
                  if (isInline) {
                    return (
                      <code className="px-1.5 py-0.5 bg-[#0d0d0d] text-brand-orange text-xs rounded font-mono">
                        {children}
                      </code>
                    );
                  }
                  return (
                    <pre className="p-3 bg-[#0d0d0d] rounded-lg overflow-x-auto mb-3">
                      <code className="text-xs text-gray-300 font-mono">{children}</code>
                    </pre>
                  );
                },
                strong: ({ children }) => (
                  <strong className="font-semibold text-white">{children}</strong>
                ),
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
        </Card>
      )}

      {error && (
        <Card className="p-3 bg-red-500/10 border-red-500/30">
          <p className="text-xs text-red-400">{error}</p>
        </Card>
      )}

      {isEditing && (
        <div className="fixed bottom-0 left-[35%] right-0 bg-[#1a1a1a] border-t border-gray-800 px-6 py-4 z-[60] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="text-xs text-gray-500">
              {charCount.toLocaleString()} characters
            </div>
            <div className="h-4 w-px bg-gray-700" />
            <div className="text-xs text-gray-400">
              Markdown formatting supported
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Button
              size="sm"
              variant="ghost"
              onClick={handleReset}
              disabled={isSaving}
              className="text-gray-400 hover:text-red-400"
            >
              Reset to Default
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={handleCancel}
              disabled={isSaving}
              className="text-gray-400 hover:text-white"
            >
              Cancel
            </Button>
            <Button
              size="sm"
              variant="brand-primary"
              onClick={handleSave}
              disabled={isSaving}
              className="gap-2 min-w-[100px]"
            >
              {isSaving ? (
                <>
                  <div className="animate-spin w-3 h-3 border border-white border-t-transparent rounded-full" />
                  Saving...
                </>
              ) : (
                'Save Changes'
              )}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};
