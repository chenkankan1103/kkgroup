# webhook_logger.py

import logging
import os
import json
from datetime import datetime

class WebhookLogger:
    """
    A class to log incoming webhooks.
    """

    def __init__(self, log_file='webhook_log.json'):
        self.log_file = log_file
        self.ensure_log_file_exists()

    def ensure_log_file_exists(self):
        """
        Ensure that the log file exists.
        """
        if not os.path.isfile(self.log_file):
            with open(self.log_file, 'w') as f:
                json.dump([], f)

    def log_webhook(self, webhook_data):
        """
        Log the incoming webhook data.
        """
        try:
            with open(self.log_file, 'r+') as f:
                logs = json.load(f)
                logs.append({
                    'data': webhook_data,
                    'timestamp': datetime.utcnow().isoformat()
                })
                f.seek(0)
                json.dump(logs, f)
                f.truncate()
        except Exception as e:
            self.handle_log_failure(e)

    def handle_log_failure(self, exception):
        """
        Handle logging failure by deleting the corrupted log file.
        """
        logging.error(f'Failed to log webhook: {exception}')
        if os.path.isfile(self.log_file):
            os.remove(self.log_file)
            self.ensure_log_file_exists()

# Example usage:
# logger = WebhookLogger()
# logger.log_webhook({'example_key': 'example_value'})
