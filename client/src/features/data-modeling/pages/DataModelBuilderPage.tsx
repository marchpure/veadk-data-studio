import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Bot, Database, GitCompare, Rocket, ShieldCheck } from 'lucide-react'
import { Button } from '../../../components/ui/button'
import { EmptyState, StatusPill, modelingStyles } from '../components/modelingUi'
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
  const loadModel = useDataModelingStore(state => state.loadModel)
  const workspaceMode = useDataModelingStore(state => state.workspaceMode)
  const setWorkspaceMode = useDataModelingStore(state => state.setWorkspaceMode)
  const openReview = useDataModelingStore(state => state.openReview)

  useEffect(() => {
    if (params.modelId && params.modelId !== activeModelId) {
      setActiveModel(params.modelId)
      void loadModel(params.modelId)
    }
  }, [params.modelId, activeModelId, setActiveModel, loadModel])

  const reviewModel = () => {
    openReview()
    setWorkspaceMode('model')
  }

  const openPublish = () => {
    openReview()
    setWorkspaceMode('publish')
  }

  if (!model?.id) {
    return (
      <div className={`flex h-full min-h-0 flex-col p-4 ${modelingStyles.page}`}>
        <EmptyState title="Loading Data Model" body="The Semantic Model is being loaded from the backend. Return to the model list if this ID no longer exists." action={<Button asChild variant="secondary"><Link to="/data-models">Back to models</Link></Button>} />
      </div>
    )
  }

  return (
    <div className={`flex h-full min-h-0 flex-col ${modelingStyles.page}`}>
      <header className="shrink-0 border-b border-[#30363a] bg-[#14181b]">
        <div className="grid gap-3 px-4 py-3 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <Button asChild size="sm" variant="ghost" className="shrink-0"><Link to="/data-models"><ArrowLeft className="h-4 w-4" /> Models</Link></Button>
              <div className="min-w-0">
                <h1 className="truncate text-lg font-semibold leading-6 text-[#f3f5f5]">{model.name}</h1>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[#9aa4ac]">
                  <span className="inline-flex items-center gap-1"><Database className="h-3.5 w-3.5 text-[#818c95]" /> {model.datasource}</span>
                  <span className="h-1 w-1 rounded-full bg-[#4b555e]" />
                  <span>Fresh 2h ago</span>
                  <span className="h-1 w-1 rounded-full bg-[#4b555e]" />
                  <span>AI generated draft</span>
                </div>
              </div>
            </div>
          </div>
          <div className="flex flex-col gap-3 xl:items-end">
            <div className="flex flex-wrap gap-2 xl:justify-end">
              <StatusPill tone={model.status === 'Published' ? 'ready' : 'warning'}>{model.status}</StatusPill>
              <StatusPill>{model.draftRevision}</StatusPill>
              <StatusPill tone="info">{model.publishedVersion}</StatusPill>
              <StatusPill tone={model.readinessLevel === 'ready' ? 'ready' : model.readinessLevel === 'blocked' ? 'blocked' : 'warning'}>{model.readiness}% readiness</StatusPill>
            </div>
            <div className="flex flex-wrap gap-2 xl:justify-end">
              <Button variant="secondary" onClick={reviewModel}><GitCompare className="h-4 w-4" /> Review model</Button>
              <Button variant="brand-primary" onClick={openPublish}><Rocket className="h-4 w-4" /> Publish</Button>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 overflow-x-auto border-t border-[#30363a] px-4 py-2 custom-scrollbar">
          <div className={modelingStyles.segmented}>
            {modeLabels.map(mode => (
              <button
                key={mode.id}
                type="button"
                onClick={() => setWorkspaceMode(mode.id)}
                className={`${modelingStyles.segmentedItem} ${
                  workspaceMode === mode.id ? 'bg-brand-orange text-white shadow-sm hover:bg-brand-orange' : ''
                }`}
                aria-pressed={workspaceMode === mode.id}
              >
                {mode.label}
              </button>
            ))}
          </div>
          <div className="hidden items-center gap-2 text-xs text-[#818c95] md:flex">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-300" />
            <span>Draft edits persist locally until publish.</span>
          </div>
        </div>
      </header>

      {workspaceMode === 'explore' && <SemanticExploreWorkspace model={model} onReviewModel={reviewModel} />}
      {workspaceMode === 'model' && <SemanticGraphWorkspace model={model} />}
      {workspaceMode === 'publish' && <PublishWorkspace model={model} />}

      <footer className="shrink-0 border-t border-[#30363a] bg-[#14181b] px-4 py-2">
        <div className="flex flex-wrap items-center gap-2 text-xs text-[#9aa4ac]">
          <span className="inline-flex items-center gap-1 text-[#d6dde2]"><Bot className="h-3.5 w-3.5 text-brand-orange" /> Agent activity</span>
          {model.validationLog.slice(0, 2).map((item, index) => <StatusPill key={`${index}-${item}`}>{item}</StatusPill>)}
          {model.validationLog.length > 2 && <span className="text-[#818c95]">+{model.validationLog.length - 2} more</span>}
        </div>
      </footer>
    </div>
  )
}
