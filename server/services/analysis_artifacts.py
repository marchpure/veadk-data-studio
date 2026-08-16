from __future__ import annotations

import html
from copy import deepcopy
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.analysis_artifacts import AnalysisArtifact
from server.models.notebooks import Notebook


class AnalysisArtifactService:
    async def create_artifact(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        user_id: UUID | None,
        notebook_id: UUID,
        name: str,
        objective: str,
        definition: dict[str, Any],
        status: str,
    ) -> AnalysisArtifact:
        notebook = await session.scalar(select(Notebook).where(Notebook.tenant_id == tenant_id, Notebook.id == notebook_id))
        if notebook is None:
            raise ValueError("Notebook not found")

        artifact = AnalysisArtifact(
            tenant_id=tenant_id,
            notebook_id=notebook_id,
            name=name,
            objective=objective,
            definition_json=self.normalize_definition(name=name, objective=objective, definition=definition),
            status=status,
            created_by=user_id,
        )
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)
        return artifact

    async def list_artifacts(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        notebook_id: UUID | None = None,
    ) -> list[AnalysisArtifact]:
        stmt = select(AnalysisArtifact).where(AnalysisArtifact.tenant_id == tenant_id)
        if notebook_id:
            stmt = stmt.where(AnalysisArtifact.notebook_id == notebook_id)
        result = await session.execute(stmt.order_by(AnalysisArtifact.updated_at.desc()))
        return list(result.scalars().all())

    async def get_artifact(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
        artifact_id: UUID | str,
    ) -> AnalysisArtifact | None:
        return await session.scalar(
            select(AnalysisArtifact).where(AnalysisArtifact.tenant_id == tenant_id, AnalysisArtifact.id == artifact_id)
        )

    async def update_artifact(
        self,
        *,
        session: AsyncSession,
        artifact: AnalysisArtifact,
        name: str | None = None,
        objective: str | None = None,
        definition: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> AnalysisArtifact:
        if name is not None:
            artifact.name = name
        if objective is not None:
            artifact.objective = objective
        if definition is not None:
            artifact.definition_json = self.normalize_definition(
                name=artifact.name,
                objective=artifact.objective,
                definition=definition,
            )
            artifact.version += 1
        if status is not None:
            artifact.status = status
        await session.commit()
        await session.refresh(artifact)
        return artifact

    def normalize_definition(self, *, name: str, objective: str, definition: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(definition or {})
        normalized.setdefault("title", name)
        normalized.setdefault("objective", objective)
        normalized.setdefault("parameters", [])
        normalized.setdefault("sections", [])
        normalized.setdefault("source_snapshot_refs", [])
        normalized.setdefault("semantic_model_versions", [])
        return normalized

    def render_markdown(self, artifact: AnalysisArtifact) -> str:
        definition = artifact.definition_json or {}
        lines = [f"# {definition.get('title') or artifact.name}", ""]
        objective = definition.get("objective") or artifact.objective
        if objective:
            lines.extend([objective, ""])
        for block in definition.get("sections", []) or []:
            lines.extend(self._render_block_markdown(block))
        source_refs = definition.get("source_snapshot_refs") or []
        if source_refs:
            lines.extend(["## Source Snapshots", ""])
            for ref in source_refs:
                lines.append(f"- `{ref}`")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def render_html(self, artifact: AnalysisArtifact) -> str:
        markdown = self.render_markdown(artifact)
        paragraphs = []
        for line in markdown.splitlines():
            if line.startswith("# "):
                paragraphs.append(f"<h1>{html.escape(line[2:])}</h1>")
            elif line.startswith("## "):
                paragraphs.append(f"<h2>{html.escape(line[3:])}</h2>")
            elif line.startswith("- "):
                paragraphs.append(f"<li>{html.escape(line[2:])}</li>")
            elif line.strip():
                paragraphs.append(f"<p>{html.escape(line)}</p>")
        return (
            "<article class=\"analysis-artifact\">"
            + "\n".join(paragraphs)
            + "</article>"
        )

    def run_preflight(self, artifact: AnalysisArtifact) -> dict[str, Any]:
        definition = artifact.definition_json or {}
        required: list[str] = []
        for block in definition.get("sections", []) or []:
            block_type = block.get("type")
            if block_type in {"metric", "chart", "table"} and not (block.get("query_ref") or block.get("metric_ref")):
                required.append(f"{block.get('title', block_type)}: query_ref or metric_ref")
            if block_type in {"evidence", "finding"} and not block.get("evidence_refs"):
                required.append(f"{block.get('title', block_type)}: evidence_refs")
        return {
            "artifact_id": artifact.id,
            "status": "not_started",
            "message": "Artifact run preflight completed; execution scheduler is not wired in this slice.",
            "required_bindings": required,
        }

    def _render_block_markdown(self, block: dict[str, Any]) -> list[str]:
        title = block.get("title") or block.get("type", "Section").title()
        block_type = block.get("type", "narrative")
        lines = [f"## {title}", ""]
        if block_type == "metric":
            metric_ref = block.get("metric_ref") or block.get("query_ref") or "unbound_metric"
            lines.append(f"Metric: `{metric_ref}`")
        elif block_type == "chart":
            query_ref = block.get("query_ref") or "unbound_query"
            visualization = block.get("visualization") or {}
            lines.append(f"Chart query: `{query_ref}`")
            if visualization:
                lines.append(f"Visualization: `{visualization.get('type', 'unknown')}`")
        elif block_type == "table":
            query_ref = block.get("query_ref") or block.get("extracted_dataset_ref") or "unbound_table"
            lines.append(f"Table source: `{query_ref}`")
        elif block_type in {"finding", "narrative", "recommendation", "evidence"}:
            text = block.get("text") or block.get("body") or ""
            if text:
                lines.append(text)
        evidence_refs = block.get("evidence_refs") or []
        if evidence_refs:
            lines.append("")
            lines.append("Evidence:")
            lines.extend([f"- `{ref}`" for ref in evidence_refs])
        lines.append("")
        return lines
