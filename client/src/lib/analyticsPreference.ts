import posthog from 'posthog-js'

const ANALYTICS_OPT_OUT_KEY = 'byaan_posthog_opt_out'

export function isAnalyticsOptedOut(): boolean {
  try {
    return localStorage.getItem(ANALYTICS_OPT_OUT_KEY) === '1'
  } catch {
    return false
  }
}

function writeFlag(optedOut: boolean): void {
  try {
    if (optedOut) {
      localStorage.setItem(ANALYTICS_OPT_OUT_KEY, '1')
    } else {
      localStorage.removeItem(ANALYTICS_OPT_OUT_KEY)
    }
  } catch {
    // ignore localStorage failures (e.g. private mode)
  }
}

export function setAnalyticsOptedOut(optedOut: boolean): void {
  writeFlag(optedOut)
  applyAnalyticsPreference(optedOut)
  // Mirror to server (best-effort) so backend PostHog calls also stop.
  // Lazy import avoids circular dependency between api.ts and this module.
  void import('../services/api').then(({ ApiService }) => {
    ApiService.setAnalyticsOptOut(optedOut)
  })
}

export function applyAnalyticsPreference(optedOut: boolean): void {
  if (!posthog || typeof posthog.opt_out_capturing !== 'function') return
  if (optedOut) {
    posthog.opt_out_capturing()
  } else {
    posthog.opt_in_capturing()
  }
}

export async function syncAnalyticsPreferenceFromServer(): Promise<void> {
  try {
    const { ApiService } = await import('../services/api')
    const serverOptOut = await ApiService.getAnalyticsOptOut()
    writeFlag(serverOptOut)
    applyAnalyticsPreference(serverOptOut)
  } catch {
    // ignore — local flag remains source of truth on failure
  }
}
