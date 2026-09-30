# PreView AI — Dependency Analysis

## 1. Overview

PreView AI builds a local **evidence-backed dependency graph** by statically analyzing project files. The graph captures relationships between files, modules, configurations, and data artifacts.

---

## 2. Analysis Pipeline

```
1. Enumerate relevant files (by extension)
2. Detect project / language type
3. Parse supported file types
4. Extract imports / references
5. Normalize target paths
6. Resolve references where possible
7. Construct graph edges with evidence
8. Store / incrementally update state
```

---

## 3. Supported File Types

| Extension | Parser | Relationship Types Detected |
|:---|:---|:---|
| `.py` | Python AST | `import`, `from ... import`, function calls, open(), string references |
| `.json` | Config parser | String path references, key references |
| `.yaml` / `.yml` | Config parser | String path references |
| `.toml` | Config parser | String path references |
| `.txt` / `.md` | Reference detector | Filename mentions, path strings |

---

## 4. Edge Types

| Edge Type | Description | Evidence Source |
|:---|:---|:---|
| `IMPORT` | Python `import` or `from ... import` statement | AST `Import` / `ImportFrom` node |
| `LOAD` | File open / load operation (`open()`, `pd.read_csv()`, etc.) | AST function call analysis |
| `READ` | Data read reference | String path detected in source |
| `REFERENCE` | General string/path reference to another file | Pattern matching |
| `CALL` | Function call across modules | AST call graph analysis |

---

## 5. Evidence Model

Every graph edge retains full evidence:

```python
EvidenceItem(
    source_file="train.py",
    target_file="dataset.csv",
    edge_type=EdgeType.LOAD,
    raw_text="open('dataset.csv')",
    line_number=14,
    confidence=ConfidenceLevel.CONFIRMED,
)
```

Evidence is displayed in the UI so users can inspect the source of every predicted impact.

---

## 6. Example Analysis

Given:
```python
# train.py
import pandas as pd
DATASET = "dataset.csv"
df = pd.read_csv(DATASET)
```

The parser detects:
- String literal `"dataset.csv"` referenced via `pd.read_csv()`
- Graph edge: `train.py → LOAD → dataset.csv`
- Evidence: `open/read_csv(DATASET)` at line 3

If `dataset.csv` is deleted/renamed, `train.py` is flagged as **HIGH RISK** with `CONFIRMED` evidence.

---

## 7. Incremental Updates

The state index uses `mtime` and `size` filters to avoid re-parsing unchanged files:

```
On filesystem event:
  if mtime changed or size changed:
    re-parse file
    update graph edges
    propagate impact
  else:
    skip re-parse
```

---

## 8. Graph Traversal

Impact propagation uses BFS from the changed node:

1. **Direct dependents**: Nodes with edges pointing to the changed file
2. **Downstream**: BFS from direct dependents (configurable depth)
3. **Test files**: Nodes matching `test_*` or in `tests/` directories

---

## 9. Confidence Levels

| Level | Meaning |
|:---|:---|
| `CONFIRMED` | Direct evidence (AST-verified edge) |
| `LIKELY` | AI-predicted with score ≥ 0.70 |
| `POSSIBLE` | AI-predicted with score ≥ 0.40 |
| `UNCERTAIN` | Weak signal; displayed with uncertainty label |

---

## 10. Limitations

- **Dynamic imports**: `importlib.import_module()`, `__import__()`, and other runtime imports are not statically detectable
- **Generated paths**: Paths constructed at runtime (e.g., `f"data/{name}.csv"`) may not resolve correctly
- **Third-party dependencies**: External package internals are not analyzed
- **Other languages**: Analysis depth varies for non-Python files
- **Closed-source binaries**: Opaque; only external-reference relationships detectable

---

## 11. Algorithms

### Reference Resolution

1. Try direct path match relative to project root
2. Try match relative to file's directory
3. Try Python module path normalization (`a.b.c` → `a/b/c.py`)
4. Fall back to filename stem match if no full path resolves

### Risk Level Assignment

Risk is determined by:
- Operation type (DELETE > MOVE/RENAME > MODIFY)
- Edge confidence (CONFIRMED > LIKELY > POSSIBLE)
- Graph path distance (direct > 1-hop > 2+ hops)
- File criticality (imports, test files, config files)

See [`AI_PIPELINE.md`](AI_PIPELINE.md) for AI-augmented risk scoring via the impact predictor.
