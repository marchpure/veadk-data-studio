import React from 'react';
import { useStore } from '@/stores/useStore';
import { X, Database, FileText, Palette, Brain, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { DatabaseUnderstandingSection } from '../DatabaseUnderstandingSection';
import { InstructionsEditor } from '../InstructionsEditor';
import { StyleGuidelinesEditor } from '../StyleGuidelinesEditor';
import { SkillsSection } from '../SkillsSection';

export const ConceptC_VerticalPillNav: React.FC = () => {
  const { isSidebarOpen, closeSidebar, activeSection, setActiveSection, databaseContext } = useStore();

  if (!isSidebarOpen) return null;

  const navItems = [
    {
      id: 'instructions' as const,
      label: 'Instructions',
      description: 'Query guidelines',
      icon: FileText,
      count: null,
      color: 'text-blue-400',
      bgColor: 'bg-blue-500/10',
      borderColor: 'border-blue-500/30',
    },
    {
      id: 'skills' as const,
      label: 'Skills',
      description: 'Custom capabilities',
      icon: Zap,
      count: null,
      color: 'text-yellow-400',
      bgColor: 'bg-yellow-500/10',
      borderColor: 'border-yellow-500/30',
    },
    {
      id: 'style' as const,
      label: 'Style Guide',
      description: 'Brand & design',
      icon: Palette,
      count: null,
      color: 'text-pink-400',
      bgColor: 'bg-pink-500/10',
      borderColor: 'border-pink-500/30',
    },
    {
      id: 'database' as const,
      label: 'Datasources',
      description: 'Schema & tables',
      icon: Database,
      count: databaseContext.reduce((sum, db) => sum + db.tables.length, 0),
      color: 'text-brand-orange',
      bgColor: 'bg-brand-orange/10',
      borderColor: 'border-brand-orange/30',
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
      <div className="fixed right-0 top-0 h-full w-[65%] min-w-[800px] max-w-[1300px] bg-[#0d0d0d] border-l border-gray-800 z-50 flex flex-col animate-slide-in-right">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-orange to-brand-pink flex items-center justify-center">
              <Brain className="w-4 h-4 text-white" />
            </div>
            <h2 className="text-lg font-semibold text-white">Context</h2>
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

        {/* Main Content - Split Layout */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Navigation */}
          <div className="w-48 border-r border-gray-800 bg-[#1a1a1a]/30 p-3 space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeSection === item.id;

              return (
                <button
                  key={item.id}
                  onClick={() => setActiveSection(item.id)}
                  className={`
                    w-full flex items-start gap-3 px-3 py-2.5 rounded-lg transition-all group
                    ${
                      isActive
                        ? `${item.bgColor} border ${item.borderColor} shadow-sm`
                        : 'hover:bg-[#2a2a2a] border border-transparent'
                    }
                  `}
                >
                  <div
                    className={`
                      w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0
                      ${isActive ? item.bgColor : 'bg-[#2a2a2a]'}
                    `}
                  >
                    <Icon className={`w-4 h-4 ${isActive ? item.color : 'text-gray-400'}`} />
                  </div>

                  <div className="flex-1 text-left min-w-0">
                    <div className="flex items-center justify-between gap-2 mb-0.5">
                      <span
                        className={`text-sm font-medium ${isActive ? 'text-white' : 'text-gray-400 group-hover:text-white'}`}
                      >
                        {item.label}
                      </span>
                      {item.count !== null && (
                        <Badge
                          variant="outline"
                          className={`text-[9px] px-1.5 py-0 h-4 ${isActive ? item.borderColor : 'border-gray-700'}`}
                        >
                          {item.count}
                        </Badge>
                      )}
                    </div>
                    <p className="text-[10px] text-gray-500">{item.description}</p>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Right Content Area */}
          <div className="flex-1 overflow-y-auto custom-scrollbar">
            <div className="p-6">
              {activeSection === 'instructions' && <InstructionsEditor />}
              {activeSection === 'skills' && <SkillsSection />}
              {activeSection === 'style' && <StyleGuidelinesEditor />}
              {activeSection === 'database' && <DatabaseUnderstandingSection />}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-800 bg-[#1a1a1a]/50">
          <p className="text-xs text-gray-500 text-center">
            Changes are saved automatically
          </p>
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

        .animate-slide-in-right {
          animation: slide-in-right 0.3s ease-out;
        }
      `}</style>
    </>
  );
};
