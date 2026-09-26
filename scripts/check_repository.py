"""Check shareable files and local Markdown links without reading runtime data."""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PATTERNS = (
    "._*",
    "*/._*",
    "config.env",
    ".env",
    ".env.*",
    "*.local.*",
    "*.log",
    "*.sqlite*",
    "*.db",
    "*.db-*",
    "*.safetensors",
    "*.onnx",
    "*.pt",
    "*.pth",
    "*.pem",
    "*.key",
    "*.pyc",
    "data/*",
    "samples/*",
    "backups/*",
    "logs/*",
    "deployment/*",
    "experiments/*",
    "scratch/*",
    "tmp/*",
    "models/*",
    "qdrant/*",
    "docs/eval/*",
    "docs/research/*",
    "docs/HANDOFF.md",
    "docs/CODEX_START.md",
    "AGENTS.md",
    "frontend/AGENTS.md",
    "frontend/node_modules/*",
    "frontend/dist/*",
    "frontend/public/demo-assets/*",
    "frontend/qa/*",
    "scripts/rag_probe_*",
    "scripts/rag_acceptance_*",
)
LINK = re.compile(r"!?\[[^\]\n]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)")


def main() -> int:
    output = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
    )
    files = {name for name in output.decode().split("\0") if name and (ROOT / name).is_file()}
    problems = []
    for name in sorted(files):
        if name != ".env.example" and any(fnmatch.fnmatch(name, p) for p in PRIVATE_PATTERNS):
            problems.append(f"Runtime/private artifact in source: {name}")
        if not name.endswith(".md"):
            continue
        source = ROOT / name
        for target in LINK.findall(source.read_text(encoding="utf-8")):
            target = target.strip("<>")
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            resolved = (source.parent / unquote(url.path)).resolve()
            if not resolved.is_relative_to(ROOT):
                problems.append(f"Local link leaves repository: {name} -> {target}")
                continue
            relative = resolved.relative_to(ROOT).as_posix()
            if relative not in files and not any(p.startswith(relative + "/") for p in files):
                problems.append(f"Link missing from shareable source: {name} -> {target}")
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(f"Repository check passed: {len(files)} shareable files; local Markdown links resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
