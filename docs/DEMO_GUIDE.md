# PreView AI — Demonstration Walkthrough Guide

This guide provides the step-by-step procedure to demonstrate **PreView AI** to evaluators, judges, and users.

---

## 1. Quick Start

### Running from Source
Double-click `run_preview_ai.bat` or run:
```cmd
run_preview_ai.bat
```
To launch directly with the ML demo project:
```cmd
run_preview_ai.bat --project "examples\demo_ml_project"
```

### Running the Standalone Executable
```cmd
dist\"PreView AI.exe" --project "examples\demo_ml_project"
```

---

## 2. Core Interactive Demo Script

Follow this sequence to showcase the unique novelty of PreView AI:

### Step 1: Open the Project & Inspect the File Explorer
1. Click **Open Folder** and select `examples/demo_ml_project`.
2. Notice the real filesystem hierarchy displayed on the left panel.
3. The project status bar indicates **Indexed** with nodes and relationships detected.

### Step 2: Select a Monitored File
1. Click on `dataset.csv` in the File Tree.
2. The Center Panel displays the file details, size, and incoming/outgoing references.

### Step 3: Ask the AI Copilot What Depends on It
1. Click the **✨ AI Copilot** button in the top toolbar (or press `Ctrl+Space`).
2. The right-hand conversational panel slides in.
3. Type: `"What files depend on dataset.csv?"`
4. **Observe:** The AI relies on **deterministic AST evidence**:
   - `train.py` loads `dataset.csv` via `open('dataset.csv')`
   - `pipeline.py` references `dataset.csv`
   - Evidence line numbers and code snippets are presented cleanly.

### Step 4: Simulate a Destructive Action (Mode A)
1. In the AI Copilot prompt, type:
   `"Delete dataset.csv"`
2. **Key Observation:**
   - **Real files remain completely untouched.**
   - The virtual simulator clones the graph into a future state.
   - The **Consequence Engine** immediately warns: **HIGH RISK**.
   - Affected files are displayed with reason: `train.py` will fail to load training data; `pipeline.py` data ingestion breaks.
3. Click **Cancel** on the proposal.
4. Verify that `dataset.csv` still exists on disk.

### Step 5: Detect External User Changes (Mode B)
1. Open Windows File Explorer (or your preferred editor).
2. Rename `dataset.csv` to `raw_dataset.csv`.
3. Switch back to PreView AI.
4. **Observe:**
   - The real-time filesystem watcher detects the external `RENAME` event.
   - A consequence alert notifies that `train.py` and `pipeline.py` now reference a broken target.

### Step 6: AI-Assisted Action Execution & Verification
1. Ask the AI: `"Move config.json into data folder"`
2. PreView AI simulates the action and presents the impact diff.
3. Click **Approve & Execute**.
4. The file operation executes.
5. The **Post-Action Verifier** immediately rescans the directory and confirms:
   - **Verification Status: MATCH**
   - Predicted outcome strictly equals actual filesystem outcome.

---

## 3. Key Differentiators to Highlight

1. **Not a Generic Chatbot:** The AI does not guess filesystem structure; it is constrained by a deterministic SQLite-backed dependency graph.
2. **Virtual Simulation First:** No destructive changes happen until consequences and downstream transitive effects are previewed and approved.
3. **Dual Operation Modes:** Handles both proactive AI-proposed actions (Mode A) and reactive external file changes (Mode B).
4. **Post-Action Verification:** Guarantees that executed operations match what was simulated.
