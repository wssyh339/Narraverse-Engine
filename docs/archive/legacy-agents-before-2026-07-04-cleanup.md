# Archived Legacy Agent Spec

This file intentionally no longer preserves the pre-2026-07-04 long-form agent specification.

The old text mixed Studio 1.0 target language, legacy outline workflow descriptions, Swarm-era planning notes, and the fixed "11 agents" system summary. Keeping the full text in the repository created ambiguity about the current source of truth.

Current source of truth:

- `AGENTS.md` is the only active project constraint.
- Formal outline generation uses only `outline_debate`.
- Current outline debate has exactly 6 runtime seats: `StoryDirectorAgent`, `MarketPositionAgent`, `StructureDoctorAgent`, `CharacterGeneratorAgent`, `SettingGeneratorAgent`, and `ContinuityAuditorAgent`.
- The 11 base AgentSpecs remain prompt/task bindings for creation, chapter writing, maintenance, and configuration surfaces; they are not outline-debate seats and must not be used as a fixed system-wide agent count.
- `chapter_planner` may support confirmed-chapter preparation, chapter cards, state changes, and specialized structure tasks only. It must not become a full-book, volume, or chapter-outline entrypoint.
- Prompt Catalog files are reusable prompt templates, not independent runtime agents.

Do not restore legacy outline source code, legacy local CLI outline paths, legacy graph components, or old planning documents from prior commits.
