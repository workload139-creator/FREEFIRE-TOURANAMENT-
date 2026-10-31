"""Durable private media storage for payment, identity and tournament evidence.

On Render, local media storage is ephemeral. When CLOUDINARY_URL is configured,
private uploads are stored as Cloudinary authenticated assets: originals and
derived files require signed delivery URLs. Local development keeps using
MEDIA_ROOT so the project still works without cloud credentials.
"""
import os

import cloudinary
import cloudinary.uploader
import cloudinary.utils
from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible


class AuthenticatedCloudinaryStorage:
    """Lazy proxy for Cloudinary's storage backend using authenticated assets.

    Importing django-cloudinary-storage validates credentials immediately, so
    defer that import until production has explicitly enabled Cloudinary.
    """

    VIDEO_PATH_MARKERS = ("/videos/",)
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}

    def __init__(self):
        from cloudinary_storage.storage import MediaCloudinaryStorage

        class _Backend(MediaCloudinaryStorage):
            def _get_resource_type(self, name):
                normalized = "/" + str(name).replace("\\", "/").lower()
                extension = os.path.splitext(normalized)[1]
                if extension in AuthenticatedCloudinaryStorage.VIDEO_EXTENSIONS or any(
                    marker in normalized
                    for marker in AuthenticatedCloudinaryStorage.VIDEO_PATH_MARKERS
                ):
                    return "video"
                return "image"

            def _upload(self, name, content):
                options = {
                    "use_filename": True,
                    "unique_filename": True,
                    "resource_type": self._get_resource_type(name),
                    "type": "authenticated",
                    "tags": self.TAG,
                }
                folder = os.path.dirname(name)
                if folder:
                    options["folder"] = folder
                return cloudinary.uploader.upload(content, **options)

            def _get_url(self, name):
                name = self._prepend_prefix(name)
                url, _options = cloudinary.utils.cloudinary_url(
                    name,
                    resource_type=self._get_resource_type(name),
                    type="authenticated",
                    sign_url=True,
                    secure=True,
                )
                return url

            def delete(self, name):
                response = cloudinary.uploader.destroy(
                    name,
                    invalidate=True,
                    resource_type=self._get_resource_type(name),
                    type="authenticated",
                )
                return response.get("result") == "ok"

        self.backend = _Backend()

    def __getattr__(self, name):
        return getattr(self.backend, name)


@deconstructible
class PrivateMediaStorage(Storage):
    """Use authenticated Cloudinary storage in production and local storage in dev.

    The public profile-photo/community storage remains unchanged. This backend is
    only used by fields that contain payment proofs, UPI QR codes, room QR codes,
    registration selfies, or kill-submission evidence.
    """

    def __init__(self):
        if getattr(settings, "CLOUDINARY_MEDIA_ENABLED", False):
            self.backend = AuthenticatedCloudinaryStorage()
        else:
            self.backend = FileSystemStorage(
                location=settings.MEDIA_ROOT,
                base_url=settings.MEDIA_URL,
            )

    def _open(self, name, mode="rb"):
        return self.backend._open(name, mode)

    def _save(self, name, content):
        return self.backend._save(name, content)

    def get_valid_name(self, name):
        return self.backend.get_valid_name(name)

    def get_available_name(self, name, max_length=None):
        return self.backend.get_available_name(name, max_length=max_length)

    def delete(self, name):
        return self.backend.delete(name)

    def exists(self, name):
        return self.backend.exists(name)

    def listdir(self, path):
        return self.backend.listdir(path)

    def size(self, name):
        return self.backend.size(name)

    def url(self, name):
        return self.backend.url(name)

    def path(self, name):
        return self.backend.path(name)
