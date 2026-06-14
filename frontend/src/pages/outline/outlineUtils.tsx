import { Tag } from "antd";
import type { Character } from "../../types/api";
import type { GenerationMode, InferenceStatus, InferenceStep } from "./types";

const SWARM_AGENT_ROLES: Record<string, string> = {
  StoryDirectorAgent: "故事总导演 Agent",
  WhyInterrogatorAgent: "为什么审问 Agent",
  WorldSettingAgent: "世界构建 Agent",
  CharacterArcAgent: "人物弧光 Agent",
  ConflictAgent: "冲突矩阵 Agent",
  PlotArchitectAgent: "长篇结构 Agent",
  BeatControllerAgent: "章节节拍 Agent",
  ForeshadowingAgent: "伏笔设计 Agent",
  EntityExtractorAgent: "实体抽取 Agent",
  ContinuityAgent: "连续性审查 Agent",
};

const LEGACY_OUTLINE_AGENT_ROLES: Record<string, string> = {
  editor_orchestrator: "总编统筹 Agent",
  one_sentence_expansion: "故事种子扩写 Agent",
  genre_market_position: "类型卖点定位 Agent",
  world_bible: "世界圣经 Agent",
  protagonist_arc: "主角成长线 Agent",
  character_tree: "人物树 Agent",
  faction_conflict: "势力冲突 Agent",
  power_system: "力量体系 Agent",
  full_structure: "全书结构 Agent",
  volume_outline: "卷纲设计 Agent",
  beat_control: "章节节拍 Agent",
  foreshadowing_manager: "伏笔账本 Agent",
  logic_audit: "逻辑审计 Agent",
};

const OUTLINE_SWARM_PREFIX = "outline_swarm/";
const BOOK_OUTLINE_AGENT_ROLES = Object.fromEntries(Object.entries(LEGACY_OUTLINE_AGENT_ROLES).filter(([agentName]) => agentName !== "beat_control"));
const BOOK_OUTLINE_SWARM_AGENT_ROLES = Object.fromEntries(Object.entries(SWARM_AGENT_ROLES).filter(([agentName]) => agentName !== "BeatControllerAgent"));
const CHAPTER_OUTLINE_AGENT_ROLES: Record<string, string> = {
  beat_control: LEGACY_OUTLINE_AGENT_ROLES.beat_control,
  foreshadowing_manager: LEGACY_OUTLINE_AGENT_ROLES.foreshadowing_manager,
  logic_audit: LEGACY_OUTLINE_AGENT_ROLES.logic_audit,
};

interface RunningInferenceOptions {
  generationMode?: GenerationMode;
  useTopologyInference?: boolean;
}

export function sameStringArray(left: string[], right: string[]) {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

export function buildSwarmInferenceSteps(outline_swarm: unknown): InferenceStep[] {
  if (!outline_swarm || typeof outline_swarm !== "object") return [];
  const agent_trace = (outline_swarm as { agent_trace?: unknown }).agent_trace;
  if (!Array.isArray(agent_trace)) return [];
  const seen = new Set<string>();
  return agent_trace
    .map((event) => (event && typeof event === "object" ? String((event as { agent_name?: unknown }).agent_name || "") : ""))
    .filter((agentName) => {
      if (!agentName || seen.has(agentName)) return false;
      seen.add(agentName);
      return true;
    })
    .map((agentName) => ({
      agent_name: agentName,
      role: SWARM_AGENT_ROLES[agentName] ?? agentName,
      output_key: "outline_swarm agent_trace",
      status: "succeeded" as const,
    }));
}

export function buildRunningInferenceSteps(options: RunningInferenceOptions = {}): InferenceStep[] {
  const generationMode = options.generationMode ?? "outline";
  const useTopologyInference = options.useTopologyInference ?? true;
  const legacySteps = Object.entries(generationMode === "chapter" ? CHAPTER_OUTLINE_AGENT_ROLES : BOOK_OUTLINE_AGENT_ROLES);
  const swarmSteps =
    generationMode === "outline" && useTopologyInference
      ? Object.entries(BOOK_OUTLINE_SWARM_AGENT_ROLES).map(([agentName, role]) => [`${OUTLINE_SWARM_PREFIX}${agentName}`, role] as const)
      : [];
  return [...legacySteps, ...swarmSteps].map(([agentName, role], index) => ({
    agent_name: agentName,
    role,
    output_key: index === 0 ? "正在读取设定并启动总纲推演" : "等待上游 Agent 交接",
    status: index === 0 ? "running" : "pending",
  }));
}

export function resolveCurrentInferenceAgent(steps: InferenceStep[], currentAgent: string | undefined, completedSteps = 0) {
  if (currentAgent && steps.some((step) => step.agent_name === currentAgent)) return currentAgent;
  if (currentAgent) {
    const swarmAgent = steps.find((step) => step.agent_name === `${OUTLINE_SWARM_PREFIX}${currentAgent}`);
    if (swarmAgent) return swarmAgent.agent_name;
  }
  const runningStep = steps.find((step) => step.status === "running");
  if (runningStep && completedSteps <= 0) return runningStep.agent_name;
  return steps[Math.min(Math.max(completedSteps, 0), Math.max(steps.length - 1, 0))]?.agent_name ?? "";
}

export function updateInferenceStepsFromJob(steps: InferenceStep[], currentAgent: string | undefined, completedSteps = 0, failed = false): InferenceStep[] {
  const resolvedAgent = resolveCurrentInferenceAgent(steps, currentAgent, completedSteps);
  const currentIndex = resolvedAgent ? steps.findIndex((step) => step.agent_name === resolvedAgent) : -1;
  return steps.map((step, index) => {
    if (failed && (index === currentIndex || (currentIndex < 0 && step.status === "running"))) {
      return { ...step, status: "failed", output_key: "任务执行失败" };
    }
    if (index < completedSteps) {
      return { ...step, status: "succeeded", output_key: step.output_key === "等待上游 Agent 交接" ? "已完成" : step.output_key };
    }
    if (index === currentIndex) {
      return { ...step, status: "running", output_key: "当前正在推演" };
    }
    return { ...step, status: step.status === "succeeded" ? "succeeded" : "pending" };
  });
}

export function getProtagonist(characters: Character[]) {
  return characters.find((item) => item.role_type === "protagonist") ?? characters[0];
}

export function summarizeProtagonist(character?: Character) {
  if (!character) return "未设置主角，可在确认前补充身份、欲望、能力或伤口。";
  const goals = character.goals?.length ? `目标：${character.goals.join("、")}` : "";
  return [character.name, character.summary, goals, character.character_arc].filter(Boolean).join("；");
}

export function readableJson(value: unknown) {
  if (value === null || value === undefined || value === "") return "暂无";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

export function statusTag(status: InferenceStatus) {
  if (status === "succeeded") return <Tag color="green">完成</Tag>;
  if (status === "running") return <Tag color="processing">推演中</Tag>;
  if (status === "failed") return <Tag color="red">失败</Tag>;
  return <Tag>等待</Tag>;
}
