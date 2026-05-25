"""Repair script for the AST rewrite engine.

Applies targeted patches to resolve the five interacting defects
in rule loading, scope resolution, visitor state management,
transformation ordering, and cached depth invalidation.
"""

import os
import shutil
import subprocess
import sys

RUNTIME_DIR = "/app/runtime"


def patch_file(filepath, old, new):
    """Apply a string replacement patch to a file."""
    with open(filepath, "r") as f:
        content = f.read()
    if old not in content:
        print(f"  Warning: pattern not found in {filepath}")
        return False
    content = content.replace(old, new)
    with open(filepath, "w") as f:
        f.write(content)
    return True


def fix_rule_loader():
    """Fix A: Strip whitespace from rule name list after splitting."""
    path = os.path.join(RUNTIME_DIR, "rule_loader.py")
    patch_file(
        path,
        'rule_names = rules_str.split(",")',
        'rule_names = [r.strip() for r in rules_str.split(",")]',
    )


def fix_scope_resolver():
    """Fix B + E: Correct config section and bypass stale cache."""
    path = os.path.join(RUNTIME_DIR, "scope_resolver.py")
    patch_file(
        path,
        'return config.getint("scoping", "max_depth")',
        'return config.getint("scoping.strict", "max_depth")',
    )
    patch_file(
        path,
        "return _cached_depth",
        "return _load_scope_depth()",
    )


def fix_visitor():
    """Fix C: Reset symbol table between file processing passes."""
    path = os.path.join(RUNTIME_DIR, "visitor.py")
    patch_file(
        path,
        "        nodes = self._parse_source(filepath)\n"
        "        filename = os.path.basename(filepath)",
        "        self.symbol_table = {}\n"
        "        nodes = self._parse_source(filepath)\n"
        "        filename = os.path.basename(filepath)",
    )


def fix_rule_chain():
    """Fix D: Use canonical sort key with rule name for deterministic ordering."""
    path = os.path.join(RUNTIME_DIR, "rule_chain.py")
    patch_file(
        path,
        'operations.sort(key=lambda op: (op["_sort_priority"], op["line"]))',
        'operations.sort(key=lambda op: (op["line"], op["_sort_rule"], op["_sort_priority"]))',
    )


def clear_caches():
    """Remove compiled bytecode to ensure patches take effect."""
    for root, dirs, files in os.walk(RUNTIME_DIR):
        for d in dirs:
            if d == "__pycache__":
                shutil.rmtree(os.path.join(root, d))


def main():
    print("Applying AST rewriter repairs...")
    fix_rule_loader()
    print("  [1/5] Rule loader: whitespace stripping applied")
    fix_scope_resolver()
    print("  [2/5] Scope resolver: config section corrected")
    print("  [3/5] Scope resolver: cache invalidation applied")
    fix_visitor()
    print("  [4/5] Visitor: symbol table reset applied")
    fix_rule_chain()
    print("  [5/5] Rule chain: sort key corrected")

    clear_caches()
    print("Caches cleared. Re-running rewriter...")

    result = subprocess.run(
        [sys.executable, "-m", "runtime.run_rewriter"],
        cwd="/app",
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("Rewriter completed successfully.")
    else:
        print(f"Rewriter failed: {result.stderr}")
        sys.exit(1)


if __name__ == "__main__":
    main()
