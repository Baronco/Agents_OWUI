"""Simple logger wrapper using Python's logging module.
Configure a module‑level logger for the proxy.
"""
import logging
import sys

logger = logging.getLogger("owui_proxy")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
