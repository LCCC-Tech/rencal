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
4. Labels have been inferred from the description and conversation.
5. Any labels to apply have been checked against existing repository labels.
6. The user has reviewed and confirmed the final issue draft, Type, and Labels.
7. The issue body does not include secrets, credentials, private keys, tokens, private URLs, or sensitive personal information.

## Workflow

1. Read the appropriate issue template.
2. Build a completed issue body using the template sections.
3. Infer the GitHub issue Type from the issue category:
   - Bug reports use Type `Bug`
   - Feature requests use Type `Feature`
   - Tasks use Type `Task`
4. Infer useful Labels from the description and conversation.
5. Run `gh label list` when possible and only apply labels that exist in the repository.
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

10. Return the created issue URL to the user.

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
- Do not apply labels that do not already exist in the repository.
- Do not include secrets, credentials, private keys, tokens, private URLs, or sensitive personal information.
- If the user includes sensitive content, warn them and redact it before creating the issue.
- If `gh` is not authenticated, tell the user to run `gh auth login`.
- If issue creation fails, report the error and preserve the drafted issue body so the user can retry.
