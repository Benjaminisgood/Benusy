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


def _normalize_endpoint(endpoint: str, *, force_http: bool = False) -> str:
    raw = endpoint.strip()
    if raw.startswith("http://"):
        host = raw.replace("http://", "", 1).strip("/")
        scheme = "http"
    elif raw.startswith("https://"):
        host = raw.replace("https://", "", 1).strip("/")
        scheme = "https"
    else:
        host = raw.strip("/")
        scheme = "https"

    if force_http:
        scheme = "http"
    return f"{scheme}://{host}"


def _sanitize_filename(filename: str | None) -> str:
    raw = (filename or "attachment").replace("\\", "/").split("/")[-1]
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._")
    return sanitized or "attachment"


def _build_object_key(filename: str | None, *, folder: str) -> str:
    prefix = settings.aliyun_oss_prefix.strip("/")
    target_folder = folder.strip("/")
    day_folder = datetime.utcnow().strftime("%Y%m%d")
    unique = uuid.uuid4().hex[:16]
    safe_name = _sanitize_filename(filename)
    key_parts = [part for part in [prefix, target_folder, day_folder, f"{unique}-{safe_name}"] if part]
    return "/".join(key_parts)


def _build_public_url(object_key: str, *, force_http: bool = False) -> str:
    custom_base_url = settings.aliyun_oss_public_base_url.strip()
    if custom_base_url:
        return f"{custom_base_url.rstrip('/')}/{quote(object_key, safe='/')}"

    normalized = _normalize_endpoint(settings.aliyun_oss_endpoint, force_http=force_http)
    scheme, endpoint = normalized.split("://", 1)
    return f"{scheme}://{settings.aliyun_oss_bucket}.{endpoint}/{quote(object_key, safe='/')}"


def _build_session():
    session = oss2.Session()
    # Ignore HTTP(S)_PROXY from runtime env to avoid proxy-induced OSS failures.
    session.session.trust_env = False
    return session


def _build_bucket(*, force_http: bool = False, is_path_style: bool = False):
    if oss2 is None:
        raise OSSConfigError("缺少 oss2 依赖，请先安装 requirements.txt 中的依赖")

    if not settings.oss_enabled():
        raise OSSConfigError("OSS 配置不完整，请检查 config.py 或环境变量")

    endpoint = _normalize_endpoint(settings.aliyun_oss_endpoint, force_http=force_http)

    auth = oss2.Auth(settings.aliyun_oss_access_key_id, settings.aliyun_oss_access_key_secret)
    return oss2.Bucket(
        auth,
        endpoint,
        settings.aliyun_oss_bucket,
        session=_build_session(),
        is_path_style=is_path_style,
    )


def _should_retry_with_http(exc: Exception) -> bool:
    details = str(exc)
    return any(
        token in details
        for token in [
            "SSLEOFError",
            "UNEXPECTED_EOF_WHILE_READING",
            "Connection aborted.",
            "RemoteDisconnected",
            "RequestError",
        ]
    )


def _upload_payload(
    *,
    object_key: str,
    payload: bytes,
    content_type: str | None = None,
) -> tuple[str, str]:
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type

    used_http_fallback = False
    last_exc: Exception | None = None
    attempts = [
        {"force_http": False, "is_path_style": False},
        {"force_http": False, "is_path_style": True},
        {"force_http": True, "is_path_style": False},
        {"force_http": True, "is_path_style": True},
    ]
    failure_messages: list[str] = []
    result = None
    for attempt in attempts:
        mode = f"{'http' if attempt['force_http'] else 'https'}|{'path' if attempt['is_path_style'] else 'virtual'}"
        try:
            bucket = _build_bucket(
                force_http=attempt["force_http"],
                is_path_style=attempt["is_path_style"],
            )
            result = bucket.put_object(object_key, payload, headers=headers or None)
            used_http_fallback = attempt["force_http"]
            break
        except Exception as exc:
            last_exc = exc
            failure_messages.append(f"{mode}: {exc}")
            if not _should_retry_with_http(exc):
                raise

    if result is None and last_exc is not None:
        raise RuntimeError("OSS 多策略上传失败: " + " ; ".join(failure_messages)) from last_exc

    if getattr(result, "status", 200) >= 300:
        raise RuntimeError(f"OSS 上传失败，HTTP {result.status}")

    return _build_public_url(object_key, force_http=used_http_fallback), object_key


def upload_task_attachment(file: UploadFile) -> tuple[str, str]:
    folder = settings.aliyun_oss_task_attachment_dir.strip("/") or "task-attachments"
    object_key = _build_object_key(file.filename, folder=folder)
    file.file.seek(0)
    payload = file.file.read() or b""
    return _upload_payload(
        object_key=object_key,
        payload=payload,
        content_type=file.content_type,
    )


def upload_payout_qr_code(
    *,
    file: UploadFile,
    user_id: int,
    method: str,
) -> tuple[str, str]:
    folder = settings.aliyun_oss_payout_qr_dir.strip("/") or "payout-qrcodes"
    safe_method = method if method in {"wechat_pay", "alipay"} else "other"
    target_folder = "/".join([folder, safe_method, f"user-{user_id}"])
    object_key = _build_object_key(file.filename, folder=target_folder)
    file.file.seek(0)
    payload = file.file.read() or b""
    return _upload_payload(
        object_key=object_key,
        payload=payload,
        content_type=file.content_type,
    )
