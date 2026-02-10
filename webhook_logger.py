# Existing content with deletion logic added

try:
    # Existing code to send messages
    pass
except Exception as e:
    if webhook_message_id:
        delete_old_message(webhook_message_id)  # Function to delete message
        webhook_message_id = None
    # Log the error or handle it accordingly
