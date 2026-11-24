# orca-harness
#
#   make help                     every target
#   make check test               what CI runs before a merge
#   make notes VERSION=0.3.0      disabled: EvCore has no release channel yet
#
# Release targets are disabled (fail closed); see PROVENANCE.md.

SHELL := /bin/bash
.DEFAULT_GOAL := help

VERSION ?=
require_version = $(if $(VERSION),,$(error VERSION is required, for example: make $@ VERSION=0.3.0))

.PHONY: help build test fmt clippy audit check size bench bench-all notes prepare tag release dist publish

help:  ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-9s %s\n", $$1, $$2}'

## Development

build:  ## release build of orcacode
	cargo build --release -p orcacode

test:  ## the workspace test suite plus the benchmark reporting tests, as CI runs them
	cargo test --workspace
	./benchmarks/run_reporting_tests.sh

fmt:  ## rustfmt check, as CI runs it
	cargo fmt --all --check

clippy:  ## clippy with warnings denied, as CI runs it
	cargo clippy --workspace --all-targets -- -D warnings

audit:  ## source-size limit: the gate, then the largest files
	./ci/check-source-size.sh
	python3 scripts/audit_crates.py --top 25

check: fmt audit clippy  ## what CI checks before the tests: fmt, source size, clippy

size: build  ## the release binary against ci/check-binary-size.sh
	./ci/check-binary-size.sh

bench:  ## benchmark smoke, as CI runs it
	cargo bench --workspace -- --test

bench-all: build  ## every suite bench.yml runs, budgets informational off Linux
	cargo build --release -p orca-harness-core --example fanout_probe
	cargo build --release -p orca-harness-tools --example tool_fanout_perf
	./benchmarks/kernel/run.sh --ci --criterion
	./benchmarks/startup/run.sh --ci
	./benchmarks/core-tools/run.sh
	python3 -m unittest discover -s benchmarks/mcp -p '*_test.py'
	python3 benchmarks/mcp/accuracy.py
	python3 benchmarks/mcp/distribution.py
	python3 benchmarks/mcp/pareto.py
	./benchmarks/subagent/run.sh --quick
	./benchmarks/subagent/sim.sh --quick

## Release (disabled)

# Disabled: EvCore has no release channel. These targets used to tag, build and
# publish upstream Orcacode, and the script now refuses them (ci/release.sh).
notes prepare tag release dist publish:  ## disabled: no EvCore release channel
	@echo "release is disabled for EvCore: no EvCore release channel is configured (see PROVENANCE.md)" >&2
	@exit 1
