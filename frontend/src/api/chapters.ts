import { requestJson } from "./client";
import type { GenerationJob } from "../types/api";

export interface PlanChaptersInput {
  volume_title: string;
  start_chapter_no: number;
  chapter_count: number;
  outline_requirement: string;
  overwrite_existing: boolean;
  idempotency_key: string;
  model: string | null;
}

export function planChapters(
  projectId: string,
  input: PlanChaptersInput,
): Promise<{ job: GenerationJob }> {
  return requestJson<{ job: GenerationJob }>(`/projects/${projectId}/chapters/plan`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}
