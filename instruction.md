# AST Rewrite Engine

Global system-wide tooling for automated source code transformation. This engine processes custom `.src` source files through a configurable set of rewrite rules, producing deterministic transformation reports and rewrite manifests.

## Architecture

The system consists of five core modules located at `/app/runtime/`:

- **`/app/runtime/rule_loader.py`** - Loads the active transformation rule set from configuration. Rules are matched against an internal registry to determine which transformations are available for the current run.

- **`/app/runtime/scope_resolver.py`** - Resolves the maximum traversal depth for AST analysis. Nodes beyond the configured depth boundary are preserved without transformation to maintain structural integrity of deeply nested constructs.

- **`/app/runtime/visitor.py`** - Traverses parsed AST nodes, builds a symbol table of variable and function bindings, and identifies transformation candidates. Each file is processed independently with isolated symbol scope to prevent cross-file contamination.

- **`/app/runtime/rule_chain.py`** - Applies the active rules to identified candidates and produces an ordered list of transformation operations. The transformation ordering uses (line, rule_name, priority) composite key to ensure deterministic output regardless of rule registration order.

- **`/app/runtime/hasher.py`** - Computes SHA-256 based integrity hashes for the transform report and rewrite manifest. Hashes are truncated to 16 hex characters.

## Configuration

The system is configured via `/app/runtime/config/transforms.ini` using standard INI format with multiple sections:

- `[project]` - Project metadata including source and output directory paths
- `[rules]` - Active rule list and per-rule priority assignments
- `[scoping]` and `[scoping.strict]` - Scope resolution parameters including maximum depth and traversal strategy
- `[output]` - Output format settings

## Source Format

Input files use a custom `.src` mini-language located in `/app/runtime/data/`. The format supports the following statement types:

```
DECL <name> = <expression>       Variable declaration
FUNC <name>(<params>) { <body> } Function definition
CALL <target> = <func>(<args>)   Function invocation
IF <condition> { <body> }        Conditional block
ASSIGN <name> = <expression>     Variable reassignment
NESTED { <statements> }          Nested scope block (increases depth)
RETURN <expression>              Return from function
```

Lines starting with `#` are comments. Blank lines are ignored. Each NESTED block increases the current scope depth by one level.

## Output

The engine produces two output files in `/app/runtime/output/`:

### transform_report.json

```json
{
  "project_id": "<configured project identifier>",
  "total_files": <number of source files processed>,
  "rules_applied": <total transformation operations across all files>,
  "active_rules": <number of rules successfully loaded>,
  "scope_depth": <configured maximum traversal depth>,
  "files_processed": {
    "<filename>": {
      "transforms": <operations applied to this file>,
      "symbols_resolved": <bindings tracked for this file>,
      "dead_eliminated": <unreferenced declarations identified>
    }
  },
  "integrity_hash": "<sha256[:16] of report excluding this field>"
}
```

### rewrite_manifest.json

```json
{
  "manifest_hash": "<sha256[:16] of operations array>",
  "operations": [
    {
      "file": "<source filename>",
      "line": <line number of target declaration>,
      "rule": "<rule name>",
      "action": "<transformation action>",
      "target": "<symbol name>",
      "scope_depth": <nesting depth of target>
    }
  ]
}
```

## Execution

Run from the `/app` working directory:

```bash
python3 -m runtime.run_rewriter
```

The engine processes source files in alphabetical order and writes results to `/app/runtime/output/`.

## Transformation Rules

- **rename** - Renames variable bindings with non-zero reference count
- **inline** - Inlines function bodies at call sites when the function has exactly one invocation
- **extract** - Extracts functions with multiple invocations into shared bindings
- **dead_code** - Eliminates declarations that have zero downstream references

Rules are applied within the configured scope depth boundary. Nodes at depths exceeding the maximum are excluded from transformation to preserve deeply nested structural patterns.
