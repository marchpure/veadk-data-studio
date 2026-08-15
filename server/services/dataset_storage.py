from __future__ import annotations

"""
Dataset-aware filesystem utilities.

This module centralizes all logic for writing, reading, and cleaning up files
associated with file-based datasets. By funnelling operations through this
service we can switch storage strategies (local disk, network share, object
store) without rewriting routers or business logic.
"""

import asyncio
import hashlib
import os
import re
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import aiofiles

from server.config.storage import dataset_directory


class SupportsAsyncRead(Protocol):
    """Protocol describing the subset of UploadFile we rely on."""

    async def read(self, size: int = -1) -> bytes: ...
    async def seek(self, offset: int, whence: int = os.SEEK_SET) -> int: ...
    async def close(self) -> None: ...

    filename: str | None


SANITIZE_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(slots=True)
class StoredFileMetadata:
    """Metadata returned by storage operations."""

    dataset_id: str
    original_filename: str
    stored_filename: str
    absolute_path: Path
    relative_path: Path
    size: int
    checksum: str


class DatasetStorageService:
    """High-level helpers for managing dataset files on disk."""

    CHUNK_SIZE = 16 * 1024 * 1024  # 16MB stream chunks

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize user-provided filenames.

        Keeps alphanumeric characters plus ``._-`` and replaces all other
        characters with underscores. Leading periods are removed to avoid
        hidden files.
        """
        name = SANITIZE_PATTERN.sub("_", filename.strip())
        name = name.lstrip(".")
        return name or "file"

    @classmethod
    def dataset_raw_directory(cls, dataset_id: str) -> Path:
        """Return (and ensure) the dataset's raw file directory."""
        base = dataset_directory(dataset_id)
        raw_dir = base / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        return raw_dir

    @classmethod
    def dataset_duckdb_directory(cls, dataset_id: str) -> Path:
        """Return the directory for DuckDB artifacts for a dataset."""
        base = dataset_directory(dataset_id)
        duckdb_dir = base / "duckdb"
        duckdb_dir.mkdir(parents=True, exist_ok=True)
        return duckdb_dir

    @classmethod
    def _deduplicate_filename(cls, directory: Path, filename: str) -> str:
        """Ensure stored filenames remain unique within a directory."""
        candidate = filename
        stem = Path(filename).stem or "file"
        suffix = Path(filename).suffix

        counter = 1
        while (directory / candidate).exists():
            candidate = f"{stem}_{counter}{suffix}"
            counter += 1
        return candidate

    @classmethod
    async def save_upload(
        cls,
        dataset_id: str,
        upload: SupportsAsyncRead,
        desired_name: str | None = None,
    ) -> StoredFileMetadata:
        """
        Stream an uploaded file to disk.

        Args:
            dataset_id: Dataset the file belongs to.
            upload: File-like object (typically FastAPI's UploadFile).
            desired_name: Optional preferred filename override.

        Returns:
            StoredFileMetadata describing the saved file.
        """
        original_name = desired_name or upload.filename or "file"
        safe_name = cls.sanitize_filename(original_name)
        raw_dir = cls.dataset_raw_directory(dataset_id)
        stored_name = cls._deduplicate_filename(raw_dir, safe_name)
        destination = raw_dir / stored_name

        size = 0
        checksum = hashlib.sha256()

        # Ensure stream starts from the beginning.
        try:
            await upload.seek(0)
        except AttributeError:
            pass

        async with aiofiles.open(destination, "wb") as outfile:
            while True:
                chunk = await upload.read(cls.CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                checksum.update(chunk)
                await outfile.write(chunk)

        try:
            await upload.seek(0)
        except AttributeError:
            pass

        return StoredFileMetadata(
            dataset_id=dataset_id,
            original_filename=original_name,
            stored_filename=stored_name,
            absolute_path=destination,
            relative_path=destination.relative_to(dataset_directory(dataset_id)),
            size=size,
            checksum=checksum.hexdigest(),
        )

    @classmethod
    async def save_bytes(
        cls,
        dataset_id: str,
        filename: str,
        data: bytes,
    ) -> StoredFileMetadata:
        """Persist raw bytes (useful for tests or generated files)."""
        safe_name = cls.sanitize_filename(filename)
        raw_dir = cls.dataset_raw_directory(dataset_id)
        stored_name = cls._deduplicate_filename(raw_dir, safe_name)
        destination = raw_dir / stored_name

        async with aiofiles.open(destination, "wb") as outfile:
            await outfile.write(data)

        checksum = hashlib.sha256(data).hexdigest()

        return StoredFileMetadata(
            dataset_id=dataset_id,
            original_filename=filename,
            stored_filename=stored_name,
            absolute_path=destination,
            relative_path=destination.relative_to(dataset_directory(dataset_id)),
            size=len(data),
            checksum=checksum,
        )

    @classmethod
    async def read_in_chunks(cls, path: Path, chunk_size: int | None = None) -> AsyncIterator[bytes]:
        """Yield file contents without loading everything into memory."""
        size = chunk_size or cls.CHUNK_SIZE
        async with aiofiles.open(path, "rb") as infile:
            while True:
                chunk = await infile.read(size)
                if not chunk:
                    break
                yield chunk

    @classmethod
    async def delete_file(cls, dataset_id: str, relative_path: str | Path) -> None:
        """Remove a stored file if it exists."""
        dataset_dir = dataset_directory(dataset_id)
        target = dataset_dir / Path(relative_path)
        if target.exists():
            await asyncio.to_thread(target.unlink)

    @classmethod
    async def delete_dataset(cls, dataset_id: str) -> None:
        """Remove all on-disk assets for a dataset."""
        dataset_dir = dataset_directory(dataset_id)
        if dataset_dir.exists():
            await asyncio.to_thread(shutil.rmtree, dataset_dir, ignore_errors=True)
