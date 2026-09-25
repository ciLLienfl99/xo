# Custom Mac ARM64 build

This repository builds the exact uploaded OxideTerm 2.0.31 revision
`4d5933c9914ab5c5efc4ff4124bdf255f6ba619d` plus the reviewed custom changes.
Upstream: https://github.com/AnalyseDeCircuit/oxideterm

The four `patch.b64.00` through `patch.b64.03` files concatenate into one
Base64-encoded XZ archive of a zero-context UTF-8 unified source diff.
`prepare.py` verifies the decompressed SHA-256 before applying it with
`git apply --unidiff-zero`. The hash is
`5ef0f6020474039270af123ee8f17ba000b563eeab63cfe50acbbe8c42b5d469`.
The build reads only these four payload parts. Older staging files are not inputs.

Changes: connection-state-dependent active-session context menus; independent
10–24 px active-session font size; macOS single-app portable storage inside
`Contents/UserData`; data-preserving program updates and rollback.

Workflow: `.github/workflows/mac-arm64.yml`. It runs on ARM64 macOS, checks
Python packaging regressions and all locale catalogs, tests native portable
runtime/update libraries, compiles the release, then validates package layout,
ARM64 executables, and their code signatures.

Download the `OxideTerm-Mac-ARM64-Bundle` artifact from a successful run.
Its application ZIP contains one `OxideTerm.app`; the ordinary upstream
nonportable app ZIP and DMG are intentionally not included.

This is a local-use custom build, not an official/notarized upstream release.
Do not replace the whole old application with Finder: its UserData is inside.
Use the included data-preserving installer described in the build's usage guide.
Interactive GUI and real SSH/SFTP testing remain separate from CI verification.

The build also publishes complete corresponding patched source, with the
original GPL-3.0-only license and third-party notices. No user session data,
passwords, signing keys, or personal settings are included in the source payload.
