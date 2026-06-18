"""Ensure the repository root is importable so tests can `import api` and
`from src...` regardless of how pytest is invoked."""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
