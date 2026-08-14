# Contributing to RenCal

Thank you for contributing to RenCal. We welcome bug reports, documentation
improvements, tests, and focused changes that improve renewable-energy
calibration and forecasting.

Please read the [Code of Conduct](CODE_OF_CONDUCT.md) before participating.

## Before you start

1. Search existing [issues](https://github.com/LCCC-Tech/rencal/issues) before
   opening a new one.
2. For a substantial change, open an issue first so the proposed scope can be
   discussed.
3. Do not include credentials, internal data, proprietary information, or
   generated build artefacts in an issue or pull request.

Use GitHub Issues for public bugs and feature requests.

## Development setup

RenCal currently supports Python 3.12 and uses `uv` for dependency and
environment management.

```bash
git clone https://github.com/LCCC-Tech/rencal.git
cd rencal
uv sync --group dev
```

Create a feature branch from `main`:

```bash
git switch main
git pull --ff-only
git switch -c <short-description>
```

## Checks

Run the repository checks before opening a pull request:

```bash
./checks.sh
```

The checks cover formatting, Ruff linting, BasedPyright type checking, and the
pytest suite. You can also run individual checks with `uv run`:

```bash
uv run ruff format --check rencal/ tests/ scripts/
uv run ruff check rencal/ tests/ scripts/
uv run basedpyright --warnings
uv run pytest tests/ -v
```

Add or update tests for behavioural changes. Keep tests deterministic and do
not commit operational or confidential datasets.

## Pull requests

Pull requests should:

- Link to the relevant issue.
- Explain the problem and the proposed solution.
- Keep the change focused and reviewable.
- Include tests for new or changed behaviour.
- Update user or developer documentation where appropriate.
- State which checks were run and whether any checks were skipped.

Open the pull request against `main`. Maintainers review and approve pull
requests; direct commits to `main` are not permitted. All required CI checks
and branch-protection rules must pass before merge.

## Commit messages and releases

Use concise, imperative commit messages. Where practical, use
[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```text
fix: handle missing ERA5 files
feat: add solar calibration model
docs: clarify local data setup
```

Release Please uses Conventional Commits to prepare a release pull request.
Maintainers review and merge that release pull request; contributors should
not edit release tags, publish to PyPI, or change release versions as part of
ordinary feature work.

## Documentation

Keep the README, tutorials under `docs/tutorials/`, and the documentation site
content accurate when behaviour changes. Public examples must use synthetic or
redistributable data and must not expose internal systems or credentials.

## Questions and support

Use [GitHub Issues](https://github.com/LCCC-Tech/rencal/issues) for public,
reproducible bugs and feature requests. For conduct reports, follow the
[Code of Conduct](CODE_OF_CONDUCT.md).
