---
name: create-gh-issue
description: Create GitHub issues using the gh CLI from this repository's issue templates. Use when the user says phrases like "create this issue", "open the issue", "submit this issue", "file this issue", "create it", "file this bug", or "file this feature request".
---

# Create GitHub Issue Skill

Use this skill when the user is ready to create a GitHub issue from a drafted bug report or feature request.

## Preconditions

Before running `gh issue create`, ensure:

1. The issue type is known:
   - Bug report
   - Feature request
2. The issue title is concise and descriptive.
3. The issue body matches the appropriate repository template:
   - `.github/ISSUE_TEMPLATE/bug_report.md`
   - `.github/ISSUE_TEMPLATE/feature_request.md`
4. The user has reviewed and confirmed the final issue draft.
5. The issue body does not include secrets, credentials, private keys, tokens, private URLs, or sensitive personal information.

## Workflow

1. Read the appropriate issue template.
2. Build a completed issue body using the template sections.
3. Preview the issue for the user:
   - Issue type
   - Title
   - Body
   - Labels, if any
4. Ask for final confirmation unless the user has already clearly confirmed both the draft and creation.
5. Write the issue body to a temporary markdown file.
6. Create the issue with GitHub CLI:

   ```bash
   gh issue create --title "<title>" --body-file "<temp-body-file>"
   ```

   If labels were explicitly confirmed:

   ```bash
   gh issue create --title "<title>" --body-file "<temp-body-file>" --label "label1,label2"
   ```

7. Return the created issue URL to the user.

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

## Safety Rules

- Do not create an issue without explicit user confirmation.
- Do not invent labels, assignees, milestones, or projects.
- Do not include secrets, credentials, private keys, tokens, private URLs, or sensitive personal information.
- If the user includes sensitive content, warn them and redact it before creating the issue.
- If `gh` is not authenticated, tell the user to run `gh auth login`.
- If issue creation fails, report the error and preserve the drafted issue body so the user can retry.
