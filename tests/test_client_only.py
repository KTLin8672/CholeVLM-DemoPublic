"""A client, nothing else.

A search of the repo's code, configs and web sources for model loading, weight
files, frame-shard or data-tree reads, test paths and a bind to every interface
must come back empty, and the venv must carry no model stack.
"""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNED = [
    ROOT / "src",
    ROOT / "configs",
    ROOT / "web" / "src",
    ROOT / "web" / "index.html",
    ROOT / "web" / "vite.config.js",
]

FORBIDDEN = {
    "model stack import": r"^\s*(import|from)\s+(torch|transformers|peft|accelerate|vllm|safetensors|onnxruntime)\b",
    "weight loading": r"from_pretrained|load_state_dict|\.safetensors\b|\.pt[\"']",
    "test root": r"chole-testset|chole-eval-test",  # the old name too
    "ood_test split": r"\bood_test\b",
    "data tree": r"\bDATA_ROOT\b",
    "bind to every interface": r"(host|bind)\s*[=:]\s*(['\"](0\.0\.0\.0|::)['\"]|true\b)",
}


def _files():
    for base in SCANNED:
        if base.is_file():
            yield base
        elif base.exists():
            yield from (
                p
                for p in base.rglob("*")
                if p.is_file()
                and p.suffix in {".py", ".yaml", ".yml", ".json", ".js", ".html", ".toml"}
            )


def test_no_forbidden_pattern_in_code():
    hits = []
    for path in _files():
        text = path.read_text(errors="replace")
        for label, pattern in FORBIDDEN.items():
            for m in re.finditer(pattern, text, flags=re.MULTILINE):
                line = text.count("\n", 0, m.start()) + 1
                hits.append(f"{path.relative_to(ROOT)}:{line}: {label}")
    assert hits == [], "\n".join(hits)


def test_venv_has_no_model_stack():
    present = [m for m in ("torch", "transformers", "peft", "vllm") if importlib.util.find_spec(m)]
    assert present == []
