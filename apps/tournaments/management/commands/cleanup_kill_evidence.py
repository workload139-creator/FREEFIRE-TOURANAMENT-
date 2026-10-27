from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tournaments.models import KillSubmission


class Command(BaseCommand):
    help = "Delete kill-evidence uploads older than 12 hours while keeping AI review and audit metadata."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=12)
        removed_files = 0
        submissions = KillSubmission.objects.filter(submitted_at__lte=cutoff).only(
            "id", "history_video", "history_image_one", "history_image_two"
        )
        for submission in submissions.iterator():
            changed_fields = []
            for field_name in ("history_video", "history_image_one", "history_image_two"):
                uploaded_file = getattr(submission, field_name)
                if not uploaded_file or not uploaded_file.name:
                    continue
                try:
                    uploaded_file.delete(save=False)
                except (OSError, ValueError) as exc:
                    self.stderr.write(f"Submission {submission.pk}: could not delete {field_name}: {exc}")
                    continue
                setattr(submission, field_name, "")
                changed_fields.append(field_name)
                removed_files += 1
            if changed_fields:
                submission.save(update_fields=changed_fields)
        self.stdout.write(self.style.SUCCESS(
            f"Kill evidence cleanup complete: {removed_files} file(s) removed; AI results and audit records retained."
        ))
