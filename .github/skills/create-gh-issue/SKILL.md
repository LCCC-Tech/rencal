---
name: create-gh-issue
description: Create GitHub issues using the gh CLI from this repository's issue templates. Use when the user says phrases like "create this issue", "open the issue", "submit this issue", "file this issue", "create it", "file this bug", "file this feature request", or "create this task".
---

# Create GitHub Issue Skill

Use this skill when the user is ready to create a GitHub issue from a drafted bug report, feature request, or task.

## Preconditions

Before running `gh issue create`, ensure:

1. The issue type is known:
   - Bug
   - Feature
   - Task
2. The issue title is concise and descriptive.
3. The issue body matches the appropriate repository template:
   - `.github/ISSUE_TEMPLATE/bug_report.md`
   - `.github/ISSUE_TEMPLATE/feature_request.md`
   - `.github/ISSUE_TEMPLATE/task.md`
4. Labels have been inferred from the description and conversation using the known repository labels below.
5. Labels have not been pre-checked with GitHub unless a previous creation attempt failed because of labels.
6. The user has reviewed and confirmed the final issue draft, Type, and Labels.
7. The issue body does not include secrets, credentials, private keys, tokens, private URLs, or sensitive personal information.

## Workflow

1. Read the appropriate issue template.
2. Build a completed issue body using the template sections.
3. Infer the GitHub issue Type from the issue category:
   - Bug reports use Type `Bug`
   - Feature requests use Type `Feature`
   - Tasks use Type `Task`
4. Infer useful Labels from the description and conversation using the known repository labels below.
5. Do not run `gh label list` as a normal preflight step. The known labels in this skill are the default source of truth.
6. Preview the issue for the user:
   - Issue type
   - Title
   - Body
   - Labels, if any
7. Ask for final confirmation unless the user has already clearly confirmed the draft, Type, Labels, and creation.
8. Write the issue body to a temporary markdown file.
9. Create the issue with GitHub CLI.

   Prefer `gh issue create` when the installed version supports `--type`:

   ```bash
   gh issue create --title "<title>" --body-file "<temp-body-file>" --type "<Bug|Feature|Task>"
   ```

   If labels were explicitly confirmed:

   ```bash
   gh issue create --title "<title>" --body-file "<temp-body-file>" --type "<Bug|Feature|Task>" --label "label1,label2"
   ```

   If the installed `gh` version does not support `gh issue create --type`, use `gh api` so the Type can still be set through the GitHub API:

   ```bash
   gh api repos/{owner}/{repo}/issues \
     -F title="<title>" \
     -F body="@<temp-body-file>" \
     -f type="<Bug|Feature|Task>" \
     --jq .html_url
   ```

   If labels were explicitly confirmed, include one `-F labels[]="<label>"` argument per label:

   ```bash
   gh api repos/{owner}/{repo}/issues \
     -F title="<title>" \
     -F body="@<temp-body-file>" \
     -f type="<Bug|Feature|Task>" \
     -F labels[]="label1" \
     -F labels[]="label2" \
     --jq .html_url
   ```

   If neither path can set the Type for this repository, create the issue without Type only after telling the user and getting confirmation.

   If issue creation fails because one or more labels are missing or invalid, then run `gh label list`, compare the requested labels against the currently available labels, remove or replace invalid labels, preview the corrected labels, and retry after user confirmation.

10. If the created issue Type is `Task`, use the `link-feature-task` skill to consider whether the new Task belongs under an existing Feature issue.
    - Do not search for a parent Feature if the Task is clearly standalone.
    - If a likely parent Feature is found, ask the user before linking.
    - Do not link automatically.
11. Return the created issue URL to the user.

## Known Repository Labels

Use these known repository labels when inferring labels. Do not call `gh label list` unless creating the issue fails because of labels.

- `breaking` — A breaking change to function signature, arguments or incompatible methodology
- `documentation` — Improvements or additions to documentation
- `duplicate` — This issue or pull request already exists
- `enhancement` — New feature or request
- `good first issue` — Good for newcomers
- `help wanted` — Extra attention is needed
- `invalid` — This doesn't seem right
- `needs info` — Further information is requested
- `wontfix` — This will not be worked on
- `generate docs` — Triggers AI to generate missing docs on PR requests
- `ci` — Updates to CI/CD pipelines
- `performance` — Speed or memory related performance improvements
- `tests` — Add missing or improved tests to existing or new feature
- `tooling` — Updates to developer tooling
- `environment` — Updating dependencies or packaging changes

Recommended defaults:

- Bug reports: use the most specific applicable label, such as `breaking`, `performance`, `environment`, `ci`, or `needs info`; if none fit, omit labels rather than inventing `bug`.
- Feature requests: usually `enhancement`.
- Documentation changes: usually `documentation`; use `generate docs` only when the issue should trigger AI-generated missing docs on PR requests.
- Tasks: usually choose the closest work-area label, such as `documentation`, `tests`, `tooling`, `ci`, `environment`, `performance`, or `enhancement`; omit labels if none clearly fit.
- Dependency, packaging, or setup work: usually `environment`.
- Developer tooling work: usually `tooling`.
- Test work: usually `tests`.

## Bug Report Body Format

```md
**Describe the bug**
<description>

**To Reproduce**
Steps to reproduce the behavior:
1. <step one>
2. <step two>
3. <step three>

**Expected behavior**
<expected behavior>

**Screenshots**
<screenshots, logs, tracebacks, or N/A>

**Desktop (please complete the following information):**
 - OS: <os or N/A>
 - Browser (for documentation site issues): <browser or N/A>
 - Related package versions: <versions or N/A>

**Additional context**
<additional context or N/A>
```

## Feature Request Body Format

```md
**Please provide a high level description of the feature.**
<description>

**Describe the proposed solution and/or implementation in more detail**
<proposed solution>

**Describe alternatives you've considered**
<alternatives or "No alternatives considered yet.">

**Additional context (Optional)**
<additional context or N/A>
```

## Task Body Format

```md
**Task summary**
<clear and concise description of the small change>

**Why this task is needed**
<motivation, maintenance need, follow-up, cleanup, or bug prevention context>

**Proposed implementation**
<expected approach, including files, commands, APIs, docs, or tests using backticks where appropriate>

**Acceptance criteria**
- [ ] <criterion one>
- [ ] <criterion two>
- [ ] <criterion three>

**Additional context (Optional)**
<additional context, links, examples, related issues, or N/A>
```

## Safety Rules

- Do not create an issue without explicit user confirmation.
- Do not invent labels, assignees, milestones, or projects.
- Do not create new labels unless the user explicitly asks.
- Do not apply labels outside the known repository labels unless the user explicitly asks or `gh label list` confirms they exist after a label-related failure.
- Do not include secrets, credentials, private keys, tokens, private URLs, or sensitive personal information.
- If the user includes sensitive content, warn them and redact it before creating the issue.
- If `gh` is not authenticated, tell the user to run `gh auth login`.
- If issue creation fails, report the error and preserve the drafted issue body so the user can retry.
