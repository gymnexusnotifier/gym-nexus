import os
import mimetypes
import uuid

from app.core.config import settings

UPLOAD_DIR = "uploads"
R2_PREFIX = "member-photos"
SUPPORT_MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
SUPPORT_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _r2_client():
    if not all((settings.r2_access_key_id, settings.r2_secret_access_key, settings.r2_bucket_name, settings.r2_endpoint_url)):
        return None
    try:
        import boto3
        return boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )
    except Exception:
        return None


def _r2_key(gym_id: str, member_id: str, extension: str) -> str:
    return f"{R2_PREFIX}/{gym_id}/{member_id}.{extension.lower()}"


def save_member_photo(gym_id: str, member_id: str, file_bytes: bytes, extension: str = "jpg") -> str:
    client = _r2_client()
    if client:
        key = _r2_key(gym_id, member_id, extension)
        client.put_object(
            Bucket=settings.r2_bucket_name,
            Key=key,
            Body=file_bytes,
            ContentType=f"image/{extension.lower()}",
        )
        return f"r2://{key}"

    gym_dir = os.path.join(UPLOAD_DIR, str(gym_id))
    os.makedirs(gym_dir, exist_ok=True)
    path = os.path.join(gym_dir, f"{member_id}.{extension}")
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path


def is_r2_photo(photo_path: str | None) -> bool:
    return bool(photo_path and photo_path.startswith("r2://"))


def get_member_photo(photo_path: str) -> bytes:
    if is_r2_photo(photo_path):
        client = _r2_client()
        if not client:
            raise FileNotFoundError("R2 storage is not configured")
        key = photo_path.removeprefix("r2://")
        return client.get_object(Bucket=settings.r2_bucket_name, Key=key)["Body"].read()
    with open(photo_path, "rb") as file:
        return file.read()


def member_photo_exists(photo_path: str | None) -> bool:
    if not photo_path:
        return False
    if not is_r2_photo(photo_path):
        return os.path.exists(photo_path)
    client = _r2_client()
    if not client:
        return False
    try:
        client.head_object(Bucket=settings.r2_bucket_name, Key=photo_path.removeprefix("r2://"))
        return True
    except Exception:
        return False


def member_photo_content_type(photo_path: str) -> str:
    return mimetypes.guess_type(photo_path)[0] or "image/jpeg"


def save_support_attachment(gym_id: str, ticket_id: str, file_bytes: bytes, content_type: str, extension: str) -> str:
    key = f"support/{gym_id}/{ticket_id}/{uuid.uuid4().hex}.{extension.lower()}"
    client = _r2_client()
    if client:
        client.put_object(Bucket=settings.r2_bucket_name, Key=key, Body=file_bytes, ContentType=content_type)
        return f"r2://{key}"
    directory = os.path.join(UPLOAD_DIR, "support", str(gym_id), str(ticket_id))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, key.rsplit("/", 1)[-1])
    with open(path, "wb") as file:
        file.write(file_bytes)
    return path


def get_support_attachment(storage_path: str) -> bytes:
    return get_member_photo(storage_path)
