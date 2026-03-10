---
description: Updates and creates documentation
name: docs
---

# docs instructions

## Style and Templates
Create Reference (API) Documentation from docstrings (Google Python Style) with reference output as if it was done by a deterministic docs generator like Sphinx. Generate .mdx files.

## Steps
1. When creating new docs, look at the recent commits which look like a new feature or significant change:
    - Read the changed files to understand what was added
    - Check if the feature is already documented in docs/web/src/content/docs/*
2. If you find undocumented features:
    - Update the relevant documentation files in packages/web/src/content/docs/*
    - Follow the existing documentation style and structure
    - Make sure to document the feature clearly with examples where appropriate
3. If all new features are already documented, report that no updates are needed
4. If you are creating a new documentation file be sure to update packages/web/astro.config.mjs too.

Focus on user-facing API changes. Skip internal refactors, bug fixes, and test updates unless they affect user-facing behavior.
Don't feel the need to document every little thing. It is perfectly okay to make 0 changes at all.
Try to keep documentation only for large features or changes that already have a good spot to be documented.

