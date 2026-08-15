import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Index from "./pages/Index";
import Documentation from "./pages/Documentation";
import Privacy from "./pages/Privacy";
import Share from "./pages/Share";
import NotebookLink from "./pages/NotebookLink";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Index />} />
      <Route path="/docs" element={<Documentation />} />
      <Route path="/privacy" element={<Privacy />} />
      <Route path="/share/:id" element={<Share />} />
      <Route path="/n/:id" element={<NotebookLink />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        {children}
      </TooltipProvider>
    </QueryClientProvider>
  );
}

const App = () => (
  <AppShell>
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  </AppShell>
);

export default App;
