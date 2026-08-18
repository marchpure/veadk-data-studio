import React from 'react';
import { ConceptA_TabbedInterface } from './concepts/ConceptA_TabbedInterface';

export const ContextSidebar: React.FC = () => {
  return (
    <div data-testid="context-sidebar">
      <ConceptA_TabbedInterface />
    </div>
  );
};
