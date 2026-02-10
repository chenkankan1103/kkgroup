def send_or_update_startup_info(...):
    ...
    try:
        ...  # Your existing patch logic
    except ...:
        # Logic to delete the old message if patch fails
        delete_old_message(...)  # Add your parameters here
        ...  # Continue with sending a new message after deletion
