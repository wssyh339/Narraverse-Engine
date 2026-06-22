import type { Chapter, Project } from "../../types/api";

const DEFAULT_CHAPTER_WORD_TARGET = 8000;

export function buildProjectScalePlan(project?: Project) {
  const chapterWordTarget = Math.max(500, Number(project?.chapter_word_target || DEFAULT_CHAPTER_WORD_TARGET));
  const chapterWordMin = Math.max(500, Number(project?.chapter_word_min || Math.max(500, chapterWordTarget - 300)));
  const chapterWordMax = Math.max(chapterWordMin, Number(project?.chapter_word_max || chapterWordTarget + 300));
  const chapterCount = Math.max(1, Number(project?.planned_chapter_count || 400));
  const volumeCount = Math.max(1, Number(project?.planned_volume_count || Math.ceil(chapterCount / 40)));
  const chaptersPerVolume = Math.max(1, Number(project?.chapters_per_volume || Math.ceil(chapterCount / volumeCount)));
  const targetWords = Math.max(0, Number(project?.target_words || chapterCount * chapterWordTarget));
  return {
    target_words: targetWords,
    volume_count: volumeCount,
    chapter_count: chapterCount,
    chapters_per_volume: chaptersPerVolume,
    chapter_word_target: chapterWordTarget,
    chapter_word_min: chapterWordMin,
    chapter_word_max: chapterWordMax,
  };
}

export function nextMissingChapterNo(volumeNo: number, chaptersPerVolume: number, chapters: Chapter[]) {
  const safeVolumeNo = Math.max(1, Number(volumeNo || 1));
  const safeChaptersPerVolume = Math.max(1, Number(chaptersPerVolume || 1));
  const startChapterNo = (safeVolumeNo - 1) * safeChaptersPerVolume + 1;
  const endChapterNo = startChapterNo + safeChaptersPerVolume - 1;
  const existing = new Set(
    chapters
      .filter((chapter) => chapter.volume_no === safeVolumeNo)
      .map((chapter) => Number(chapter.chapter_no))
      .filter((chapterNo) => chapterNo >= startChapterNo && chapterNo <= endChapterNo),
  );
  for (let chapterNo = startChapterNo; chapterNo <= endChapterNo; chapterNo += 1) {
    if (!existing.has(chapterNo)) return chapterNo;
  }
  return endChapterNo;
}
