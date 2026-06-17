"""Storage for heavy artifact payloads (cube/feature COGs).

The agent never receives these bytes — only ``summary`` does — and the UI
fetches them as render URLs. v1 ships a local-filesystem store so the feature
needs no object-store dependency or running MinIO; a future S3/MinIO store
implements the same :class:`ArtifactStore` protocol and the service is unchanged
(ADR 0002 D3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import anyio

from geogent_backend.config import get_settings


class ArtifactStoreError(Exception):
    """A read/write against the artifact store failed."""


class ArtifactStore(Protocol):
    async def put(self, artifact_id: str, key: str, data: bytes) -> str:
        """Persist ``data`` under ``(artifact_id, key)``; return its storage URI."""

    async def get(self, artifact_id: str, key: str) -> bytes:
        """Read back the bytes stored under ``(artifact_id, key)``."""


class LocalArtifactStore:
    """Writes assets under ``<root>/<artifact_id>/<key>`` on the local disk."""

    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def _path(self, artifact_id: str, key: str) -> Path:
        # artifact_id is a server-generated uuid4 hex and key is a fixed asset
        # name from our own code — neither is caller-controlled, so there is no
        # path-traversal surface here. Guard anyway in case that changes.
        if "/" in artifact_id or ".." in artifact_id or ".." in key:
            raise ArtifactStoreError("Invalid artifact id or key")
        return self._root / artifact_id / key

    async def put(self, artifact_id: str, key: str, data: bytes) -> str:
        path = self._path(artifact_id, key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        try:
            await anyio.to_thread.run_sync(_write)
        except OSError as exc:
            raise ArtifactStoreError(f"Failed to write asset: {exc}") from exc
        return f"file://{path}"

    async def get(self, artifact_id: str, key: str) -> bytes:
        path = self._path(artifact_id, key)
        try:
            return await anyio.to_thread.run_sync(path.read_bytes)
        except FileNotFoundError as exc:
            raise ArtifactStoreError("Asset not found") from exc
        except OSError as exc:
            raise ArtifactStoreError(f"Failed to read asset: {exc}") from exc


def get_artifact_store() -> ArtifactStore:
    return LocalArtifactStore(get_settings().artifact_storage_dir)
