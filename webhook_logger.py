import logging
import time

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class WebHookLogger:
    def __init__(self, url):
        self.url = url

    def log(self, event):
        logging.info(f"Sending event to {self.url}: {event}")
        # Simulate sending a webhook (this is where you would implement the actual HTTP request)
        time.sleep(1)  # Simulating network delay
        logging.info(f"Event sent: {event}")

    def log_with_deletion_logic(self, event):
        try:
            self.log(event)
        except Exception as e:
            logging.error(f"Failed to log event: {e}")
            # Handle deletion logic here (e.g., delete a failed log entry or reset state)
            logging.info("Deletion logic executed due to an error.")
