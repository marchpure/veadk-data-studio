import { createContext, useContext, useState, type ReactNode } from 'react'

interface SidebarContextType {
  triggerSidebar: () => void
  untriggerSidebar: () => void
  isSidebarTriggered: boolean
}

const SidebarContext = createContext<SidebarContextType | undefined>(undefined)

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [isSidebarTriggered, setIsSidebarTriggered] = useState(false)

  const triggerSidebar = () => {
    setIsSidebarTriggered(true)
  }

  const untriggerSidebar = () => {
    setIsSidebarTriggered(false)
  }

  return (
    <SidebarContext.Provider value={{ triggerSidebar, untriggerSidebar, isSidebarTriggered }}>
      {children}
    </SidebarContext.Provider>
  )
}

export function useSidebar() {
  const context = useContext(SidebarContext)
  if (context === undefined) {
    throw new Error('useSidebar must be used within a SidebarProvider')
  }
  return context
}
