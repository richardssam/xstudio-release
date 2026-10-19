#!/usr/bin/env python3
"""Make xSTUDIO.app self-contained by copying in any missing dylibs.

Usage: macos_bundle_deps.py <path/to/xSTUDIO.app> <search dir> [<search dir> ...]

xSTUDIO's install step runs macdeployqt, which deploys Qt but does not
reliably pull in the vcpkg libraries the app links through @rpath (spdlog,
fmt, OpenImageIO, ...). Those then resolve on the build machine via its
absolute rpaths, and fail anywhere else ("Library not loaded:
@rpath/libspdlog...").

This script walks every Mach-O file in the bundle, and for each dependency:
  - system libraries (/usr/lib, /System) are left alone;
  - @rpath/<name> that is not already in Contents/Frameworks is copied there
    from the first search directory that has it;
  - an absolute path outside the system (e.g. /opt/homebrew/..., the build
    tree) is copied into Contents/Frameworks and the reference is rewritten
    to @rpath/<name>;
  - @executable_path / @loader_path references are checked to exist.
Newly copied libraries are scanned too, until nothing more is missing. The
main executables get @executable_path/../Frameworks on their rpath.

Any dependency that cannot be satisfied is reported and the script exits 1,
so a broken bundle fails CI instead of failing on someone's Mac.
"""
import os
import pathlib
import shutil
import subprocess
import sys

MACHO_MAGICS = {
    b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe",  # 64/32-bit little endian
    b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce",  # big endian
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",  # universal
}
SYSTEM_PREFIXES = ("/usr/lib/", "/System/")


def is_macho(path: pathlib.Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        with open(path, "rb") as fh:
            return fh.read(4) in MACHO_MAGICS
    except OSError:
        return False


def run(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def install_name(path: pathlib.Path):
    out = run("otool", "-D", str(path)).splitlines()
    return out[1].strip() if len(out) > 1 else None


def dependencies(path: pathlib.Path):
    """Return load commands of a Mach-O file, excluding its own install name."""
    own = install_name(path)
    deps = []
    for line in run("otool", "-L", str(path)).splitlines()[1:]:
        line = line.strip()
        if not line or line.endswith(":"):  # per-architecture headers
            continue
        dep = line.split(" (compatibility")[0].strip()
        if dep != own and dep not in deps:
            deps.append(dep)
    return deps


def rpaths(path: pathlib.Path):
    out = run("otool", "-l", str(path)).splitlines()
    found = []
    for i, line in enumerate(out):
        if line.strip() == "cmd LC_RPATH":
            for follow in out[i + 1:i + 4]:
                follow = follow.strip()
                if follow.startswith("path "):
                    found.append(follow[5:].split(" (offset")[0])
    return found


def bundle_rpath_dirs(binary: pathlib.Path, contents: pathlib.Path):
    """Directories inside the bundle where @rpath lookups from `binary` can land."""
    dirs = [contents / "Frameworks"]
    for rp in rpaths(binary):
        if rp.startswith("@loader_path"):
            d = binary.parent / rp[len("@loader_path"):].lstrip("/")
        elif rp.startswith("@executable_path"):
            d = contents / "MacOS" / rp[len("@executable_path"):].lstrip("/")
        else:
            continue  # absolute rpaths point at the build machine
        dirs.append(d.resolve())
    return dirs


def copy_into_frameworks(src: pathlib.Path, rel: str, frameworks: pathlib.Path):
    """Copy a dylib (or the .framework that contains it) into Frameworks."""
    parts = pathlib.PurePosixPath(rel).parts
    fw = next((p for p in parts if p.endswith(".framework")), None)
    if fw:
        fw_src = src
        while fw_src.name != fw:
            fw_src = fw_src.parent
        dest = frameworks / fw
        if not dest.exists():
            shutil.copytree(fw_src, dest, symlinks=True,
                            ignore=shutil.ignore_patterns("Headers", "*.prl"))
        target = frameworks / rel
    else:
        target = frameworks / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src.resolve(), target)
    os.chmod(target, 0o755)
    subprocess.run(["install_name_tool", "-id", f"@rpath/{rel}", str(target)],
                   check=True, capture_output=True)
    return target


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    app = pathlib.Path(sys.argv[1]).resolve()
    search = [pathlib.Path(p).resolve() for p in sys.argv[2:]]
    contents = app / "Contents"
    frameworks = contents / "Frameworks"
    frameworks.mkdir(exist_ok=True)

    # Main executables must be able to find Contents/Frameworks via @rpath.
    for exe in sorted((contents / "MacOS").iterdir()):
        if is_macho(exe) and "@executable_path/../Frameworks" not in rpaths(exe):
            run("install_name_tool", "-add_rpath", "@executable_path/../Frameworks", str(exe))
            print(f"added rpath @executable_path/../Frameworks to {exe.name}")

    copied, problems, scanned = [], [], set()
    queue = sorted(p for p in app.rglob("*") if is_macho(p))
    while queue:
        binary = queue.pop(0)
        if binary in scanned:
            continue
        scanned.add(binary)
        for dep in dependencies(binary):
            if dep.startswith(SYSTEM_PREFIXES):
                continue
            where = binary.relative_to(app)

            if dep.startswith("@rpath/"):
                rel = dep[len("@rpath/"):]
                if any((d / rel).exists() for d in bundle_rpath_dirs(binary, contents)):
                    continue
                src = next((d / rel for d in search if (d / rel).exists()), None)
                if src is None:
                    problems.append(f"{where}: cannot find {dep} in any search dir")
                    continue
                queue.append(copy_into_frameworks(src, rel, frameworks))
                copied.append(rel)

            elif dep.startswith(("@executable_path/", "@loader_path/")):
                base = contents / "MacOS" if dep.startswith("@executable_path/") else binary.parent
                resolved = (base / dep.split("/", 1)[1]).resolve()
                if not resolved.exists():
                    problems.append(f"{where}: {dep} does not exist in the bundle")

            elif dep.startswith("/"):
                src = pathlib.Path(dep)
                if str(src).startswith(str(app)):
                    continue
                if not src.exists():
                    problems.append(f"{where}: absolute dependency {dep} not found")
                    continue
                rel = src.name
                if not (frameworks / rel).exists():
                    queue.append(copy_into_frameworks(src, rel, frameworks))
                    copied.append(rel)
                run("install_name_tool", "-change", dep, f"@rpath/{rel}", str(binary))

    print(f"Scanned {len(scanned)} Mach-O files; copied {len(copied)} libraries into Frameworks:")
    for rel in copied:
        print(f"  {rel}")
    for p in problems:
        print(f"::error::{p}")
    if problems:
        print(f"FAILED: {len(problems)} dependencies cannot be satisfied inside the app "
              "(listed above). The app would crash or lose features on other Macs.")
        return 1
    print("OK: every dependency resolves inside the app bundle.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
