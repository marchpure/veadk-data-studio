export interface AppConfig {
  posthog?: {
    api_key: string | null;
    host: string;
  };
}

let configCache: AppConfig | null = null;

// Check if running in Tauri without importing any modules
function isTauriContext(): boolean {
  return (
    typeof window !== "undefined" && typeof window.__TAURI__ !== "undefined"
  );
}

export async function loadConfig(): Promise<AppConfig> {
  if (configCache) {
    return configCache;
  }

  const inTauri = isTauriContext();

  // Only import Tauri modules if we're actually running in Tauri
  if (inTauri) {
    try {
      const { readTextFile, BaseDirectory } = await import('@tauri-apps/plugin-fs');
      const configText = await readTextFile('config.json', { baseDir: BaseDirectory.Resource });
      const config = JSON.parse(configText) as AppConfig;

      console.log('Configuration loaded from config.json:', {
        hasPostHogKey: !!config.posthog?.api_key,
        postHogHost: config.posthog?.host,
      });

      configCache = config;
      return config;
    } catch (error) {
      console.warn('Failed to load config.json from Tauri resources:', error);
    }
  }

  const fallbackConfig: AppConfig = {
    posthog: {
      api_key: import.meta.env.VITE_PUBLIC_POSTHOG_KEY || null,
      host: import.meta.env.VITE_PUBLIC_POSTHOG_HOST || 'https://us.i.posthog.com',
    },
  };

  console.log('Using fallback configuration from build-time env vars:', {
    hasPostHogKey: !!fallbackConfig.posthog?.api_key,
    postHogHost: fallbackConfig.posthog?.host,
  });

  configCache = fallbackConfig;
  return fallbackConfig;
}

export function isDevMode(): boolean {
  return import.meta.env.VITE_DEV_MODE === 'true';
}

export async function getPostHogConfig() {
  // Disable PostHog in dev mode
  if (isDevMode()) {
    console.log('PostHog disabled in dev mode (VITE_DEV_MODE=true)');
    return { api_key: null, host: 'https://us.i.posthog.com' };
  }

  const config = await loadConfig();
  return config.posthog || { api_key: null, host: 'https://us.i.posthog.com' };
}
