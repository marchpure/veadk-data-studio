import { createRoot, hydrateRoot } from "react-dom/client";
import posthog from "posthog-js";
import { PostHogProvider } from "@posthog/react";
import App from "./App.tsx";
import "./index.css";
import "./styles/landing.css";

if (typeof window !== "undefined" && import.meta.env.VITE_PUBLIC_POSTHOG_KEY) {
  posthog.init(import.meta.env.VITE_PUBLIC_POSTHOG_KEY, {
    api_host: import.meta.env.VITE_PUBLIC_POSTHOG_HOST || "https://us.i.posthog.com",
    defaults: "2026-01-30",
    persistence: "localStorage",
    autocapture: true,
    capture_pageview: "history_change",
    capture_pageleave: true,
    capture_performance: true,
    enable_heatmaps: true,
    person_profiles: "identified_only",
    session_recording: {
      maskAllInputs: true,
      maskTextSelector: "[data-private]",
    },
  });
  posthog.register({ app_surface: "web" });
}

const tree = (
  <PostHogProvider client={posthog}>
    <App />
  </PostHogProvider>
);

const root = document.getElementById("root")!;

if (root.children.length > 0) {
  hydrateRoot(root, tree);
} else {
  createRoot(root).render(tree);
}
