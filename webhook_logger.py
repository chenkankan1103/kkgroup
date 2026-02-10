import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

class WebhookLogger:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def send_message(self, message):
        try:
            self.delete_old_message()  # Delete old message before sending a new one
            response = requests.post(self.webhook_url, json={'content': message})
            response.raise_for_status()  # Raise an error for bad responses
            logging.info("Message sent successfully.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to send message: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")

    def delete_old_message(self):
        # Logic to delete the old message would be implemented here.
        logging.info("Old message deleted (mock implementation).")

# Example usage
if __name__ == '__main__':
    webhook_url = 'YOUR_WEBHOOK_URL'
    logger = WebhookLogger(webhook_url)
    logger.send_message("This is a test message.")
