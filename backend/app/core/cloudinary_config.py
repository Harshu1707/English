"""Server-side Cloudinary configuration.

Never imported from client code. The API secret must never reach the browser;
only this module (and code that calls into it on the server) ever touches it.
"""
import cloudinary

from app.core.config import settings

_configured = False


def configure_cloudinary() -> None:
    """Configure the Cloudinary SDK from environment settings.

    Raises a clear RuntimeError if credentials are missing, instead of failing
    obscurely on first upload.
    """
    global _configured
    if _configured:
        return
    missing = [
        name
        for name, value in (
            ("CLOUDINARY_CLOUD_NAME", settings.cloudinary_cloud_name),
            ("CLOUDINARY_API_KEY", settings.cloudinary_api_key),
            ("CLOUDINARY_API_SECRET", settings.cloudinary_api_secret),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Cloudinary is not configured. Missing environment variable(s): "
            + ", ".join(missing)
        )
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )
    _configured = True
