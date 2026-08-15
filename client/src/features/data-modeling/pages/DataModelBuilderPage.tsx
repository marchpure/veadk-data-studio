import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, GitCompare, Rocket } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { StatusPill } from '../components/modelingUi'
import { SemanticExploreWorkspace } from '../explore/SemanticExploreWorkspace'
import { SemanticGraphWorkspace } from '../model/SemanticGraphWorkspace'
import { PublishWorkspace } from '../publish/PublishWorkspace'
import { selectActiveModel, useDataModelingStore } from '../store/useDataModelingStore'
import type { WorkspaceMode } from '../types'

const modeLabels: Array<{ id: WorkspaceMode; label: string }> = [
  { id: 'explore', label: 'Explore' },
  { id: 'model', label: 'Model' },
  { id: 'publish', label: 'Publish' },
]

export default function DataModelBuilderPage() {
  const params = useParams()
  const model = useDataModelingStore(selectActiveModel)
  const activeModelId = useDataModelingStore(state => state.activeModelId)
  const setActiveModel = useDataModelingStore(state => state.setActiveModel)
  const workspaceMode = useDataModelingStore(state => state.workspaceMode)
  const setWorkspaceMode = useDataModelingStore(state => state.setWorkspaceMode)
  const openReview = useDataModelingStore(state => state.openReview)

  useEffect(() => {
    if (params.modelId && params.modelId !== activeModelId) {
      setActiveModel(params.modelId)
    }
  }, [params.modelId, activeModelId, setActiveModel])

  const reviewModel = () => {
    openReview()
    setWorkspaceMode('model')
  }

  const openPublish = () => {
    openReview()
    setWorkspaceMode('publish')
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#171717] text-white">
      <header className="shrink-0 border-b border-[#2a2a2a] bg-[#1a1a1a]">
        <div className="flex flex-col gap-3 px-4 py-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Button asChild size="sm" variant="ghost"><Link to="/data-models"><ArrowLeft className="h-4 w-4" /> Models</Link></Button>
              <h1 className="truncate text-lg font-semibold text-white">{model.name}</h1>
              <StatusPill tone={model.status === 'Published' ? 'ready' : 'warning'}>{model.status}</StatusPill>
              <StatusPill>{model.draftRevision}</StatusPill>
              <StatusPill tone="info">{model.publishedVersion}</StatusPill>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-[#9a9a9a]">
              <span>Fresh 2h ago</span>
              <span>{model.datasource}</span>
              <span>AI generated</span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={reviewModel}><GitCompare className="h-4 w-4" /> Review model</Button>
            <Button variant="brand-primary" onClick={openPublish}><Rocket className="h-4 w-4" /> Publish</Button>
          </div>
        </div>
        <div className="flex gap-1 overflow-x-auto border-t border-[#2a2a2a] px-4 py-2 custom-scrollbar">
          {modeLabels.map(mode => (
            <button
              key={mode.id}
              type="button"
              onClick={() => setWorkspaceMode(mode.id)}
              className={`rounded-md px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring ${
                workspaceMode === mode.id ? 'bg-brand-orange text-white' : 'text-[#bdbdbd] hover:bg-[#262626]'
              }`}
              aria-pressed={workspaceMode === mode.id}
            >
              {mode.label}
            </button>
          ))}
        </div>
      </header>

      {workspaceMode === 'explore' && <SemanticExploreWorkspace model={model} onReviewModel={reviewModel} />}
      {workspaceMode === 'model' && <SemanticGraphWorkspace model={model} />}
      {workspaceMode === 'publish' && <PublishWorkspace model={model} />}

      <footer className="shrink-0 border-t border-[#2a2a2a] bg-[#1a1a1a] px-4 py-2">
        <div className="flex flex-wrap items-center gap-2 text-xs text-[#9a9a9a]">
          <span className="text-[#d0d0d0]">Agent activity</span>
          {model.validationLog.slice(0, 4).map((item, index) => <StatusPill key={`${index}-${item}`}>{item}</StatusPill>)}
        </div>
      </footer>
    </div>
  )
}
