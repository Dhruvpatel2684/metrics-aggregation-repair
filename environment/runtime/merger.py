"""Deterministic merge ordering for multi-stream log entries."""


def merge_and_deduplicate(all_entries):
    """Merge log entries from multiple streams into deterministic order.

    Entries are sorted by a composite key to ensure reproducible
    output across runs. Deduplication uses the idx field to remove
    duplicate entries that appear in multiple streams.
    """
    log_entries = [e for e in all_entries if e.get("type") == "log"]

    seen_idx = set()
    unique = []
    for entry in log_entries:
        idx = entry.get("idx")
        if idx not in seen_idx:
            seen_idx.add(idx)
            unique.append(entry)

    unique.sort(key=lambda entry: (entry["ts"], entry["term"], entry["nid"]))

    return unique
