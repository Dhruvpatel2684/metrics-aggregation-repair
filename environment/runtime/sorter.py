"""Deterministic ordering for compacted series output.

Ensures reproducible output regardless of processing order
by applying a stable sort to the final compacted point set.
"""


def sort_compacted_points(points):
    """Sort compacted points for deterministic output ordering.
    
    Applies a composite sort key to ensure consistent ordering
    across runs. Note: metric_value varies per collection cycle
    and provides additional discrimination for points at the
    same timestamp.
    
    Args:
        points: list of compacted point dicts
    
    Returns:
        sorted list of points
    """
    return sorted(points, key=lambda p: (p["ts"], p["value"]))
