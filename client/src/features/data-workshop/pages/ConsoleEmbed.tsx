import { useParams } from 'react-router-dom'
import {
  OpenConnectorSurface,
  type OpenConnectorSurfaceKey,
} from './OpenConnectorSurface'

const legacySurfaceByPath: Record<string, OpenConnectorSurfaceKey> = {
  actions: 'actions',
  traces: 'runs',
  access: 'access',
}

/**
 * Compatibility adapter for the frozen RC router.
 *
 * Integration should route directly to OpenConnectorSurface and remove this
 * free-form consolePath API. Unsupported legacy paths deliberately land on the
 * providers surface instead of requesting a non-existent OpenConnector route.
 */
export function ConsoleEmbed({ title, consolePath }: { title: string; consolePath: string }) {
  const surface = legacySurfaceByPath[consolePath.split('?')[0]] ?? 'providers'
  return <OpenConnectorSurface surface={surface} title={title} />
}

export function NewConnectionEmbed() {
  const { providerId = 'oracle' } = useParams()
  const providerName = providerId === 'oracle' ? 'Oracle' : providerId
  return <OpenConnectorSurface surface="providers" title={`新建 ${providerName} 连接`} />
}
