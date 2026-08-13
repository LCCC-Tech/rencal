# Issue tracker: Local Markdown

Issues and specs for this repo live as Markdown files in `.scratch/`. The directory is gitignored so local issue drafts stay out of version control until they are manually promoted to GitHub Issues.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`
- Triage state is recorded as a `Status:` line near the top of each issue file
- Comments and conversation history append to the bottom under a `## Comments` heading

## Publishing workflow

When a skill says to publish to the issue tracker, create the Markdown file under `.scratch/<feature-slug>/`. When an issue is ready, manually copy or promote it to the project's GitHub Issues.
