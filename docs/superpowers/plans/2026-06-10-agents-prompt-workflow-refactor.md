# Archived: prompt workflow refactor plan

This historical implementation plan has been superseded by the current project contract in `AGENTS.md`.

Do not use this file as an active development source. Current behavior is:

- Formal outline generation uses only `outline_debate`.
- `/api/workflows` must not expose legacy outline planning workflows.
- Prompt Catalog files are reusable prompt tasks, not independent runtime Agents.
- `chapter_planner` may support confirmed-chapter preparation only; it must not become a full-book outline entrypoint.
