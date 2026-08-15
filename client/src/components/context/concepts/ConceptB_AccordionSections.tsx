import React, { useState } from 'react';
import { useStore } from '@/stores/useStore';
import { X, Database, FileText, Palette, Brain, ChevronDown, ChevronRight, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { DatabaseUnderstandingSection } from '../DatabaseUnderstandingSection';
import { InstructionsEditor } from '../InstructionsEditor';
import { StyleGuidelinesEditor } from '../StyleGuidelinesEditor';
import { SkillsSection } from '../SkillsSection';

export const ConceptB_AccordionSections: React.FC = () => {
  const { isSidebarOpen, closeSidebar, databaseContext } = useStore();
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['instructions']));

  if (!isSidebarOpen) return null;

  const toggleSection = (sectionId: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(sectionId)) {
      newExpanded.delete(sectionId);
    } else {
      newExpanded.add(sectionId);
    }
    setExpandedSections(newExpanded);
  };

  const sections = [
    {
      id: 'instructions',
      label: 'Global Instructions',
      icon: FileText,
      count: null,
      countLabel: null,
      color: 'text-blue-400',
      bgColor: 'bg-blue-500/10',
      component: <InstructionsEditor />,
    },
    {
      id: 'skills',
      label: 'Skills',
      icon: Zap,
      count: null,
      countLabel: null,
      color: 'text-yellow-400',
      bgColor: 'bg-yellow-500/10',
      component: <SkillsSection />,
    },
    {
      id: 'style',
      label: 'Style & Brand Guidelines',
      icon: Palette,
      count: null,
      countLabel: null,
      color: 'text-pink-400',
      bgColor: 'bg-pink-500/10',
      component: <StyleGuidelinesEditor />,
    },
    {
      id: 'database',
      label: 'Datasource Understanding',
      icon: Database,
      count: databaseContext.reduce((sum, db) => sum + db.tables.length, 0),
      countLabel: 'tables',
      color: 'text-brand-orange',
      bgColor: 'bg-brand-orange/10',
      component: <DatabaseUnderstandingSection />,
    },
  ];

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 transition-opacity duration-300"
        onClick={closeSidebar}
      />

      {/* Sidebar Panel */}
      <div className="fixed right-0 top-0 h-full w-[65%] min-w-[700px] max-w-[1200px] bg-[#0d0d0d] border-l border-gray-800 z-50 flex flex-col animate-slide-in-right">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-orange to-brand-pink flex items-center justify-center">
              <Brain className="w-4 h-4 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">Context</h2>
              <p className="text-xs text-gray-400">Manage AI knowledge and preferences</p>
            </div>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={closeSidebar}
            className="h-8 w-8 p-0 text-gray-400 hover:text-white"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Accordion Content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          <div className="p-4 space-y-3">
            {sections.map((section) => {
              const Icon = section.icon;
              const isExpanded = expandedSections.has(section.id);

              return (
                <div
                  key={section.id}
                  className="border border-gray-800 rounded-lg overflow-hidden bg-[#1a1a1a] transition-all"
                >
                  {/* Section Header */}
                  <button
                    onClick={() => toggleSection(section.id)}
                    className="w-full flex items-center justify-between p-4 hover:bg-[#2a2a2a] transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-lg ${section.bgColor} flex items-center justify-center`}>
                        <Icon className={`w-4 h-4 ${section.color}`} />
                      </div>
                      <div className="text-left">
                        <h3 className="text-sm font-semibold text-white">{section.label}</h3>
                        {section.count !== null && (
                          <p className="text-xs text-gray-400">
                            {section.count} {section.countLabel}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {section.count !== null && (
                        <Badge variant="outline" className="text-[10px] px-2 py-0.5 border-gray-700">
                          {section.count}
                        </Badge>
                      )}
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-gray-400" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-gray-400" />
                      )}
                    </div>
                  </button>

                  {/* Section Content */}
                  {isExpanded && (
                    <div className="px-4 pb-4 pt-2 border-t border-gray-800 animate-fade-in">
                      {section.component}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-800 bg-[#1a1a1a]/50">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500">Changes are saved automatically</span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setExpandedSections(new Set(['instructions', 'skills', 'style', 'database']))}
              className="h-6 text-xs text-brand-orange hover:text-brand-orange"
            >
              Expand All
            </Button>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes slide-in-right {
          from {
            transform: translateX(100%);
          }
          to {
            transform: translateX(0);
          }
        }

        @keyframes fade-in {
          from {
            opacity: 0;
            transform: translateY(-8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .animate-slide-in-right {
          animation: slide-in-right 0.3s ease-out;
        }

        .animate-fade-in {
          animation: fade-in 0.2s ease-out;
        }
      `}</style>
    </>
  );
};
