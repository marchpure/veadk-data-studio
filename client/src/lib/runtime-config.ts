declare global {
  interface Window {
    __RUNTIME_CONFIG__?: {
      apiUrl?: string
      isHosted?: boolean
      isSelfHosted?: boolean
      orgName?: string
      googleClientId?: string
    }
  }
}

export interface RuntimeConfig {
  apiUrl: string
  isHosted: boolean
  isSelfHosted: boolean
  orgName: string
  googleClientId: string
}

function getRuntimeConfig(): RuntimeConfig {
  const runtimeConfig = window.__RUNTIME_CONFIG__ || {}

  const isHosted = runtimeConfig.isHosted ?? (import.meta.env.VITE_IS_HOSTED === 'true')
  const isSelfHosted = runtimeConfig.isSelfHosted ?? (import.meta.env.VITE_IS_SELF_HOSTED === 'true')

  const apiUrl = runtimeConfig.apiUrl ?? ''

  return {
    apiUrl,
    isHosted,
    isSelfHosted,
    orgName: runtimeConfig.orgName ?? 'Byaan',
    googleClientId: runtimeConfig.googleClientId ?? import.meta.env.VITE_GOOGLE_CLIENT_ID ?? ''
  }
}

const config = getRuntimeConfig()

export const getApiBaseUrl = (): string => {
  return config.apiUrl ? `${config.apiUrl}/api` : '/api'
}

export const isHostedMode = (): boolean => {
  return window.__RUNTIME_CONFIG__?.isHosted ?? config.isHosted
}

export const isSelfHostedMode = (): boolean => {
  return window.__RUNTIME_CONFIG__?.isSelfHosted ?? config.isSelfHosted
}

export const getOrgName = (): string => {
  return config.orgName
}

export const getGoogleClientId = (): string => {
  return config.googleClientId
}

export default config
