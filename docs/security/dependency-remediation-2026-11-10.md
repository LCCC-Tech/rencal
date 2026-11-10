# Dependency vulnerability remediation (10 November 2026)

Tracking issue: [#98](https://github.com/LCCC-Tech/rencal/issues/98).

## Scope and evidence

The Wiz MCP inventory for `LCCC-Tech/rencal/main` returned 291 open findings
across 48 packages: 10 critical, 146 high, 113 medium and 22 low. This includes
end-of-life findings and potentially overlapping CVE/GHSA identifiers; it is not
a count of distinct exploitable vulnerabilities. Findings were last detected on
10 November 2026. All pages were retrieved and consolidated by package and
lockfile, rather than only reviewing the initial page.

There are 196 Python findings across 25 packages and 95 documentation-site
findings across 23 packages. The changes are based on the latest `main` at
`52b02db`, not on an unmerged feature branch. Internal tenant identifiers,
resource identifiers and authentication details are deliberately omitted.

The versions below describe repository remediation, **not resolution in Wiz**.
Wiz must rescan the merged revision (and rebuilt/redeployed artifacts where
applicable) before its findings can be confirmed resolved. Package version
comparisons do not prove runtime reachability or the absence of other CVEs.

Final lockfile verification accounts for all 291 source findings: 280 have
patched versions and 11 concern dependencies removed from the resolved graphs.
All ten critical findings have patched versions; none relies on suppression.

## Critical findings

| Package | Critical advisories | Critical-only minimum | Resolved version |
| --- | --- | --- | --- |
| certifi | GHSA-6q48-6c7w-9gw2 | 2026.10.18 | 2026.10.23 |
| Pillow | CVE-2026-96639, CVE-2026-112398, CVE-2026-112900, CVE-2026-112393, CVE-2026-112403 | 13.0.0 | 13.0.0 |
| PyJWT | CVE-2026-102268 | 2.14.0 | 2.15.1 |
| AnyIO | CVE-2026-63374 | 4.14.2 | 4.14.2 |
| jupyter-server | CVE-2026-44727 | 2.20.0 | 2.21.1 |
| Astro | GHSA-26w7-cxv4-gfx2 | 7.2.8 | 7.4.8 |

The selected versions must also satisfy the higher floors required by other
findings, including PyJWT >=2.15.0, jupyter-server >=2.21.0 and Astro >=7.3.2.
Every locked occurrence of the six critical packages was checked against its
fix floor. Future advisory coverage belongs in vulnerability scanning, not
hard-coded package-version unit tests.

## Python consolidation

All occurrences in `uv.lock` were compared against each finding's fixed
version, not just against a package-level recommended version. Some finding
recommendations lag other advisories for the same package.

| Package | Previous lock | Required floor / chosen floor | Updated lock | Findings |
| --- | --- | --- | --- | ---: |
| anyio | 4.11.0 | 4.14.2 | 4.14.2 | 2 |
| azure-core | 1.36.0 | 1.38.0 | 1.41.0 | 1 |
| bleach | 6.2.0 | 6.4.0 | 6.4.0 | 2 |
| certifi | 2025.10.5 | 2026.10.19 | 2026.10.23 | 1 |
| cryptography | 46.0.3 | 50.0.0 | 50.0.2 | 6 |
| filelock | 3.20.0 | 4.2.1 | 4.2.10 | 4 |
| fonttools | 4.60.1 | 4.60.2 | 4.68.0 | 1 |
| idna | 3.11 | 3.15 | 3.20 | 1 |
| jupyter-server | 2.17.0 | 2.21.0 | 2.21.1 | 6 |
| jupyterlab | 4.4.10 | 4.5.11 | 4.6.6 | 13 |
| mistune | 3.1.4 | 3.3.3 | 3.4.0 | 16 |
| nbconvert | 7.16.6 | 7.17.2 | 7.17.2 | 4 |
| notebook | 7.4.7 | 7.6.3 | 7.6.5 | 2 |
| pillow | 12.0.0 | 13.0.0 | 13.0.0 | 60 |
| pyarrow | 22.0.0 | 23.0.1 | 26.0.1 | 1 |
| pygments | 2.19.2 | 2.20.0 | 2.21.0 | 1 |
| pyjwt | 2.10.1 | 2.15.0 | 2.15.1 | 16 |
| pytest | 8.4.2 | 9.0.3 | 9.2.0 | 1 |
| python-dotenv | 1.2.1 | 1.2.2 | 1.2.4 | 1 |
| requests | 2.32.5 | 2.33.0 | 2.34.2 | 1 |
| setuptools | 80.9.0 | 84.1.0 if present | Removed from resolved graph | 2 |
| soupsieve | 2.8 | 2.10 | 4.1 | 5 |
| tornado | 6.5.2 | 6.6 | 6.6.1 | 23 |
| urllib3 | 2.5.0 | 2.8.0 | 2.8.0 | 6 |
| virtualenv | 20.35.3 | 21.14.13 | 21.15.6 | 20 |

Runtime direct requirements (`requests`, `python-dotenv`, `pyarrow`) and the
development `pytest` requirement now declare patched minimum versions. The
other floors are recorded as `tool.uv.constraint-dependencies`: they restrict
resolution without installing optional notebook/Azure/dev dependencies in the
base environment. They are **not** transitive requirements published in the
wheel metadata, so consumers maintaining their own lockfiles must also update
those lockfiles. The resolver also updated supporting dependencies such as
MSAL, packaging and distlib to satisfy the new graph.

Certifi's critical finding lists 2026.10.18 as fixed, but its catalog recommends
2026.10.19 or later because that release restores unaffected emSign roots.
The constraint uses the latter floor; the lock resolves
to 2026.10.23.

### Finding with no supplied fix

The individual finding for Mistune CVE-2026-44708 supplied no fixed version.
Its Wiz catalog description identifies Mistune 3.2.1 as the fix and links the
[upstream advisory](https://github.com/advisories/GHSA-8g87-j6q8-g93x).
The resolved 3.4.0 is newer than that fix and the other Mistune floors. This
finding was checked explicitly rather than silently treating a missing fixed
version as remediated.

## Documentation-site consolidation

| Package | Previous lock | Required floor (per supported release line) | Updated lock | Findings |
| --- | --- | --- | --- | ---: |
| @ungap/structured-clone | 1.3.0 | 1.3.1 | 1.4.0 | 1 |
| @xmldom/xmldom | 0.9.8 | 0.9.12 | 0.9.12 | 18 |
| astro | 5.16.4 | 7.3.2 | 7.4.8 | 12 |
| baseline-browser-mapping | 2.9.5 | 2.11.0 | Removed | 1 |
| browserslist | 4.28.1 | 4.28.7 | Removed | 2 |
| defu | 6.1.4 | 6.1.5 | 6.1.7 | 1 |
| devalue | 5.5.0 | 5.9.3 | 6.0.3 | 13 |
| diff | 5.2.0 | 5.2.2 | 9.0.0 | 1 |
| h3 | 1.15.4 | 1.15.9 | 1.15.11 | 5 |
| js-yaml | 4.1.1 | 4.3.2 | Removed | 4 |
| katex | 0.16.33 | 0.18.2 | 0.18.10 | 1 |
| nanoid | 3.3.11 | 3.3.18 | 3.3.20 | 3 |
| picomatch | 2.3.1, 4.0.3 | 2.3.2 / 4.0.4 | 2.3.2, 4.0.7 | 4 |
| postcss | 8.5.6 | 8.5.23 | 8.5.32 | 4 |
| postcss-selector-parser | 6.1.2 | 6.1.5 | 7.2.0 | 2 |
| rollup | 4.53.3 | 4.59.0 | Removed | 1 |
| sharp | 0.34.5 | 0.35.5 | 0.35.5 | 3 |
| smol-toml | 1.5.2 | 1.9.0 | 1.9.1 | 3 |
| source-map-js | 1.2.1 | 1.2.2 | 1.2.2 | 1 |
| svgo | 4.0.0 | 4.1.0 | 4.1.0 | 4 |
| tsconfck | 3.1.6 | No fix supplied (end-of-life) | Removed | 1 |
| vite | 6.4.1 | 6.4.4 | 8.3.7 | 9 |
| yaml | 2.8.2 | 2.8.3 | 2.9.1 | 1 |

Every remaining root/nested occurrence was checked. Picomatch's catalog for
CVE-2026-33671 and CVE-2026-33672 explicitly identifies fixes in each supported
release line (2.3.2, 3.0.2 and 4.0.4); the retained 2.3.2 instance is patched,
not an unresolved dependency that needs an incompatible forced major upgrade.
The EOL `tsconfck` finding has no supplied fix and is addressed by removing it
through the Astro migration.

### Required migration changes

- Upgraded Starlight to 0.42.10 alongside Astro 7.4.8 and Sharp 0.35.5.
- Moved Astro CSP configuration from `experimental.csp` to `security.csp`,
  preserving the existing script/style protections and inline-style hashing.
- Selected Astro 7's explicit unified Markdown processor, retaining MathJax
  and the accessibility-label plugin, and migrated autogenerated sidebars.
- Replaced the unsupported `@astrojs/tailwind` integration with Tailwind 4's
  Vite plugin. Existing theme values now live in CSS; the obsolete Tailwind 3
  configuration was removed. This is a compatibility migration, not a redesign.
- Updated the custom PageFrame to Starlight's native sidebar popover contract,
  preserving the corporate footer and excluding it from focus while the mobile
  menu is open. Updated mobile-menu CSS selectors to match the new component.
- Declared Node >=22.23.4 and npm >=9.6.5, matching Astro's engine requirements.
  Existing workflows already use Node 24 and need no changes.
- Scoped a KaTeX >=0.18.2 override to `micromark-extension-math`, whose declared
  dependency otherwise retains vulnerable 0.16.x. The HTML rendering API smoke
  check passes. The site continues to use its existing MathJax renderer.

## Validation

- `uv sync --locked --all-groups` and `uv lock --check`.
- Ruff formatting and lint checks; BasedPyright with warnings enabled.
- Existing pytest suite: **47 passed** (no permanent hard-coded package-version
  tests added).
- Wheel and source distribution build with `uv build --no-sources`.
- Compatibility smoke checks: Pillow PNG and PyArrow/Parquet round trips,
  PyJWT signing/verification, notebook HTML export, AnyIO execution, Azure
  credential construction (no cloud authentication/network request), and
  wind/solar calibrator imports.
- `pip-audit` against a fully pinned export of all dependency groups:
  **no known vulnerabilities found**. This is complementary evidence, not a
  substitute for the Wiz rescan.
- `npm ci`: reproducible installation without changing the lockfile.
- `npm test`: documentation build (31 pages) and internal-link checks.
- `npm audit`: **zero vulnerabilities**, including development dependencies.
- Final generated CSP verification: matching hashes for 306 nonempty inline
  scripts, 32 style blocks and 6,006 style attributes across all 31 pages.
- Browser verification of desktop/mobile rendering, math, theme switching,
  Pagefind search and cookie rejection. The mobile menu required the PageFrame
  compatibility fix described above. The subsequent browser recheck passes
  opening, button/Escape dismissal, navigation, focus exclusion, and
  mobile-to-desktop-to-mobile resizing/reopening without console/CSP errors.

The build emitted existing warnings about the uv-build version range and a
deprecated license classifier. Neither prevented the wheel/sdist build; this
security change does not alter packaging backend or licensing policy.

Astro also warns about Shiki inline styles and missing optional i18n/404
content. The existing final-output CSP integration supplies the inline-style
hashes; the explicit hash check above confirms coverage without disabling CSP.
The documentation build and internal-link checks complete successfully.

## Rollout and platform confirmation

1. Review and merge the remediation branch after required CI checks pass.
2. Install from the committed lockfiles (`uv sync --locked` with the required
   groups and `npm ci` for the documentation site). Do not reuse stale virtual
   environments or `node_modules` from older artifacts.
3. Rebuild and publish the documentation site through its existing workflow.
   Rebuild any other artifacts that vendor the old Python dependencies. This
   branch does not publish a Python release or perform production deployments.
4. Request or await a fresh Wiz repository scan of the merged revision. Confirm
   that all ten critical finding identifiers listed above are no longer open
   on that revision; investigate retained findings using their detected paths
   and artifact revisions rather than closing them manually.
5. If a separate cloud/deployed-artifact finding remains, verify that it is
   running the rebuilt artifact before treating the repository fix as a
   deployment fix. No cloud vulnerability status has been modified here.
