-- Source Understanding schema proposal.
-- Integration Owner should rebuild/rebase this into the single Alembic head and choose down_revision.

CREATE TABLE source_understanding_runs (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  connection_id UUID NULL REFERENCES connections(id) ON DELETE SET NULL,
  datasource_id VARCHAR(120) NOT NULL,
  provider VARCHAR(60) NOT NULL CHECK (provider IN ('database')),
  status VARCHAR(30) NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
  analyzer_version VARCHAR(100) NOT NULL,
  source_snapshot_ids_json JSON NOT NULL,
  summary_json JSON NOT NULL,
  drift_json JSON NOT NULL,
  error_json JSON NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP NULL
);

CREATE INDEX ix_source_understanding_runs_tenant_id ON source_understanding_runs(tenant_id);
CREATE INDEX ix_source_understanding_runs_connection_id ON source_understanding_runs(connection_id);
CREATE INDEX ix_source_understanding_runs_datasource_id ON source_understanding_runs(datasource_id);
CREATE INDEX ix_source_understanding_runs_status ON source_understanding_runs(status);

CREATE TABLE source_skill_candidates (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  run_id UUID NOT NULL REFERENCES source_understanding_runs(id) ON DELETE CASCADE,
  resource_id UUID NOT NULL REFERENCES source_resources(id) ON DELETE CASCADE,
  snapshot_id UUID NOT NULL REFERENCES source_snapshots(id) ON DELETE CASCADE,
  candidate_type VARCHAR(40) NOT NULL CHECK (
    candidate_type IN ('schema_map', 'data_profile', 'relationship', 'data_truth', 'quality_gotcha')
  ),
  title VARCHAR(255) NOT NULL,
  statement TEXT NOT NULL,
  structured_payload_json JSON NOT NULL,
  evidence_ids_json JSON NOT NULL,
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
  validation_status VARCHAR(30) NOT NULL CHECK (validation_status IN ('not_run', 'passed', 'warning', 'failed')),
  validation_json JSON NOT NULL,
  review_status VARCHAR(30) NOT NULL CHECK (review_status IN ('suggested', 'verified', 'rejected', 'stale')),
  reviewed_at TIMESTAMP NULL,
  review_note TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_source_skill_candidates_tenant_id ON source_skill_candidates(tenant_id);
CREATE INDEX ix_source_skill_candidates_run_id ON source_skill_candidates(run_id);
CREATE INDEX ix_source_skill_candidates_resource_id ON source_skill_candidates(resource_id);
CREATE INDEX ix_source_skill_candidates_snapshot_id ON source_skill_candidates(snapshot_id);
CREATE INDEX ix_source_skill_candidates_candidate_type ON source_skill_candidates(candidate_type);
CREATE INDEX ix_source_skill_candidates_validation_status ON source_skill_candidates(validation_status);
CREATE INDEX ix_source_skill_candidates_review_status ON source_skill_candidates(review_status);

-- Existing enum/check updates needed in the integration migration:
-- source_resources.resource_type add database_catalog, database_schema, database_table.
-- evidence_fragments.fragment_type add database_catalog, database_schema, database_table,
-- database_column, database_sample, database_constraint.
