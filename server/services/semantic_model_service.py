from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from server.models.connections import Connection
from server.models.datasets import Dataset
from server.models.semantic_models import (
    SemanticModel,
    SemanticModelAuditEvent,
    SemanticModelDimension,
    SemanticModelEntity,
    SemanticModelField,
    SemanticModelMetric,
    SemanticModelRelationship,
    SemanticModelVersion,
)
from server.services.file_operations import DataFrameFileService
from server.services.raw_query import AsyncRawQueryService
from server.tools.sql import DIALECT_MAP, validate_sql_query


def _json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return deepcopy(fallback)
    if isinstance(value, (dict, list)):
        return deepcopy(value)
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return deepcopy(fallback)


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _next_version(label: str) -> str:
    if label.startswith("v") and label[1:].isdigit():
        return f"v{int(label[1:]) + 1}"
    return "v1"


def _quote_identifier(name: str) -> str:
    cleaned = str(name).strip().replace('"', '""')
    if not cleaned:
        raise ValueError("Identifier cannot be empty")
    return ".".join(f'"{part}"' for part in cleaned.split("."))


def _table_reference(table: str, schema: str | None = None, datasource_kind: str | None = None) -> str:
    table_name = str(table).strip()
    schema_name = str(schema or "").strip()
    normalized_kind = str(datasource_kind or "").lower()
    if normalized_kind == "sqlite" and schema_name.lower() in {"sqlite", "main"}:
        schema_name = ""
    if normalized_kind == "duckdb" and schema_name.lower() in {"duckdb", "main", "projection"}:
        schema_name = ""
    if schema_name:
        return f"{_quote_identifier(schema_name)}.{_quote_identifier(table_name)}"
    return _quote_identifier(table_name)


def _query_rows(result: dict[str, Any]) -> Any:
    if result.get("result") is not None:
        return result.get("result")
    return result.get("data")


def _split_qualified_field(value: str) -> tuple[str, str] | None:
    parts = [part for part in str(value or "").split(".") if part]
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


@dataclass(frozen=True)
class _SemanticQueryTarget:
    kind: str
    db_type: str
    connection_id: str | None = None
    connection_obj: dict[str, Any] | None = None
    dataset_id: str | None = None


