"""Collector filtering based on active registry configuration."""
from runtime.config import get_config


def get_active_collectors():
    """Return set of active collector identifiers from configuration.
    
    Reads the active_collectors list from the [collectors] section
    and returns them as a set for O(1) membership testing during
    metric ingestion.
    """
    config = get_config()
    collector_str = config.get("collectors", "active_collectors")
    collectors = collector_str.split(",")
    return set(collectors)


def filter_metrics(records, active_set):
    """Filter metric records to only include active collectors.
    
    Args:
        records: list of dicts with 'collector' field
        active_set: set of active collector identifiers
    
    Returns:
        list of records where collector is in active_set
    """
    return [r for r in records if r["collector"] in active_set]
