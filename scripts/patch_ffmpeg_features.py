#!/usr/bin/env python3
"""Add or remove vcpkg features on the ffmpeg dependency in xSTUDIO's vcpkg.json.

Usage: patch_ffmpeg_features.py <path/to/vcpkg.json> "<add1,add2,...>" ["<remove1,remove2,...>"]

Empty lists leave the manifest untouched, so the build matches upstream
exactly. Feature names are vcpkg ffmpeg port features, e.g. "nonfree",
"fdk-aac", "x264", "x265". See https://vcpkg.io/en/package/ffmpeg.html

Removing x264 and x265 is what turns xSTUDIO's FFmpeg from a GPL build into
an LGPL one: in the vcpkg port they are the only features xSTUDIO enables that
pull in the 'gpl' feature. FFmpeg's own H.264/HEVC *decoders* are unaffected.
"""
import json
import sys


def split(raw: str):
    return [f.strip() for f in raw.split(",") if f.strip()]


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print(__doc__)
        return 2

    path = sys.argv[1]
    add = split(sys.argv[2])
    remove = split(sys.argv[3]) if len(sys.argv) == 4 else []
    if not add and not remove:
        print("No FFmpeg feature changes requested; using upstream vcpkg.json as-is.")
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
        for feat in remove:
            if feat in features:
                features.remove(feat)
                print(f"removed FFmpeg feature: {feat}")
            else:
                print(f"FFmpeg feature not present, nothing to remove: {feat}")
        for feat in add:
            if feat not in features:
                features.append(feat)
                print(f"added FFmpeg feature: {feat}")
        break
    else:
        print("ERROR: no ffmpeg dependency found in", path, file=sys.stderr)
        return 1

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    print("FFmpeg features now:", ", ".join(features))
    gpl_now = any(f in features for f in ("gpl", "x264", "x265", "all-gpl"))
    print("FFmpeg licence for this build:", "GPL" if gpl_now else "LGPL")
    if "nonfree" in add:
        print("WARNING: 'nonfree' makes the resulting FFmpeg binaries "
              "non-redistributable. Keep these builds private.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
