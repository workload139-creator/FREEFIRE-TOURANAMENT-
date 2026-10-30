from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateMediaStorage(FileSystemStorage):
    """Keep verification, payment and room-access uploads on protected local media storage.

    Public profile photos and community posts continue to use the configured
    default storage (Cloudinary when CLOUDINARY_URL is set). Private uploads
    must not inherit that public default until signed/private Cloudinary delivery
    and per-user authorization are implemented.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", settings.MEDIA_ROOT)
        kwargs.setdefault("base_url", settings.MEDIA_URL)
        super().__init__(*args, **kwargs)
