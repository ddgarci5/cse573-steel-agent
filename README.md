# Agentic AI for Design of Steel Structural Members

CSE 573 (Semantic Web Mining), Group 13, Project 18. See `CLAUDE.md` for scope, rules and the backlog.

## Setup (Windows, uv)
```
uv venv --python 3.14 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```

Not in git (copyrighted or free downloads you must place yourself):
- `steelagent/data/aisc-shapes-database-v16_0.xlsx`: free AISC Shapes Database v16.0 download (rename the `.` in the version to `_`).
- `references/aisc-sample-tables/`: AISC Manual sample-table PDFs (flat folder).
- `references/teaching-modules/`, `references/design-examples/`: the sponsor's modules and the AISC Design Examples.
- Ollama (System C pilot, agent): `scoop install ollama` (0.40.16 tested). Start it with `ollama serve`; no models are pulled by the repo.
- `validation/parse_tables.py` needs **poppler** `pdftotext` (`scoop install poppler`; tested with 26.09.0). It scans PATH for it and rejects the xpdf build bundled with Git for Windows on purpose.

## Run
From `steelagent/`:
```
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe validation\run_all.py     # saves results\validation_<UTC>\ with meta.json
```
