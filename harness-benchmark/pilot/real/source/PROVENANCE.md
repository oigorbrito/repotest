# Provenance

EvCore's first code commit is a snapshot import, not a continuation of any
earlier history. Its only Git ancestor is the EvCore template commit
`a1d4252f96200031691bcd179441243639216b23` ("Initial commit"). No commits,
branches or tags from Orca Harness or FineCore were imported.

Import date: 2026-11-15.

## Source

| Item | Value |
| --- | --- |
| Upstream | [okikorg/orca-harness](https://github.com/okikorg/orca-harness) |
| Upstream commit | `2a9fd399cfbbaad773e3cbed92bb6e24d7561f01` (an ancestor of upstream `main`; 5 commits after `orcacode-v0.9.0`, 7 before `orcacode-v0.10.0`) |
| Upstream tree | `9c35d0dd0d7e0f226063f16dd80161e231628e2b` |
| Import reference | FineCore commit `e036dd7a7e2a040b4da1152d99aede0552cb1641` ("chore: import Orca upstream tree verbatim at 2a9fd399") |
| Import reference tree | `9c35d0dd0d7e0f226063f16dd80161e231628e2b` (identical to upstream; `git diff-tree` is empty) |
| Historical reference | [oigorbrito/FineCore](https://github.com/oigorbrito/FineCore), consulted only |
| Identity source | [FineCore PR #188](https://github.com/oigorbrito/FineCore/pull/188), merge commit `d2011bc752842c66fc508d65c03c011c959cc8df` |

Both source commits were fetched directly from GitHub and resolve to the same
tree object: 1101 blobs (1076 `100644`, 25 `100755`), no symbolic links and no
submodules. The EvCore tree was built from those tree and blob objects alone.

## Differences from the upstream tree

The final tree is `9c35d0dd` plus the changes below; no other path differs and
no file mode changes. `git diff 2a9fd399 <this commit>` reproduces the list.

### Identity, adapted from PR #188

PR #188 was written against Orca v0.12.0 (`d89bf274`), which is newer than
this baseline, so its hunks were applied by content rather than copied, with
`FineCore`/`FINECORE`/`finecore` written as `EvCore`/`EVCORE`/`evcore`. No
v0.12.0 code was brought in.

- `crates/cli/Cargo.toml`, `crates/cli/src/evcore.rs`: an `evcore` binary that
  `include!`s `main.rs`, built alongside the unchanged `orcacode` binary.
- `crates/cli/src/main.rs`, `crates/cli/src/headless.rs`: system and bare
  prompts begin "You are EvCore". The USAGE text says "the application's device
  login" (PR #188 changed this line in `usage.rs`, which the baseline keeps in
  `main.rs`).
- `crates/cli/src/run_args.rs`: `--help` shows an EvCore header and the invoked
  binary name. `--version`, `resume` errors and the `update` line use the
  invoked binary name or the disabled-updater note. These are the same
  replacements as PR #188, applied to the baseline's parser.
- `crates/cli/src/approval.rs`, `crates/cli/src/tui/runtime/terminal.rs`: the
  headless approval hint, session-end line and resume hint use the invoked
  binary name.
- `crates/cli/src/plugin/mod.rs`: plugin usage reads `evcore plugin …` for both
  binaries, as in PR #188.
- `crates/cli/src/tui/components/welcome.rs`: welcome card `EVCORE` with the
  subtitle "EvCore — your terminal coding agent".
- `crates/cli/src/tui/command_catalog.rs`, `tui/commands/{dispatch,integrations,refine}.rs`,
  `tui/keys/helpers.rs`, `tui/keys/overlays/apply.rs`,
  `tui/runtime/submission.rs`, `tui/render/overlays.rs`: neutral wording
  ("exit the application", "restart the application", "Missing models? Check
  account access.").
- Tests: `crates/cli/src/main_tests.rs`, `tui/tests/core_4_welcome_help.rs` and
  the new `crates/cli/tests/evcore_identity.rs`.
- `README.md`: the title is EvCore, and a provenance note says the
  documentation below it describes upstream Orcacode.

### Approved functional change: upstream updater disabled

This change comes from PR #188 commit `5d5fd1dd`. Upstream `update` ran the
orcapods.ai installer, and startup polled `orcapods.ai/dl/orcacode/latest.json`.
In EvCore, either path would replace EvCore with upstream Orcacode.

- `crates/cli/src/update.rs`: `update` exits with status 1 and prints
  `update unavailable: no EvCore update channel is configured`. It makes no
  network call and starts no installer.
- `crates/cli/src/runtime/interactive.rs`: the startup update check is removed.

No replacement update mechanism was added. The upstream unit tests in
`update.rs` (`updater_uses_the_public_installer_and_propagates_download_failures`
and `update_comparison_is_numeric_and_fails_closed`) were removed with the code
they tested. `tests/evcore_identity.rs` covers the disabled path instead.

### Deviations from PR #188

- `evcore_identity.rs` drops `--provider local`. The baseline has no
  `--provider` flag, and `--base-url` already selects the local provider.
- `core_4_welcome_help.rs::welcome_centres_the_visible_card_not_its_maximum_width`
  is an adaptation, not a restored upstream assertion. The upstream test looks
  up the upstream subtitle text ("A small, fast agent runtime for your
  terminal") and uses its length as the card width. EvCore's subtitle is
  different, so that text cannot be found and the upstream assertion cannot run
  unchanged. The EvCore test keeps the same property, that the indent equals
  `(90 - W) / 2`, but takes `W` from the widest rendered card row (trailing
  spaces trimmed, indent removed). The ±1 cell tolerance from PR #188 is not
  used. Rendering is unchanged. Reviewers should confirm this adapted assertion
  is acceptable.
- Text produced by the mechanical rename uses "an EvCore" instead of "a EvCore".

### Template files

The template's `README.md` and `evidence-repo-template/` (19 files) are not in
this tree. They remain in the ancestor commit `a1d4252f`.

## Bootstrap identity and release lockdown

This section covers changes made on branch `bootstrap/evcore-initial-base`
after the import above. Its base is the commit `0de23d35afa648d32e31c9c86a4665e849af6727`.

### Metadata

- `Cargo.toml` (`[workspace.package]`): `repository` and `homepage` point to
  `https://github.com/oigorbrito/EvCore`. No other domain is used.
- `crates/cli/Cargo.toml`: the package description identifies EvCore.
- `CONTRIBUTING.md`: issues and contributions go to `oigorbrito/EvCore`.
- `README.md`: presents EvCore as the product, explains its origin in Orca
  Harness, and marks upstream installers, releases, field manual, screenshots
  and benchmark figures as upstream reference. The upstream installer commands
  were removed from the install section, because they install upstream Orcacode.

### Release channel blocked

Decision: EvCore has no release channel of its own yet, so nothing from this
repository is published. The upstream channel was an external publication
path: it created GitHub Releases for `orcacode-v*` tags and pushed binaries
with an admin token to a fixed external host (`releases-production-7656.up.railway.app`).

- `.github/workflows/release-orcacode.yml` is removed from the active
  workflows directory. No replacement workflow was added. Its history stays
  in git.
- `ci/release.sh` refuses `notes`, `prepare`, `tag`, `build` and `publish`.
  The publishing code is still in the file, but nothing reaches it.
- `Makefile`: `notes`, `prepare`, `tag`, `release`, `dist` and `publish`
  fail. The former `git push origin HEAD` in `release` is gone.
- `ci/README.md` and `CONTRIBUTING.md` state that releases are disabled.
- No tag, GitHub Release, binary upload or host push was created or run.
- The updater stays disabled and fails closed: `update` exits with status 1
  and makes no network call (see "Approved functional change" above).

To enable releases later, record a new decision here, define the EvCore
assets, version policy, update endpoint and credentials, and review a new
pipeline. Do not reuse the removed workflow or the `orcapods.ai` and Orca host
endpoints.

### CI

- `.github/workflows/ci.yml` also runs on `push` to
  `bootstrap/evcore-initial-base`. The existing gates are unchanged: fmt,
  source size, clippy, tests, benchmark reporting tests, bench smoke, and the
  release binary size.

### Fidelity against upstream

Compared with upstream tree `9c35d0dd0d7e0f226063f16dd80161e231628e2b`, the
commit `2a9fd399cfbbaad773e3cbed92bb6e24d7561f01` was re-fetched and confirmed
to resolve to that tree.

- 1,103 blobs in HEAD against 1,101 upstream: 1,076 unchanged files (same
  blob ids, same modes), 27 modified, 3 added and 1 removed (the release
  workflow).
- No mode changes. `ci/release.sh` keeps mode `100755`.
- `LICENSE` and `NOTICE` are byte-identical to upstream.
- Modified: `ci.yml`, `CONTRIBUTING.md`, `Cargo.toml`, `Makefile`, `README.md`,
  `ci/README.md`, `ci/release.sh`, `crates/cli/Cargo.toml`, and 19 Rust files
  under `crates/cli/src`, as listed in "Differences from the upstream tree" and
  "Bootstrap identity and release lockdown".
- Added: `PROVENANCE.md`, `crates/cli/src/evcore.rs`,
  `crates/cli/tests/evcore_identity.rs`.
- Removed: `.github/workflows/release-orcacode.yml`.
- History: three commits. The template `a1d4252` is the only ancestor. Neither
  upstream nor FineCore commits are in the history, and no tags or stashes exist.

### Verification record

Host: Windows, rustc/cargo 1.99.1, `CARGO_BUILD_JOBS=2`. Baseline comparisons
ran on a `git archive` of `0de23d35`.

- `cargo fmt --all --check`: PASS.
- `cargo build --release -p orcacode`: PASS. `evcore` and `orcacode` run;
  `update` exits 1 for both. The 6.7 MB size gate is defined for the Linux and
  macOS CI builds and was not evaluated on this Windows binary.
- `cargo test -p orcacode --test evcore_identity` (identity and updater
  safety): PASS, 3/3.
- `cargo test --workspace`: not green on Windows. The same failures appear on
  the baseline: `orca-harness-extensions` session rotation (rename of an open
  directory), `orca-harness-sdk` processes and skills (`sh`, program lookup,
  Windows source paths), `orca-harness-tool-extensions` agent plugin cwd,
  `orcacode` tests for path separators, clipboard paths and `/etc/passwd`, and
  `orca-harness-tools` burst and core-tools tests, which hang on Windows. Not
  caused by this change; not verified on Linux.
- `orca-harness-sandbox-providers`: BLOCKED on Windows, since its test code uses
  `std::os::unix` without a `cfg` gate.
- `cargo clippy --workspace --all-targets -- -D warnings`: FAIL, pre-existing.
  `orca-harness-core` trips `result_large_err` under this toolchain, and other
  crates have lint errors. No lint was allowed to make the gate pass.

### Scheduled benchmarks not changed

`.github/workflows/bench-live.yml` still runs on a daily schedule and may call
external model APIs. It is outside this change. It was not run.

## Not changed

These items stay as they are in the baseline: crate and package names
(`orcacode`, `orca-harness-*`), `ORCA_*` variables, configuration, session and
credential paths (`orcacode/…`), the `orcacode/<version>` user agent, the
OpenRouter title "Orca Code" (PR #188 also kept it), the `orca` theme, plugin
manifest paths, APIs, protocols, authentication, the remaining workflows, `docs/` (upstream reference), `LICENSE` and
`NOTICE`. The release workflow was removed in the section above.

The FineCore README provenance block is not imported, because it describes a
different base. FineCore-specific tooling under `legacy/` is not imported
either.
