"""Export/check the public contract without starting workers or reading runtime data."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aigc.api import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "frontend/openapi.json")
    args = parser.parse_args()
    app = create_app(config={})
    content = json.dumps(app.openapi(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    assert app.state.store is None and app.state.comfy is None and app.state.agent is None
    if args.check:
        if not args.output.exists() or args.output.read_text() != content:
            parser.exit(
                1, "API contract changed: run make contracts and commit the generated files.\n"
            )
    else:
        args.output.write_text(content)
    for name in ("canvas-presets.json", "anima-outfit-previews.json"):
        source = ROOT / "integrations" / name
        target = ROOT / "frontend/src/data" / name
        if args.check:
            if not target.exists() or target.read_bytes() != source.read_bytes():
                parser.exit(1, f"Frontend catalog changed: run make contracts ({name}).\n")
        else:
            target.write_bytes(source.read_bytes())
    print(f"OpenAPI contract {'verified' if args.check else 'exported'}: {args.output.name}")


if __name__ == "__main__":
    main()
