#!/usr/bin/env python3
"""Apply small, idempotent fixes to an upstream xSTUDIO checkout.

Usage: fix_upstream.py <path/to/xstudio>

Each fix only changes code that matches a known-bad pattern, so on a ref
where upstream has already fixed it, the script does nothing.

Fixes:
  - QML files with '#' comments (invalid in QML; v1.3.0 ships one in
    FileSystemBrowser.qml, which makes qmlcachegen fail). Fixed on develop.
"""
import pathlib
import re
import sys

HASH_COMMENT = re.compile(r"^(\s*)#(\s)", re.MULTILINE)


def fix_qml_hash_comments(root: pathlib.Path) -> int:
    changed = 0
    for qml in root.rglob("*.qml"):
        if "build" in qml.relative_to(root).parts[:1]:
            continue
        text = qml.read_text(encoding="utf-8")
        new, n = HASH_COMMENT.subn(r"\1//\2", text)
        if n:
            qml.write_text(new, encoding="utf-8")
            print(f"fixed {n} '#' comment(s) in {qml.relative_to(root)}")
            changed += n
    return changed


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = pathlib.Path(sys.argv[1])
    total = fix_qml_hash_comments(root)
    print(f"Upstream fixes applied: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
