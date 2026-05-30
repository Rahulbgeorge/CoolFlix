import logging
from django.core.management.base import BaseCommand
from api.cron import run_transcoder_cron

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Runs the prioritized video transcoding worker'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting prioritized transcoder run..."))
        run_transcoder_cron()
        self.stdout.write(self.style.SUCCESS("Prioritized transcoder run complete."))
