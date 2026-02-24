from __future__ import annotations

import re
import uuid
from datetime import datetime
from urllib.parse import quote

from fastapi import UploadFile

from app.core.config import settings

try:
    import oss2
except ImportError:  # pragma: no cover - validated during runtime usage
    oss2 = None


class OSSConfigError(RuntimeError):
    pass


def _sanitize_filename(filename: str | None) -> str:
    raw = (filename or "attachment").replace("\\", "/").split("/")[-1]
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._")
    return sanitized or "attachment"


def _build_object_key(filename: str | None) -> str:
    prefix = settings.aliyun_oss_prefix.strip("/")
    folder = settings.aliyun_oss_task_attachment_dir.strip("/") or "task-attachments"
    day_folder = datetime.utcnow().strftime("%Y%m%d")
    unique = uuid.uuid4().hex[:16]
    safe_name = _sanitize_filename(filename)
    key_parts = [part for part in [prefix, folder, day_folder, f"{unique}-{safe_name}"] if part]
    return "/".join(key_parts)


def _build_public_url(object_key: str) -> str:
    custom_base_url = settings.aliyun_oss_public_base_url.strip()
    if custom_base_url:
        return f"{custom_base_url.rstrip('/')}/{quote(object_key, safe='/')}"

    endpoint = settings.aliyun_oss_endpoint.replace("https://", "").replace("http://", "").strip("/")
    return f"https://{settings.aliyun_oss_bucket}.{endpoint}/{quote(object_key, safe='/')}"


def _build_bucket():
    if oss2 is None:
        raise OSSConfigError("缺少 oss2 依赖，请先安装 requirements.txt 中的依赖")

    if not settings.oss_enabled():
        raise OSSConfigError("OSS 配置不完整，请检查 config.py 或环境变量")

    endpoint = settings.aliyun_oss_endpoint
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"https://{endpoint}"

    auth = oss2.Auth(settings.aliyun_oss_access_key_id, settings.aliyun_oss_access_key_secret)
    return oss2.Bucket(auth, endpoint, settings.aliyun_oss_bucket)


def upload_task_attachment(file: UploadFile) -> tuple[str, str]:
    bucket = _build_bucket()
    object_key = _build_object_key(file.filename)

    headers = {}
    if file.content_type:
        headers["Content-Type"] = file.content_type

    file.file.seek(0)
    result = bucket.put_object(object_key, file.file, headers=headers or None)
    if getattr(result, "status", 200) >= 300:
        raise RuntimeError(f"OSS 上传失败，HTTP {result.status}")

    return _build_public_url(object_key), object_key
