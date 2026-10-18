# xstudio-release

GitHub Actions that build [xSTUDIO](https://github.com/AcademySoftwareFoundation/xstudio) from upstream for **Windows (x64)** and **macOS (Apple Silicon)**.

This repo is not a fork. It holds only build automation. xSTUDIO's source is cloned at build time, at whatever tag, branch or commit you pick, and built the way the upstream build guides describe.

| Platform | Runner | Output |
|---|---|---|
| Windows x64 | `windows-2022` | `xSTUDIO-<ref>-windows-x64-setup.exe` (NSIS installer) |
| macOS arm64 | `macos-15` | `xSTUDIO-<ref>-macos-arm64.dmg` (ad hoc signed) |

## Running a build

**Manually:** go to Actions → **Build xSTUDIO** → **Run workflow**. Pick the upstream ref (default `v1.3.0`) and which platforms to build. The installers appear as artifacts on the run and are kept for 14 days.

**From a tag:** push a tag named after the upstream release:

```
git tag v1.3.0 && git push origin v1.3.0
```

That builds upstream `v1.3.0` on both platforms and creates a **draft** GitHub Release with both installers attached. Nothing becomes public until you publish the draft.

## The first run is slow

xSTUDIO uses vcpkg, which builds every dependency from source: FFmpeg, Python, OpenImageIO, OpenEXR, OCIO, OTIO and more. On a cold cache this takes hours, and on GitHub-hosted runners it can approach the 6-hour job limit.

The workflow is built for this:

- **Dependencies are a separate step** with a 320-minute timeout.
- **The cache is saved even if that step fails or times out.** vcpkg stores each package as soon as it's built, so the next run resumes where the last one stopped.
- **If a job dies in the dependency step, click "Re-run failed jobs".** The second attempt picks up the finished packages and usually completes.

After that, a build where dependencies haven't changed spends roughly 10–20 minutes on them (restore plus verify), then compiles xSTUDIO itself.

## Caching

The cache uses vcpkg's file provider stored in the GitHub Actions cache. Be aware of its limits:

- **7-day expiry:** an entry is evicted if nothing restores it for 7 days. `keep-cache-warm.yml` restores both platform caches every Monday to reset that clock. Delete that workflow if you'd rather not spend the minutes.
- **~10 GB per repo:** when the total is exceeded, the oldest entries go first. Each save holds the full set, so losing old entries costs nothing.
- **Saved only when something new was built**, to avoid filling the quota with identical copies.

If the cache is lost, the next build is simply cold again; nothing breaks.

### Longer-lived alternatives

- **GitHub Packages (NuGet)** is vcpkg's recommended backend for GitHub. Entries persist indefinitely and are stored per package. On a private repo it counts against your Packages storage. See [Microsoft's tutorial](https://learn.microsoft.com/vcpkg/consume/binary-caching-github-packages). To switch, change `VCPKG_BINARY_SOURCES` to the `nuget,...` form and add the `nuget sources add` step. macOS also needs `brew install mono`.
- **A self-hosted runner**, e.g. a Mac you own, for the macOS job. Change `runs-on: macos-15` to `runs-on: [self-hosted, macOS, ARM64]` and point `ROOT` at a fixed directory. The cache then lives on that disk permanently, there's no 6-hour limit, and no macOS minute multiplier. The machine has to be awake when a build runs.

## Codecs and licensing

Read this before making builds public. This is not legal advice.

**What the stock build already does.** Upstream `vcpkg.json` builds FFmpeg with the `x264` and `x265` features. In vcpkg these pull in the `gpl` feature, so **a stock xSTUDIO build already ships GPL-licensed FFmpeg libraries**. FFmpeg's built-in decoders are also included: ProRes, DNxHD/HR, H.264, HEVC and AAC. xSTUDIO itself doesn't restrict which codecs it uses.

**Patents are a separate question.** H.264, HEVC and AAC are covered by patent pools, and ProRes is Apple's. Building these codecs is fine; distributing binaries that contain them may need licences, depending on who receives them and where.

**The `ffmpeg_extra_features` input** adds vcpkg FFmpeg features on top of upstream, e.g. `nonfree,fdk-aac`. **`nonfree` makes the FFmpeg binaries legally non-redistributable.** Builds with it should stay in a private repo and must not go into public releases.

**Visibility.** On a public repo, run artifacts and releases can be downloaded by anyone, which counts as distribution. A private repo keeps builds to you and your collaborators. Private repos use your Actions minutes, and macOS minutes are billed at a multiplier.

## macOS: opening an unsigned build

The DMG is ad hoc signed, not signed or notarised with an Apple Developer ID. The first time you open it, Gatekeeper will block it. Either right-click the app → **Open**, or run:

```
xattr -dr com.apple.quarantine /Applications/xSTUDIO.app
```

To ship properly signed builds, add Developer ID signing and `notarytool` steps with your certificate stored in repo secrets.

## How the build maps to the upstream guides

| Upstream step | Here |
|---|---|
| Qt 6.5.3 + Qt Image Formats | `jurplel/install-qt-action` (aqtinstall), cached |
| vcpkg at the pinned commit | Read from `builtin-baseline` in the checked-out `vcpkg.json`, so it follows whatever ref you build |
| `CMakeUserPresets.json` with `Qt6_DIR` | Passed as `-DQt6_DIR=...` alongside the stock `WinNinjaRelease` / `MacOSNinjaRelease` preset |
| Windows: VS 2022 dev shell, NSIS, `--target package` | `ilammy/msvc-dev-cmd`, NSIS on the runner image (or installed via choco), same build command |
| macOS: Homebrew tools, `--target install` | Same tools; the resulting `xSTUDIO.app` is put into a DMG |

Upstream's presets expect vcpkg in a folder next to the xSTUDIO checkout (`../vcpkg`), so both are cloned under one short root: `C:\x` on Windows, `~/x` on macOS. The short Windows path also keeps vcpkg clear of path-length limits.

## Possible next steps

- **Linux:** a Rocky 9 container job using the `LinuxNinjaRelease` preset.
- **Faster cold builds:** a release-only vcpkg triplet (`VCPKG_BUILD_TYPE release`) skips debug builds of every dependency. It roughly halves dependency time, but differs from upstream's triplets, so test it first.
- **Intel Macs:** a `macos-13` job with the `MacOSIntelNinjaRelease` preset and the `x64-osx` triplet.
