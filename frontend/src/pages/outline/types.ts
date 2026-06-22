import type { Chapter, Volume } from "../../types/api";

export type OutlineView = "outline" | "volume" | "chapter" | "chapterOutline";

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
