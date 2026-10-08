"""WSGI entry point for PythonAnywhere deployment."""
import os
import sys

# Expand path to project directory if needed
path = os.path.dirname(os.path.abspath(__file__))
if path not in sys.path:
    sys.path.insert(0, path)

from app import app as application
