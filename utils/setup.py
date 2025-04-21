# setup_path.py
import sys
import os

def setup_paths():
    """
    This function sets up the paths for the A2A project.
    It adds the A2A path to the system path if it is not already present.
    """
    __curdir__ = os.getcwd()
    if "notebooks" in __curdir__ or "utils" in __curdir__ or "src" in __curdir__:
        a2a_path = os.path.abspath("../A2A")
    else:
        a2a_path = os.path.abspath("A2A")
    if a2a_path not in sys.path:
        sys.path.insert(0, a2a_path)