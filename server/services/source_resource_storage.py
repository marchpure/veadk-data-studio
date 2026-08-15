from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import aiofiles

from server.config.storage import DEFAULT_DATA_DIR
from server.services.dataset_storage import DatasetStorageService


@dataclass(slots=True, frozen=True)
class StoredSourcePayload:
    absolute_path: Path
    raw_storage_uri: str
    size: int
    content_hash: str
    stored_filename: str


class SourceResourceStorageService:
    """Filesystem storage for immutable source snapshots."""

    @staticmethod
    def source_directory(tenant_id: UUID, resource_id: UUID) -> Path:
        root = DEFAULT_DATA_DIR / "source_resources" / str(tenant_id) / str(resource_id)
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    async def save_bytes(
        cls,
        *,
        tenant_id: UUID,
        resource_id: UUID,
        filename: str,
        data: bytes,
    ) -> StoredSourcePayload:
        directory = cls.source_directory(tenant_id=tenant_id, resource_id=resource_id)
        safe_name = DatasetStorageService.sanitize_filename(filename)
        digest = hashlib.sha256(data).hexdigest()
        stored_filename = f"{digest[:16]}-{safe_name}"
        destination = directory / stored_filename

        async with aiofiles.open(destination, "wb") as outfile:
            await outfile.write(data)

        return StoredSourcePayload(
            absolute_path=destination,
            raw_storage_uri=f"file://{destination}",
            size=len(data),
            content_hash=f"sha256:{digest}",
            stored_filename=stored_filename,
        )
