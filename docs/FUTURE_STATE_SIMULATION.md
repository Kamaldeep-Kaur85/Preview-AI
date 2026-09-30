# PreView AI — Future State Simulation

## 1. Overview

PreView AI's **Virtual Future-State Simulator** lets users (and the AI Copilot) preview the consequences of file operations **before any real filesystem change occurs**.

> **Invariant**: The real filesystem is never modified during simulation.

---

## 2. Simulation Architecture

```
REAL STATE (current on-disk graph)
       ↓
Virtual State clone (in-memory copy)
       ↓
Apply proposed operation to virtual state
       ↓
Run Consequence Engine on virtual state
       ↓
Show predicted impact diff to user
       ↓
User Approves → Execute on real filesystem
User Cancels → Discard virtual state
```

---

## 3. Supported Operations

| Operation | Virtual State Change |
|:---|:---|
| **DELETE** | Remove node; mark all edges pointing to it as broken |
| **MOVE** | Update node path; check reference resolution at new location |
| **RENAME** | Update node name + path; re-evaluate all references using new name |
| **MODIFY** | Mark node as changed; re-evaluate downstream impact |

---

## 4. Simulation Examples

### DELETE

```
Before:  model.pkl  exists  →  app.py LOADS  model.pkl
         train.py   exists  →  app.py CALLS  train.py

Simulation:  model.pkl absent in virtual state
             app.py flagged HIGH RISK (broken LOAD reference)

Real:    model.pkl unchanged on disk
```

### MOVE

```
Before:  dataset.csv at root/  →  train.py READS  dataset.csv

Simulation:  dataset.csv at root/data/
             train.py flagged MEDIUM RISK (path reference now broken)

Real:    dataset.csv unchanged at root/
```

### RENAME

```
Before:  auth.py  →  routes/login.py IMPORTS  auth.py

Simulation:  auth.py renamed to auth_v2.py
             routes/login.py flagged HIGH RISK (import now broken)

Real:    auth.py unchanged
```

---

## 5. State Revalidation

Before executing an approved action:

1. The system takes a fresh snapshot of the current real filesystem state
2. Compares it to the state at simulation time
3. If any relevant files changed (by external editors, other processes):
   - The stale simulation is **invalidated**
   - The system re-runs the simulation on the fresh state
   - User sees updated impact before re-approving

This prevents executing approved actions against stale previews.

---

## 6. State Diff Model

After execution, the verifier computes:

```
PREDICTED STATE  vs  ACTUAL STATE
```

Change categories:
- `ADDED` — file exists in actual but not predicted
- `REMOVED` — file absent in actual but present in predicted
- `MOVED` — path changed between states
- `RENAMED` — name changed
- `MODIFIED` — content/metadata changed
- `RELATIONSHIP_ADDED` — new dependency edge
- `RELATIONSHIP_REMOVED` — dependency edge broken
- `RELATIONSHIP_CHANGED` — edge target or type changed

---

## 7. Execution Gate

No action executes without passing all gates:

```
VALID ACTION (operation is supported)
         +
VALID SCOPE (target is within monitored root)
         +
CURRENT STATE VERIFIED (not stale)
         +
USER APPROVAL (explicit click on Approve)
         =
EXECUTABLE ACTION
```

---

## 8. Limitations

- **Dynamic runtime behavior**: Simulation is static (graph-based). Runtime behavior (subprocess calls, dynamically-generated paths, environment variables) is not simulated.
- **Binary / non-text content**: MODIFY simulation for binary files is limited to metadata tracking (no content diff).
- **External processes**: Applications with open file handles to simulation targets may block execution (reported as `File Locked` error).
- **Full OS simulation**: Operating system state, registry, running processes — all outside scope.
