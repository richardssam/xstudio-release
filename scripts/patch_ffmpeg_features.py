#!/usr/bin/env python3
"""Add extra vcpkg features to the ffmpeg dependency in xSTUDIO's vcpkg.json.

Usage: patch_ffmpeg_features.py <path/to/vcpkg.json> "<feature1,feature2,...>"

An empty feature list leaves the manifest untouched, so the build matches
upstream exactly. Feature names are vcpkg ffmpeg port features, e.g.
"nonfree", "fdk-aac", "dav1d". See https://vcpkg.io/en/package/ffmpeg.html
"""
import json
import sys


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    path, raw = sys.argv[1], sys.argv[2]
    extra = [f.strip() for f in raw.split(",") if f.strip()]
    if not extra:
        print("No extra FFmpeg features requested; using upstream vcpkg.json as-is.")
        return 0

    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    deps = manifest.get("dependencies", [])
    for i, dep in enumerate(deps):
        name = dep if isinstance(dep, str) else dep.get("name")
        if name != "ffmpeg":
            continue
        if isinstance(dep, str):
            dep = {"name": "ffmpeg", "features": []}
            deps[i] = dep
        features = dep.setdefault("features", [])
        for feat in extra:
            if feat not in features:
                features.append(feat)
        break
    else:
        print("ERROR: no ffmpeg dependency found in", path, file=sys.stderr)
        return 1

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    print("FFmpeg features now:", ", ".join(features))
    if "nonfree" in extra:
        print("WARNING: 'nonfree' makes the resulting FFmpeg binaries "
              "non-redistributable. Keep these builds private.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
