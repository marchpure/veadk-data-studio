import { isTauriApp } from '../lib/tauri-api'

const ACCESS_TOKEN_KEY = 'byaan_auth_token'
const REFRESH_TOKEN_KEY = 'byaan_refresh_token'

let accessToken: string | null = null

const readSessionToken = (): string | null => {
  if (typeof window === 'undefined' || !window.sessionStorage) return null
  return window.sessionStorage.getItem(ACCESS_TOKEN_KEY)
}

export const getAccessToken = (): string | null => {
  if (accessToken) return accessToken
  if (isTauriApp()) {
    accessToken = readSessionToken()
  }
  return accessToken
}

export const setAccessToken = (token: string | null): void => {
  accessToken = token
  if (!isTauriApp()) return
  if (typeof window === 'undefined' || !window.sessionStorage) return
  if (token) {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, token)
  } else {
    window.sessionStorage.removeItem(ACCESS_TOKEN_KEY)
  }
}

export const clearAccessToken = (): void => {
  accessToken = null
  if (typeof window === 'undefined' || !window.sessionStorage) return
  window.sessionStorage.removeItem(ACCESS_TOKEN_KEY)
}

const readSessionRefreshToken = (): string | null => {
  if (typeof window === 'undefined' || !window.sessionStorage) return null
  return window.sessionStorage.getItem(REFRESH_TOKEN_KEY)
}

export const getRefreshToken = (): string | null => {
  return readSessionRefreshToken()
}

export const setRefreshToken = (token: string | null): void => {
  if (typeof window === 'undefined' || !window.sessionStorage) return
  if (token) {
    window.sessionStorage.setItem(REFRESH_TOKEN_KEY, token)
  } else {
    window.sessionStorage.removeItem(REFRESH_TOKEN_KEY)
  }
}

export const clearRefreshToken = (): void => {
  if (typeof window === 'undefined' || !window.sessionStorage) return
  window.sessionStorage.removeItem(REFRESH_TOKEN_KEY)
}
