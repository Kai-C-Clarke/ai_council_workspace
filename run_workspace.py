#!/usr/bin/env python3
"""
Run AI Council Workspace

Simple script to start the AI Council Workspace with default configuration.
"""

import sys
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from ai_council.main import main

if __name__ == "__main__":
    main()