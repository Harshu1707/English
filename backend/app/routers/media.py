from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.database.session import get_db
from app.models.models import Lesson, LessonMedia, User
from app.schemas.contracts import LessonMediaOut
from app.services.media_service import destroy_on_cloudinary, upload_to_cloudinary, validate_upload

router = APIRouter(prefix="/admin/media", tags=["admin-media"])

CLOUDINARY_FOLDER = "verba/lessons"


def _get_lesson_or_404(db: Session, lesson_id: int) -> Lesson:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    return lesson


def _get_media_or_404(db: Session, media_id: int) -> LessonMedia:
    media = db.get(LessonMedia, media_id)
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    return media


@router.get("/lesson/{lesson_id}", response_model=list[LessonMediaOut])
def list_lesson_media(
    lesson_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    _get_lesson_or_404(db, lesson_id)
    return db.query(LessonMedia).filter(LessonMedia.lesson_id == lesson_id).all()


@router.post("/lesson/{lesson_id}", response_model=LessonMediaOut, status_code=status.HTTP_201_CREATED)
async def upload_lesson_media(
    lesson_id: int,
    media_type: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
    file: UploadFile = File(...),
):
    """Upload a lesson video, podcast/audio file, or thumbnail image to Cloudinary
    and record its metadata against the given lesson.
    """
    _get_lesson_or_404(db, lesson_id)
    resource_type = validate_upload(media_type, file)
    result = await upload_to_cloudinary(file, resource_type=resource_type, folder=CLOUDINARY_FOLDER)

    media = LessonMedia(
        lesson_id=lesson_id,
        url=result["secure_url"],
        media_type=media_type,
        provider="cloudinary",
        public_id=result.get("public_id"),
        resource_type=result.get("resource_type"),
        format=result.get("format"),
        width=result.get("width"),
        height=result.get("height"),
        file_size=result.get("bytes"),
        duration_seconds=int(result["duration"]) if result.get("duration") else None,
        original_filename=file.filename,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


@router.put("/{media_id}", response_model=LessonMediaOut)
async def replace_lesson_media(
    media_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
    file: UploadFile = File(...),
):
    """Replace the file behind an existing media record: upload the new asset first,
    then swap the database row, then remove the old Cloudinary asset last so a failed
    upload never leaves the lesson without working media.
    """
    media = _get_media_or_404(db, media_id)
    resource_type = validate_upload(media.media_type, file)
    result = await upload_to_cloudinary(file, resource_type=resource_type, folder=CLOUDINARY_FOLDER)

    old_public_id, old_resource_type = media.public_id, media.resource_type

    media.url = result["secure_url"]
    media.provider = "cloudinary"
    media.public_id = result.get("public_id")
    media.resource_type = result.get("resource_type")
    media.format = result.get("format")
    media.width = result.get("width")
    media.height = result.get("height")
    media.file_size = result.get("bytes")
    media.duration_seconds = int(result["duration"]) if result.get("duration") else None
    media.original_filename = file.filename
    db.commit()
    db.refresh(media)

    if old_public_id:
        try:
            destroy_on_cloudinary(old_public_id, resource_type=old_resource_type or resource_type)
        except HTTPException:
            # New media already saved; the old asset is now orphaned and can be
            # cleaned up later rather than reporting a failed replace to the admin.
            pass

    return media


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lesson_media(
    media_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    media = _get_media_or_404(db, media_id)
    if media.public_id:
        destroy_on_cloudinary(media.public_id, resource_type=media.resource_type or "image")
    db.delete(media)
    db.commit()
    return None
