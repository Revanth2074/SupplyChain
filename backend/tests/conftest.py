"""Pytest setup: make backend/ importable. No test calls Synapt, the LLM or loads the 100k-row dataset."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
