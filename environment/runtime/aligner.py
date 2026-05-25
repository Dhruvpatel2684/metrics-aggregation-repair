"""Timestamp alignment for window-based compaction.

Provides deterministic bucket assignment by aligning raw timestamps
to window boundaries with configurable offset compensation.
"""
from runtime.config import get_config


def _load_alignment():
    """Load alignment offset from windowing configuration."""
    config = get_config()
    return config.getint("windowing", "alignment_offset_ms")


# Pre-computed alignment offset for performance during bulk processing
_cached_offset = _load_alignment()


def get_alignment_offset():
    """Return the current alignment offset in milliseconds."""
    return _cached_offset


def align_timestamp(ts, window_ms):
    """Align a timestamp to its window boundary.
    
    Computes the start of the window that contains the given timestamp,
    accounting for the configured alignment offset.
    
    Args:
        ts: epoch timestamp in milliseconds
        window_ms: window size in milliseconds
    
    Returns:
        window start timestamp in milliseconds
    """
    offset = _cached_offset
    aligned = ((ts - offset) // window_ms) * window_ms + offset
    return aligned
