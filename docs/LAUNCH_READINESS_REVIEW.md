# ARTEMIS Launch Readiness Review

**Review date:** 2026-10-24  
**Reviewed revision:** `main` at `351ca8422f7b5b54e80a9c1ce03a222e02415b6b`  
**Scope:** Static repository and release-process review. This document does not claim that device tests, the complete test suite, or a release build were executed during this review.

## Executive assessment

ARTEMIS has a meaningful engineering foundation: a Python 3.12+ automation runtime, device and mock drivers, CLI and SDK surfaces, an MCP server, a web console, deterministic and device-oriented test layers, a locked dependency graph, dependency-source checks, a code-quality ratchet, frontend build tests, and wheel-install smoke tests.

The next improvement should focus on **release evidence and repeatability**, not a rewrite of the engine. The immediate CI change in this branch removes a manual-only condition from the deterministic Python test step so that the suite described as the pull-request baseline in `CONTRIBUTING.md` also runs on push and pull-request events.

## Evidence collected

The review checked the default-branch metadata, current repository tree, `README.md`, `CONTRIBUTING.md`, `pyproject.toml`, `.github/workflows/ci.yml`, `Makefile`, `scripts/check_dependency_sources.py`, and `scripts/quality_ratchet.py`.

| Observation | Evidence | Meaning |
|---|---|---|
| The fork's `main` matched upstream `main` at review time | Both pointed to `351ca8422f7b5b54e80a9c1ce03a222e02415b6b` | No local changes were present on the default branch at that revision. |
| The deterministic Python tests were manual-only in CI | The pytest step had `if: github.event_name == 'workflow_dispatch'` | Push and PR events ran lint, format, type-check, frontend tests/build, and packaging checks, but skipped this Python test step. |
| Contributor guidance disagreed with CI | `CONTRIBUTING.md` says `make test` is the same suite used by pull-request CI | The workflow and its documentation were inconsistent. |
| CI already checks several important release properties | `ci.yml` includes dependency-source verification, Ruff, a quality ratchet, Pyright, frontend tests/build, wheel builds, isolated wheel installation, and CLI/resource smoke checks | Preserve these checks and extend evidence where gaps remain. |
| No release entries were returned | GitHub Releases endpoint returned an empty list | No GitHub release artifact was available to verify at review time. This does not prove that no one has distributed builds elsewhere. |
| No workflow runs were returned by the GitHub Actions API | `actions/runs?per_page=10` returned `total_count: 0` | A successful live CI run was not available as evidence. Check repository Actions settings and trigger a run before relying on the workflow. |
| The `main` branch API reported `protected: false` | Branch metadata | Enable protection/rules and required checks before treating CI as a merge gate. |
| GitHub Issues were disabled in repository metadata | `has_issues: false` | Enable the tracker if public bug reports and launch feedback are intended. |
| `playground-submit` was behind `main` and had no unique commits in the comparison | GitHub compare endpoint reported `ahead_by: 0`, `behind_by: 4` | It should not be treated as a source of additional changes without a fresh review. |

## Priority 0 — make test results part of the release evidence

### 1. Run the deterministic Python suite for pushes and pull requests

The workflow change in this branch removes the manual-dispatch-only guard from the existing deterministic pytest step. It continues to use the repository's existing test paths, coverage measurement, and 60% coverage floor.

**Acceptance criteria**

- The CI workflow starts on a push and a pull request.
- The Python quality job actually executes the deterministic pytest suite.
- A deliberately failing deterministic test fails the job.
- The suite remains within the configured job timeout.
- Device-, credential-, cloud-, and manual-only tests remain in their intended separately provisioned lanes.

If runtime cost becomes material, profile the suite and define an explicit fast PR subset plus a scheduled/full-suite lane. Do not silently make the only deterministic behavioral suite manual-only while contributor documentation says it gates PRs.

### 2. Obtain a real successful workflow run

The repository had no Actions runs visible in the API during this review, so the configured workflow has not been verified operationally here.

**Acceptance criteria**

- Confirm GitHub Actions are enabled for the fork.
- Trigger CI from the branch or a pull request.
- Verify every intended job has a successful result.
- Check that generated wheels contain the bundled configuration and UI resources.
- Keep the run URL and revision SHA with the release evidence.

A valid YAML file is not proof that the workflow can complete, and a green build is not proof that an Android device flow works.

### 3. Enforce branch-level release gates

The `main` branch metadata reported no protection. Configure GitHub branch protection or a ruleset to require the expected CI jobs, block force-pushes, and require review where appropriate. Configure the job names only after a real run confirms their exact status-check names.

## Priority 1 — make releases reproducible

### 4. Add a tag-driven release workflow

