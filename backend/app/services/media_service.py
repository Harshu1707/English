import io

from fastapi import HTTPException, UploadFile, status

from app.core.cloudinary_config import configure_cloudinary
from app.core.config import settings

# media_type (as stored on LessonMedia) -> (Cloudinary resource_type, allowed extensions)
MEDIA_TYPE_RULES = {
    "video": ("video", {"mp4", "mov", "webm", "mkv"}),
    "audio": ("video", {"mp3", "wav", "m4a", "ogg"}),  # Cloudinary serves audio via the video pipeline
    "thumbnail": ("image", {"jpg", "jpeg", "png", "webp"}),
    "image": ("image", {"jpg", "jpeg", "png", "webp"}),
}


def _extension(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def validate_upload(media_type: str, file: UploadFile) -> str:
    """Validate media_type/extension and return the Cloudinary resource_type to use."""
    rule = MEDIA_TYPE_RULES.get(media_type)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported media_type '{media_type}'. Expected one of: {', '.join(MEDIA_TYPE_RULES)}",
        )
    resource_type, allowed_extensions = rule
    ext = _extension(file.filename)
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{ext or 'unknown'}' is not allowed for media_type '{media_type}'. Allowed: {', '.join(sorted(allowed_extensions))}",
        )
    return resource_type


async def upload_to_cloudinary(file: UploadFile, *, resource_type: str, folder: str) -> dict:
    try:
        configure_cloudinary()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    contents = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_size_mb}MB limit",
        )

    import cloudinary.uploader  # imported lazily so config is applied first

    try:
        return cloudinary.uploader.upload(
            io.BytesIO(contents),
            resource_type=resource_type,
            folder=folder,
            use_filename=True,
            unique_filename=True,
            overwrite=False,
        )
    except Exception as exc:  # Cloudinary raises its own error classes; surface a safe message
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Upload to Cloudinary failed: {exc}")


def destroy_on_cloudinary(public_id: str, *, resource_type: str) -> None:
    try:
        configure_cloudinary()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    import cloudinary.uploader

    try:
        cloudinary.uploader.destroy(public_id, resource_type=resource_type)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Delete on Cloudinary failed: {exc}")


# ---------------------------------------------------------------------------
# Practice recordings (learner speech), as opposed to admin lesson media above.
# Browsers record as webm/ogg (Chrome, Firefox) or mp4/m4a (Safari); uploads add wav/mp3.
# ---------------------------------------------------------------------------
RECORDING_EXTENSIONS = {"webm", "ogg", "wav", "mp3", "m4a", "mp4"}


def sniff_audio_container(head: bytes) -> str | None:
    """Recognise an audio/video container from its first bytes (filenames and content-types
    are client-controlled, so they are never trusted on their own)."""
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if head[4:8] == b"ftyp":
        return "mp4"
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "mp3"
    return None


def validate_recording_upload(file: UploadFile, head: bytes) -> None:
    ext = _extension(file.filename)
    if ext not in RECORDING_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{ext or 'unknown'}' recordings are not supported. Allowed: {', '.join(sorted(RECORDING_EXTENSIONS))}",
        )
    if sniff_audio_container(head) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That file doesn't look like a valid audio recording.",
        )


def analysis_audio_url(public_id: str) -> str:
    """Signed Cloudinary URL that delivers a stored recording as MP3.

    Speech analysis gets one predictable format regardless of what the browser recorded
    (webm/opus, mp4/aac, ...); Cloudinary transcodes on delivery, so no ffmpeg is needed here.
    Signed, so it also works if the Cloudinary account has strict transformations enabled.
    """
    configure_cloudinary()
    import cloudinary.utils

    url, _options = cloudinary.utils.cloudinary_url(
        public_id, resource_type="video", format="mp3", secure=True, sign_url=True
    )
    return url

