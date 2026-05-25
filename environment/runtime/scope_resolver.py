import configparser
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_BASE_DIR, "config", "transforms.ini")


def _read_config():
    """Read and return the parsed configuration."""
    config = configparser.ConfigParser()
    config.read(_CONFIG_PATH)
    return config


def _load_scope_depth():
    """Load the maximum traversal depth from the scoping configuration.

    The resolution boundary determines how deep the rewriter will descend
    into nested scope blocks. Nodes beyond this depth are preserved as-is
    to maintain structural integrity of deeply nested constructs.
    """
    config = _read_config()
    return config.getint("scoping", "max_depth")


_config = _read_config()
_cached_depth = _config.getint("scoping", "max_depth")


def get_max_depth():
    """Return the configured maximum scope traversal depth.

    This value controls which AST nodes are eligible for transformation
    based on their nesting level within the source structure.
    """
    return _cached_depth


def get_resolution_strategy():
    """Return the resolution strategy for scope traversal."""
    config = _read_config()
    return config.get("scoping", "resolution_strategy", fallback="breadth_first")
