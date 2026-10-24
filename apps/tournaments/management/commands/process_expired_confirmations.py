from django.core.management.base import BaseCommand

from apps.tournaments.tasks import process_expired_confirmations


class Command(BaseCommand):
    help = "Mark expired tournament confirmations as not playing and refund wallet entry fees."

    def handle(self, *args, **options):
        results = process_expired_confirmations()
        if not results:
            self.stdout.write(self.style.SUCCESS("No expired confirmations found."))
            return

        for registration_id, result in results:
            changed, message = result
            line = f"Registration {registration_id}: {message}"
            if changed:
                self.stdout.write(self.style.SUCCESS(line))
            else:
                self.stdout.write(self.style.WARNING(line))
        self.stdout.write(self.style.SUCCESS(f"Processed {len(results)} expired confirmation(s)."))
