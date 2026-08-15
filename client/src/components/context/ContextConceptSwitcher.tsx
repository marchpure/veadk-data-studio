import React, { useState } from 'react';
import { ConceptA_TabbedInterface } from './concepts/ConceptA_TabbedInterface';
import { ConceptB_AccordionSections } from './concepts/ConceptB_AccordionSections';
import { ConceptC_VerticalPillNav } from './concepts/ConceptC_VerticalPillNav';
import { useStore } from '@/stores/useStore';

type ConceptType = 'A' | 'B' | 'C';

export const LearningConceptSwitcher: React.FC = () => {
  const { isSidebarOpen } = useStore();
  const [activeConcept, setActiveConcept] = useState<ConceptType>('A');

  if (!isSidebarOpen) return null;

  return (
    <>
      {activeConcept === 'A' && <ConceptA_TabbedInterface />}
      {activeConcept === 'B' && <ConceptB_AccordionSections />}
      {activeConcept === 'C' && <ConceptC_VerticalPillNav />}

      <div className="fixed bottom-6 right-[calc(65%+20px)] z-[60] bg-[#2a2a2a] border border-gray-700 rounded-lg p-3 shadow-2xl">
        <div className="text-xs text-gray-400 mb-2 font-semibold">Design Concept</div>
        <div className="flex gap-2">
          <button
            onClick={() => setActiveConcept('A')}
            className={`px-3 py-1.5 text-xs rounded transition-all ${
              activeConcept === 'A'
                ? 'bg-brand-orange text-white shadow-glow-orange'
                : 'bg-[#1a1a1a] text-gray-400 hover:text-white'
            }`}
          >
            A: Tabs
          </button>
          <button
            onClick={() => setActiveConcept('B')}
            className={`px-3 py-1.5 text-xs rounded transition-all ${
              activeConcept === 'B'
                ? 'bg-brand-orange text-white shadow-glow-orange'
                : 'bg-[#1a1a1a] text-gray-400 hover:text-white'
            }`}
          >
            B: Accordion
          </button>
          <button
            onClick={() => setActiveConcept('C')}
            className={`px-3 py-1.5 text-xs rounded transition-all ${
              activeConcept === 'C'
                ? 'bg-brand-orange text-white shadow-glow-orange'
                : 'bg-[#1a1a1a] text-gray-400 hover:text-white'
            }`}
          >
            C: Pills
          </button>
        </div>
      </div>

      <style>{`
        .shadow-glow-orange {
          box-shadow: 0 0 20px rgba(255, 107, 53, 0.3);
        }
      `}</style>
    </>
  );
};