The current CI uploads Python distributions as short-retention artifacts. That is useful for build inspection, but it is not a durable release process.

A release workflow should be triggered only by an intentional version tag and should:

1. Verify the tag matches the package version and release notes.
2. Run the complete release test matrix appropriate to the release.
3. Build the client wheel, main wheel, and source distribution from the tagged revision.
4. Install artifacts in a clean environment and smoke-test the CLI and bundled assets.
5. Attach artifacts and checksums to a GitHub Release.
6. Publish to a package index only after trusted publishing/credentials and project ownership are configured.
7. Record the source commit, Python version, dependency lock, and build run in the release metadata.

Do not publish a package automatically from an unverified tag or assume a successful build alone establishes compatibility with all Android versions.

### 5. Keep platform-dependent tests explicit

Preserve the separation already expressed by the Makefile and pytest markers:

- Deterministic unit/tool tests: run on regular CI.
- Cross-component tests requiring model credentials or external services: run in a dedicated lane with secrets and cost controls.
- Android/device and E2E tests: run on an authorized emulator or physical device, with the Android version, device model, backend, and relevant environment recorded.
- Real-device video acceptance: archive the test result and logs, with privacy-aware retention.

A release candidate should pass both software-only checks and at least one supported real-device acceptance profile.

### 6. Establish a versioned benchmark evidence record

The README states a 99%+ AndroidWorld completion rate. Keep benchmark claims tied to reproducible evidence rather than a badge alone. Record the benchmark repository/revision, task set, profile, model/provider and version, Android image/device, run count, success definition, exceptions, and machine-readable results. Do not change benchmark claims based only on a small smoke test.

## Priority 2 — harden operations and maintainability

### 7. Improve supply-chain controls

- Keep `uv.lock` and `apps/showcase_ui/package-lock.json` checked and reproducible.
- Retain the public dependency-source guard.
- Review dependency update PRs and add a scheduled vulnerability scan for Python and npm dependencies.
- Consider pinning GitHub Actions to full commit SHAs for stronger supply-chain integrity.
- Generate checksums and optionally an SBOM for release artifacts.

### 8. Treat device access as a security boundary

Document and test which actions can change device state, how ADB/device authorization is granted, what the accessibility helper can read, where screenshots/videos/logs are retained, and how the helper is removed. Ensure credentials and session material are not written to task logs. Keep the UIAutomator fallback and helper installation/uninstallation paths covered by device tests.

### 9. Monitor task quality, latency, and cost separately

A single completion percentage is insufficient for a mobile automation agent. Track at least:

- task success rate split by task family, app, device/Android version, and execution profile;
- action retry, timeout, recovery, and verification-failure rates;
- end-to-end task duration and per-action latency;
- model calls, tokens, and cost per successful task;
- crash rate and fallback frequency;
- regressions between benchmark revisions.

Use confidence intervals and repeated runs for benchmark comparisons. Keep benchmark datasets and production/user traces separate; avoid publishing or retaining sensitive phone content without appropriate consent.

## Hatchable deployment boundary

Hatchable is not a suitable runtime for the entire ARTEMIS engine: the project requires Python, ADB/device connectivity, Android tooling, and native/media dependencies. Do not attempt to port that execution engine into Hatchable's managed JavaScript isolate.

Hatchable may be appropriate for a separate marketing site, documentation front door, public status page, or an authenticated control/analytics surface. Keep device execution on a provisioned machine or container with explicit device access. Any companion service must authenticate access, validate inputs, avoid exposing device credentials, and never execute arbitrary natural-language requests on a privileged device without the intended policy checks.

## Launch checklist

- [ ] CI run is green on the exact release candidate SHA.
- [ ] Deterministic Python suite runs for PRs and pushes.
- [ ] Frontend tests and production build pass.
- [ ] Client wheel, main wheel, and source distribution build and install cleanly.
- [ ] Bundled UI/config assets and CLI entry points pass installed-package smoke tests.
- [ ] At least one real-device acceptance profile passes.
- [ ] Device helper permissions, fallback behavior, uninstall path, and log retention are verified.
- [ ] Benchmark statements link to reproducible results for the released revision.
- [ ] Version, changelog, installation instructions, supported environments, and known limitations are current.
- [ ] Release artifacts and checksums are attached to a versioned GitHub Release.
- [ ] Required checks and branch protection are active.
- [ ] GitHub Issues or another feedback channel is enabled and monitored.

## External references

- [Google ARTEMIS repository](https://github.com/google/artemis)
- [ARTEMIS AndroidWorld benchmark repository](https://github.com/google-research/android_world)
- [GitHub Actions security hardening](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions)
- [GitHub release management](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
- [OWASP Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/)
