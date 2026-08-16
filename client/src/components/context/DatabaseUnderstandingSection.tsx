import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useStore } from '@/stores/useStore';
import { useQueryClient } from '@tanstack/react-query';
import { Database, Edit2, Check, X, Plus, Loader2, RefreshCw, ChevronDown, ChevronRight, Upload, FileText, Lock, Users } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tooltip } from '@/components/ui/tooltip';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useDatasources } from '@/hooks/useDBConnections';
import { useScopes } from '@/hooks/useScopes';
import { ApiService, isMultiDatabaseSchema, type DatabaseSchemaResponse, type DatabaseTable, type DatabaseColumn, type MongoCollection, type SourceSkillCandidate, type SourceUnderstanding } from '@/services/api';
import { showToast } from '@/utils/toast';
import { useAppConfig } from '@/hooks/useAppConfig';
import { isTauriApp } from '@/lib/tauri-api';

interface DatabaseUnderstandingSectionProps {
  schema?: DatabaseSchemaResponse
  datasourceType?: string
  enableEditing?: boolean
  enableSearch?: boolean
  enableSelector?: boolean
  compact?: boolean
}

type UnderstandingTab = 'overview' | 'resources' | 'profile' | 'skills' | 'evidence' | 'quality' | 'drift'

const understandingTabs: Array<{ id: UnderstandingTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'resources', label: 'Resources' },
  { id: 'profile', label: 'Profile' },
  { id: 'skills', label: 'Source Skills' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'quality', label: 'Quality' },
  { id: 'drift', label: 'Sync/Drift' },
]

