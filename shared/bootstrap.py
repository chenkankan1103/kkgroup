# -*- coding: utf-8 -*-
"""
Bootstrap module to set up the environment for kkgroup bots.
Adjusts sys.path to include the project root and initializes UTF-8 encoding.
"""

import os
import sys


def setup_environment():
    """Set up the Python environment for the kkgroup project.

    This function:
    1. Adds the project root to sys.path if not already present
    2. Initializes UTF-8 encoding handling

    Returns:
        function: The setup_utf8_logging function from shared.utils.encoding_handler
    """
    # Get the directory of this file (shared/bootstrap.py)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Go up two levels to get to the project root: shared/bootstrap.py -> shared/ -> project root
    project_root = os.path.dirname(os.path.dirname(current_dir))

    # Add project root to sys.path if not already present
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Initialize UTF-8 encoding
    from shared.utils.encoding_handler import init_all, setup_utf8_logging
    init_all()

    return setup_utf8_logging