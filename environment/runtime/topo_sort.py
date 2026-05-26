def topological_sort(entries):
    """Sort resolved entries by topological level and visit characteristics.

    Produces a deterministic ordering of packages for manifest output.
    """
    return sorted(entries, key=lambda e: (e["level"], e["visit_count"]))
