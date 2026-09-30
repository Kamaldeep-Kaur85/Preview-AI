# PreView AI — Demo ML Project

This is the **real demo project** used for PreView AI acceptance tests.

## File Structure

| File | Role | Depends On |
|------|------|-----------|
| `dataset.csv` | Training/evaluation data | — |
| `config.json` | Configuration | `model.pkl`, `dataset.csv` |
| `train.py` | Training script | `dataset.csv`, `config.json` |
| `evaluate.py` | Evaluation script | `dataset.csv`, `model.pkl`, `config.json` |
| `pipeline.py` | Orchestrator | `train.py`, `evaluate.py`, `dataset.csv` |
| `app.py` | Application entry | `model.pkl`, `dataset.csv`, `config.json` |

## Dependency Graph

```
dataset.csv
    │
    ├── train.py       (opens dataset.csv via csv.DictReader)
    ├── evaluate.py    (opens dataset.csv via csv.DictReader)
    ├── pipeline.py    (references dataset.csv)
    └── app.py         (reads dataset.csv via pd.read_csv)

model.pkl
    │
    ├── evaluate.py    (opens model.pkl via pickle.load)
    └── app.py         (opens model.pkl via pickle.load)

config.json
    │
    ├── train.py       (opens config.json via json.load)
    ├── evaluate.py    (opens config.json via json.load)
    └── app.py         (opens config.json via json.load)
```

## Acceptance Tests

### Test 1 — Delete dataset.csv
Expected: train.py, evaluate.py, pipeline.py, app.py all appear as affected.

### Test 2 — Move dataset.csv → data/dataset.csv
Expected: All files with references to dataset.csv appear as potentially broken.

### Test 3 — Rename dataset.csv → data.csv (via Windows Explorer)
Expected: PreView AI detects the rename and shows broken references.

### Test 4 — Delete requirements.txt (no dependents)
Expected: No confirmed dependent files.
