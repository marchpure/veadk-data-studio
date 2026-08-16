export const Scopes = {
  // Notebook scopes
  NOTEBOOK_CREATE: 'notebook.create',
  NOTEBOOK_READ: 'notebook.read',
  NOTEBOOK_READ_OWN: 'notebook.read_own',
  NOTEBOOK_UPDATE: 'notebook.update',
  NOTEBOOK_UPDATE_OWN: 'notebook.update_own',
  NOTEBOOK_DELETE: 'notebook.delete',
  NOTEBOOK_DELETE_OWN: 'notebook.delete_own',

  // Connection scopes
  CONNECTION_CREATE: 'connection.create',
  CONNECTION_READ: 'connection.read',
  CONNECTION_UPDATE: 'connection.update',
  CONNECTION_UPDATE_OWN: 'connection.update_own',
  CONNECTION_DELETE: 'connection.delete',
  CONNECTION_DELETE_OWN: 'connection.delete_own',

  // Dataset scopes
  DATASET_CREATE: 'dataset.create',
  DATASET_READ: 'dataset.read',
  DATASET_UPDATE: 'dataset.update',
  DATASET_UPDATE_OWN: 'dataset.update_own',
  DATASET_DELETE: 'dataset.delete',
  DATASET_DELETE_OWN: 'dataset.delete_own',

  // LLM Connection scopes
  LLM_CONNECTION_CREATE: 'llm_connection.create',
  LLM_CONNECTION_READ: 'llm_connection.read',
  LLM_CONNECTION_UPDATE: 'llm_connection.update',
  LLM_CONNECTION_UPDATE_OWN: 'llm_connection.update_own',
  LLM_CONNECTION_DELETE: 'llm_connection.delete',
  LLM_CONNECTION_DELETE_OWN: 'llm_connection.delete_own',

  // Query scopes
  QUERY_CREATE: 'query.create',
  QUERY_READ: 'query.read',
  QUERY_READ_OWN: 'query.read_own',
  QUERY_UPDATE: 'query.update',
  QUERY_UPDATE_OWN: 'query.update_own',
  QUERY_DELETE: 'query.delete',
  QUERY_DELETE_OWN: 'query.delete_own',
  QUERY_EXECUTE: 'query.execute',

  // Dashboard scopes
  DASHBOARD_READ: 'dashboard.read',
  DASHBOARD_QUERY: 'dashboard.query',
  DASHBOARD_CREATE: 'dashboard.create',
  DASHBOARD_EDIT: 'dashboard.edit',
  DASHBOARD_PUBLISH: 'dashboard.publish',
  DASHBOARD_EXPORT: 'dashboard.export',
  DASHBOARD_SHARE: 'dashboard.share',

  // Annotation scopes
  ANNOTATION_CREATE: 'annotation.create',
  ANNOTATION_READ: 'annotation.read',
  ANNOTATION_UPDATE: 'annotation.update',
  ANNOTATION_DELETE: 'annotation.delete',

  // Tenant scopes
  TENANT_READ: 'tenant.read',
  TENANT_UPDATE: 'tenant.update',
  TENANT_INVITE: 'tenant.invite',
  TENANT_REMOVE_MEMBER: 'tenant.remove_member',
  TENANT_MANAGE_ROLES: 'tenant.manage_roles',

  // User scopes
  USER_READ: 'user.read',
  USER_UPDATE: 'user.update',

  // Settings scopes
  SETTINGS_READ: 'settings.read',
  SETTINGS_UPDATE: 'settings.update',

  // Folder scopes
  FOLDER_CREATE: 'folder.create',
  FOLDER_READ: 'folder.read',
  FOLDER_UPDATE: 'folder.update',
  FOLDER_DELETE: 'folder.delete',
  FOLDER_MANAGE_MEMBERS: 'folder.manage_members',
  FOLDER_SHARE_NOTEBOOK: 'folder.share_notebook',

  // Viewer scopes
  VIEWER_DASHBOARD_READ: 'viewer.dashboard_read',
} as const

export type ScopeType = (typeof Scopes)[keyof typeof Scopes]
