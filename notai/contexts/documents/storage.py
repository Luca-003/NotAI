"""MinIO storage helper - async wrapper sopra il client minio sync."""

from __future__ import annotations

import asyncio
import hashlib
import io
from functools import lru_cache

from minio import Minio

from notai.config import get_settings


@lru_cache(maxsize=1)
def _client() -> Minio:
    s = get_settings()
    return Minio(
        f"{s.minio.host}:{s.minio.port}",
        access_key=s.minio.root_user,
        secret_key=s.minio.root_password.get_secret_value(),
        secure=False,
    )


async def put_blob(
    bucket: str,
    key: str,
    data: bytes,
    content_type: str,
) -> tuple[str, str]:
    """Carica un blob binario su MinIO. Ritorna (storage_uri, sha256_hex)."""
    sha = hashlib.sha256(data).hexdigest()

    def _put() -> None:
        _client().put_object(
            bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    await asyncio.to_thread(_put)
    return f"s3://{bucket}/{key}", sha


async def put_text(
    bucket: str,
    key: str,
    content: str,
    content_type: str = "text/markdown",
) -> tuple[str, str]:
    """Carica una stringa su MinIO. Ritorna (storage_uri, sha256_hex)."""
    return await put_blob(bucket, key, content.encode("utf-8"), content_type)


async def get_blob(bucket: str, key: str) -> bytes:
    """Legge un oggetto da MinIO come bytes."""

    def _get() -> bytes:
        r = _client().get_object(bucket, key)
        try:
            return r.read()
        finally:
            r.close()
            r.release_conn()

    return await asyncio.to_thread(_get)


async def get_text(bucket: str, key: str) -> str:
    """Legge un oggetto da MinIO come stringa UTF-8."""
    data = await get_blob(bucket, key)
    return data.decode("utf-8")


def parse_storage_uri(uri: str) -> tuple[str, str]:
    """Estrae (bucket, key) da uno storage_uri tipo s3://bucket/path/key."""
    if not uri.startswith("s3://"):
        raise ValueError(f"invalid storage_uri: {uri}")
    rest = uri[len("s3://"):]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise ValueError(f"invalid storage_uri: {uri}")
    return bucket, key


__all__ = [
    "get_blob",
    "get_text",
    "parse_storage_uri",
    "put_blob",
    "put_text",
]
