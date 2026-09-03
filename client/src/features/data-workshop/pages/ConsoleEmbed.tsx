import { ExternalLink, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { workshopApi } from '../api'
import { AsyncState } from '../components/AsyncState'
import type { LoadState } from '../types'

export function ConsoleEmbed({ title, consolePath }: { title: string; consolePath: string }) {
  const [state, setState] = useState<LoadState>('loading')
  const [launchUrl, setLaunchUrl] = useState('')
  const load = useCallback(async () => {
    setState('loading')
    try {
      const session = await workshopApi.createLaunchSession()
      const proxyRoot = session.launch_url.split('?')[0]
      const separator = consolePath.includes('?') ? '&' : '?'
      setLaunchUrl(`${proxyRoot}${consolePath}${separator}embed=studio`)
      setState('ready')
    } catch {
      setState('error')
    }
  }, [consolePath])
  useEffect(() => { void load() }, [load])

  return <div className="dw-page dw-console-page">
    <div className="dw-page-heading dw-heading-row"><div><span className="dw-eyebrow">OpenConnector Console</span><h1>{title}</h1><p>通过短期 HttpOnly 会话加载，管理凭据不会进入浏览器地址或存储。</p></div>{launchUrl && <a className="dw-button dw-button-secondary" href={launchUrl}><ExternalLink size={16} />新窗口打开</a>}</div>
    {state === 'ready' ? <div className="dw-console-frame"><iframe title={`OpenConnector ${title}`} src={launchUrl} onError={() => setState('error')} /></div> : <AsyncState state={state === 'empty' ? 'error' : state} message="无法建立 OpenConnector Console 会话，请检查服务配置。" onRetry={load} />}
    {state === 'ready' && <button className="dw-icon-text dw-console-refresh" onClick={() => void load()}><RefreshCw size={15} />刷新会话</button>}
  </div>
}

export function NewConnectionEmbed() {
  const { providerId = 'oracle' } = useParams()
  const providerName = providerId === 'oracle' ? 'Oracle' : providerId
  return <ConsoleEmbed title={`新建 ${providerName} 连接`} consolePath={`connections/new?provider=${encodeURIComponent(providerId)}`} />
}
