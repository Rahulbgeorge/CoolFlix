import os
import sys
import fcntl
import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from api.models import Video
from api.transcoder import VideoProcessor

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Decoupled background worker to process pending transcoding tasks from the database sequentially'

    def handle(self, *args, **options):
        # Determine the project root to store the lock file securely
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        lock_file_path = os.path.join(base_dir, 'transcoder.lock')
        
        # Acquire exclusive non-blocking lock to prevent multiple concurrent instances
        lock_file = open(lock_file_path, 'w')
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            self.stdout.write(self.style.WARNING("Another instance of the transcoder is already running. Exiting..."))
            sys.exit(0)

        self.stdout.write(self.style.SUCCESS("Acquired file lock. Starting transcoder cycle..."))
        
        # Reset stalled processing videos (e.g. from crash during last run)
        try:
            stalled_count = Video.objects.filter(status='processing').update(status='pending', progress=0.0)
            if stalled_count > 0:
                self.stdout.write(f"Reset {stalled_count} stalled 'processing' video(s) back to 'pending'.")
        except Exception as e:
            logger.error(f"Failed to reset stalled videos: {e}")

        # Sequentially process pending transcodes
        processed_count = 0
        while True:
            video_id = None
            try:
                # Atomically select the first pending video and mark it processing
                with transaction.atomic():
                    video = Video.objects.filter(status='pending').order_by('created_at').select_for_update().first()
                    if video:
                        video.status = 'processing'
                        video.progress = 5.0
                        video.save()
                        video_id = video.id
            except Exception as db_err:
                self.stderr.write(f"Database query error during queue check: {db_err}")
                break

            if video_id is None:
                break  # No more pending videos in the queue

            self.stdout.write(self.style.MIGRATE_LABEL(f"Starting processing for video ID {video_id}..."))
            try:
                VideoProcessor.process_video_pipeline(video_id)
                processed_count += 1
                self.stdout.write(self.style.SUCCESS(f"Finished processing video ID {video_id}."))
            except Exception as proc_err:
                logger.error(f"Error during execution pipeline of video ID {video_id}: {proc_err}")
                self.stderr.write(self.style.ERROR(f"Pipeline error for video ID {video_id}: {proc_err}"))

        self.stdout.write(self.style.SUCCESS(f"Transcoding loop finished. Processed {processed_count} video(s) in this cycle."))
