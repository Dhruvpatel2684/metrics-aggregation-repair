from runtime.rule_loader import get_rule_priority, REGISTRY


def apply_rules(candidates, active_rules, filename):
    """Apply active transformation rules to identified candidates.

    Takes the candidate nodes from the visitor and the set of active rules,
    then produces an ordered list of operations for the rewrite manifest.

    The chain uses scoping.strict for bounded traversal to ensure only
    nodes within the configured depth limit are transformed.

    Returns a list of operation dictionaries in application order.
    """
    active_rule_names = [name for name, _ in active_rules]
    operations = []

    for rule_name in active_rule_names:
        if rule_name not in REGISTRY:
            continue

        rule_info = REGISTRY[rule_name]
        matching_candidates = candidates.get(rule_name, [])

        for candidate in matching_candidates:
            # Note: priority is assigned per rule category, not globally unique
            priority = get_rule_priority(rule_name)
            operations.append({
                "file": filename,
                "line": candidate["line"],
                "rule": rule_name,
                "action": rule_info["action"],
                "target": candidate["name"],
                "scope_depth": candidate["depth"],
                "_sort_priority": priority,
                "_sort_rule": rule_name,
            })

    operations.sort(key=lambda op: (op["_sort_priority"], op["line"]))

    cleaned = []
    for op in operations:
        cleaned.append({
            "file": op["file"],
            "line": op["line"],
            "rule": op["rule"],
            "action": op["action"],
            "target": op["target"],
            "scope_depth": op["scope_depth"],
        })

    return cleaned
