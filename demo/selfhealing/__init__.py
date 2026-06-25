"""Exposes tracking submodules cleanly to package roots"""
from .metrics_monitor import monitor

__all__ = ["monitor"]