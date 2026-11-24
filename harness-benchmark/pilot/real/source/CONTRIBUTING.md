# Contributing to EvCore

Contributions are welcome: bug reports, docs fixes, new providers, tools and
extensions.

EvCore is derived from [Orca Harness](https://github.com/okikorg/orca-harness).
Issues and pull requests for EvCore go to this repository. Problems that also
exist in upstream Orca Harness can be reported there too, but keep EvCore
reports in EvCore.

## Workflow

1. Open an [issue](https://github.com/oigorbrito/EvCore/issues) to report a
   bug or discuss a change before you build it.
2. Fork, branch, and keep the change focused. Match the surrounding code and
   add tests for behavior you change.
3. Run `cargo test --workspace`, `cargo clippy --workspace --all-targets` and
   `cargo fmt --all` before opening a pull request.

Compatibility names stay as they are: crate names `orcacode` and
`orca-harness-*`, the `orcacode` binary, `ORCA_*` variables, and the
configuration, session and credential paths. Do not rename them in a
contribution. See [PROVENANCE.md](PROVENANCE.md) for the full list.

## Using AI tools and agents

Using AI coding tools and agents (Claude Code, Orcacode, Copilot, Cursor and
similar) is fine for most contributions, including providers, tools,
extensions, the CLI, workflows, tests and docs. The usual bar still applies:
you are the author of the pull request, so read and understand every line you
submit, and make sure it builds and passes the checks above.

### Exception: `crates/harness-core`

`crates/harness-core` is the kernel every other crate depends on. Changes to
it need human review:

- A human must review and understand every change to `crates/harness-core`
  before it is submitted. Do not open a pull request with agent-written core
  changes that nobody has read.
- Say in the pull request description when AI tools were used for core
  changes, and what you checked by hand.
- Core changes are reviewed by a maintainer before merge, regardless of how
  they were written.
- If you are running an agent on this repo, configure it to ask before editing
  `crates/harness-core`.

## Releases

EvCore has no release channel yet. Do not add tags, release workflows or
publishing steps in a contribution. See [ci/README.md](ci/README.md).

## License

By contributing you agree that your contributions are licensed under the
Apache License 2.0.
