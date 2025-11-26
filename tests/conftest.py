"""
Pytest configuration for kokoro-onnx-fastapi tests.

This module configures the Python path for tests to properly import
from the src directory.
"""

import sys
import os

# Add src directories to path for imports
src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
chinese_dir = os.path.join(src_dir, 'chinese')

for path in [src_dir, chinese_dir]:
    abs_path = os.path.abspath(path)
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)
