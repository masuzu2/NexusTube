# -*- coding: utf-8 -*-
"""Pytest root configuration and headless environment initialization."""
import os
import sys

# Force SDL dummy audio driver in headless / CI environments without audio hardware
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("NEXUSTUBE_HEADLESS", "1")

# Ensure repository root is in sys.path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
