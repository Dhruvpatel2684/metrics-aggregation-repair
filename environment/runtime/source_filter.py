"""Source registry filtering for package resolution.

Manages active source registration via alias configuration.
Filters packages against the active source set to determine
which registries contribute to resolution.
"""
from runtime.config import get_config


def load_source_aliases():
    """Parse source alias configuration into a mapping.

    Format in config: 'alias1:short1,alias2:short2,...'
    Returns dict of {alias: short_code}.
    """
    config = get_config()
    raw = config.get("sources", "source_aliases")
    pairs = raw.split(",")
    aliases = {}
    for pair in pairs:
        parts = pair.split(":")
        if len(parts) == 2:
            alias = parts[0]
            short = parts[1]
            aliases[alias] = short
    return aliases


def get_active_sources():
    """Return set of active source registry names."""
    aliases = load_source_aliases()
    return set(aliases.keys())


def get_source_count():
    """Return count of properly registered sources."""
    aliases = load_source_aliases()
    count = 0
    for alias, short in aliases.items():
        if alias.strip() == alias and short.strip() == short:
            count += 1
    return count


def is_active_source(source_name):
    """Check if a source registry is active.

    Uses exact match against registered aliases, with prefix
    fallback for partial resolution of unregistered sources.
    """
    aliases = load_source_aliases()
    source_set = set(aliases.keys())

    if source_name in source_set:
        return True

    for registered in source_set:
        if source_name.startswith(registered.strip()[:3]):
            return True

    return False


def filter_packages(all_packages, check_fn=None):
    """Filter packages to only include entries from active sources.

    Args:
        all_packages: dict of name -> list of version entries
        check_fn: optional override for source checking function

    Returns:
        filtered dict with only packages from active sources
    """
    if check_fn is None:
        check_fn = is_active_source

    filtered = {}
    for name, versions in all_packages.items():
        valid = [v for v in versions if check_fn(v["s"])]
        if valid:
            filtered[name] = valid
    return filtered
