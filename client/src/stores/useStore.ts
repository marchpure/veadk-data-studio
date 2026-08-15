import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { createChatSlice } from './slices/chatSlice'
import type { ChatSlice } from './slices/chatSlice'
import { createNotebookSlice } from './slices/notebookSlice'
import type { NotebookSlice } from './slices/notebookSlice'
import { createConnectionSlice } from './slices/connectionSlice'
import type { ConnectionSlice } from './slices/connectionSlice'
import { createLLMSlice } from './slices/llmSlice'
import type { LLMSlice } from './slices/llmSlice'
import { createUISlice } from './slices/uiSlice'
import type { UISlice } from './slices/uiSlice'
import { createSchemaSlice } from './slices/schemaSlice'
import type { SchemaSlice } from './slices/schemaSlice'

import { createTableMentionsSlice } from './slices/tableMentionSlice'
import type { TableMentionsSlice } from './slices/tableMentionSlice'
import { createDownloadSlice } from './slices/downloadSlice'
import type { DownloadSlice } from './slices/downloadSlice'
import { createContextSlice } from './slices/contextSlice'
import type { ContextSlice } from './slices/contextSlice'
import { createWaitlistSlice } from './slices/waitlistSlice'
import type { WaitlistSlice } from './slices/waitlistSlice'
import { createAuthSlice } from './slices/authSlice'
import type { AuthSlice } from './slices/authSlice'
import { createTenantSlice } from './slices/tenantSlice'
import type { TenantSlice } from './slices/tenantSlice'
import { createFolderSlice } from './slices/folderSlice'
import type { FolderSlice } from './slices/folderSlice'
import { createGitHubSlice } from './slices/githubSlice'
import type { GitHubSlice } from './slices/githubSlice'
import { createPlanSlice } from './slices/planSlice'
import type { PlanSlice } from './slices/planSlice'

export type StoreState = ChatSlice & NotebookSlice & ConnectionSlice & LLMSlice & UISlice & SchemaSlice & TableMentionsSlice & DownloadSlice & ContextSlice & WaitlistSlice & AuthSlice & TenantSlice & FolderSlice & GitHubSlice & PlanSlice

export const useStore = create<StoreState>()(
  devtools(
    (...a) => ({
      ...createChatSlice(...a),
      ...createNotebookSlice(...a),
      ...createConnectionSlice(...a),
      ...createLLMSlice(...a),
      ...createUISlice(...a),
      ...createSchemaSlice(...a),
      ...createTableMentionsSlice(...a),
      ...createDownloadSlice(...a),
      ...createContextSlice(...a),
      ...createWaitlistSlice(...a),
      ...createAuthSlice(...a),
      ...createTenantSlice(...a),
      ...createFolderSlice(...a),
      ...createGitHubSlice(...a),
      ...createPlanSlice(...a),
    }),
    {
      name: 'app-store',
    }
  )
)