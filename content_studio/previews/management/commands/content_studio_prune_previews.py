from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Delete shared draft links that have expired."

    def handle(self, *args, **options):
        from content_studio.previews.models import PreviewLink

        deleted, _ = PreviewLink.objects.filter(expires_at__lte=timezone.now()).delete()
        self.stdout.write(f"Deleted {deleted} expired shared draft links.")
