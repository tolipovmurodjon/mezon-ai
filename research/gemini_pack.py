"""One flat folder for Gemini: select all files, drop them in. Rebuild after every change.

    .venv/Scripts/python.exe -X utf8 -m research.gemini_pack      # -> D:\\10_projects\\mezon\\gemini\\ (no subfolders)

Ten files at most (01-07 brain notes, 08 project rules, 09 product code, 10 data/training code). Code is bundled
into two Markdown files with each file's path as a heading. Never includes data, caches, secrets or decision texts.
"""

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "gemini"
SECRET = re.compile(
    r"\.env|secret|token|password|credential|\.jks|\.keystore|serviceAccount|google-services", re.IGNORECASE
)
PRODUCT = [
    "mezon/report.py",
    "mezon/config.py",
    "mezon/version.py",
    "mezon/agent.py",
    "mezon/ask.py",
    "mezon/conclusion.py",
    "mezon/plain.py",
    "mezon/llm.py",
    "mezon/region_report.py",
    "mezon/rules/*.py",
    "mezon/lawstore/*.py",
    "mezon/decisions/*.py",
    "mezon/api/main.py",
]
PIPELINE = [
    "mezon/sync/*.py",
    "research/benchmark.py",
    "research/train_data.py",
    "research/train_pilot.py",
    "research/hf_corpus.py",
    "research/qwen_format.py",
    "research/overnight_summary.py",
    "scripts/overnight.sh",
    "research/freshness.py",
    "research/demo_check.py",
    "research/polite_http.py",
    "research/textnorm.py",
    "research/regnum.py",
    "pyproject.toml",
]


def bundle(title: str, patterns: list[str]) -> str:
    parts = [
        f"# {title}",
        "",
        "Mezon source code (Python 3.12, FastAPI, SQLite). Each section is one file.",
        "",
    ]
    for pat in patterns:
        for f in sorted(ROOT.glob(pat)):
            rel = f.relative_to(ROOT).as_posix()
            if f.name == "__init__.py" or SECRET.search(rel) or not f.is_file():
                continue
            lang = {"py": "python", "sh": "bash", "toml": "toml"}.get(f.suffix.lstrip("."), "")
            parts += [
                f"## {rel}",
                f"```{lang}",
                f.read_text(encoding="utf-8", errors="replace").rstrip(),
                "```",
                "",
            ]
    return "\n".join(parts)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    brain = sorted((ROOT / "docs" / "brain").glob("0*.md"))
    for f in brain:
        shutil.copy(f, OUT / f.name)
    shutil.copy(ROOT / "CLAUDE.md", OUT / "08_project_rules_CLAUDE.md")
    (OUT / "09_code_product.md").write_text(
        bundle("09 · Product code: rules, law store, agent, API", PRODUCT), encoding="utf-8"
    )
    (OUT / "10_code_data_training.md").write_text(
        bundle("10 · Data, sync and training code", PIPELINE), encoding="utf-8"
    )
    for f in sorted(OUT.iterdir()):
        print(f"{f.stat().st_size / 1024:7.0f} KB  {f.name}")
    print(f"{len(list(OUT.iterdir()))} files -> {OUT}")


if __name__ == "__main__":
    main()
