import React, { useEffect, useState } from 'react';
import { useStore } from '@/stores/useStore';
import { BookOpen, Trash2, Tag, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { ConfirmationModal } from '@/components/ConfirmationModal';

export const LearningsViewer: React.FC = () => {
  const { learnings, isLoadingLearnings, loadLearnings, deleteLearning } = useStore();
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    loadLearnings();
  }, [loadLearnings]);

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await deleteLearning(deleteTarget.id);
    } catch {
      // error handled in store
    } finally {
      setIsDeleting(false);
      setDeleteTarget(null);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
          <BookOpen className="w-5 h-5 text-emerald-400" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white">Learnings</h3>
          <p className="text-xs text-gray-400">
            Patterns and insights discovered by the AI, shared across all team members
          </p>
        </div>
      </div>

      <Card className="p-3 bg-emerald-500/5 border-emerald-500/20">
        <p className="text-xs text-emerald-400">
          Learnings are automatically saved when the AI discovers data patterns, fixes query errors, or finds schema quirks. They are injected into future conversations to avoid repeating mistakes.
        </p>
      </Card>

      {isLoadingLearnings ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin w-5 h-5 border-2 border-emerald-400 border-t-transparent rounded-full" />
          <span className="ml-3 text-sm text-gray-400">Loading learnings...</span>
        </div>
      ) : learnings.length === 0 ? (
        <Card className="p-8 bg-[#1a1a1a] border-gray-800 text-center">
          <BookOpen className="w-8 h-8 text-gray-600 mx-auto mb-3" />
          <p className="text-sm text-gray-400 mb-1">No learnings yet</p>
          <p className="text-xs text-gray-500">
            The AI will save learnings here as it discovers patterns, fixes errors, and learns from your data.
          </p>
        </Card>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">{learnings.length} learning{learnings.length !== 1 ? 's' : ''}</span>
          </div>

          {learnings.map((item) => (
            <Card key={item.id} className="p-4 bg-[#1a1a1a] border-gray-800 hover:border-gray-700 transition-colors group">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <h4 className="text-sm font-medium text-white mb-1 truncate">{item.title}</h4>
                  <p className="text-xs text-gray-300 leading-relaxed">{item.learning}</p>

                  {item.context && (
                    <p className="text-xs text-gray-500 mt-2 italic">Context: {item.context}</p>
                  )}

                  <div className="flex items-center gap-3 mt-2">
                    {item.tags && (
                      <div className="flex items-center gap-1">
                        <Tag className="w-3 h-3 text-gray-500" />
                        <span className="text-xs text-gray-500">{item.tags}</span>
                      </div>
                    )}
                    {item.updated_at && (
                      <div className="flex items-center gap-1">
                        <Clock className="w-3 h-3 text-gray-600" />
                        <span className="text-xs text-gray-600">{formatDate(item.updated_at)}</span>
                      </div>
                    )}
                  </div>
                </div>

                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setDeleteTarget({ id: item.id, title: item.title })}
                  className="h-7 w-7 p-0 text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <ConfirmationModal
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDeleteConfirm}
        title="Delete Learning?"
        message={<>This will permanently delete <span className="font-semibold text-white">"{deleteTarget?.title}"</span>. This cannot be undone.</>}
        confirmText="Delete"
        type="danger"
        loading={isDeleting}
      />
    </div>
  );
};
