from django.core.management.base import BaseCommand

from apps.tournaments.services import process_expired_ready_registrations


class Command(BaseCommand):
    help = "Refund registrations that missed the 60-second room confirmation deadline."

    def handle(self, *args, **options):
        count = process_expired_ready_registrations()
        self.stdout.write(self.style.SUCCESS(
            f"Processed {count} expired tournament registration(s)."
        ))