class SemanticModelService:
    @staticmethod
    async def load_model(session: AsyncSession, tenant_id: UUID, slug: str) -> SemanticModel | None:
        result = await session.execute(
            select(SemanticModel)
            .where(SemanticModel.tenant_id == tenant_id, SemanticModel.slug == slug)
            .options(
                selectinload(SemanticModel.entities).selectinload("*"),
                selectinload(SemanticModel.relationships),
                selectinload(SemanticModel.metrics),
                selectinload(SemanticModel.dimensions),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_models(session: AsyncSession, tenant_id: UUID) -> list[dict[str, Any]]:
        result = await session.execute(
            select(SemanticModel)
            .where(SemanticModel.tenant_id == tenant_id)
            .order_by(SemanticModel.updated_at.desc())
            .options(
                selectinload(SemanticModel.entities).selectinload("*"),
                selectinload(SemanticModel.relationships),
                selectinload(SemanticModel.metrics),
                selectinload(SemanticModel.dimensions),
            )
        )
        return [SemanticModelService.model_to_payload(model) for model in result.scalars().unique().all()]

    @staticmethod
    def model_to_payload(model: SemanticModel) -> dict[str, Any]:
        consumers = _json_load(model.consumers_json, {})
        explore = _json_load(model.explore_json, {})
        review = _json_load(model.review_json, {})
        mcp = _json_load(model.mcp_json, {})
        validation_log = _json_load(model.validation_log_json, [])
        entities = [
            {
                "id": entity.slug,
                "name": entity.name,
                "businessName": entity.business_name,
                "table": entity.table_name,
                "description": entity.description,
                "primaryKey": entity.primary_key,
                "schema": _json_load(entity.profile_json, {}).get("schema"),
                "profile": _json_load(entity.profile_json, {}),
                "fields": [
                    {
                        "name": field.name,
                        "sourceField": field.source_field,
                        "type": field.data_type,
                        "role": field.role,
                    }
                    for field in entity.fields
                ],
            }
            for entity in model.entities
        ]
        return {
            "id": model.slug,
            "name": model.name,
            "domain": model.domain,
            "owner": model.owner,
            "datasource": model.datasource_name,
            "datasourceId": model.datasource_id,
            "datasourceKind": model.datasource_kind,
            "status": model.status,
            "revision": model.revision,
            "draftRevision": model.draft_revision,
            "publishedVersion": model.published_version,
            "readiness": model.readiness,
            "readinessLevel": model.readiness_level,
            "driftAlerts": model.drift_alerts,
            "consumers": {
                "agents": int(consumers.get("agents", 0) or 0),
                "mcp": int(consumers.get("mcp", 0) or 0),
                "skills": int(consumers.get("skills", 0) or 0),
                "dashboards": int(consumers.get("dashboards", 0) or 0),
                "savedQueries": int(consumers.get("savedQueries", 0) or 0),
            },
            "updatedAt": model.updated_at.isoformat() if model.updated_at else "",
            "description": model.description,
            "entities": entities,
            "relationships": [
                {
                    "id": rel.slug,
                    "fromEntity": rel.from_entity,
                    "toEntity": rel.to_entity,
                    "label": rel.label,
                    "joinFields": _json_load(rel.join_fields_json, []),
                    "cardinality": rel.cardinality,
                    "fkEvidence": rel.fk_evidence,
                    "uniqueRate": rel.unique_rate,
                    "orphanRate": rel.orphan_rate,
                    "fanoutRisk": rel.fanout_risk,
                    "validationStatus": rel.validation_status,
                    "status": rel.status,
                    "validationMessage": rel.validation_message,
                }
                for rel in model.relationships
            ],
            "metrics": [
                {
                    "id": metric.slug,
                    "name": metric.name,
                    "businessName": metric.business_name,
                    "definition": metric.definition,
                    "kind": metric.kind,
                    "formula": metric.formula,
                    "filter": metric.filter_expr,
                    "timeField": metric.time_field,
                    "defaultGrain": metric.default_grain,
                    "dimensions": _json_load(metric.dimensions_json, []),
                    "unit": metric.unit,
                    "owner": metric.owner,
                    "certification": metric.certification,
                    "lineage": _json_load(metric.lineage_json, []),
                    "preview": _json_load(metric.preview_json, {}),
                }
                for metric in model.metrics
            ],
            "dimensions": [
                {
                    "id": dimension.slug,
                    "name": dimension.name,
                    "entityId": dimension.entity_slug,
                    "field": dimension.field,
                    "description": dimension.description,
                }
                for dimension in model.dimensions
            ],
            "calculatedFields": review.get("calculatedFields") or [],
            "suggestions": [],
            "readinessDetail": _json_load(
                review.get("readinessDetail"),
                {
                    "score": model.readiness,
                    "level": model.readiness_level,
                    "components": [],
                    "reliableQuestions": [],
                    "unreliableQuestions": [],
                    "blockers": [],
                    "warnings": [],
                },
            ),
            "explore": explore,
            "review": review,
            "mcp": mcp,
            "validationLog": validation_log,
        }

    @staticmethod
    async def update_model(
        session: AsyncSession,
        tenant_id: UUID,
        slug: str,
        payload: dict[str, Any],
        user_id: UUID | None,
    ) -> dict[str, Any] | None:
        model = await SemanticModelService.load_model(session, tenant_id, slug)
        if model is None:
            return None
        expected_revision = payload.get("expected_revision", payload.get("expectedRevision"))
        if expected_revision is None:
            raise ValueError("expected_revision is required for Semantic Model updates.")
        if int(expected_revision) != model.revision:
            raise RuntimeError(f"Semantic Model revision conflict: current revision is {model.revision}.")

        definition_changed = False
        for source, attr in (
            ("name", "name"),
            ("domain", "domain"),
            ("owner", "owner"),
            ("description", "description"),
        ):
            if source in payload and payload[source] is not None:
                setattr(model, attr, str(payload[source]))
                definition_changed = True

        if "explore" in payload and isinstance(payload["explore"], dict):
            model.explore_json = _json_dump(payload["explore"])
        if "consumers" in payload and isinstance(payload["consumers"], dict):
            model.consumers_json = _json_dump(payload["consumers"])
        if "review" in payload and isinstance(payload["review"], dict):
            model.review_json = _json_dump({**_json_load(model.review_json, {}), **payload["review"]})
        if isinstance(payload.get("calculatedFields"), list):
            review = _json_load(model.review_json, {})
            review["calculatedFields"] = payload["calculatedFields"]
            model.review_json = _json_dump(review)
            definition_changed = True
        if "mcp" in payload and isinstance(payload["mcp"], dict):
            mcp = {**_json_load(model.mcp_json, {}), **payload["mcp"]}
            if "rawSqlFallback" in payload["mcp"] and payload["mcp"]["rawSqlFallback"]:
                # Raw SQL fallback is deliberately gated server-side. The UI can
                # request it, but normal semantic model updates cannot enable it.
                mcp["rawSqlFallback"] = False
            model.mcp_json = _json_dump(mcp)

        if isinstance(payload.get("metrics"), list):
            await SemanticModelService._replace_metrics(session, model, payload["metrics"])
            definition_changed = True
        if isinstance(payload.get("relationships"), list):
            await SemanticModelService._replace_relationships(session, model, payload["relationships"])
            definition_changed = True
        if isinstance(payload.get("dimensions"), list):
            await SemanticModelService._replace_dimensions(session, model, payload["dimensions"])
            definition_changed = True
        if isinstance(payload.get("entities"), list):
            await SemanticModelService._replace_entities(session, model, payload["entities"])
            definition_changed = True

        model.revision += 1
        if definition_changed:
            model.status = "Draft"
            model.draft_revision = f"draft-{model.revision}"
        log_entry = "Draft updated." if definition_changed else "Workspace state updated."
        model.validation_log_json = _json_dump([log_entry, *_json_load(model.validation_log_json, [])])
        session.add(
            SemanticModelAuditEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                model_id=model.id,
                user_id=user_id,
                action="semantic_model_updated",
                details_json=_json_dump({"revision": model.revision}),
            )
        )
        await session.commit()
        return SemanticModelService.model_to_payload(await SemanticModelService.load_model(session, tenant_id, slug))

    @staticmethod
    async def _replace_metrics(session: AsyncSession, model: SemanticModel, items: list[dict[str, Any]]) -> None:
        existing = {metric.slug: metric for metric in model.metrics}
        seen: set[str] = set()
        for index, item in enumerate(items):
            slug = str(item.get("id") or item.get("name") or item.get("businessName") or "").strip()
            if not slug:
                raise ValueError("Metric id is required.")
            metric = existing.get(slug)
            if metric is None:
                metric = SemanticModelMetric(model_id=model.id, slug=slug, name=slug, formula="")
                session.add(metric)
            seen.add(slug)
            previous_definition = (
                metric.formula,
                metric.filter_expr,
                metric.time_field,
                metric.default_grain,
            )
            metric.name = str(item.get("name") or slug)
            metric.business_name = str(item.get("businessName") or item.get("business_name") or metric.name)
            metric.definition = str(item.get("definition") or "")
            metric.kind = str(item.get("kind") or "measure")
            metric.formula = str(item.get("formula") or "")
            metric.filter_expr = str(item.get("filter") or item.get("filter_expr") or "")
            metric.time_field = str(item.get("timeField") or item.get("time_field") or "")
            metric.default_grain = str(item.get("defaultGrain") or item.get("default_grain") or "month")
            metric.dimensions_json = _json_dump(item.get("dimensions") or [])
            metric.unit = str(item.get("unit") or "")
            metric.owner = str(item.get("owner") or model.owner)
            metric.certification = str(item.get("certification") or "draft")
            metric.lineage_json = _json_dump(item.get("lineage") or [])
            next_definition = (
                metric.formula,
                metric.filter_expr,
                metric.time_field,
                metric.default_grain,
            )
            if previous_definition != next_definition:
                metric.preview_json = _json_dump(
                    {
                        "currentValue": "Run query",
                        "trend": "",
                        "breakdown": [],
                        "explanation": metric.definition,
                        "sql": "",
                        "validation": "Metric definition changed. Run Validate and query_metric to refresh evidence.",
                    }
                )
                metric.compiled_sql = ""
                metric.validation_status = "warning"
            else:
                metric.preview_json = _json_dump(item.get("preview") or _json_load(metric.preview_json, {}))
                metric.compiled_sql = str((item.get("preview") or {}).get("sql") or metric.compiled_sql or "")
                metric.validation_status = str(
                    item.get("validationStatus")
                    or item.get("validation_status")
                    or metric.validation_status
                    or "warning"
                )
            metric.sort_order = index
        for slug, metric in existing.items():
            if slug not in seen:
                await session.delete(metric)

    @staticmethod
    async def _replace_relationships(session: AsyncSession, model: SemanticModel, items: list[dict[str, Any]]) -> None:
        existing = {relationship.slug: relationship for relationship in model.relationships}
        seen: set[str] = set()
        for index, item in enumerate(items):
            slug = str(item.get("id") or item.get("label") or "").strip()
            if not slug:
                raise ValueError("Relationship id is required.")
            relationship = existing.get(slug)
            if relationship is None:
                relationship = SemanticModelRelationship(model_id=model.id, slug=slug)
                session.add(relationship)
            seen.add(slug)
            relationship.from_entity = str(item.get("fromEntity") or item.get("from_entity") or "")
            relationship.to_entity = str(item.get("toEntity") or item.get("to_entity") or "")
            relationship.label = str(item.get("label") or slug)
            relationship.join_fields_json = _json_dump(item.get("joinFields") or item.get("join_fields") or [])
            relationship.cardinality = str(item.get("cardinality") or "many-to-one")
            relationship.fk_evidence = str(item.get("fkEvidence") or item.get("fk_evidence") or "")
            relationship.unique_rate = float(item.get("uniqueRate") or item.get("unique_rate") or 0)
            relationship.orphan_rate = float(item.get("orphanRate") or item.get("orphan_rate") or 0)
            relationship.fanout_risk = str(item.get("fanoutRisk") or item.get("fanout_risk") or "medium")
            relationship.validation_status = str(
                item.get("validationStatus") or item.get("validation_status") or "warning"
            )
            relationship.status = str(item.get("status") or "candidate")
            relationship.validation_message = str(item.get("validationMessage") or item.get("validation_message") or "")
            relationship.evidence_json = _json_dump(item.get("evidence") or [])
            relationship.sort_order = index
        for slug, relationship in existing.items():
            if slug not in seen:
                await session.delete(relationship)

    @staticmethod
    async def _replace_dimensions(session: AsyncSession, model: SemanticModel, items: list[dict[str, Any]]) -> None:
        existing = {dimension.slug: dimension for dimension in model.dimensions}
        seen: set[str] = set()
        for index, item in enumerate(items):
            slug = str(item.get("id") or item.get("name") or "").strip()
            if not slug:
                raise ValueError("Dimension id is required.")
            dimension = existing.get(slug)
            if dimension is None:
                dimension = SemanticModelDimension(model_id=model.id, slug=slug)
                session.add(dimension)
            seen.add(slug)
            dimension.name = str(item.get("name") or slug)
            dimension.entity_slug = str(item.get("entityId") or item.get("entity_slug") or "")
            dimension.field = str(item.get("field") or "")
            dimension.description = str(item.get("description") or "")
            dimension.sort_order = index
        for slug, dimension in existing.items():
            if slug not in seen:
                await session.delete(dimension)

    @staticmethod
    async def _replace_entities(session: AsyncSession, model: SemanticModel, items: list[dict[str, Any]]) -> None:
        existing = {entity.slug: entity for entity in model.entities}
        seen: set[str] = set()
        for index, item in enumerate(items):
            slug = str(item.get("id") or item.get("name") or "").strip()
            if not slug:
                raise ValueError("Entity id is required.")
            entity = existing.get(slug)
            if entity is None:
                entity = SemanticModelEntity(id=uuid4(), model_id=model.id, slug=slug)
                session.add(entity)
            seen.add(slug)
            entity.name = str(item.get("name") or slug)
            entity.business_name = str(item.get("businessName") or item.get("business_name") or entity.name)
            entity.table_name = str(item.get("table") or item.get("table_name") or entity.name)
            entity.description = str(item.get("description") or "")
            entity.primary_key = str(item.get("primaryKey") or item.get("primary_key") or "")
            entity.entity_type = str(item.get("entityType") or item.get("entity_type") or "dimension")
            entity.validation_status = str(item.get("validationStatus") or item.get("validation_status") or "valid")
            entity.profile_json = _json_dump(item.get("profile") or {})
            entity.lineage_json = _json_dump(item.get("lineage") or [])
            entity.permission_json = _json_dump(item.get("permission") or {})
            entity.sort_order = index
            await SemanticModelService._replace_entity_fields(session, entity, item.get("fields") or [])
        for slug, entity in existing.items():
            if slug not in seen:
                await session.delete(entity)

    @staticmethod
    async def _replace_entity_fields(
        session: AsyncSession, entity: SemanticModelEntity, items: list[dict[str, Any]]
    ) -> None:
        existing = {field.name: field for field in entity.fields}
        seen: set[str] = set()
        for index, item in enumerate(items):
            name = str(item.get("name") or item.get("sourceField") or item.get("source_field") or "").strip()
            if not name:
                continue
            field = existing.get(name)
            if field is None:
                field = SemanticModelField(entity_id=entity.id, name=name)
                session.add(field)
            seen.add(name)
            field.source_field = str(item.get("sourceField") or item.get("source_field") or name)
            field.data_type = str(item.get("type") or item.get("data_type") or "unknown")
            field.role = str(item.get("role") or "attribute")
            field.nullable = bool(item.get("nullable", True))
            field.profile_json = _json_dump(item.get("profile") or {})
            field.sort_order = index
        for name, field in existing.items():
            if name not in seen:
                await session.delete(field)

    @staticmethod
    def _readiness_detail(model: SemanticModel) -> dict[str, Any]:
        structural = 95 if model.entities and model.metrics else 45
        semantic = min(95, 50 + len(model.dimensions) * 7 + len(model.relationships) * 5 + len(model.metrics) * 10)
        blocked_relationships = [
            rel for rel in model.relationships if rel.validation_status == "blocked" and rel.status != "rejected"
        ]
        query = 90 if model.metrics else 35
        governance = 85 if all(metric.certification != "draft" for metric in model.metrics) else 68
        evidence = 80 if any(_json_load(metric.lineage_json, []) for metric in model.metrics) else 50
        blockers = []
        if not model.entities:
            blockers.append("No entities are defined.")
        if not model.metrics:
            blockers.append("No metrics are defined.")
        if blocked_relationships:
            blockers.append("Blocked relationships must be fixed or rejected.")
        score = round(structural * 0.2 + semantic * 0.25 + query * 0.25 + governance * 0.15 + evidence * 0.15)
        level = "blocked" if blockers else "ready" if score >= 85 else "warning"
        warnings = []
        if any(metric.certification == "draft" for metric in model.metrics):
            warnings.append("Some metrics are still draft certified.")
        return {
            "score": score,
            "level": level,
            "components": [
                {"id": "structural", "name": "Structural completeness", "score": structural, "status": "ready"},
                {
                    "id": "semantic",
                    "name": "Semantic completeness",
                    "score": semantic,
                    "status": "ready" if semantic >= 85 else "warning",
                },
                {
                    "id": "query",
                    "name": "Query correctness",
                    "score": query,
                    "status": "ready" if query >= 85 else "blocked",
                },
                {
                    "id": "governance",
                    "name": "Governance",
                    "score": governance,
                    "status": "ready" if governance >= 85 else "warning",
                },
                {
                    "id": "evidence",
                    "name": "Evidence coverage",
                    "score": evidence,
                    "status": "ready" if evidence >= 80 else "warning",
                },
            ],
            "reliableQuestions": [
                f"What is {metric.business_name} by available dimensions?" for metric in model.metrics
            ],
            "unreliableQuestions": []
            if not blockers
            else ["Questions requiring unresolved relationships are not reliable yet."],
            "blockers": blockers,
            "warnings": warnings,
        }

    @staticmethod
    async def validate_model(
        session: AsyncSession, tenant_id: UUID, slug: str, user_id: UUID | None
    ) -> dict[str, Any] | None:
        model = await SemanticModelService.load_model(session, tenant_id, slug)
        if model is None:
            return None
        model.status = "Validating"
        detail = SemanticModelService._readiness_detail(model)
        model.readiness = int(detail["score"])
        model.readiness_level = str(detail["level"])
        model.status = "Validation Failed" if detail["blockers"] else "Ready for Review"
        review = _json_load(model.review_json, {})
        review["readinessDetail"] = detail
        review["validationSummary"] = {
            "status": "passed" if not detail["blockers"] else "failed",
            "validatedAt": datetime.utcnow().isoformat(),
            "blockers": detail["blockers"],
        }
        model.review_json = _json_dump(review)
        model.validation_log_json = _json_dump(
            [f"Validated model: {review['validationSummary']['status']}", *_json_load(model.validation_log_json, [])]
        )
        session.add(
            SemanticModelAuditEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                model_id=model.id,
                user_id=user_id,
                action="semantic_model_validated",
                details_json=_json_dump(review["validationSummary"]),
            )
        )
        await session.commit()
        return SemanticModelService.model_to_payload(await SemanticModelService.load_model(session, tenant_id, slug))

    @staticmethod
    async def publish_model(
        session: AsyncSession, tenant_id: UUID, slug: str, user_id: UUID | None
    ) -> dict[str, Any] | None:
        model = await SemanticModelService.load_model(session, tenant_id, slug)
        if model is None:
            return None
        detail = SemanticModelService._readiness_detail(model)
        if detail["blockers"]:
            raise ValueError("Semantic Model cannot be published until validation blockers are resolved.")
        next_version = _next_version(model.published_version)
        model.status = "Published"
        model.published_version = next_version
        model.readiness = int(detail["score"])
        model.readiness_level = str(detail["level"])
        snapshot = SemanticModelService.model_to_payload(model)
        model.status = "Published"
        model.published_version = next_version
        model.readiness = int(detail["score"])
        model.readiness_level = str(detail["level"])
        review = _json_load(model.review_json, {})
        review.update(
            {
                "opened": True,
                "reviewed": True,
                "publishedAt": datetime.utcnow().isoformat(),
                "publishedVersion": next_version,
                "publishedSnapshot": snapshot,
                "readinessDetail": detail,
            }
        )
        model.review_json = _json_dump(review)
        mcp = _json_load(model.mcp_json, {})
        mcp.setdefault("rawSqlFallback", False)
        mcp["exposedVersion"] = next_version
        mcp["allowedMetrics"] = [metric.slug for metric in model.metrics]
        mcp["allowedDimensions"] = [dimension.slug for dimension in model.dimensions]
        model.mcp_json = _json_dump(mcp)
        model.validation_log_json = _json_dump(
            [f"Published {next_version}.", *_json_load(model.validation_log_json, [])]
        )
        source_snapshot_ids = SemanticModelService._source_snapshot_ids(review)
        session.add(
            SemanticModelVersion(
                id=uuid4(),
                tenant_id=tenant_id,
                model_id=model.id,
                version_label=next_version,
                revision=model.revision,
                snapshot_json=_json_dump(snapshot),
                source_snapshot_ids_json=_json_dump(source_snapshot_ids),
                physical_schema_json=_json_dump(SemanticModelService._physical_schema_payload(model)),
                review_json=_json_dump(
                    {
                        "source_snapshot": source_snapshot_ids[0] if source_snapshot_ids else None,
                        "source_snapshot_ids": source_snapshot_ids,
                        "lineage": review.get("sourceUnderstandingLineage", []),
                        "validation_summary": review.get("validationSummary", {}),
                    }
                ),
                published_by=user_id,
            )
        )
        session.add(
            SemanticModelAuditEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                model_id=model.id,
                user_id=user_id,
                action="semantic_model_published",
                details_json=_json_dump({"version": next_version}),
            )
        )
        await session.commit()
        return SemanticModelService.model_to_payload(await SemanticModelService.load_model(session, tenant_id, slug))

    @staticmethod
    def _source_snapshot_ids(review: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        for item in review.get("sourceUnderstandingLineage") or []:
            if isinstance(item, dict) and item.get("source_snapshot_id"):
                ids.append(str(item["source_snapshot_id"]))
        return list(dict.fromkeys(ids))

    @staticmethod
    def _physical_schema_payload(model: SemanticModel) -> dict[str, Any]:
        return {
            "datasource_id": model.datasource_id,
            "datasource_kind": model.datasource_kind,
            "entities": [
                {
                    "table": entity.table_name,
                    "primary_key": entity.primary_key,
                    "fields": [
                        {"name": field.source_field, "type": field.data_type, "role": field.role}
                        for field in entity.fields
                    ],
                }
                for entity in model.entities
            ],
        }

    @staticmethod
    def _metric_by_slug_or_name(model: SemanticModel, value: str | None) -> SemanticModelMetric | None:
        if not value:
            return model.metrics[0] if model.metrics else None
        normalized = value.lower()
        return next(
            (
                metric
                for metric in model.metrics
                if metric.slug.lower() == normalized
                or metric.name.lower() == normalized
                or metric.business_name.lower() == normalized
            ),
            None,
        )

    @staticmethod
    def _dimension_by_slug_or_name(model: SemanticModel, value: str | None) -> SemanticModelDimension | None:
        if not value:
            return None
        normalized = value.lower()
        return next(
            (
                dimension
                for dimension in model.dimensions
                if dimension.slug.lower() == normalized
                or dimension.name.lower() == normalized
                or dimension.field.lower() == normalized
            ),
            None,
        )

    @staticmethod
    def _compile_metric_sql(
        model: SemanticModel,
        metric: SemanticModelMetric,
        dimension: SemanticModelDimension | None,
    ) -> str:
        entity = SemanticModelService._query_entity(model.entities, metric.formula, metric.filter_expr, None)
        if entity is None:
            raise ValueError("Semantic Model has no entity to query.")
        entity_profile = _json_load(entity.profile_json, {})
        table_ref = _table_reference(entity.table_name, entity_profile.get("schema"), model.datasource_kind)
        select_parts: list[str] = []
        group_parts: list[str] = []
        join_clause = ""
        if dimension is not None:
            join_clause = SemanticModelService._join_clause_for_dimension(model, entity, dimension)
            field_expr = f"{_quote_identifier(dimension.entity_slug)}.{_quote_identifier(dimension.field)}"
            select_parts.append(f"{field_expr} AS {_quote_identifier(dimension.slug)}")
            group_parts.append(field_expr)
        metric_expr = metric.formula.strip()
        if not metric_expr:
            raise ValueError(f"Metric '{metric.slug}' has no formula.")
        select_parts.append(f"{metric_expr} AS {_quote_identifier(metric.slug)}")
        sql = f"SELECT {', '.join(select_parts)} FROM {table_ref} AS {_quote_identifier(entity.slug)}{join_clause}"
        if metric.filter_expr.strip():
            sql += f" WHERE {metric.filter_expr.strip()}"
        if group_parts:
            sql += f" GROUP BY {', '.join(group_parts)}"
        return sql

    @staticmethod
    def _payload_metric_by_slug_or_name(model: dict[str, Any], value: str | None) -> dict[str, Any] | None:
        metrics = model.get("metrics") or []
        if not metrics:
            return None
        if not value:
            return metrics[0]
        normalized = str(value).lower()
        return next(
            (
                metric
                for metric in metrics
                if str(metric.get("id", "")).lower() == normalized
                or str(metric.get("name", "")).lower() == normalized
                or str(metric.get("businessName", "")).lower() == normalized
            ),
            None,
        )

    @staticmethod
    def _payload_dimension_by_slug_or_name(model: dict[str, Any], value: str | None) -> dict[str, Any] | None:
        if not value:
            return None
        normalized = str(value).lower()
        return next(
            (
                dimension
                for dimension in model.get("dimensions") or []
                if str(dimension.get("id", "")).lower() == normalized
                or str(dimension.get("name", "")).lower() == normalized
                or str(dimension.get("field", "")).lower() == normalized
            ),
            None,
        )

    @staticmethod
    def _compile_payload_metric_sql(
        model: dict[str, Any],
        metric: dict[str, Any],
        dimension: dict[str, Any] | None,
    ) -> str:
        entities = model.get("entities") or []
        if not entities:
            raise ValueError("Published Semantic Model has no entity to query.")
        entity = SemanticModelService._payload_query_entity(
            entities,
            str(metric.get("formula") or ""),
            str(metric.get("filter") or ""),
            None,
        )
        if entity is None:
            raise ValueError("Published Semantic Model has no entity to query.")
        datasource_kind = str(model.get("datasourceKind") or model.get("datasource_kind") or "")
        table_ref = _table_reference(
            str(entity.get("table") or ""),
            entity.get("schema") or (entity.get("profile") or {}).get("schema"),
            datasource_kind,
        )
        select_parts: list[str] = []
        group_parts: list[str] = []
        join_clause = ""
        if dimension is not None:
            join_clause = SemanticModelService._payload_join_clause_for_dimension(model, entity, dimension)
            field_expr = f"{_quote_identifier(str(dimension.get('entityId') or ''))}.{_quote_identifier(str(dimension.get('field') or ''))}"
            select_parts.append(
                f"{field_expr} AS {_quote_identifier(str(dimension.get('id') or dimension.get('field')))}"
            )
            group_parts.append(field_expr)
        metric_expr = str(metric.get("formula") or "").strip()
        if not metric_expr:
            raise ValueError(f"Metric '{metric.get('id')}' has no formula.")
        select_parts.append(f"{metric_expr} AS {_quote_identifier(str(metric.get('id') or metric.get('name')))}")
        sql = f"SELECT {', '.join(select_parts)} FROM {table_ref} AS {_quote_identifier(str(entity.get('id') or entity.get('name')))}{join_clause}"
        if str(metric.get("filter") or "").strip():
            sql += f" WHERE {str(metric.get('filter')).strip()}"
        if group_parts:
            sql += f" GROUP BY {', '.join(group_parts)}"
        return sql

    @staticmethod
    def _query_entity(
        entities: list[SemanticModelEntity],
        formula: str,
        filter_expr: str,
        preferred_slug: str | None,
    ) -> SemanticModelEntity | None:
        if not entities:
            return None
        by_slug = {entity.slug: entity for entity in entities}
        if preferred_slug and preferred_slug in by_slug:
            return by_slug[preferred_slug]
        expression = f"{formula or ''} {filter_expr or ''}".lower()
        for entity in entities:
            if f"{entity.slug.lower()}." in expression:
                return entity
        return entities[0]

    @staticmethod
    def _join_clause_for_dimension(
        model: SemanticModel,
        base_entity: SemanticModelEntity,
        dimension: SemanticModelDimension,
    ) -> str:
        if dimension.entity_slug == base_entity.slug:
            return ""
        target = next((entity for entity in model.entities if entity.slug == dimension.entity_slug), None)
        if target is None:
            return ""
        for relationship in model.relationships:
            if relationship.from_entity == base_entity.slug and relationship.to_entity == target.slug:
                return SemanticModelService._relationship_join_clause(
                    relationship, target, datasource_kind=model.datasource_kind
                )
            if relationship.from_entity == target.slug and relationship.to_entity == base_entity.slug:
                return SemanticModelService._relationship_join_clause(
                    relationship,
                    target,
                    reverse=True,
                    datasource_kind=model.datasource_kind,
                )
        return ""

    @staticmethod
    def _relationship_join_clause(
        relationship: SemanticModelRelationship,
        target: SemanticModelEntity,
        *,
        reverse: bool = False,
        datasource_kind: str | None = None,
    ) -> str:
        join_fields = _json_load(relationship.join_fields_json, [])
        predicates: list[str] = []
        for join_field in join_fields:
            if not isinstance(join_field, dict):
                continue
            left = _split_qualified_field(str(join_field.get("to") if reverse else join_field.get("from") or ""))
            right = _split_qualified_field(str(join_field.get("from") if reverse else join_field.get("to") or ""))
            if not left or not right:
                continue
            predicates.append(
                f"{_quote_identifier(left[0])}.{_quote_identifier(left[1])} = "
                f"{_quote_identifier(right[0])}.{_quote_identifier(right[1])}"
            )
        if not predicates:
            return ""
        target_profile = _json_load(target.profile_json, {})
        target_ref = _table_reference(target.table_name, target_profile.get("schema"), datasource_kind)
        return f" LEFT JOIN {target_ref} AS {_quote_identifier(target.slug)} ON {' AND '.join(predicates)}"

    @staticmethod
    def _payload_query_entity(
        entities: list[dict[str, Any]],
        formula: str,
        filter_expr: str,
        preferred_slug: str | None,
    ) -> dict[str, Any] | None:
        if not entities:
            return None
        by_slug = {str(entity.get("id") or entity.get("name") or ""): entity for entity in entities}
        if preferred_slug and preferred_slug in by_slug:
            return by_slug[preferred_slug]
        expression = f"{formula or ''} {filter_expr or ''}".lower()
        for entity in entities:
            slug = str(entity.get("id") or entity.get("name") or "").lower()
            if slug and f"{slug}." in expression:
                return entity
        return entities[0]

    @staticmethod
    def _payload_join_clause_for_dimension(
        model: dict[str, Any],
        base_entity: dict[str, Any],
        dimension: dict[str, Any],
    ) -> str:
        base_slug = str(base_entity.get("id") or base_entity.get("name") or "")
        target_slug = str(dimension.get("entityId") or "")
        if not target_slug or target_slug == base_slug:
            return ""
        entities = model.get("entities") or []
        target = next(
            (entity for entity in entities if str(entity.get("id") or entity.get("name") or "") == target_slug), None
        )
        if target is None:
            return ""
        for relationship in model.get("relationships") or []:
            if relationship.get("fromEntity") == base_slug and relationship.get("toEntity") == target_slug:
                return SemanticModelService._payload_relationship_join_clause(
                    relationship,
                    target,
                    datasource_kind=str(model.get("datasourceKind") or model.get("datasource_kind") or ""),
                )
            if relationship.get("fromEntity") == target_slug and relationship.get("toEntity") == base_slug:
                return SemanticModelService._payload_relationship_join_clause(
                    relationship,
                    target,
                    reverse=True,
                    datasource_kind=str(model.get("datasourceKind") or model.get("datasource_kind") or ""),
                )
        return ""

    @staticmethod
    def _payload_relationship_join_clause(
        relationship: dict[str, Any],
        target: dict[str, Any],
        *,
        reverse: bool = False,
        datasource_kind: str | None = None,
    ) -> str:
        predicates: list[str] = []
        for join_field in relationship.get("joinFields") or []:
            if not isinstance(join_field, dict):
                continue
            left = _split_qualified_field(str(join_field.get("to") if reverse else join_field.get("from") or ""))
            right = _split_qualified_field(str(join_field.get("from") if reverse else join_field.get("to") or ""))
            if not left or not right:
                continue
            predicates.append(
                f"{_quote_identifier(left[0])}.{_quote_identifier(left[1])} = "
                f"{_quote_identifier(right[0])}.{_quote_identifier(right[1])}"
            )
        if not predicates:
            return ""
        target_ref = _table_reference(
            str(target.get("table") or ""),
            target.get("schema") or (target.get("profile") or {}).get("schema"),
            datasource_kind,
        )
        target_alias = str(target.get("id") or target.get("name") or "")
        return f" LEFT JOIN {target_ref} AS {_quote_identifier(target_alias)} ON {' AND '.join(predicates)}"

    @staticmethod
    async def _published_snapshot_payload(
        session: AsyncSession,
        model: SemanticModel,
    ) -> dict[str, Any] | None:
        version = await session.scalar(
            select(SemanticModelVersion).where(
                SemanticModelVersion.model_id == model.id,
                SemanticModelVersion.version_label == model.published_version,
            )
        )
        if version is None:
            return None
        return _json_load(version.snapshot_json, {})

    @staticmethod
    async def _resolve_query_target(
        session: AsyncSession,
        tenant_id: UUID,
        datasource_id: str,
    ) -> _SemanticQueryTarget:
        parsed_id: UUID | None = None
        try:
            parsed_id = UUID(str(datasource_id))
        except ValueError:
            parsed_id = None
        connection: Connection | None = None
        if parsed_id is not None:
            dataset = await session.scalar(
                select(Dataset)
                .where(Dataset.tenant_id == tenant_id, Dataset.id == parsed_id)
                .options(selectinload(Dataset.connection))
            )
            if dataset is not None and dataset.type == "connection" and dataset.connection is not None:
                connection = dataset.connection
            elif dataset is not None and dataset.type == "file":
                return _SemanticQueryTarget(
                    kind="file_dataset",
                    db_type="duckdb",
                    dataset_id=str(dataset.id),
                    connection_obj={
                        "dataset_id": str(dataset.id),
                        "dataset_type": "file",
                        "db_type": "duckdb",
                    },
                )
            if connection is None:
                connection = await session.scalar(
                    select(Connection).where(Connection.tenant_id == tenant_id, Connection.id == parsed_id)
                )
        if connection is None:
            raise ValueError("Published model datasource was not found.")
        connection_obj = await connection.get_decrypted_connection_obj(session)
        if not connection_obj:
            raise ValueError("Published model datasource credentials could not be decrypted.")
        return _SemanticQueryTarget(
            kind="connection",
            db_type=connection.type,
            connection_id=str(connection.id),
            connection_obj=connection_obj,
        )

    @staticmethod
    async def _execute_query_target(
        session: AsyncSession,
        target: _SemanticQueryTarget,
        *,
        query: str,
        limit: int,
        timeout: int,
    ) -> dict[str, Any]:
        if target.kind == "file_dataset":
            if not target.dataset_id:
                return {"success": False, "error": "Published model projected dataset was not found."}
            return await DataFrameFileService.execute_duckdb_query_on_dataset(
                session=session,
                dataset_id=target.dataset_id,
                query=query,
                limit=limit,
                timeout=timeout,
            )
        if not target.connection_id or target.connection_obj is None:
            return {"success": False, "error": "Published model datasource connection was not found."}
        return await AsyncRawQueryService.execute_raw_query(
            query=query,
            db_type=target.db_type,
            connection_id=target.connection_id,
            connection_obj=target.connection_obj,
            limit=limit,
            timeout=timeout,
        )

    @staticmethod
    async def run_query_metric(
        session: AsyncSession,
        tenant_id: UUID,
        slug: str,
        request: dict[str, Any],
        user_id: UUID | None,
    ) -> dict[str, Any] | None:
        model = await SemanticModelService.load_model(session, tenant_id, slug)
        if model is None:
            return None
        if model.published_version == "v0":
            raise RuntimeError("Semantic Model must be published before MCP metric queries can run.")
        published = await SemanticModelService._published_snapshot_payload(session, model)
        if published is not None:
            return await SemanticModelService._run_published_payload_query_metric(
                session=session,
                model=model,
                published=published,
                request=request,
                user_id=user_id,
            )
        metric = SemanticModelService._metric_by_slug_or_name(model, request.get("metric"))
        if metric is None:
            raise ValueError("Metric not found in Semantic Model.")
        dimension = SemanticModelService._dimension_by_slug_or_name(model, request.get("dimension"))
        if request.get("dimension") and dimension is None:
            raise ValueError("Dimension not found in Semantic Model.")
        mcp = _json_load(model.mcp_json, {})
        if metric.slug not in set(mcp.get("allowedMetrics") or [item.slug for item in model.metrics]):
            raise PermissionError("Metric is not exposed to MCP.")
        if dimension and dimension.slug not in set(
            mcp.get("allowedDimensions") or [item.slug for item in model.dimensions]
        ):
            raise PermissionError("Dimension is not exposed to MCP.")
        sql = SemanticModelService._compile_metric_sql(model, metric, dimension)
        query_target = await SemanticModelService._resolve_query_target(session, tenant_id, model.datasource_id)
        dialect = DIALECT_MAP.get(query_target.db_type)
        safe_sql = validate_sql_query(sql, dialect=dialect)
        result = await SemanticModelService._execute_query_target(
            session,
            query_target,
            query=safe_sql,
            limit=int(request.get("limit") or 100),
            timeout=int(request.get("timeout") or 30),
        )
        if result.get("success") is False or result.get("error"):
            return {
                "resolvedMetric": metric.business_name,
                "modelVersion": model.published_version,
                "status": "failed",
                "error": result.get("error") or "Semantic query failed",
                "sql": safe_sql,
                "lineage": _json_load(metric.lineage_json, []),
                "freshness": datetime.utcnow().isoformat(),
                "policyDecision": "allowed",
                "warnings": result.get("hint") or "",
            }
        payload = {
            "resolvedMetric": metric.business_name,
            "modelVersion": model.published_version,
            "status": "completed",
            "result": _query_rows(result),
            "returnedCount": result.get("returned_count"),
            "totalCount": result.get("total_count"),
            "limited": result.get("limited"),
            "sql": safe_sql,
            "lineage": _json_load(metric.lineage_json, []),
            "freshness": datetime.utcnow().isoformat(),
            "policyDecision": "allowed",
            "warnings": [],
        }
        mcp["lastResult"] = {
            "resolvedMetric": payload["resolvedMetric"],
            "modelVersion": payload["modelVersion"],
            "result": str(payload["result"][:1] if isinstance(payload["result"], list) else payload["result"]),
            "freshness": payload["freshness"],
            "lineage": payload["lineage"],
            "policyDecision": payload["policyDecision"],
        }
        model.mcp_json = _json_dump(mcp)
        model.validation_log_json = _json_dump(
            [f"MCP query_metric executed for {metric.slug}.", *_json_load(model.validation_log_json, [])]
        )
        session.add(
            SemanticModelAuditEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                model_id=model.id,
                user_id=user_id,
                action="semantic_query_metric",
                details_json=_json_dump({"metric": metric.slug, "dimension": dimension.slug if dimension else None}),
            )
        )
        await session.commit()
        return payload

    @staticmethod
    async def _run_published_payload_query_metric(
        session: AsyncSession,
        model: SemanticModel,
        published: dict[str, Any],
        request: dict[str, Any],
        user_id: UUID | None,
    ) -> dict[str, Any]:
        metric = SemanticModelService._payload_metric_by_slug_or_name(published, request.get("metric"))
        if metric is None:
            raise ValueError("Metric not found in published Semantic Model.")
        dimension = SemanticModelService._payload_dimension_by_slug_or_name(published, request.get("dimension"))
        if request.get("dimension") and dimension is None:
            raise ValueError("Dimension not found in published Semantic Model.")
        mcp = published.get("mcp") or _json_load(model.mcp_json, {})
        allowed_metrics = set(mcp.get("allowedMetrics") or [item.get("id") for item in published.get("metrics") or []])
        allowed_dimensions = set(
            mcp.get("allowedDimensions") or [item.get("id") for item in published.get("dimensions") or []]
        )
        if metric.get("id") not in allowed_metrics:
            raise PermissionError("Metric is not exposed to MCP.")
        if dimension and dimension.get("id") not in allowed_dimensions:
            raise PermissionError("Dimension is not exposed to MCP.")
        sql = SemanticModelService._compile_payload_metric_sql(published, metric, dimension)
        query_target = await SemanticModelService._resolve_query_target(session, model.tenant_id, model.datasource_id)
        safe_sql = validate_sql_query(sql, dialect=DIALECT_MAP.get(query_target.db_type))
        result = await SemanticModelService._execute_query_target(
            session,
            query_target,
            query=safe_sql,
            limit=int(request.get("limit") or 100),
            timeout=int(request.get("timeout") or 30),
        )
        payload = {
            "resolvedMetric": metric.get("businessName") or metric.get("name"),
            "modelVersion": model.published_version,
            "status": "completed" if not (result.get("success") is False or result.get("error")) else "failed",
            "result": _query_rows(result) if not result.get("error") else None,
            "error": result.get("error"),
            "returnedCount": result.get("returned_count"),
            "totalCount": result.get("total_count"),
            "limited": result.get("limited"),
            "sql": safe_sql,
            "lineage": metric.get("lineage") or [],
            "freshness": datetime.utcnow().isoformat(),
            "policyDecision": "allowed",
            "warnings": [] if not result.get("hint") else result.get("hint"),
        }
        mcp_state = _json_load(model.mcp_json, {})
        mcp_state["lastResult"] = {
            "resolvedMetric": payload["resolvedMetric"],
            "modelVersion": payload["modelVersion"],
            "result": str((payload["result"] or [])[:1] if isinstance(payload["result"], list) else payload["result"]),
            "freshness": payload["freshness"],
            "lineage": payload["lineage"],
            "policyDecision": payload["policyDecision"],
        }
        model.mcp_json = _json_dump(mcp_state)
        model.validation_log_json = _json_dump(
            [f"MCP query_metric executed for {metric.get('id')}.", *_json_load(model.validation_log_json, [])]
        )
        session.add(
            SemanticModelAuditEvent(
                id=uuid4(),
                tenant_id=model.tenant_id,
                model_id=model.id,
                user_id=user_id,
                action="semantic_query_metric",
                details_json=_json_dump(
                    {
                        "metric": metric.get("id"),
                        "dimension": dimension.get("id") if dimension else None,
                        "version": model.published_version,
                    }
                ),
            )
        )
        await session.commit()
        return payload
