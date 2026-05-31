import logging
from django.core.management.base import BaseCommand
from api.cron import run_fast_pipeline_cron

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Runs the fast stream copy and preview pipeline worker (20-30s)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting fast stream copy pipeline run..."))
        run_fast_pipeline_cron()
        self.stdout.write(self.style.SUCCESS("Fast stream copy pipeline run complete."))
