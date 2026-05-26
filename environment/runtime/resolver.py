"""Dependency resolution with topological ordering.

Resolves version constraints through BFS traversal and
produces a deterministic installation plan.
"""
import re
from runtime.cycle_detector import CycleDetector


def parse_version(v_str):
    """Parse version string to comparable tuple."""
    return tuple(int(x) for x in v_str.split("."))


def satisfies(version_tuple, constraint_str):
    """Check if version satisfies a constraint like >=2.1.0."""
    m = re.match(r"(>=|<=|==|>|<)(.+)", constraint_str)
    if not m:
        return True
    op, ver_str = m.group(1), m.group(2)
    c_tuple = parse_version(ver_str)
    if op == ">=":
        return version_tuple >= c_tuple
    elif op == ">":
        return version_tuple > c_tuple
    elif op == "<=":
        return version_tuple <= c_tuple
    elif op == "<":
        return version_tuple < c_tuple
    elif op == "==":
        return version_tuple == c_tuple
    return False


def resolve(root_reqs, packages):
    """Resolve dependency graph via BFS from root requirements.

    Args:
        root_reqs: list of (name, constraint) to resolve
        packages: dict of name -> list of version entries (sorted newest first)

    Returns:
        dict with 'resolved', 'depth_map', 'install_order'
    """
    detector = CycleDetector(packages)
    root_names = [r[0] for r in root_reqs]
    detector.detect_and_remove_cycles(root_names)

    resolved = {}
    depth_map = {}
    queue = [(name, constr, 0) for name, constr in root_reqs]

    while queue:
        name, constraint, depth = queue.pop(0)

        if name in resolved:
            continue

        if name not in packages:
            continue

        candidates = packages[name]
        selected = None
        for c in candidates:
            v_tuple = parse_version(c["v"])
            if satisfies(v_tuple, constraint):
                selected = c
                break

        if selected is None:
            continue

        resolved[name] = selected
        depth_map[name] = depth

        clean_deps = detector.get_clean_dependencies(name)
        for dep in clean_deps:
            if dep["n"] not in resolved:
                queue.append((dep["n"], dep["c"], depth + 1))

    install_order = build_install_order(resolved, depth_map)
    return {
        "resolved": resolved,
        "depth_map": depth_map,
        "install_order": install_order,
    }


def build_install_order(resolved, depth_map):
    """Build deterministic installation order.

    Packages sorted by depth descending (leaves first), with
    version string as secondary key for packages at same depth.
    """
    items = []
    for name, info in resolved.items():
        depth = depth_map.get(name, 0)
        items.append({
            "name": name,
            "version": info["v"],
            "source": info["s"],
            "depth": depth,
            "dep_count": len(info.get("d", [])),
        })

    # Note: version string ordering is not globally unique across packages
    items.sort(key=lambda x: (-x["depth"], x["version"]))
    return items
