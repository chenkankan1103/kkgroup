# -*- coding: utf-8 -*-
"""
Bootstrap module to set up the environment for kkgroup bots.
Initializes UTF-8 encoding and other shared setup.
"""

def setup_environment():
    """Set up the Python environment for the kkgroup project.

    This function:
    1. Initializes UTF-8 encoding handling

    Returns:
        function: The setup_utf8_logging function from shared.utils.encoding_handler
    """
    # Initialize UTF-8 encoding
    from shared.utils.encoding_handler import init_all, setup_utf8_logging
    init_all()

    return setup_utf8_logging