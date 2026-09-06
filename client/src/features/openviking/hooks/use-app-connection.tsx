import * as React from 'react'
import { DISCONNECTED_OPENVIKING_SCOPE } from '../profile-selection'

export type OpenVikingProfile = {
  api_key_configured?: boolean
  api_key_masked?: string
  created_at: string | number
  credential_mode?: 'managed' | 'byok'
  display_name: string
  last_validated_at?: string | number | null
  profile_id: string
  root_resource_ref: string
  status: 'pending' | 'ready' | 'error'
  updated_at: string | number
  workspace_uri: string
}

type AppConnectionContextValue = {
  activeProfile: OpenVikingProfile | null
  identityScopeKey: string
}

const AppConnectionContext =
  React.createContext<AppConnectionContextValue | null>(null)

let activeProfileId = ''

export function getActiveOpenVikingProfileId(): string {
  return activeProfileId
}

export function setActiveOpenVikingProfileId(profileId: string): void {
  activeProfileId = profileId
}

export function AppConnectionProvider({
  children,
  profile,
}: {
  children: React.ReactNode
  profile: OpenVikingProfile | null
}) {
  React.useLayoutEffect(() => {
    setActiveOpenVikingProfileId(profile?.profile_id ?? '')
    return () => {
      setActiveOpenVikingProfileId('')
    }
  }, [profile])

  return (
    <AppConnectionContext.Provider
      value={{
        activeProfile: profile,
        identityScopeKey:
          profile?.profile_id ?? DISCONNECTED_OPENVIKING_SCOPE,
      }}
    >
      {children}
    </AppConnectionContext.Provider>
  )
}

export function useAppConnection(): AppConnectionContextValue {
  const value = React.useContext(AppConnectionContext)
  if (!value) {
    throw new Error(
      'useAppConnection must be used within AppConnectionProvider.',
    )
  }
  return value
}

export function useOpenVikingIdentityScopeKey(): string {
  const value = React.useContext(AppConnectionContext)
  return (
    value?.identityScopeKey ||
    getActiveOpenVikingProfileId() ||
    DISCONNECTED_OPENVIKING_SCOPE
  )
}
