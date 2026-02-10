import logging
import json
from telegram import Update
from telegram.ext import CallbackContext

class WebhookLogger:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def log_update(self, update: Update):
        self.logger.info('Received update: %s', update)

    def handle_edit(self, update: Update, context: CallbackContext):
        message = update.message
        try:
            # Assume we are trying to edit a message
            context.bot.edit_message_text(
                text='New content',
                chat_id=message.chat_id,
                message_id=message.message_id
            )
        except Exception as e:
            self.logger.error('Failed to edit message: %s', e)
            try:
                # Attempt to delete the old message if edit fails
                context.bot.delete_message(chat_id=message.chat_id, message_id=message.message_id)
            except Exception as delete_error:
                self.logger.error('Failed to delete old message: %s', delete_error)
            # Now send a new message instead
            context.bot.send_message(chat_id=message.chat_id, text='Fallback: New content')
