# Updated uicommands/views/selection_views.py

# Importing necessary modules


# Function that handles selection views

def selection_view_function(result):
    # Assuming result is a dict that holds the necessary values
    yield_amount = result.get("yield_amount", 0)  # Changed from yield to yield_amount
    return yield_amount
