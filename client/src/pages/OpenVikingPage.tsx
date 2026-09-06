import { OpenVikingWorkspace } from '../features/openviking/OpenVikingWorkspace'
import { useAppConfig } from '../hooks/useAppConfig'

export default function OpenVikingPage() {
  const { openVikingCredentialPolicy } = useAppConfig()
  return <OpenVikingWorkspace credentialPolicy={openVikingCredentialPolicy} />
}
