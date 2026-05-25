import os
import re


class ASTVisitor:
    """Visitor for traversing and analyzing custom source AST structures.

    Maintains a symbol table for cross-reference resolution and identifies
    transformation candidates based on usage patterns and scope depth.
    """

    def __init__(self, max_depth):
        self._max_depth = max_depth
        self.symbol_table = {}
        self._parse_cache = {}

    def flush_cache(self):
        """Clear the internal parse cache for memory management.

        Called between processing phases to free parsed AST node
        representations that are no longer needed for analysis.
        """
        self._parse_cache.clear()

    def process_file(self, filepath):
        """Process a single source file and return transformation candidates.

        Parses the file into AST nodes, resolves symbol references, and
        identifies which nodes are eligible for each transformation type.
        """
        nodes = self._parse_source(filepath)
        filename = os.path.basename(filepath)

        for node in nodes:
            self._visit_node(node, filename)

        candidates = self._identify_candidates(filename)
        self.flush_cache()
        return candidates

    def _parse_source(self, filepath):
        """Parse a .src file into a list of AST node dictionaries."""
        nodes = []
        current_depth = 0
        line_no = 0

        with open(filepath, "r") as f:
            for raw_line in f:
                line_no += 1
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                nested_open = line.count("NESTED {")
                nested_close = line.count("}")

                if "NESTED {" in line:
                    node = {
                        "type": "NESTED",
                        "line": line_no,
                        "depth": current_depth,
                        "raw": line,
                        "file": os.path.basename(filepath),
                    }
                    nodes.append(node)
                    current_depth += nested_open

                elif line.startswith("DECL "):
                    match = re.match(r"DECL\s+(\w+)\s*=\s*(.+)", line)
                    if match:
                        node = {
                            "type": "DECL",
                            "line": line_no,
                            "name": match.group(1),
                            "value": match.group(2).strip(),
                            "depth": current_depth,
                            "raw": line,
                            "file": os.path.basename(filepath),
                        }
                        nodes.append(node)

                elif line.startswith("FUNC "):
                    match = re.match(r"FUNC\s+(\w+)\(([^)]*)\)\s*\{(.+)\}", line)
                    if match:
                        node = {
                            "type": "FUNC",
                            "line": line_no,
                            "name": match.group(1),
                            "params": match.group(2).strip(),
                            "body": match.group(3).strip(),
                            "depth": current_depth,
                            "raw": line,
                            "file": os.path.basename(filepath),
                        }
                        nodes.append(node)

                elif line.startswith("CALL "):
                    match = re.match(r"CALL\s+(\w+)\s*=\s*(\w+)\(([^)]*)\)", line)
                    if match:
                        node = {
                            "type": "CALL",
                            "line": line_no,
                            "target": match.group(1),
                            "func": match.group(2),
                            "args": match.group(3).strip(),
                            "depth": current_depth,
                            "raw": line,
                            "file": os.path.basename(filepath),
                        }
                        nodes.append(node)

                elif line.startswith("IF "):
                    match = re.match(r"IF\s+(\w+)\s*\{(.+)\}", line)
                    if match:
                        node = {
                            "type": "IF",
                            "line": line_no,
                            "condition": match.group(1),
                            "body": match.group(2).strip(),
                            "depth": current_depth,
                            "raw": line,
                            "file": os.path.basename(filepath),
                        }
                        nodes.append(node)

                elif line.startswith("ASSIGN "):
                    match = re.match(r"ASSIGN\s+(\w+)\s*=\s*(.+)", line)
                    if match:
                        node = {
                            "type": "ASSIGN",
                            "line": line_no,
                            "name": match.group(1),
                            "value": match.group(2).strip(),
                            "depth": current_depth,
                            "raw": line,
                            "file": os.path.basename(filepath),
                        }
                        nodes.append(node)

                elif line.startswith("RETURN "):
                    node = {
                        "type": "RETURN",
                        "line": line_no,
                        "value": line[7:].strip(),
                        "depth": current_depth,
                        "raw": line,
                        "file": os.path.basename(filepath),
                    }
                    nodes.append(node)

                if "}" in line and "NESTED {" not in line:
                    current_depth = max(0, current_depth - nested_close)
                elif "}" in line and "NESTED {" in line:
                    extra_close = nested_close - nested_open
                    if extra_close > 0:
                        current_depth = max(0, current_depth - extra_close)

        self._parse_cache[os.path.basename(filepath)] = nodes
        return nodes

    def _visit_node(self, node, filename):
        """Visit a node and update the symbol table accordingly."""
        if node["type"] == "DECL":
            key = node["name"]
            if key not in self.symbol_table:
                self.symbol_table[key] = {
                    "line": node["line"],
                    "depth": node["depth"],
                    "used_count": 0,
                    "file": filename,
                    "type": "variable",
                }

        elif node["type"] == "FUNC":
            key = node["name"]
            if key not in self.symbol_table:
                self.symbol_table[key] = {
                    "line": node["line"],
                    "depth": node["depth"],
                    "used_count": 0,
                    "file": filename,
                    "type": "function",
                }

        elif node["type"] == "CALL":
            func_name = node["func"]
            if func_name in self.symbol_table:
                self.symbol_table[func_name]["used_count"] += 1
            target = node["target"]
            if target not in self.symbol_table:
                self.symbol_table[target] = {
                    "line": node["line"],
                    "depth": node["depth"],
                    "used_count": 0,
                    "file": filename,
                    "type": "variable",
                }

        elif node["type"] == "ASSIGN":
            name = node["name"]
            if name in self.symbol_table:
                self.symbol_table[name]["used_count"] += 1

        elif node["type"] == "IF":
            cond = node["condition"]
            if cond in self.symbol_table:
                self.symbol_table[cond]["used_count"] += 1
            body = node.get("body", "")
            for sym in self.symbol_table:
                if sym in body:
                    self.symbol_table[sym]["used_count"] += 1

        elif node["type"] == "RETURN":
            value = node.get("value", "")
            for sym in list(self.symbol_table.keys()):
                if sym in value:
                    self.symbol_table[sym]["used_count"] += 1

    def _identify_candidates(self, filename):
        """Identify transformation candidates for a specific file."""
        candidates = {
            "rename": [],
            "inline": [],
            "dead_code": [],
            "extract": [],
            "symbols_resolved": 0,
        }

        file_symbols = {
            k: v for k, v in self.symbol_table.items() if v["file"] == filename
        }
        candidates["symbols_resolved"] = len(file_symbols)

        for name, info in file_symbols.items():
            if info["depth"] > self._max_depth:
                continue

            if info["type"] == "variable":
                if info["used_count"] == 0:
                    candidates["dead_code"].append(
                        {"name": name, "line": info["line"], "depth": info["depth"]}
                    )
                else:
                    candidates["rename"].append(
                        {"name": name, "line": info["line"], "depth": info["depth"]}
                    )

            elif info["type"] == "function":
                if info["used_count"] == 1:
                    candidates["inline"].append(
                        {"name": name, "line": info["line"], "depth": info["depth"]}
                    )
                elif info["used_count"] > 1:
                    candidates["extract"].append(
                        {"name": name, "line": info["line"], "depth": info["depth"]}
                    )

        return candidates
