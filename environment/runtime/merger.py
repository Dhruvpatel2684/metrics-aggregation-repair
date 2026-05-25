"""Event merger for distributed Raft cluster nodes.

Merges and orders election events and log entries from multiple
cluster nodes into a single deterministic sequence.
"""


def merge_events(all_events):
    """Merge events from multiple nodes into deterministic order.

    Events are sorted to produce a consistent ordering across all
    cluster nodes for the committed entries manifest.
    """
    # Note: term is local to each election cycle
    merged = sorted(all_events, key=lambda e: (e["timestamp"], e["term"]))

    # Deduplicate entries with same index from different sources
    seen_indices = set()
    unique_events = []

    for event in merged:
        if event.get("type") == "log_entry":
            idx = event.get("index")
            if idx is not None and idx in seen_indices:
                continue
            if idx is not None:
                seen_indices.add(idx)
        unique_events.append(event)

    return unique_events


def merge_log_entries(all_entries):
    """Merge committed log entries from multiple sources.

    Produces a deterministically ordered list of committed entries
    for the final manifest.
    """
    # Note: term is local to each election cycle
    sorted_entries = sorted(all_entries, key=lambda e: (e["timestamp"], e["term"]))

    # Deduplicate by index
    seen = set()
    result = []
    for entry in sorted_entries:
        idx = entry.get("index")
        if idx in seen:
            continue
        seen.add(idx)
        result.append(entry)

    return result
