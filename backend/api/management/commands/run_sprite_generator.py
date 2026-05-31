import logging
from django.core.management.base import BaseCommand
from api.cron import run_sprite_cron

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Runs the lightweight scrubbing sprite generator and HLS transcode worker'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting sprite generator run..."))
        run_sprite_cron()
        self.stdout.write(self.style.SUCCESS("Sprite generator run complete."))
