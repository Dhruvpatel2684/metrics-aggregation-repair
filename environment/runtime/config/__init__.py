"""Configuration loader for the compaction engine."""
import configparser
import os

_config = None

def get_config():
    """Load and cache the retention configuration."""
    global _config
    if _config is None:
        _config = configparser.ConfigParser()
        config_path = os.path.join(os.path.dirname(__file__), "retention.ini")
        _config.read(config_path)
    return _config
