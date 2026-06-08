import { requestJson } from "./client";
import type { ProjectSnapshot, StoryBible } from "../types/api";

export interface CreateProjectInput {
  title: string;
  genre: string;
  target_reader: string;
  premise: string;
  style_guide: string;
  language: string;
  planned_chapter_count: number;
  chapter_word_target: number;
}

export interface UpdateStoryBibleInput {
  world_setting: string;
  main_conflict: string;
  themes: string[];
  style_guide: string;
  narrative_pov: StoryBible["narrative_pov"];
  forbidden_elements: string[];
  continuity_rules: string[];
}

export function createProject(input: CreateProjectInput): Promise<ProjectSnapshot> {
  return requestJson<ProjectSnapshot>("/projects", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateStoryBible(
  projectId: string,
  input: UpdateStoryBibleInput,
): Promise<{ story_bible: StoryBible }> {
  return requestJson<{ story_bible: StoryBible }>(`/projects/${projectId}/story-bible`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}
