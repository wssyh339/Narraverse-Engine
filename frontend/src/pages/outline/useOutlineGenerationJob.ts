import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { studioApi } from "../../api/studio";
import type { GenerationJob } from "../../types/api";
import type { GenerationMode, InferenceStep } from "./types";
import { buildRunningInferenceSteps, resolveCurrentInferenceAgent, updateInferenceStepsFromJob } from "./outlineUtils";

interface MessageApi {
  info: (content: string) => void;
  success: (content: string) => void;
  error: (content: string) => void;
}

interface UseOutlineGenerationJobInput {
  generationMode: GenerationMode;
  useTopologyInference: boolean;
  planIsPending: boolean;
  messageApi: MessageApi;
  setInferenceSteps: (updater: (steps: InferenceStep[]) => InferenceStep[]) => void;
  setActiveAgentName: (agentName: string) => void;
  onComplete: (outlinePlan: Record<string, unknown> | null, job: GenerationJob) => void;
}

function sameInferenceSteps(left: InferenceStep[], right: InferenceStep[]) {
  return (
    left.length === right.length &&
    left.every((step, index) => {
      const other = right[index];
      return other && step.agent_name === other.agent_name && step.role === other.role && step.output_key === other.output_key && step.status === other.status;
    })
  );
}

export function useOutlineGenerationJob({
  generationMode,
  useTopologyInference,
  planIsPending,
  messageApi,
  setInferenceSteps,
  setActiveAgentName,
  onComplete,
}: UseOutlineGenerationJobInput) {
  const [runningOutlineJobId, setRunningOutlineJobId] = useState("");
  const handledTerminalJobIds = useRef(new Set<string>());
  const messageApiRef = useRef(messageApi);
  const onCompleteRef = useRef(onComplete);
  const runningJobQuery = useQuery({
    queryKey: ["outline-generation-job", runningOutlineJobId],
    queryFn: () => studioApi.getJob(runningOutlineJobId),
    enabled: Boolean(runningOutlineJobId),
    refetchInterval: (queryInfo) => {
      const job = (queryInfo.state.data as { job: GenerationJob } | undefined)?.job;
      return job && ["succeeded", "failed", "cancelled", "canceled"].includes(job.status) ? false : 1200;
    },
  });

  useEffect(() => {
    messageApiRef.current = messageApi;
    onCompleteRef.current = onComplete;
  }, [messageApi, onComplete]);

  useEffect(() => {
    const job = runningJobQuery.data?.job;
    if (!job || !runningOutlineJobId || job.id !== runningOutlineJobId) return;
    const completedSteps = Number(job.progress?.completed_steps ?? 0);
    const currentAgent = job.current_agent || job.progress?.current_step || "";
    const fallbackSteps = buildRunningInferenceSteps({ generationMode, useTopologyInference });
    setActiveAgentName(resolveCurrentInferenceAgent(fallbackSteps, currentAgent, completedSteps));
    setInferenceSteps((steps) => {
      const baseSteps = steps.length ? steps : fallbackSteps;
      const nextSteps = updateInferenceStepsFromJob(baseSteps, currentAgent, completedSteps, job.status === "failed");
      return sameInferenceSteps(steps, nextSteps) ? steps : nextSteps;
    });

    if (job.status === "succeeded") {
      if (handledTerminalJobIds.current.has(job.id)) return;
      handledTerminalJobIds.current.add(job.id);
      const result = job.result && typeof job.result === "object" ? (job.result as { outline_plan?: unknown }) : {};
      const outlinePlan = result.outline_plan && typeof result.outline_plan === "object" ? (result.outline_plan as Record<string, unknown>) : null;
      onCompleteRef.current(outlinePlan, job);
      setRunningOutlineJobId("");
      messageApiRef.current.success(generationMode === "outline" ? "大纲推演完成，请确认后写入" : "章纲推演完成，请确认后写入");
    }

    if (job.status === "failed") {
      if (handledTerminalJobIds.current.has(job.id)) return;
      handledTerminalJobIds.current.add(job.id);
      setRunningOutlineJobId("");
      messageApiRef.current.error(job.error?.message || "大纲推演失败");
    }
  }, [generationMode, runningJobQuery.data?.job, runningOutlineJobId, setActiveAgentName, setInferenceSteps, useTopologyInference]);

  return {
    isOutlineGenerating: planIsPending || Boolean(runningOutlineJobId),
    startOutlineJob: setRunningOutlineJobId,
    clearOutlineJob: () => setRunningOutlineJobId(""),
  };
}
