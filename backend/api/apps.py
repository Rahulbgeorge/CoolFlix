import os
from django.apps import AppConfig

class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        # Prevent starting the background thread in the dev-server reload wrapper
        is_dev_reload_wrapper = 'RUN_MAIN' in os.environ and os.environ.get('RUN_MAIN') != 'true'
        if not is_dev_reload_wrapper:
            from .transcoder import start_worker
            start_worker()

