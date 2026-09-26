"""Import the shared encoder from the CASTER package.

The encoder lives in ``aigc/rag_encoder.py`` so that evaluation, indexing and the
online query path cannot drift apart. The build scripts run from the RAG
workspace, which is a sibling of the deployment, so the package root is added to
``sys.path`` here. Override it with ``--package-root`` if the layout changes.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_PACKAGE_ROOT = Path(
    os.environ.get("AIGC_PACKAGE_ROOT", Path(__file__).resolve().parents[1])
)
_package_root: Path | None = None


def add_package_root(root: Path | None = None) -> Path:
    global _package_root
    candidate = (
        Path(root).expanduser().resolve() if root else (_package_root or DEFAULT_PACKAGE_ROOT)
    )
    if not (candidate / "aigc" / "rag_encoder.py").is_file():
        raise SystemExit("找不到 aigc 包：%s（用 --package-root 指定部署根目录）" % candidate)
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
    _package_root = candidate
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=None)
    args = parser.parse_args()
    root = add_package_root(args.package_root)
    from aigc.rag_encoder import DEFAULT_INSTRUCTION, Encoder, fingerprint, instruct

    print("package root:", root)
    print(
        "fingerprint(0.6B, 1024, 2048):",
        fingerprint("97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3", 1024, 2048),
    )
    print("default instruction:", DEFAULT_INSTRUCTION)
    print("instruct example:", instruct(DEFAULT_INSTRUCTION, "女仆装")[:60], "...")
    print("Encoder:", Encoder.__name__)


ENCODER_API = ("Encoder", "DEFAULT_INSTRUCTION", "fingerprint", "instruct")


def __getattr__(name):
    """Re-export the encoder API from the package after the root is added.

    The build scripts import ``Encoder`` and ``fingerprint`` from this module so
    that there is exactly one implementation, in the package.

    Only those names are answered. The import system probes a module for
    ``__path__`` and ``__all__`` before resolving ``from rag_encoder import X``,
    and answering such a probe imported the package as a side effect - which
    pinned ``sys.path`` to the default root before ``--package-root`` could be
    read, so an override silently did nothing.
    """
    if name not in ENCODER_API:
        raise AttributeError(name)
    add_package_root()
    from aigc import rag_encoder as _encoder

    return getattr(_encoder, name)


if __name__ == "__main__":
    main()
