import base64
import mimetypes
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from minio import Minio
from minio.error import S3Error


class StorageError(RuntimeError):
    """Kesalahan yang aman ditampilkan pada antarmuka pengguna."""


def _encode_text(value: str) -> str:
    return base64.urlsafe_b64encode((value or "").encode("utf-8")).decode("ascii")


def _decode_text(value: str | None) -> str:
    if not value:
        return ""
    try:
        return base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return value


def _metadata_value(metadata: dict[str, str], key: str) -> str:
    candidates = [key, key.lower(), f"x-amz-meta-{key}", f"X-Amz-Meta-{key}"]
    lowered = {str(k).lower(): str(v) for k, v in metadata.items()}
    for candidate in candidates:
        value = lowered.get(candidate.lower())
        if value is not None:
            return value
    return ""


class MinioStorage:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        region: str | None = None,
        public_endpoint: str | None = None,
    ) -> None:
        self.bucket = bucket

        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region=region or None,
        )

        self.public_client = Minio(
            public_endpoint or endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region=region or "us-east-1",
        )

    @classmethod
    def from_environment(cls) -> "MinioStorage":
        return cls(
            endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            bucket=os.getenv("MINIO_BUCKET", "gameplay-videos"),
            secure=os.getenv("MINIO_SECURE", "false").lower() in {"1", "true", "yes"},
            region=os.getenv("MINIO_REGION") or None,
            public_endpoint=os.getenv(
                "MINIO_PUBLIC_ENDPOINT",
                "localhost:9000",
            ),
        )

    def _ensure_bucket(self) -> None:
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except Exception as exc:
            raise StorageError(
                "Tidak dapat terhubung ke MinIO. Pastikan server MinIO aktif dan konfigurasi .env benar."
            ) from exc

    def upload_video(
        self,
        file_path: str,
        original_filename: str,
        title: str,
        game: str,
        category: str,
        description: str,
    ) -> str:
        self._ensure_bucket()
        now = datetime.now(timezone.utc)
        extension = Path(original_filename).suffix.lower()
        object_name = f"videos/{now:%Y/%m}/{uuid.uuid4().hex}_{Path(original_filename).stem}{extension}"
        content_type = mimetypes.guess_type(original_filename)[0] or "application/octet-stream"
        metadata = {
            "title-b64": _encode_text(title),
            "game-b64": _encode_text(game),
            "category-b64": _encode_text(category),
            "description-b64": _encode_text(description),
            "original-name-b64": _encode_text(original_filename),
            "uploaded-at": now.isoformat(),
        }
        try:
            self.client.fput_object(
                bucket_name=self.bucket,
                object_name=object_name,
                file_path=file_path,
                content_type=content_type,
                metadata=metadata,
            )
            return object_name
        except Exception as exc:
            raise StorageError("Upload gagal. Periksa koneksi MinIO dan kapasitas penyimpanan.") from exc

    def _to_video_dict(self, object_item: Any, stat: Any) -> dict[str, Any]:
        metadata = stat.metadata or {}
        uploaded_raw = _metadata_value(metadata, "uploaded-at")
        uploaded_at = uploaded_raw or (
            object_item.last_modified.isoformat() if object_item.last_modified else ""
        )
        original_name = _decode_text(_metadata_value(metadata, "original-name-b64"))
        title = _decode_text(_metadata_value(metadata, "title-b64"))
        game = _decode_text(_metadata_value(metadata, "game-b64"))
        category = _decode_text(_metadata_value(metadata, "category-b64")) or "Gameplay"
        description = _decode_text(_metadata_value(metadata, "description-b64"))

        fallback_name = Path(object_item.object_name).name.split("_", 1)[-1]
        original_name = original_name or fallback_name
        title = title or Path(original_name).stem.replace("_", " ").title()

        return {
            "object_name": object_item.object_name,
            "title": title,
            "game": game,
            "category": category,
            "description": description,
            "original_name": original_name,
            "size": int(getattr(object_item, "size", 0) or getattr(stat, "size", 0) or 0),
            "content_type": getattr(stat, "content_type", None) or "application/octet-stream",
            "uploaded_at": uploaded_at,
            "last_modified": object_item.last_modified,
        }

    def list_videos(self, query: str = "") -> list[dict[str, Any]]:
        self._ensure_bucket()
        videos: list[dict[str, Any]] = []
        try:
            for item in self.client.list_objects(self.bucket, prefix="videos/", recursive=True):
                stat = self.client.stat_object(self.bucket, item.object_name)
                video = self._to_video_dict(item, stat)
                haystack = " ".join(
                    [video["title"], video["game"], video["category"], video["original_name"]]
                ).lower()
                if not query or query.lower() in haystack:
                    videos.append(video)
        except S3Error as exc:
            raise StorageError(f"Gagal membaca isi bucket: {exc.code}.") from exc
        except Exception as exc:
            raise StorageError("Gagal membaca daftar video dari MinIO.") from exc

        return sorted(
            videos,
            key=lambda item: item["last_modified"] or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

    def get_video(self, object_name: str) -> dict[str, Any]:
        self._ensure_bucket()
        try:
            stat = self.client.stat_object(self.bucket, object_name)
            object_stub = type(
                "ObjectStub",
                (),
                {
                    "object_name": object_name,
                    "size": stat.size,
                    "last_modified": stat.last_modified,
                },
            )()
            return self._to_video_dict(object_stub, stat)
        except Exception as exc:
            raise StorageError("Video tidak ditemukan atau tidak dapat dibaca.") from exc

    def presigned_url(self, object_name: str, download: bool = False) -> str:
        self._ensure_bucket()
        response_headers = None
        if download:
            video = self.get_video(object_name)
            safe_name = video["original_name"].replace('"', "")
            response_headers = {
                "response-content-disposition": f'attachment; filename="{safe_name}"'
            }
        try:
            return self.public_client.presigned_get_object(
                self.bucket,
                object_name,
                expires=timedelta(hours=1),
                response_headers=response_headers,
            )
        except Exception as exc:
            raise StorageError("Tautan video tidak dapat dibuat.") from exc

    def delete_video(self, object_name: str) -> None:
        self._ensure_bucket()
        try:
            self.client.remove_object(self.bucket, object_name)
        except Exception as exc:
            raise StorageError("Video gagal dihapus dari bucket.") from exc
