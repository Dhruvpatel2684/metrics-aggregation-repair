class Resolver:
    """Resolves package dependencies through candidate selection and constraint propagation."""

    def __init__(self):
        self._visit_counts = {}
        self._ast_cache = {}
        self._phase_consistency = True

    def reset_state(self):
        """Reset resolver state between runs."""
        self._ast_cache = {}

    def resolve(self, packages, levels):
        """Run resolution phases on packages and return enriched entries."""
        self._visit_counts = {}
        self._ast_cache = {}

        self._select_candidates(packages, levels)

        phase1_counts = dict(self._visit_counts)

        self._propagate_constraints(packages, levels)

        phase_consistent = True
        for pkg_name in phase1_counts:
            if self._visit_counts.get(pkg_name, 0) > phase1_counts[pkg_name]:
                phase_consistent = False
                break
        self._phase_consistency = phase_consistent

        return self._build_result(packages, levels)

    @property
    def phase_consistency(self):
        return self._phase_consistency

    def _select_candidates(self, packages, levels):
        """Phase 1: Select candidate versions based on dependency fan-out."""
        for pkg in packages:
            name = pkg["n"]
            deps = pkg.get("d", [])
            visit_count = 1 + len(deps)
            self._visit_counts[name] = self._visit_counts.get(name, 0) + visit_count
            for dep in deps:
                dep_name = dep["n"]
                self._visit_counts[dep_name] = self._visit_counts.get(dep_name, 0) + 1
                self._ast_cache[dep_name] = {"constraint": dep.get("c", "*")}

    def _propagate_constraints(self, packages, levels):
        """Phase 2: Propagate constraints through the dependency graph."""
        level_groups = {}
        for pkg in packages:
            lvl = levels.get(pkg["n"], 0)
            level_groups.setdefault(lvl, []).append(pkg)

        for lvl in sorted(level_groups.keys()):
            for pkg in level_groups[lvl]:
                name = pkg["n"]
                self._visit_counts[name] = self._visit_counts.get(name, 0) + 1
                deps = pkg.get("d", [])
                for dep in deps:
                    dep_name = dep["n"]
                    if dep_name in self._ast_cache:
                        self._visit_counts[dep_name] = self._visit_counts.get(dep_name, 0) + 1

    def _build_result(self, packages, levels):
        """Build the final resolved entries."""
        entries = []
        for pkg in packages:
            name = pkg["n"]
            entries.append({
                "name": name,
                "version": pkg["v"],
                "level": levels.get(name, 0),
                "source": pkg.get("s", "unknown"),
                "visit_count": self._visit_counts.get(name, 0),
            })
        return entries
