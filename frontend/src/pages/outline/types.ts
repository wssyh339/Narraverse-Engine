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
  volume_title: string;
  outline_requirement: string;
  custom_input: string;
}

export type OutlineView = "outline" | "volume" | "chapter" | "chapterOutline";
export type GenerationMode = "outline" | "volume" | "chapter";
export type InferenceStatus = "pending" | "running" | "succeeded" | "failed";

export interface InferenceStep {
  agent_name: string;
  role: string;
  output_key: string;
  status: InferenceStatus;
}

export interface OutlineDirectoryHandlers {
  setSelectedView: (view: OutlineView) => void;
  setSelectedVolumeId: (volumeId: string) => void;
  setSelectedChapterId: (chapterId: string) => void;
  setBatchManagementEnabled: (enabled: boolean) => void;
  openCreateVolume: () => void;
  openCreateChapter: () => void;
  openGenerationPreview: (mode: GenerationMode) => void;
  confirmClearOutline: () => void;
  confirmDeleteVolume: (volume: Volume) => void;
  toggleDirectorySelection: (checked: boolean) => void;
  toggleVolumeSelection: (volumeNo: number, checked: boolean) => void;
  toggleChapterSelection: (chapterId: string, checked: boolean) => void;
  confirmTrashChapter: (chapter: Chapter) => void;
  confirmBatchTrashChapters: () => void;
}
