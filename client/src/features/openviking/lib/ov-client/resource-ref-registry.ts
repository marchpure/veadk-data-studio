import { getActiveOpenVikingProfileId } from '../../hooks/use-app-connection'

const resourceRefs = new Map<string, string>()

function scopedKey(uri: string, profileId?: string): string {
  return `${profileId ?? getActiveOpenVikingProfileId()}:${uri}`
}

export function getOpenVikingResourceRef(uri: string): string | undefined {
  const value = uri.trim()
  return (
    resourceRefs.get(scopedKey(value)) ??
    resourceRefs.get(
      scopedKey(value.endsWith('/') ? value.slice(0, -1) : `${value}/`),
    )
  )
}

export function registerOpenVikingRoot(
  uri: string,
  ref: string,
  profileId?: string,
): void {
  resourceRefs.set(scopedKey(uri, profileId), ref)
  if (uri.startsWith('viking://') && uri !== 'viking://') {
    const withoutSlash = uri.endsWith('/') ? uri.slice(0, -1) : uri
    resourceRefs.set(scopedKey(withoutSlash, profileId), ref)
    resourceRefs.set(scopedKey(`${withoutSlash}/`, profileId), ref)
  }
}

export function clearOpenVikingResourceRefs(): void {
  resourceRefs.clear()
}
