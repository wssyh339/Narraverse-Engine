import type { Chapter, Volume } from "../../types/api";

export interface LongOutlineForm {
  title: string;
  genre: string;
  target_reader: string;
  premise: string;
  world_setting: string;
  protagonist: string;
  target_words: number;
  volume_count: number;
  chapters_per_volume: number;
  chapter_word_target: number;
  chapter_word_min: number;
  chapter_word_max: number;
  scale_plan?: Record<string, number>;
  volume_title: string;
  outline_requirement: string;
  custom_input: string;
  use_topology_inference: boolean;
}

export type OutlineView = "outline" | "volume" | "chapter" | "chapterOutline";
export type GenerationMode = "outline" | "chapter";
export type InferenceStatus = "pending" | "running" | "succeeded" | "failed";

export interface InferenceStep {
  agent_name: string;
  role: string;
  output_key: string;
  status: InferenceStatus;
}

export interface OutlineTopologyNode {
  id: string;
  label: string;
  type: "agent" | "artifact" | "gate" | "decision" | string;
  status: InferenceStatus | "blocked" | "needs_user_review" | string;
  summary: string;
  agent_name?: string;
  payload?: Record<string, unknown>;
}

export interface OutlineTopologyEdge {
  id: string;
  source: string;
  target: string;
  type: "handoff" | "depends_on" | "emits" | "reviews" | "blocks" | "revises" | "approves" | string;
  label: string;
  reason?: string;
  weight?: number;
}

export interface OutlineTopology {
  mode: "topology" | "linear" | string;
  generation_kind: string;
  nodes: OutlineTopologyNode[];
  edges: OutlineTopologyEdge[];
  events: Record<string, unknown>[];
  artifacts: Record<string, unknown>[];
  metrics: Record<string, unknown>;
}

export interface OutlineDirectoryHandlers {
  setSelectedView: (view: OutlineView) => void;
  setSelectedVolumeId: (volumeId: string) => void;
  setSelectedChapterId: (chapterId: string) => void;
  setDetailOpen: (open: boolean) => void;
  setBatchManagementEnabled: (enabled: boolean) => void;
  openCreateVolume: () => void;
  openCreateChapter: () => void;
  confirmClearOutline: () => void;
  confirmDeleteVolume: (volume: Volume) => void;
  confirmBatchDeleteVolumes: () => void;
  toggleDirectorySelection: (checked: boolean) => void;
  toggleVolumeSelection: (volumeNo: number, checked: boolean) => void;
  toggleVolumeOutlineSelection: (volumeId: string, checked: boolean) => void;
  toggleAllVolumeOutlines: (checked: boolean) => void;
  toggleChapterSelection: (chapterId: string, checked: boolean) => void;
  confirmTrashChapter: (chapter: Chapter) => void;
  confirmBatchTrashChapters: () => void;
}
