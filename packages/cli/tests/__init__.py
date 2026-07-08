"""Test package: make the corral package importable without installation."""

import os
import sys

SRC = os.path.join(os.path.dirname(__file__), os.pardir, "src")
sys.path.insert(0, os.path.abspath(SRC))
