# -*- coding: utf-8 -*-
"""
Entry point for running bots as a module: python -m bots
This ensures sys.path includes the parent directory so relative imports work.
"""

import sys
import os

# Ensure parent directory is in sys.path for relative imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Now import and run bot
from .bot import main

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
