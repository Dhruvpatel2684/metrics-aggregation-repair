import configparser
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_BASE_DIR, "config", "transforms.ini")

REGISTRY = {
    "rename": {
        "action": "rename_binding",
        "description": "Rename variable bindings to normalized identifiers",
    },
    "inline": {
        "action": "inline_expansion",
        "description": "Inline single-use function bodies at call sites",
    },
    "extract": {
        "action": "extract_subexpression",
        "description": "Extract repeated subexpressions into new bindings",
    },
    "dead_code": {
        "action": "eliminate_dead",
        "description": "Remove declarations with zero downstream references",
    },
}


def load_active_rules():
    """Load active rule set from configuration.

    Returns a list of (rule_name, rule_info) tuples for rules that
    are both listed in the config and present in the registry.
    """
    config = configparser.ConfigParser()
    config.read(_CONFIG_PATH)

    rules_str = config.get("rules", "active_rules")
    rule_names = rules_str.split(",")

    active = []
    for name in rule_names:
        if name in REGISTRY:
            active.append((name, REGISTRY[name]))

    return active


def get_rule_priority(rule_name):
    """Retrieve the configured priority for a given rule."""
    config = configparser.ConfigParser()
    config.read(_CONFIG_PATH)
    key = f"{rule_name}_priority"
    return config.getint("rules", key, fallback=99)
