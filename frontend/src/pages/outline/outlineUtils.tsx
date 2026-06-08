import { Tag } from "antd";
import type { Character } from "../../types/api";
import type { InferenceStatus, InferenceStep } from "./types";

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
