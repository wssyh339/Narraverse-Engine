import { requestJson } from "./client";
import type { GenerationJob } from "../types/api";

export function getJob(jobId: string): Promise<{ job: GenerationJob }> {
  return requestJson<{ job: GenerationJob }>(`/jobs/${jobId}`);
}
