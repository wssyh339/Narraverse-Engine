import { useMemo } from "react";
import type { Chapter, Volume } from "../../types/api";

interface BulkSelectionInput {
  volumes: Volume[];
  chapters: Chapter[];
  selectedChapterIds: string[];
  selectedVolumeIds: string[];
  chaptersByVolumeNo: Map<number, Chapter[]>;
}

export function useOutlineBulkSelection({
  volumes,
  chapters,
  selectedChapterIds,
  selectedVolumeIds,
  chaptersByVolumeNo,
}: BulkSelectionInput) {
  const selectedChapterIdsAcrossDirectory = useMemo(
    () => selectedChapterIds.filter((chapterId) => chapters.some((chapter) => chapter.id === chapterId)),
    [chapters, selectedChapterIds],
  );
  const deletableVolumeIds = useMemo(
    () => volumes.filter((volume) => !(chaptersByVolumeNo.get(volume.volume_no)?.length ?? 0)).map((volume) => volume.id),
    [chaptersByVolumeNo, volumes],
  );
  const selectedVolumeIdsAcrossDirectory = useMemo(
    () => selectedVolumeIds.filter((volumeId) => deletableVolumeIds.includes(volumeId)),
    [deletableVolumeIds, selectedVolumeIds],
  );
  return {
    selectedChapterIdsAcrossDirectory,
    deletableVolumeIds,
    selectedVolumeIdsAcrossDirectory,
    allDirectorySelected: chapters.length > 0 && selectedChapterIdsAcrossDirectory.length === chapters.length,
    partialDirectorySelected: selectedChapterIdsAcrossDirectory.length > 0 && selectedChapterIdsAcrossDirectory.length !== chapters.length,
    allVolumeOutlinesSelected: deletableVolumeIds.length > 0 && selectedVolumeIdsAcrossDirectory.length === deletableVolumeIds.length,
    partialVolumeOutlinesSelected: selectedVolumeIdsAcrossDirectory.length > 0 && selectedVolumeIdsAcrossDirectory.length !== deletableVolumeIds.length,
  };
}
