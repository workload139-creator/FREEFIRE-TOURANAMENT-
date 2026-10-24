
from pathlib import Path

from django.core.exceptions import ValidationError


MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_IMAGE_SIZE = 5 * 1024 * 1024   # 5 MB

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def validate_history_video(video):
    extension = Path(video.name).suffix.lower()

    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        raise ValidationError(
            "Video sirf MP4, MOV ya WEBM format mein upload karein."
        )

    if video.size > MAX_VIDEO_SIZE:
        raise ValidationError(
            "Video ka size 50 MB se zyada nahi hona chahiye."
        )

    if video.size == 0:
        raise ValidationError("Uploaded video khaali hai.")


def validate_history_images(images):
    if not images or len(images) < 2:
        raise ValidationError(
            "Kam-se-kam 2 match-history screenshots upload karein."
        )

    for image in images:
        extension = Path(image.name).suffix.lower()

        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValidationError(
                "Screenshots JPG, JPEG, PNG ya WEBP format mein hone chahiye."
            )

        if image.size == 0:
            raise ValidationError(
                f"{image.name}: image khaali hai."
            )

        if image.size > MAX_IMAGE_SIZE:
            raise ValidationError(
                f"{image.name}: image ka size 5 MB se zyada hai."
            )
