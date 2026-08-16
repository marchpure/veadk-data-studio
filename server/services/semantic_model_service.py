from __future__ import annotations

import json
from copy import deepcopy
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
    SemanticModelMetric,
)
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
            "status": model.status,
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
            "calculatedFields": [],
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
                {"id": "semantic", "name": "Semantic completeness", "score": semantic, "status": "ready" if semantic >= 85 else "warning"},
                {"id": "query", "name": "Query correctness", "score": query, "status": "ready" if query >= 85 else "blocked"},
                {"id": "governance", "name": "Governance", "score": governance, "status": "ready" if governance >= 85 else "warning"},
                {"id": "evidence", "name": "Evidence coverage", "score": evidence, "status": "ready" if evidence >= 80 else "warning"},
            ],
            "reliableQuestions": [f"What is {metric.business_name} by available dimensions?" for metric in model.metrics],
            "unreliableQuestions": [] if not blockers else ["Questions requiring unresolved relationships are not reliable yet."],
            "blockers": blockers,
            "warnings": warnings,
        }

    @staticmethod
    async def validate_model(session: AsyncSession, tenant_id: UUID, slug: str, user_id: UUID | None) -> dict[str, Any] | None:
        model = await SemanticModelService.load_model(session, tenant_id, slug)
        if model is None:
            return None
        detail = SemanticModelService._readiness_detail(model)
        model.readiness = int(detail["score"])
        model.readiness_level = str(detail["level"])
        review = _json_load(model.review_json, {})
        review["readinessDetail"] = detail
        review["validationSummary"] = {
            "status": "passed" if not detail["blockers"] else "blocked",
            "validatedAt": datetime.utcnow().isoformat(),
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
    async def publish_model(session: AsyncSession, tenant_id: UUID, slug: str, user_id: UUID | None) -> dict[str, Any] | None:
        model = await SemanticModelService.load_model(session, tenant_id, slug)
        if model is None:
            return None
        detail = SemanticModelService._readiness_detail(model)
        if detail["blockers"]:
            raise ValueError("Semantic Model cannot be published until validation blockers are resolved.")
        next_version = _next_version(model.published_version)
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
        model.validation_log_json = _json_dump([f"Published {next_version}.", *_json_load(model.validation_log_json, [])])
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
        entity = model.entities[0] if model.entities else None
        if entity is None:
            raise ValueError("Semantic Model has no entity to query.")
        table_ref = _quote_identifier(entity.table_name)
        select_parts: list[str] = []
        group_parts: list[str] = []
        if dimension is not None:
            field_expr = f"{_quote_identifier(dimension.entity_slug)}.{_quote_identifier(dimension.field)}"
            select_parts.append(f"{field_expr} AS {_quote_identifier(dimension.slug)}")
            group_parts.append(field_expr)
        metric_expr = metric.formula.strip()
        if not metric_expr:
            raise ValueError(f"Metric '{metric.slug}' has no formula.")
        select_parts.append(f"{metric_expr} AS {_quote_identifier(metric.slug)}")
        sql = f"SELECT {', '.join(select_parts)} FROM {table_ref} AS {_quote_identifier(entity.slug)}"
        if metric.filter_expr.strip():
            sql += f" WHERE {metric.filter_expr.strip()}"
        if group_parts:
            sql += f" GROUP BY {', '.join(group_parts)}"
        return sql

    @staticmethod
    async def _resolve_query_connection(
        session: AsyncSession,
        tenant_id: UUID,
        datasource_id: str,
    ) -> tuple[Connection, dict[str, Any]]:
        parsed_id: UUID | None = None
        try:
            parsed_id = UUID(str(datasource_id))
        except ValueError:
            parsed_id = None
        connection: Connection | None = None
        if parsed_id is not None:
            dataset = await session.scalar(
                select(Dataset).where(Dataset.tenant_id == tenant_id, Dataset.id == parsed_id).options(selectinload(Dataset.connection))
            )
            if dataset is not None and dataset.type == "connection" and dataset.connection is not None:
                connection = dataset.connection
            if connection is None:
                connection = await session.scalar(select(Connection).where(Connection.tenant_id == tenant_id, Connection.id == parsed_id))
        if connection is None:
            raise ValueError("Published model datasource connection was not found.")
        connection_obj = await connection.get_decrypted_connection_obj(session)
        if not connection_obj:
            raise ValueError("Published model datasource credentials could not be decrypted.")
        return connection, connection_obj

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
        if model.status != "Published" or model.published_version == "v0":
            raise RuntimeError("Semantic Model must be published before MCP metric queries can run.")
        metric = SemanticModelService._metric_by_slug_or_name(model, request.get("metric"))
        if metric is None:
            raise ValueError("Metric not found in Semantic Model.")
        dimension = SemanticModelService._dimension_by_slug_or_name(model, request.get("dimension"))
        if request.get("dimension") and dimension is None:
            raise ValueError("Dimension not found in Semantic Model.")
        mcp = _json_load(model.mcp_json, {})
        if metric.slug not in set(mcp.get("allowedMetrics") or [item.slug for item in model.metrics]):
            raise PermissionError("Metric is not exposed to MCP.")
        if dimension and dimension.slug not in set(mcp.get("allowedDimensions") or [item.slug for item in model.dimensions]):
            raise PermissionError("Dimension is not exposed to MCP.")
        sql = SemanticModelService._compile_metric_sql(model, metric, dimension)
        dialect = DIALECT_MAP.get(model.datasource_kind)
        safe_sql = validate_sql_query(sql, dialect=dialect)
        connection, connection_obj = await SemanticModelService._resolve_query_connection(session, tenant_id, model.datasource_id)
        result = await AsyncRawQueryService.execute_raw_query(
            query=safe_sql,
            db_type=connection.type,
            connection_id=str(connection.id),
            connection_obj=connection_obj,
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
            "result": result.get("result", result),
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
        model.validation_log_json = _json_dump([f"MCP query_metric executed for {metric.slug}.", *_json_load(model.validation_log_json, [])])
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
