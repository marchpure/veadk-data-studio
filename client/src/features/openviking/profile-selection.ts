import type { OpenVikingProfile } from './hooks/use-app-connection'

export const ACTIVE_OPENVIKING_PROFILE_KEY = 'openviking.activeProfileId'
export const DISCONNECTED_OPENVIKING_SCOPE = 'openviking-disconnected'

export function profileScopedQueryKey(
  name: string,
  identityScopeKey: string,
  ...parts: unknown[]
): unknown[] {
  return identityScopeKey === DISCONNECTED_OPENVIKING_SCOPE
    ? [name, ...parts]
    : [name, identityScopeKey, ...parts]
}

export function selectReadyProfileId(
  profiles: OpenVikingProfile[],
  currentProfileId: string,
): string {
  const current = profiles.find(
    (profile) =>
      profile.profile_id === currentProfileId && profile.status === 'ready',
  )
  return current?.profile_id ?? profiles.find((profile) => profile.status === 'ready')?.profile_id ?? ''
}
