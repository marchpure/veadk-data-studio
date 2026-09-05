const resourceRefs = new Map<string, string>()

export function getOpenVikingResourceRef(uri: string): string | undefined {
  const value = uri.trim()
  return (
    resourceRefs.get(value) ??
    resourceRefs.get(value.endsWith('/') ? value.slice(0, -1) : `${value}/`)
  )
}

export function registerOpenVikingRoot(uri: string, ref: string): void {
  resourceRefs.set(uri, ref)
  if (uri.startsWith('viking://') && uri !== 'viking://') {
    const withoutSlash = uri.endsWith('/') ? uri.slice(0, -1) : uri
    resourceRefs.set(withoutSlash, ref)
    resourceRefs.set(`${withoutSlash}/`, ref)
  }
}
