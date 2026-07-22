# Archived: prompt lifecycle workflow plan

This historical implementation plan has been superseded by the current project contract in `AGENTS.md`.

Do not use this file as an active development source. Current behavior is:

- Formal outline generation uses the round-based `outline_debate` service and `OutlineDebatePanel`.
- Prompt lifecycle views are documentation and configuration surfaces, not alternate outline runtimes.
- The active chapter lifecycle is `next_chapter_state_change -> chapter_prep -> chapter_card -> scene_outline -> draft_generation -> draft_self_check -> draft_rewrite -> narrative_ledger_update`.
- Legacy outline workflow IDs must remain absent from current APIs and frontend surfaces.
