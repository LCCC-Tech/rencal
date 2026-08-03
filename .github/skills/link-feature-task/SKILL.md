---
name: link-feature-task
description: Link Task issues to parent Feature issues and suggest Task breakdowns for broad Feature issues. Use after creating a Task that may belong under an existing Feature, or after drafting/creating a broad Feature that may need smaller Task issues.
---

# Link Feature Task Skill

Use this skill to keep broad Feature issues connected to smaller, atomic Task issues.

There are two supported flows:

1. **Task-to-Feature linking:** after creating a Task issue, decide whether it belongs as a sub-task under an existing Feature issue.
2. **Feature-to-Tasks breakdown:** after drafting or creating a broad Feature issue, suggest smaller Task issues that could be created underneath it.

## Definitions

- **Feature:** A larger user-facing enhancement or capability. GitHub issue Type `Feature`.
- **Task:** A bounded, atomic implementation, cleanup, docs, test, refactor, or follow-up item. GitHub issue Type `Task`.
- **Parent feature:** The Feature issue that owns or coordinates one or more Task issues.
- **Sub-task:** A Task issue linked under a parent Feature issue.

## Task-to-Feature Linking Flow

Use this flow after creating a Task issue.

1. Consider whether the Task appears to be part of a larger Feature.
   - Strong signals: the task implements part of a broader user-facing capability, mentions a feature area, follows from a feature discussion, or is one step in a multi-step change.
   - Weak signals: standalone cleanup, typo fix, isolated bug prevention, small docs correction, or maintenance with no broader product change.
2. If it likely belongs to a Feature, search existing open Feature issues.
3. Prefer targeted searches from the Task title, body, labels, affected files, and key domain terms.
4. If a likely parent Feature is found, summarize why it looks related and ask the user before linking.
5. If no likely parent is found, say so briefly and do not create a parent automatically unless the user asks.

Example searches:

```bash
gh issue list --state open --search "type:Feature <keywords>" --json number,title,url,body,labels
```

If `type:Feature` search is unsupported, fall back to labels or plain search:

```bash
gh issue list --state open --label enhancement --search "<keywords>" --json number,title,url,body,labels
```

## Linking a Task Under a Feature

Prefer GitHub's native sub-issue relationship when the installed `gh` version supports it:

```bash
gh issue edit <task-number-or-url> --set-parent <feature-number-or-url>
```

If that command is not supported, use the available `gh issue` relationship command shown by `gh issue edit --help`, if present.

If native sub-issues are not supported for this repository or CLI version, fall back to a comment-based link after user confirmation:

```bash
gh issue comment <task-number-or-url> --body "Parent feature: <feature-url>"
gh issue comment <feature-number-or-url> --body "Sub-task: <task-url>"
```

When using the comment fallback, explain that this is not a native GitHub sub-issue relationship.

Do not link issues without explicit user confirmation.

## Feature-to-Tasks Breakdown Flow

Use this flow when a Feature issue seems broad enough to benefit from smaller Task issues.

A Feature may be broad if it includes multiple independently deliverable parts, touches several files or packages, needs separate docs/tests/migration work, or has multiple acceptance criteria that could be implemented independently.

When a Feature seems broad:

1. Tell the user the feature may benefit from sub-tasks.
2. Suggest 2-6 candidate Task issues.
3. Keep each Task atomic and implementation-oriented.
4. Include for each suggested Task:
   - Draft title
   - Brief task summary
   - Likely files or areas using backticks, if known
   - Acceptance criteria
5. Ask which tasks, if any, the user wants to create.
6. If the user chooses tasks to create, create each as Type `Task` using the `create-gh-issue` skill.
7. After each Task is created, offer to link it under the parent Feature using the Task-to-Feature linking flow.

## Safety Rules

- Do not create Task issues without explicit user confirmation.
- Do not link Task issues to Feature issues without explicit user confirmation.
- Do not assume a parent Feature when search results are ambiguous; present likely candidates and ask.
- Do not create duplicate tasks. If similar open tasks exist, mention them and ask whether to reuse/link instead.
- Preserve issue URLs and numbers in summaries so the user can verify the relationship.
