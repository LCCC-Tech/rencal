---
name: Task
about: Track a small, atomic implementation or maintenance task
title: "AV3-1760: Add baseline Ruff and Sphinx documentation automation"
labels: "ci, documentation, tooling"
assignees: ""
type: Task

---

**Task summary**

Add a reproducible, repository-local quality and documentation baseline for
RenCal. The rollout should make Ruff, pytest, Interrogate, and Sphinx use the
same locked development environment, while keeping current lint, documentation,
and docstring-coverage findings visible rather than hiding them with broad
exclusions.

**Why this task is needed**

RenCal already has Ruff, pytest, and Sphinx-related configuration, but the
tooling is split across dependency groups and does not yet provide a portable
documentation build, generated API documentation, or an automated view of
docstring coverage. Consolidating the checks gives contributors and CI a
repeatable baseline and makes documentation gaps measurable before any separate
cleanup work is undertaken.

**Proposed implementation**

1. Update `pyproject.toml` and regenerate `uv.lock`:
   - Preserve the existing Python 3.12 support and runtime dependencies.
   - Add Interrogate, Sphinx, AutoAPI, the Markdown builder, and the RTD theme
     to the development environment used by CI. Reconcile the existing `dev`
     and `docs` dependency groups rather than creating a second undocumented
     dependency source.
   - Keep the existing Ruff and pytest conventions, adding only the shared
     settings needed for the rollout.
2. Add or update CI checks so Ruff formatting and linting expose the current
   baseline without blocking the initial rollout, while pytest remains blocking.
3. Add portable Sphinx/AutoAPI configuration under `docs/source/` and a
   `docs/Makefile`. Adapt AutoAPI paths and the index to RenCal's current
   top-level `rencal/` package and existing documentation structure; verify the
   generated toctree target after the first build.
4. Add `scripts/documentation/format_confluence_markdown.py` and
   `scripts/documentation/post-process-confluence.sh` to transform generated
   AutoAPI Markdown into readable, Confluence-ready pages. The formatter should
   clean anchors, generate stable dotted module names, rewrite renamed-page
   links, and support clean/verbose operation.
5. Add deterministic tests in
   `tests/documentation/test_format_confluence_markdown.py` covering package
   inference, module naming, output paths, heading/anchor cleanup, link
   rewriting, multiple pages, and the no-input failure case. Tests must not
   require credentials, network access, or external services.
6. Add `pipelines/documentation.yml` using `uv sync --locked` and the repository
   development environment to:
   - build Sphinx Markdown;
   - generate Confluence-ready Markdown;
   - run Interrogate with `--fail-under 0 --verbose`;
   - publish raw reports, generated documentation, and an informational
     coverage summary as build artifacts.
7. Keep the documentation build blocking, but treat Interrogate coverage as
   informational. Do not conceal existing Ruff findings, undocumented code, or
   Sphinx warnings with broad exclusions. Any exclusions must be narrow,
   intentional, and reviewed.
8. Update `.gitignore` for raw Sphinx/AutoAPI output and explicitly choose
   whether reviewed Confluence-ready pages are tracked.

**Acceptance criteria**

- [ ] The work is implemented on branch `AV3-1760-ruff-rencal`.
- [ ] `uv lock --check` and `uv sync --locked --group dev` succeed using the
      final `pyproject.toml` and `uv.lock`.
- [ ] `uv run ruff check . --statistics`, `uv run ruff format .`, and
      `uv run pytest` run from the locked environment; Ruff findings are
      reported rather than broadly excluded and pytest remains blocking in CI.
- [ ] `make -C docs markdown SPHINXBUILD="uv run python -m sphinx.cmd.build"`
      produces Markdown API documentation, with a verified valid AutoAPI
      toctree and reviewed warnings.
- [ ] The Confluence post-processing wrapper generates output from the
      documentation build and rewritten links resolve in the generated tree.
- [ ] Focused formatter tests pass with
      `uv run pytest tests/documentation/test_format_confluence_markdown.py`.
- [ ] Interrogate runs with `--fail-under 0 --verbose`, includes a parseable
      `TOTAL` row, and publishes an informational Markdown summary without
      failing solely because coverage is low.
- [ ] `pipelines/documentation.yml` installs dependencies from `pyproject.toml`
      and `uv.lock`, publishes documentation and reports, and replaces any old
      documentation pipeline name.
- [ ] Raw Sphinx, AutoAPI, and temporary build output is ignored according to
      the documented artifact policy.
- [ ] `git diff --check` passes and the final working tree/branch status is
      recorded.

**Additional context (Optional)**

This is a tooling and baseline-establishment change, not a request for a large
Ruff cleanup or immediate docstring-coverage target. Fixing individual lint,
docstring, or Sphinx findings should be handled in follow-up issues. Existing
RenCal documentation is currently built as an Astro site under `docs/web`; the
Sphinx/AutoAPI setup should coexist with that site and avoid committing caches
or generated build artifacts.
