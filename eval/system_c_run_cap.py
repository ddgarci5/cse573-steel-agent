"""Run the System C pilot with a different output-token cap WITHOUT editing eval/system_c_pilot.py.

The scoring/classifier code lives in system_c_pilot.py and must stay byte-identical across caps, so this wrapper only overrides the
module constant NUM_PREDICT (read at call time by run()) and then calls the same run(). Prompts, parser, temperature, seed and repeats are unchanged.

Usage (repo root):
  .venv/Scripts/python.exe eval/system_c_run_cap.py --max-tokens 4000 --backend voyager --model qwen38-27b --repeats 3 --run-dir results/<new dir>
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import system_c_pilot as S  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--max-tokens", type=int, required=True)
ap.add_argument("--backend", choices=["ollama", "voyager"], default="voyager")
ap.add_argument("--model", required=True)
ap.add_argument("--repeats", type=int, default=3)
ap.add_argument("--run-dir", default=None)
a = ap.parse_args()
S.NUM_PREDICT = a.max_tokens
print(f"max output tokens = {S.NUM_PREDICT}; scorer file sha256 = "
      f"{__import__('hashlib').sha256(Path(S.__file__).read_bytes()).hexdigest()[:12]}", flush=True)
S.run(a)
