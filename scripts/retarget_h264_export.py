#!/usr/bin/env python3
"""Point xSTUDIO's H.264 export presets at the OS's H.264 encoder.

Usage: retarget_h264_export.py <path/to/xstudio> <macos|windows>

xSTUDIO's movie export runs its bundled ffmpeg with "-c:v libx264 ...". When
the build drops x264 (to keep FFmpeg LGPL), those presets would fail. This
swaps them for the encoder the operating system provides, which Apple and
Microsoft license:
  macOS   -> h264_videotoolbox (VideoToolbox)
  Windows -> h264_mf           (Media Foundation)
Both are enabled in vcpkg's FFmpeg port on those platforms.

libx264-only options (-preset, -tune, -crf) don't apply to these encoders,
so the presets switch to a target bitrate instead. Only files that contain
"libx264" are touched; running it twice changes nothing.
"""
import pathlib
import re
import sys

ENCODER = {"macos": "h264_videotoolbox", "windows": "h264_mf"}

# Map each upstream libx264 option string to an OS-encoder equivalent.
# The LowQ preset (-crf 30) becomes a low bitrate; the others a high one.
FILES = [
    "src/plugin/video_output/video_renderer/src/video_render_prefs.json",
    "python/src/xstudio/api/session/session.py",
]
X264_OPTS = re.compile(r"-c:v libx264((?: -[A-Za-z:_]+ [^\s\"',]+)*)")


def replacement(encoder: str, opts: str) -> str:
    bitrate = "4M" if "-crf" in opts else "20M"
    return f"-c:v {encoder} -pix_fmt yuv420p -b:v {bitrate}"


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[2] not in ENCODER:
        print(__doc__)
        return 2
    root = pathlib.Path(sys.argv[1])
    encoder = ENCODER[sys.argv[2]]
    total = 0
    for rel in FILES:
        path = root / rel
        if not path.exists():
            print(f"skip (not in this xSTUDIO version): {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        new, n = X264_OPTS.subn(lambda m: replacement(encoder, m.group(1)), text)
        if n:
            path.write_text(new, encoding="utf-8")
            print(f"{rel}: {n} libx264 preset(s) -> {encoder}")
            total += n
    if "libx264" in "".join((root / r).read_text(encoding="utf-8")
                            for r in FILES if (root / r).exists()):
        print("ERROR: a libx264 reference is left that this script didn't recognise",
              file=sys.stderr)
        return 1
    print(f"H.264 export presets retargeted: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