export const DatabaseUnderstandingSection: React.FC<DatabaseUnderstandingSectionProps> = ({
  schema: propsSchema,
  datasourceType: propsType,
  enableEditing = true,
  enableSearch = true,
  enableSelector = true,
  compact = false,
}) => {
  const { data: datasourcesResponse, isLoading: loadingDatasources, error: datasourcesError } = useDatasources();

  const {
    databaseContext,
    selectedDatasourceId,
    setSelectedDatasource,
    updateTableDescription,
    updateColumnAnnotation,
    toggleColumnRedaction,
    toggleTableRedaction,
    loadDatasourceSchema,
    loadDatasourceAnnotations,
    datasourceSchemas,
  } = useStore();

  const [loadingSchema, setLoadingSchema] = useState<string | null>(null);
  const [schemaError, setSchemaError] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const { canEditDatasource } = useScopes();

  const [editingTable, setEditingTable] = useState<string | null>(null);
  const [editingColumn, setEditingColumn] = useState<{ table: string; column: string } | null>(null);
  const [tempDescription, setTempDescription] = useState('');
  const [tempAnnotation, setTempAnnotation] = useState('');
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');

  const [editingName, setEditingName] = useState(false);
  const [tempName, setTempName] = useState('');
  const [isPublic, setIsPublic] = useState(false);
  const [isRefreshingSchema, setIsRefreshingSchema] = useState(false);
  const [isUpdatingVisibility, setIsUpdatingVisibility] = useState(false);
  const [isUpdatingDataset, setIsUpdatingDataset] = useState(false);
  const [existingFiles, setExistingFiles] = useState<Array<{file_id: string, filename: string, alias: string, size: number}>>([]);
  const [newFilesToUpload, setNewFilesToUpload] = useState<File[]>([]);
  const [removedFileIds, setRemovedFileIds] = useState<Set<string>>(new Set());
  const newFilesInputRef = useRef<HTMLInputElement>(null);
  const [understandingTab, setUnderstandingTab] = useState<UnderstandingTab>('overview');
  const [sourceUnderstanding, setSourceUnderstanding] = useState<SourceUnderstanding | null>(null);
  const [loadingUnderstanding, setLoadingUnderstanding] = useState(false);
  const [understandingError, setUnderstandingError] = useState<string | null>(null);
  const [isAnalyzingUnderstanding, setIsAnalyzingUnderstanding] = useState(false);
  const [reviewingCandidateId, setReviewingCandidateId] = useState<string | null>(null);
  const [isCreatingSemanticDraft, setIsCreatingSemanticDraft] = useState(false);

  const { isSelfHosted } = useAppConfig();
  const showSharingFeatures = !isTauriApp() && isSelfHosted;

  const datasources = datasourcesResponse?.items || [];

  const isMongoCollection = (data: DatabaseTable | MongoCollection): data is MongoCollection => {
    return typeof data === 'object' && data !== null && 'sample_fields' in data && !('columns' in data);
  };

  const toggleTable = (tableName: string) => {
    setExpandedTables(prev => {
      const next = new Set(prev);
      if (next.has(tableName)) {
        next.delete(tableName);
      } else {
        next.add(tableName);
      }
      return next;
    });
  };

  const selectedDatasource = datasources.find(ds => ds.id === selectedDatasourceId);
  const schema = selectedDatasourceId ? datasourceSchemas[selectedDatasourceId] : null;

  const effectiveSchema = propsSchema || schema;
  const singleSchema = effectiveSchema && !isMultiDatabaseSchema(effectiveSchema) ? effectiveSchema : null;
  const effectiveType = propsType || selectedDatasource?.database_type;
  const selectedDatabaseType = selectedDatasource?.database_type || selectedDatasource?.type;
  const selectedDatabaseTypeKey = selectedDatabaseType ? String(selectedDatabaseType) : undefined;
  const normalizedDatabaseType = selectedDatabaseTypeKey === 'postgresql' || selectedDatabaseTypeKey === 'postgres'
    ? 'pg'
    : selectedDatabaseTypeKey;
  const canUseSourceUnderstanding =
    selectedDatasource?.source_type === 'connection' &&
    !!normalizedDatabaseType &&
    ['oracle', 'pg', 'mysql', 'sqlite', 'mssql', 'mongo', 'dynamodb'].includes(normalizedDatabaseType);
  const canCreateSemanticDraftFromUnderstanding =
    !!normalizedDatabaseType && !['mongo', 'dynamodb'].includes(normalizedDatabaseType);
  const verifiedSourceCandidates = sourceUnderstanding?.candidates.filter(candidate => candidate.review_status === 'verified') || [];

  const filteredTables = useMemo(() => {
    if (!singleSchema?.schema) return [];

    const entries = Object.entries(singleSchema.schema) as Array<[string, DatabaseTable | MongoCollection]>;
    if (!searchQuery.trim()) return entries;

    const query = searchQuery.toLowerCase();
    return entries.filter(([tableName]) =>
      tableName.toLowerCase().includes(query)
    );
  }, [singleSchema, searchQuery]);

  useEffect(() => {
    if (enableSelector && datasources.length > 0 && !selectedDatasourceId && !propsSchema) {
      setSelectedDatasource(datasources[0].id);
    }
  }, [datasources, selectedDatasourceId, setSelectedDatasource, enableSelector, propsSchema]);

  // Fetch schema for selected datasource (only when not using props)
  useEffect(() => {
    const shouldFetchSchema = !propsSchema && selectedDatasourceId && !datasourceSchemas[selectedDatasourceId];
    if (!shouldFetchSchema) return;

    const fetchSchema = async () => {
      setLoadingSchema(selectedDatasourceId);
      setSchemaError(null);

      try {
        const schema = await ApiService.getDatasourceSchema(selectedDatasourceId);
        loadDatasourceSchema(selectedDatasourceId, schema);
        await loadDatasourceAnnotations(selectedDatasourceId);
      } catch (error: unknown) {
        console.error('Error fetching schema:', error);
        setSchemaError(error instanceof Error ? error.message : 'Failed to fetch schema');
      } finally {
        setLoadingSchema(null);
      }
    };

    fetchSchema();
  }, [selectedDatasourceId, datasourceSchemas, loadDatasourceSchema, loadDatasourceAnnotations, propsSchema]);

  useEffect(() => {
    if (selectedDatasource) {
      setIsPublic(selectedDatasource.is_public ?? false);
      setTempName(selectedDatasource.name || '');
      setEditingName(false);
      setNewFilesToUpload([]);
      setRemovedFileIds(new Set());
      if (selectedDatasource.source_type === 'dataset' && selectedDatasource.files) {
        setExistingFiles(selectedDatasource.files.map((f) => ({
          file_id: f.id || f.file_id,
          filename: f.name || f.filename,
          alias: f.alias,
          size: f.size,
        })));
      } else {
        setExistingFiles([]);
      }
    }
  }, [selectedDatasource?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!selectedDatasourceId || !canUseSourceUnderstanding) {
      setSourceUnderstanding(null);
      setUnderstandingError(null);
      return;
    }

    let cancelled = false;
    const fetchUnderstanding = async () => {
      setLoadingUnderstanding(true);
      setUnderstandingError(null);
      try {
        const payload = await ApiService.getDatasourceUnderstanding(selectedDatasourceId);
        if (!cancelled) {
          setSourceUnderstanding(payload);
        }
      } catch (error: unknown) {
        if (!cancelled) {
          setUnderstandingError(error instanceof Error ? error.message : 'Failed to load Source Understanding');
        }
      } finally {
        if (!cancelled) {
          setLoadingUnderstanding(false);
        }
      }
    };

    fetchUnderstanding();
    return () => {
      cancelled = true;
    };
  }, [selectedDatasourceId, canUseSourceUnderstanding]);

  const handleToggleVisibility = async () => {
    if (!selectedDatasource) return;
    const newIsPublic = !isPublic;
    setIsUpdatingVisibility(true);
    try {
      await ApiService.updateDatasourceVisibility(selectedDatasource.id, newIsPublic);
      setIsPublic(newIsPublic);
      queryClient.invalidateQueries({ queryKey: ['datasources'] });
      showToast.success(newIsPublic ? 'Datasource shared with team' : 'Datasource set to private');
    } catch (error: unknown) {
      showToast.error(`Failed to update visibility: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsUpdatingVisibility(false);
    }
  };

  const handleRefreshSchema = async () => {
    if (!selectedDatasource?.connection_id) return;
    setIsRefreshingSchema(true);
    try {
      await ApiService.refreshConnectionSchema(selectedDatasource.connection_id);
      const newSchema = await ApiService.getDatasourceSchema(selectedDatasource.id);
      loadDatasourceSchema(selectedDatasource.id, newSchema);
      await loadDatasourceAnnotations(selectedDatasource.id);
      showToast.success('Schema refreshed successfully');
    } catch (error: unknown) {
      showToast.error(`Failed to refresh schema: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsRefreshingSchema(false);
    }
  };

  const handleAnalyzeUnderstanding = async (refreshSchema = false) => {
    if (!selectedDatasourceId) return;
    setIsAnalyzingUnderstanding(true);
    setUnderstandingError(null);
    try {
      const payload = await ApiService.analyzeDatasourceUnderstanding(selectedDatasourceId, { refresh_schema: refreshSchema });
      setSourceUnderstanding(payload);
      setUnderstandingTab('skills');
      showToast.success('Source Understanding analysis completed');
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      setUnderstandingError(message);
      showToast.error(`Failed to analyze source: ${message}`);
    } finally {
      setIsAnalyzingUnderstanding(false);
    }
  };

  const handleReviewSourceCandidate = async (candidate: SourceSkillCandidate, action: 'accept' | 'edit' | 'reject') => {
    if (!selectedDatasourceId) return;
    let statement: string | undefined;
    let note: string | undefined;
    if (action === 'edit') {
      const next = window.prompt('Edit the verified statement before accepting:', candidate.statement);
      if (next === null) return;
      statement = next.trim() || candidate.statement;
      note = 'Edited from Datasource Understanding workspace.';
    }

    setReviewingCandidateId(candidate.id);
    try {
      const payload = await ApiService.reviewSourceSkillCandidate(selectedDatasourceId, candidate.id, {
        action,
        statement,
        note,
      });
      setSourceUnderstanding(payload);
      showToast.success(action === 'reject' ? 'Candidate rejected' : 'Candidate verified');
    } catch (error: unknown) {
      showToast.error(`Failed to review candidate: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setReviewingCandidateId(null);
    }
  };

  const handleCreateSemanticDraft = async () => {
    if (
      !selectedDatasourceId ||
      !selectedDatasource ||
      verifiedSourceCandidates.length === 0 ||
      !canCreateSemanticDraftFromUnderstanding
    )
      return;
    setIsCreatingSemanticDraft(true);
    try {
      const response = await ApiService.createSemanticModelDraftFromSourceUnderstanding(selectedDatasourceId, {
        model_id: `${selectedDatasource.name || 'source'}-source-draft`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''),
        name: `${selectedDatasource.name || 'Source'} Semantic Draft`,
        domain: 'Source Understanding',
        owner: 'Data Team',
        candidate_ids: verifiedSourceCandidates.map(candidate => candidate.id),
      });
      queryClient.invalidateQueries({ queryKey: ['semantic-models'] });
      showToast.success(`Semantic model draft updated: ${response.model?.name || response.model?.id || 'Draft'}`);
    } catch (error: unknown) {
      showToast.error(`Failed to create semantic draft: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsCreatingSemanticDraft(false);
    }
  };

  const handleSaveName = async () => {
    if (!selectedDatasource || !tempName.trim()) return;
    setIsUpdatingDataset(true);
    try {
      await ApiService.updateDataset(selectedDatasource.id, {
        name: tempName.trim(),
        files: existingFiles.map(f => ({ file_id: f.file_id, filename: f.filename, alias: f.alias, size: f.size })),
      });
      queryClient.invalidateQueries({ queryKey: ['datasources'] });
      setEditingName(false);
      showToast.success('Datasource name updated');
    } catch (error: unknown) {
      showToast.error(`Failed to update name: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsUpdatingDataset(false);
    }
  };

  const handleNewFilesSelection = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || []);
    if (selectedFiles.length === 0) return;
    const existingNames = new Set(existingFiles.map(f => f.filename));
    const duplicates = selectedFiles.filter(f => existingNames.has(f.name));
    if (duplicates.length > 0) {
      showToast.error(`Files already exist: ${duplicates.map(f => f.name).join(', ')}`);
      if (newFilesInputRef.current) newFilesInputRef.current.value = '';
      return;
    }
    setNewFilesToUpload(prev => [...prev, ...selectedFiles]);
  };

  const handleRemoveExistingFile = (fileId: string) => {
    setExistingFiles(prev => prev.filter(f => f.file_id !== fileId));
    setRemovedFileIds(prev => new Set(prev).add(fileId));
  };

  const handleSaveFileChanges = async () => {
    if (!selectedDatasource) return;
    setIsUpdatingDataset(true);
    try {
      const updated = await ApiService.updateDataset(selectedDatasource.id, {
        name: tempName.trim() || undefined,
        files: existingFiles.map(f => ({ file_id: f.file_id, filename: f.filename, alias: f.alias, size: f.size })),
        newFiles: newFilesToUpload.length > 0 ? newFilesToUpload : undefined,
      });
      if (updated?.files) {
        setExistingFiles(updated.files.map((f: { id?: string; file_id?: string; name?: string; filename?: string; alias: string; size: number }) => ({
          file_id: f.file_id || f.id || '',
          filename: f.filename || f.name || '',
          alias: f.alias,
          size: f.size,
        })));
      }
      queryClient.invalidateQueries({ queryKey: ['datasources'] });
      queryClient.invalidateQueries({ queryKey: ['notebook-connections'] });
      setNewFilesToUpload([]);
      setRemovedFileIds(new Set());
      if (newFilesInputRef.current) newFilesInputRef.current.value = '';
      try {
        const refreshedSchema = await ApiService.getDatasourceSchema(selectedDatasource.id);
        loadDatasourceSchema(selectedDatasource.id, refreshedSchema);
        await loadDatasourceAnnotations(selectedDatasource.id);
      } catch (schemaErr) {
        console.error('Failed to refresh schema after file changes:', schemaErr);
      }
      showToast.success('File changes saved');
    } catch (error: unknown) {
      showToast.error(`Failed to save changes: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsUpdatingDataset(false);
    }
  };

  const hasFileChanges = removedFileIds.size > 0 || newFilesToUpload.length > 0;

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleEditTableDescription = (tableName: string, currentDescription: string) => {
    setEditingTable(tableName);
    setTempDescription(currentDescription || '');
  };

  const handleSaveTableDescription = (tableName: string) => {
    if (!selectedDatasourceId) return;
    updateTableDescription(selectedDatasourceId, tableName, tempDescription);
    setEditingTable(null);
  };

  const handleEditColumnAnnotation = (tableName: string, columnName: string, currentAnnotation: string) => {
    setEditingColumn({ table: tableName, column: columnName });
    setTempAnnotation(currentAnnotation || '');
  };

  const handleSaveColumnAnnotation = (tableName: string, columnName: string) => {
    if (!selectedDatasourceId) return;
    updateColumnAnnotation(selectedDatasourceId, tableName, columnName, tempAnnotation);
    setEditingColumn(null);
  };

  const getBadgeVariant = (type: string) => {
    switch (type) {
      case 'pg':
        return 'postgres';
      case 'mongo':
        return 'mongodb';
      case 'csv':
      case 'excel':
      case 'parquet':
      case 'json':
        return 'csv';
      case 'mysql':
        return 'mysql';
      case 'sqlite':
        return 'sqlite';
      default:
        return 'default';
    }
  };

  const formatDbType = (type: string): string => {
    switch (type) {
      case 'pg':
        return 'PostgreSQL'
      case 'mongo':
        return 'MongoDB'
      case 'mysql':
        return 'MySQL'
      case 'sqlite':
        return 'SQLite'
      case 'mssql':
        return 'SQL Server'
      case 'csv':
        return 'CSV File'
      case 'excel':
        return 'Excel File'
      case 'parquet':
        return 'Parquet File'
      case 'json':
        return 'JSON File'
      default:
        return type.toUpperCase()
    }
  };

  // Get user annotations from databaseContext
  const getUserAnnotations = (tableName: string) => {
    const dbContext = databaseContext.find(db => db.datasourceId === selectedDatasourceId);
    return dbContext?.tables.find(t => t.tableName === tableName);
  };

  // Loading state
  if (loadingDatasources) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-6">
        <Loader2 className="w-8 h-8 text-brand-orange animate-spin mb-4" />
        <p className="text-sm text-gray-400">Loading datasources...</p>
      </div>
    );
  }

  // Error state
  if (datasourcesError) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-6">
        <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center mb-4">
          <X className="w-8 h-8 text-red-400" />
        </div>
        <h3 className="text-lg font-semibold text-white mb-2">Error Loading Datasources</h3>
        <p className="text-sm text-gray-400 text-center max-w-sm">
          {datasourcesError.message || 'Failed to load datasources'}
        </p>
      </div>
    );
  }

  // Empty state
  if (datasources.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-6">
        <div className="w-16 h-16 rounded-full bg-brand-orange/10 flex items-center justify-center mb-4">
          <Database className="w-8 h-8 text-brand-orange" />
        </div>
        <h3 className="text-lg font-semibold text-white mb-2">No Datasources Connected</h3>
        <p className="text-sm text-gray-400 text-center max-w-sm">
          Connect a database or upload files to start building schema understanding and insights.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Datasource Selector */}
      {enableSelector && datasources.length > 1 && (
        <div>
          <label className="text-xs text-gray-400 mb-2 block">Select Datasource</label>
          <Select value={selectedDatasourceId || ''} onValueChange={setSelectedDatasource}>
            <SelectTrigger className="w-full bg-[#1a1a1a] border-gray-700 text-white">
              <SelectValue placeholder="Choose a datasource" />
            </SelectTrigger>
            <SelectContent className="bg-[#2a2a2a] border-gray-700">
              {datasources.map((ds) => (
                <SelectItem
                  key={ds.id}
                  value={ds.id}
                  className="text-white hover:bg-[#333333]"
                >
                  {ds.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Search Filter */}
      {enableSearch && effectiveSchema && Object.keys(effectiveSchema.schema || {}).length > 0 && (
        <div>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search tables..."
            className="w-full px-3 py-2 text-sm bg-[#1a1a1a] border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:border-brand-orange"
          />
        </div>
      )}

      {/* Datasource Header */}
      {selectedDatasource && (
        <div className="pb-3 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <Database className="w-5 h-5 text-brand-orange" />
            <div className="flex-1">
              <div className="flex items-center gap-1.5">
                <h3 className="text-sm font-semibold text-white truncate" title={selectedDatasource.name}>{selectedDatasource.name}</h3>
                {enableEditing && selectedDatasource.source_type === 'connection' && (
                  <Tooltip content="Credentials stored encrypted">
                    <span className="inline-flex items-center justify-center">
                      <Lock className="w-3 h-3 text-gray-500" />
                    </span>
                  </Tooltip>
                )}
              </div>
              <div className="flex items-center gap-2">
                {schema && (
                  <p className="text-xs text-gray-400">
                    {Object.keys(effectiveSchema?.schema || {}).length} table{Object.keys(effectiveSchema?.schema || {}).length !== 1 ? 's' : ''}
                  </p>
                )}
                <div className="flex-1" />
                {enableEditing && selectedDatasource.source_type === 'connection' && canEditDatasource(selectedDatasource.created_by) && (
                  <div className="flex items-center gap-1.5">
                    {showSharingFeatures && (
                      <div className="flex items-center gap-1">
                        <span className="text-[10px] text-gray-500">Share with team</span>
                        <Switch
                          size="sm"
                          checked={isPublic}
                          onCheckedChange={handleToggleVisibility}
                          disabled={isUpdatingVisibility}
                        />
                      </div>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={handleRefreshSchema}
                      disabled={isRefreshingSchema}
                      className="text-xs text-gray-400 hover:text-white h-6 px-1.5 gap-1"
                    >
                      {isRefreshingSchema ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <RefreshCw className="w-3.5 h-3.5" />
                      )}
                      <span className="text-[10px]">Refresh</span>
                    </Button>
                  </div>
                )}
                {enableEditing && selectedDatasource.source_type === 'dataset' && showSharingFeatures && canEditDatasource(selectedDatasource.created_by) && (
                  <div className="flex items-center gap-1">
                    <span className="text-[10px] text-gray-500">Share with team</span>
                    <Switch
                      size="sm"
                      checked={isPublic}
                      onCheckedChange={handleToggleVisibility}
                      disabled={isUpdatingVisibility}
                    />
                  </div>
                )}
              </div>
            </div>
            {effectiveType && (
              <Badge variant={getBadgeVariant(effectiveType)}>
                {formatDbType(effectiveType)}
              </Badge>
            )}
          </div>
        </div>
      )}

      {/* Source Understanding Workspace */}
      {selectedDatasource && canUseSourceUnderstanding && (
        <div className="rounded-lg border border-gray-800 bg-[#141414]">
          <div className="flex flex-col gap-3 border-b border-gray-800 p-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h4 className="text-sm font-semibold text-white">Understanding workspace</h4>
                <span className="rounded-full border border-brand-orange/30 bg-brand-orange/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-brand-orange">
                  Source Snapshot first
                </span>
              </div>
              <p className="mt-1 text-xs text-gray-500">
                Turns database schema, keys, profiles, comments, samples, and constraints into evidence-backed Source Skills.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => handleAnalyzeUnderstanding(false)}
                disabled={isAnalyzingUnderstanding || !enableEditing || !canEditDatasource(selectedDatasource.created_by)}
                className="h-8 text-xs"
              >
                {isAnalyzingUnderstanding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                Re-analyze
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => handleAnalyzeUnderstanding(true)}
                disabled={isAnalyzingUnderstanding || !enableEditing || !canEditDatasource(selectedDatasource.created_by)}
                className="h-8 text-xs text-gray-400 hover:text-white"
              >
                {['mongo', 'dynamodb'].includes(normalizedDatabaseType || '') ? 'Refresh document profile' : 'Refresh schema + analyze'}
              </Button>
              <Button
                size="sm"
                variant="brand-primary"
                onClick={handleCreateSemanticDraft}
                disabled={
                  isCreatingSemanticDraft ||
                  verifiedSourceCandidates.length === 0 ||
                  !canCreateSemanticDraftFromUnderstanding ||
                  !enableEditing ||
                  !canEditDatasource(selectedDatasource.created_by)
                }
                className="h-8 text-xs"
              >
                {isCreatingSemanticDraft ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                Create model draft
              </Button>
            </div>
          </div>

          <div className="flex gap-1 overflow-x-auto border-b border-gray-800 p-2">
            {understandingTabs.map(tab => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setUnderstandingTab(tab.id)}
                className={`shrink-0 rounded-md px-2.5 py-1.5 text-xs transition-colors ${
                  understandingTab === tab.id ? 'bg-brand-orange text-white' : 'text-gray-400 hover:bg-[#202020] hover:text-white'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {loadingUnderstanding && (
            <div className="flex items-center gap-2 p-3 text-xs text-gray-400">
              <Loader2 className="h-4 w-4 animate-spin text-brand-orange" />
              Loading Source Understanding...
            </div>
          )}

          {understandingError && !loadingUnderstanding && (
            <div className="m-3 rounded-md border border-red-900/40 bg-red-950/20 p-3 text-xs text-red-300">
              {understandingError}
            </div>
          )}

          {!loadingUnderstanding && !sourceUnderstanding?.latest_run && (
            <div className="p-4">
              <div className="rounded-md border border-dashed border-gray-700 bg-[#101010] p-4">
                <div className="text-sm font-medium text-white">No Source Understanding run yet</div>
                <p className="mt-1 max-w-2xl text-xs text-gray-500">
                  Run analysis to create catalog/schema/table Source Resources, immutable Source Snapshots, evidence fragments, and reviewable Source Skill candidates.
                </p>
                <Button
                  size="sm"
                  variant="brand-primary"
                  onClick={() => handleAnalyzeUnderstanding(false)}
                  disabled={isAnalyzingUnderstanding || !enableEditing || !canEditDatasource(selectedDatasource.created_by)}
                  className="mt-3 h-8 text-xs"
                >
                  {isAnalyzingUnderstanding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Database className="h-3.5 w-3.5" />}
                  Analyze source
                </Button>
              </div>
            </div>
          )}

          {!loadingUnderstanding && sourceUnderstanding?.latest_run && (
            <div className="p-3">
              {understandingTab === 'overview' && (
                <div className="grid gap-2 md:grid-cols-4">
                  <UnderstandingStat label="Resources" value={sourceUnderstanding.overview.resource_count ?? 0} />
                  <UnderstandingStat label="Snapshots" value={sourceUnderstanding.overview.snapshot_count ?? 0} />
                  <UnderstandingStat label="Candidates" value={sourceUnderstanding.overview.candidate_count ?? 0} />
                  <UnderstandingStat label="Verified" value={sourceUnderstanding.overview.verified_count ?? 0} />
                  <div className="md:col-span-4 rounded-md border border-gray-800 bg-[#101010] p-3">
                    <div className="text-xs uppercase tracking-wide text-gray-500">Latest run</div>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-300">
                      <StatusChip label={sourceUnderstanding.latest_run.status} tone={sourceUnderstanding.latest_run.status === 'completed' ? 'ready' : 'warning'} />
                      <StatusChip label={sourceUnderstanding.latest_run.analyzer_version} tone="info" />
                      <span>Last analyzed: {sourceUnderstanding.overview.last_analyzed_at || 'n/a'}</span>
                      <span>Readiness: {sourceUnderstanding.overview.readiness ?? 0}%</span>
                    </div>
                  </div>
                </div>
              )}

              {understandingTab === 'resources' && (
                <div className="space-y-2">
                  {sourceUnderstanding.resources.map(resource => (
                    <div key={resource.id} className="rounded-md border border-gray-800 bg-[#101010] p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs text-white">{resource.name}</span>
                        <StatusChip label={resource.resource_type} tone="info" />
                        <StatusChip label={resource.status} tone={resource.status === 'ready' ? 'ready' : 'warning'} />
                      </div>
                      <div className="mt-2 truncate text-[11px] text-gray-500">Snapshot: {resource.latest_snapshot_id || 'n/a'}</div>
                      {resource.external_id && <div className="mt-1 truncate text-[11px] text-gray-600">{resource.external_id}</div>}
                    </div>
                  ))}
                </div>
              )}

              {understandingTab === 'profile' && (
                <div className="grid gap-2 md:grid-cols-3">
                  <UnderstandingStat label="Tables" value={sourceUnderstanding.profile.table_count ?? 0} />
                  <UnderstandingStat label="Columns" value={sourceUnderstanding.profile.column_count ?? 0} />
                  <UnderstandingStat label="Relationships" value={sourceUnderstanding.profile.relationship_count ?? 0} />
                  <div className="md:col-span-3 rounded-md border border-gray-800 bg-[#101010] p-3">
                    <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">Candidate mix</div>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(sourceUnderstanding.profile.candidate_counts || {}).map(([key, value]) => (
                        <StatusChip key={key} label={`${formatCandidateType(key)}: ${String(value)}`} tone="info" />
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {understandingTab === 'skills' && (
                <div className="space-y-2">
                  {sourceUnderstanding.candidates.length === 0 && (
                    <div className="rounded-md border border-gray-800 bg-[#101010] p-3 text-xs text-gray-500">
                      This source has profile snapshots and evidence, but no semantic candidates. Review a projection before creating production metrics.
                    </div>
                  )}
                  {sourceUnderstanding.candidates.map(candidate => (
                    <CandidateCard
                      key={candidate.id}
                      candidate={candidate}
                      loading={reviewingCandidateId === candidate.id}
                      onAccept={() => handleReviewSourceCandidate(candidate, 'accept')}
                      onEdit={() => handleReviewSourceCandidate(candidate, 'edit')}
                      onReject={() => handleReviewSourceCandidate(candidate, 'reject')}
                      canReview={enableEditing && canEditDatasource(selectedDatasource.created_by)}
                    />
                  ))}
                </div>
              )}

              {understandingTab === 'evidence' && (
                <div className="space-y-2">
                  {sourceUnderstanding.evidence.length === 0 && <div className="text-xs text-gray-500">No evidence linked to current candidates.</div>}
                  {sourceUnderstanding.evidence.map(item => (
                    <div key={item.id} className="rounded-md border border-gray-800 bg-[#101010] p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusChip label={item.fragment_type} tone="info" />
                        {item.confidence && <StatusChip label={item.confidence} tone={item.confidence === 'high' ? 'ready' : 'warning'} />}
                        <span className="text-[11px] text-gray-500">{Array.isArray(item.title_path) ? item.title_path.join(' / ') : ''}</span>
                      </div>
                      <p className="mt-2 text-xs leading-relaxed text-gray-300">{item.text}</p>
                      <pre className="mt-2 max-h-24 overflow-auto rounded bg-[#080808] p-2 text-[10px] text-gray-500">
                        {JSON.stringify(item.locator_json, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              )}

              {understandingTab === 'quality' && (
                <div className="space-y-2">
                  <div className="grid gap-2 md:grid-cols-2">
                    <UnderstandingStat label="Blockers" value={sourceUnderstanding.quality.blockers ?? 0} />
                    <UnderstandingStat label="Warnings" value={sourceUnderstanding.quality.warnings ?? 0} />
                  </div>
                  {(sourceUnderstanding.quality.items || []).map((item: { id: string; title: string; statement: string; review_status: string }) => (
                    <div key={item.id} className="rounded-md border border-gray-800 bg-[#101010] p-3">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-white">{item.title}</span>
                        <StatusChip label={item.review_status} tone={reviewTone(item.review_status)} />
                      </div>
                      <p className="mt-1 text-xs text-gray-400">{item.statement}</p>
                    </div>
                  ))}
                </div>
              )}

              {understandingTab === 'drift' && (
                <div className="rounded-md border border-gray-800 bg-[#101010] p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-white">Sync / Drift</span>
                    <StatusChip label={sourceUnderstanding.sync_drift.status || 'stable'} tone={sourceUnderstanding.sync_drift.status === 'drift_detected' ? 'warning' : 'ready'} />
                  </div>
                  <div className="mt-3 space-y-2">
                    {(sourceUnderstanding.sync_drift.events || []).length === 0 && <div className="text-xs text-gray-500">No drift detected in the latest run.</div>}
                    {(sourceUnderstanding.sync_drift.events || []).map((event: Record<string, unknown>, index: number) => (
                      <pre key={index} className="overflow-auto rounded bg-[#080808] p-2 text-[10px] text-gray-500">
                        {JSON.stringify(event, null, 2)}
                      </pre>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* File Dataset Settings */}
      {enableEditing && selectedDatasource && selectedDatasource.source_type === 'dataset' && canEditDatasource(selectedDatasource.created_by) && (
        <div className="pb-3 border-b border-gray-800">
          <div className="rounded-lg bg-[#141414] border border-gray-800 divide-y divide-gray-800">
            {/* File Dataset: Name */}
            {selectedDatasource.source_type === 'dataset' && (
              <div className="px-3 py-2.5">
                <label className="text-[10px] text-gray-500 uppercase tracking-wider block mb-1">Name</label>
                {editingName ? (
                  <div className="flex items-center gap-1">
                    <input
                      type="text"
                      value={tempName}
                      onChange={(e) => setTempName(e.target.value)}
                      className="flex-1 px-2 py-1 text-xs bg-[#0d0d0d] border border-gray-700 rounded text-white focus:outline-none focus:border-brand-orange"
                      autoFocus
                    />
                    <Button size="sm" variant="ghost" onClick={handleSaveName} disabled={isUpdatingDataset} className="h-6 w-6 p-0 text-green-400 hover:text-green-300">
                      {isUpdatingDataset ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => { setEditingName(false); setTempName(selectedDatasource.name || ''); }} className="h-6 w-6 p-0 text-gray-400 hover:text-gray-300">
                      <X className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                ) : (
                  <div className="flex items-center gap-1 group">
                    <span className="text-xs text-gray-300 flex-1">{selectedDatasource.name}</span>
                    <Button size="sm" variant="ghost" onClick={() => setEditingName(true)} className="h-5 w-5 p-0 opacity-0 group-hover:opacity-100 text-gray-400 hover:text-white">
                      <Edit2 className="w-3 h-3" />
                    </Button>
                  </div>
                )}
              </div>
            )}

            {/* File Dataset: Files */}
            {selectedDatasource.source_type === 'dataset' && (
              <div className="px-3 py-2.5">
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-[10px] text-gray-500 uppercase tracking-wider">Files</label>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => newFilesInputRef.current?.click()}
                    className="text-[10px] text-brand-orange hover:text-orange-400 h-5 px-1.5"
                  >
                    <Upload className="w-3 h-3 mr-1" />
                    Add Files
                  </Button>
                </div>
                <input
                  ref={newFilesInputRef}
                  type="file"
                  multiple
                  accept={
                    selectedDatasource.type === 'csv' ? '.csv' :
                    selectedDatasource.type === 'excel' ? '.xlsx,.xls' :
                    selectedDatasource.type === 'parquet' ? '.parquet' :
                    '.json'
                  }
                  onChange={handleNewFilesSelection}
                  className="hidden"
                />
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {newFilesToUpload.map((file, index) => (
                    <div key={`new-${index}`} className="flex items-center gap-2 p-1.5 rounded bg-[#0d0d0d] border border-green-800/40">
                      <FileText className="w-3.5 h-3.5 text-green-500 shrink-0" />
                      <span className="text-xs text-white flex-1 truncate">{file.name}</span>
                      <span className="text-[10px] text-gray-500 shrink-0">{formatFileSize(file.size)}</span>
                      <Button size="sm" variant="ghost" onClick={() => setNewFilesToUpload(prev => prev.filter((_, i) => i !== index))} className="h-5 w-5 p-0 text-red-400 hover:text-red-300 shrink-0">
                        <X className="w-3 h-3" />
                      </Button>
                    </div>
                  ))}
                  {existingFiles.map((file) => (
                    <div key={file.file_id} className="flex items-center gap-2 p-1.5 rounded bg-[#0d0d0d]">
                      <FileText className="w-3.5 h-3.5 text-brand-orange shrink-0" />
                      <span className="text-xs text-white flex-1 truncate">{file.filename}</span>
                      <span className="text-[10px] text-gray-500 shrink-0">{formatFileSize(file.size)}</span>
                      <Button size="sm" variant="ghost" onClick={() => handleRemoveExistingFile(file.file_id)} className="h-5 w-5 p-0 text-red-400 hover:text-red-300 shrink-0">
                        <X className="w-3 h-3" />
                      </Button>
                    </div>
                  ))}
                  {existingFiles.length === 0 && newFilesToUpload.length === 0 && (
                    <p className="text-xs text-gray-500 italic py-1">No files</p>
                  )}
                </div>
                {hasFileChanges && (
                  <Button
                    size="sm"
                    variant="brand-primary"
                    onClick={handleSaveFileChanges}
                    disabled={isUpdatingDataset}
                    className="w-full mt-2 h-7 text-xs"
                  >
                    {isUpdatingDataset ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : null}
                    Save File Changes
                  </Button>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Schema Loading State */}
      {loadingSchema && (
        <div className="flex flex-col items-center justify-center py-12 px-6">
          <Loader2 className="w-8 h-8 text-brand-orange animate-spin mb-4" />
          <p className="text-sm text-gray-400">Loading schema...</p>
        </div>
      )}

      {/* Schema Error State */}
      {schemaError && !loadingSchema && (
        <div className="flex flex-col items-center justify-center py-12 px-6">
          <div className="w-12 h-12 rounded-full bg-red-500/10 flex items-center justify-center mb-4">
            <X className="w-6 h-6 text-red-400" />
          </div>
          <p className="text-sm text-gray-400 text-center">{schemaError}</p>
          {selectedDatasourceId && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => loadDatasourceSchema(selectedDatasourceId, null as any)} // eslint-disable-line @typescript-eslint/no-explicit-any
              className="mt-4 text-brand-orange hover:text-brand-orange"
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              Retry
            </Button>
          )}
        </div>
      )}

      {/* Tables */}
      {effectiveSchema && !loadingSchema && (
        <div className={compact ? "max-h-96 overflow-y-auto space-y-3" : "space-y-3"}>
          {filteredTables.length > 0 ? (
            filteredTables.map(([tableName, tableData]) => {
              const table = tableData as DatabaseTable;
              const userAnnotation = getUserAnnotations(tableName);
              const tableDescription = userAnnotation?.semanticDescription || '';
              const isExpanded = expandedTables.has(tableName);

              return (
                <Card key={tableName} className={`p-4 border-gray-800 transition-colors ${userAnnotation?.redacted ? 'bg-[#120d0d] border-red-900/30' : 'bg-[#1a1a1a]'}`}>
                  <div className="mb-3">
                    <div className="flex items-center justify-between mb-2">
                <button
                  onClick={() => toggleTable(tableName)}
                  className="flex items-center gap-2 text-left flex-1 hover:text-brand-orange transition-colors"
                >
                  {isExpanded ? (
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-gray-400" />
                  )}
                  <h4 className="text-sm font-mono font-semibold text-white">{tableName}</h4>
                  <span className="text-xs text-gray-500">
                    {isMongoCollection(tableData)
                      ? `${tableData.sample_fields?.length || 0} fields`
                      : `${table.columns?.length || 0} columns`}
                  </span>
                </button>
                {enableEditing && (
                  <>
                    {editingTable === tableName ? (
                      <div className="flex gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleSaveTableDescription(tableName)}
                          className="h-6 w-6 p-0 text-green-400 hover:text-green-300"
                        >
                          <Check className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setEditingTable(null)}
                          className="h-6 w-6 p-0 text-gray-400 hover:text-gray-300"
                        >
                          <X className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1">
                        {selectedDatasourceId && canEditDatasource(selectedDatasource?.created_by) && (
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] text-gray-500">Redact</span>
                            <Switch
                              size="sm"
                              variant="destructive"
                              checked={!!userAnnotation?.redacted}
                              onCheckedChange={(checked) => toggleTableRedaction(selectedDatasourceId, tableName, checked)}
                            />
                          </div>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleEditTableDescription(tableName, tableDescription)}
                          className="h-6 w-6 p-0 text-gray-400 hover:text-white"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    )}
                  </>
                )}
              </div>

              {enableEditing && editingTable === tableName && (
                <textarea
                  value={tempDescription}
                  onChange={(e) => setTempDescription(e.target.value)}
                  className="w-full px-3 py-2 text-xs bg-[#0d0d0d] border border-gray-700 rounded-md text-gray-300 focus:outline-none focus:border-brand-orange resize-none"
                  rows={3}
                  placeholder="Describe what this table represents..."
                />
              )}
              {editingTable !== tableName && tableDescription && (
                <p className="text-xs text-gray-400 leading-relaxed">{tableDescription}</p>
              )}
              {editingTable !== tableName && !tableDescription && enableEditing && (
                <p className="text-xs text-gray-500 italic leading-relaxed">No description added yet. Click the edit icon to add one.</p>
              )}
            </div>

            {/* Columns / Fields */}
            {isExpanded && (
            <div className={`space-y-1.5 ${userAnnotation?.redacted ? 'opacity-40' : ''}`}>
              {isMongoCollection(tableData) ? (
                <>
                  <div className="flex items-center gap-2 mb-2">
                    <div className="h-px flex-1 bg-gray-800" />
                    <span className="text-[10px] text-gray-500 uppercase tracking-wider">
                      {tableData.sample_fields.length} fields
                    </span>
                    <div className="h-px flex-1 bg-gray-800" />
                  </div>

                  {tableData.sample_fields.map((fieldName: string) => {
                    const userColumnAnnotation = userAnnotation?.columns.find(c => c.name === fieldName);
                    const annotation = userColumnAnnotation?.annotation || '';
                    const isRedacted = userColumnAnnotation?.redacted || false;

                    return (
                      <div
                        key={fieldName}
                        className={`group flex items-center gap-2 p-2 rounded transition-colors ${isRedacted ? 'bg-[#120d0d]' : 'hover:bg-[#0d0d0d]'}`}
                      >
                        <div className={`flex-1 min-w-0 ${isRedacted ? 'opacity-40' : ''}`}>
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-xs font-mono text-white">{fieldName}</span>
                            <span className="text-[10px] text-gray-500">mongodb field</span>
                          </div>

                          {enableEditing && editingColumn?.table === tableName && editingColumn?.column === fieldName && (
                            <div className="flex items-center gap-1">
                              <input
                                type="text"
                                value={tempAnnotation}
                                onChange={(e) => setTempAnnotation(e.target.value)}
                                className="flex-1 px-2 py-1 text-[11px] bg-[#0d0d0d] border border-gray-700 rounded text-gray-300 focus:outline-none focus:border-brand-orange"
                                placeholder="Add annotation..."
                                autoFocus
                              />
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => handleSaveColumnAnnotation(tableName, fieldName)}
                                className="h-5 w-5 p-0 text-green-400 hover:text-green-300"
                              >
                                <Check className="w-3 h-3" />
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => setEditingColumn(null)}
                                className="h-5 w-5 p-0 text-gray-400 hover:text-gray-300"
                              >
                                <X className="w-3 h-3" />
                              </Button>
                            </div>
                          )}
                          {!(editingColumn?.table === tableName && editingColumn?.column === fieldName) && annotation && (
                            <div className="flex items-center gap-1 group">
                              <p className="text-[11px] text-gray-500 italic">{annotation}</p>
                              {enableEditing && (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => handleEditColumnAnnotation(tableName, fieldName, annotation)}
                                  className="h-4 w-4 p-0 opacity-0 group-hover:opacity-100 text-gray-500 hover:text-white"
                                >
                                  <Edit2 className="w-2.5 h-2.5" />
                                </Button>
                              )}
                            </div>
                          )}
                          {!(editingColumn?.table === tableName && editingColumn?.column === fieldName) && !annotation && enableEditing && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleEditColumnAnnotation(tableName, fieldName, '')}
                              className="h-5 text-[10px] px-1 py-0 text-gray-500 hover:text-brand-orange"
                            >
                              <Plus className="w-2.5 h-2.5 mr-1" />
                              Add note
                            </Button>
                          )}
                        </div>
                        {enableEditing && selectedDatasourceId && canEditDatasource(selectedDatasource?.created_by) && (
                          <div className="flex items-center gap-1.5 shrink-0">
                            <span className="text-[10px] text-gray-500">Redact</span>
                            <Switch
                              size="sm"
                              variant="destructive"
                              checked={isRedacted}
                              onCheckedChange={(checked) => toggleColumnRedaction(selectedDatasourceId, tableName, fieldName, checked)}
                            />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </>
              ) : (
                <>
                  <div className="flex items-center gap-2 mb-2">
                    <div className="h-px flex-1 bg-gray-800" />
                    <span className="text-[10px] text-gray-500 uppercase tracking-wider">
                      {table.columns?.length || 0} columns
                    </span>
                    <div className="h-px flex-1 bg-gray-800" />
                  </div>

                  {table.columns?.map((column: DatabaseColumn) => {
                const userColumnAnnotation = userAnnotation?.columns.find((c: { name: string }) => c.name === column.name);
                const annotation = userColumnAnnotation?.annotation || '';
                const isRedacted = userColumnAnnotation?.redacted || false;

                return (
                  <div
                    key={column.name}
                    className={`group flex items-center gap-2 p-2 rounded transition-colors ${isRedacted ? 'bg-[#120d0d]' : 'hover:bg-[#0d0d0d]'}`}
                  >
                    <div className={`flex-1 min-w-0 ${isRedacted ? 'opacity-40' : ''}`}>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-mono text-white">{column.name}</span>
                        <span className="text-[10px] text-gray-500">{column.type}</span>
                      </div>

                      {enableEditing && editingColumn?.table === tableName && editingColumn?.column === column.name && (
                        <div className="flex items-center gap-1">
                          <input
                            type="text"
                            value={tempAnnotation}
                            onChange={(e) => setTempAnnotation(e.target.value)}
                            className="flex-1 px-2 py-1 text-[11px] bg-[#0d0d0d] border border-gray-700 rounded text-gray-300 focus:outline-none focus:border-brand-orange"
                            placeholder="Add annotation..."
                            autoFocus
                          />
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleSaveColumnAnnotation(tableName, column.name)}
                            className="h-5 w-5 p-0 text-green-400 hover:text-green-300"
                          >
                            <Check className="w-3 h-3" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setEditingColumn(null)}
                            className="h-5 w-5 p-0 text-gray-400 hover:text-gray-300"
                          >
                            <X className="w-3 h-3" />
                          </Button>
                        </div>
                      )}
                      {!(editingColumn?.table === tableName && editingColumn?.column === column.name) && annotation && (
                        <div className="flex items-center gap-1 group">
                          <p className="text-[11px] text-gray-500 italic">{annotation}</p>
                          {enableEditing && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleEditColumnAnnotation(tableName, column.name, annotation)}
                              className="h-4 w-4 p-0 opacity-0 group-hover:opacity-100 text-gray-500 hover:text-white"
                            >
                              <Edit2 className="w-2.5 h-2.5" />
                            </Button>
                          )}
                        </div>
                      )}
                      {!(editingColumn?.table === tableName && editingColumn?.column === column.name) && !annotation && enableEditing && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleEditColumnAnnotation(tableName, column.name, '')}
                          className="h-5 text-[10px] px-1 py-0 text-gray-500 hover:text-brand-orange"
                        >
                          <Plus className="w-2.5 h-2.5 mr-1" />
                          Add note
                        </Button>
                      )}
                    </div>
                    {enableEditing && selectedDatasourceId && canEditDatasource(selectedDatasource?.created_by) && (
                      <div className="flex items-center gap-1.5 shrink-0">
                        <span className="text-[10px] text-gray-500">Redact</span>
                        <Switch
                          size="sm"
                          variant="destructive"
                          checked={isRedacted}
                          onCheckedChange={(checked) => toggleColumnRedaction(selectedDatasourceId, tableName, column.name, checked)}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
              </>
            )}
            </div>
            )}
          </Card>
        );
      })
    ) : (
      <div className="flex flex-col items-center justify-center py-12 px-6">
        <div className="w-12 h-12 rounded-full bg-gray-800 flex items-center justify-center mb-4">
          <Database className="w-6 h-6 text-gray-500" />
        </div>
        <p className="text-sm font-medium text-gray-400 mb-1">No tables found</p>
        <p className="text-xs text-gray-500 text-center">
          {searchQuery ? `No tables match "${searchQuery}"` : 'No tables in this datasource'}
        </p>
      </div>
    )}
        </div>
      )}
    </div>
  );
};

function UnderstandingStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-gray-800 bg-[#101010] p-3">
      <div className="text-[10px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-1 text-lg font-semibold text-white">{String(value)}</div>
    </div>
  );
}

function StatusChip({ label, tone = 'neutral' }: { label: string; tone?: 'ready' | 'warning' | 'danger' | 'info' | 'neutral' }) {
  const className = tone === 'ready'
    ? 'border-green-800/50 bg-green-950/30 text-green-300'
    : tone === 'warning'
      ? 'border-yellow-800/50 bg-yellow-950/30 text-yellow-300'
      : tone === 'danger'
        ? 'border-red-800/50 bg-red-950/30 text-red-300'
        : tone === 'info'
          ? 'border-blue-800/50 bg-blue-950/30 text-blue-300'
          : 'border-gray-700 bg-[#171717] text-gray-400';
  return <span className={`rounded-full border px-2 py-0.5 text-[10px] ${className}`}>{label}</span>;
}

function CandidateCard({
  candidate,
  loading,
  canReview,
  onAccept,
  onEdit,
  onReject,
}: {
  candidate: SourceSkillCandidate
  loading: boolean
  canReview: boolean
  onAccept: () => void
  onEdit: () => void
  onReject: () => void
}) {
  const evidenceSummary = candidate.evidence
    .slice(0, 3)
    .map(item => Array.isArray(item.title_path) ? item.title_path.join(' / ') : item.fragment_type)
    .join(' · ');

  return (
    <div className="rounded-md border border-gray-800 bg-[#101010] p-3">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-white">{candidate.title}</span>
            <StatusChip label={formatCandidateType(candidate.candidate_type)} tone="info" />
            <StatusChip label={candidate.validation_status} tone={validationTone(candidate.validation_status)} />
            <StatusChip label={candidate.review_status} tone={reviewTone(candidate.review_status)} />
            <span className="text-[10px] text-gray-500">{Math.round(candidate.confidence * 100)}% confidence</span>
            <span className="text-[10px] text-gray-600">{candidate.generator} v{candidate.version}</span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-gray-400">{candidate.statement}</p>
          {evidenceSummary && (
            <div className="mt-2 text-[11px] text-gray-600">
              Evidence: {evidenceSummary}
            </div>
          )}
        </div>
        {canReview && (
          <div className="flex shrink-0 flex-wrap gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={onAccept}
              disabled={loading || candidate.review_status === 'verified'}
              className="h-7 px-2 text-xs text-green-300 hover:text-green-200"
            >
              {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
              Accept
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={onEdit}
              disabled={loading}
              className="h-7 px-2 text-xs text-gray-400 hover:text-white"
            >
              <Edit2 className="h-3 w-3" />
              Edit
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={onReject}
              disabled={loading || candidate.review_status === 'rejected'}
              className="h-7 px-2 text-xs text-red-300 hover:text-red-200"
            >
              <X className="h-3 w-3" />
              Reject
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

function formatCandidateType(type: string) {
  switch (type) {
    case 'schema_map':
      return 'Schema Map';
    case 'data_profile':
      return 'Data Profile';
    case 'relationship':
      return 'Relationship/Join';
    case 'data_truth':
      return 'Data Truth';
    case 'quality_gotcha':
      return 'Quality/Gotchas';
    default:
      return type;
  }
}

function validationTone(status: string): 'ready' | 'warning' | 'danger' | 'neutral' {
  if (status === 'passed') return 'ready';
  if (status === 'warning' || status === 'not_run') return 'warning';
  if (status === 'failed') return 'danger';
  return 'neutral';
}

function reviewTone(status: string): 'ready' | 'warning' | 'danger' | 'neutral' {
  if (status === 'verified') return 'ready';
  if (status === 'suggested' || status === 'stale') return 'warning';
  if (status === 'rejected') return 'danger';
  return 'neutral';
}
