import type { Chapter, Project, StoryBible, Volume } from "../../types/api";
import type { GenerationMode, LongOutlineForm } from "./types";

interface InitialValuesInput {
  mode: GenerationMode;
  project?: Project;
  storyBible?: StoryBible;
  protagonistSummary: string;
  selectedVolume?: Volume;
}

interface PlanRequestInput {
  mode: GenerationMode;
  values: LongOutlineForm;
  projectId: string;
  selectedVolume?: Volume;
  selectedChapter?: Chapter;
  selectedChapters?: Chapter[];
  outlineContext?: Record<string, unknown> | null;
}

export function buildInitialOutlineValues({ mode, project, storyBible, protagonistSummary, selectedVolume }: InitialValuesInput): LongOutlineForm {
  const scalePlan = buildProjectScalePlan(project);
  return {
    title: project?.title ?? "",
    genre: project?.genre ?? "",
    target_reader: project?.target_reader ?? "",
    premise: project?.premise ?? "",
    world_setting: storyBible?.world_setting ?? project?.premise ?? "",
    protagonist: protagonistSummary,
    target_words: scalePlan.target_words,
    volume_count: scalePlan.volume_count,
    chapters_per_volume: scalePlan.chapters_per_volume,
    chapter_word_target: scalePlan.chapter_word_target,
    chapter_word_min: scalePlan.chapter_word_min,
    chapter_word_max: scalePlan.chapter_word_max,
    scale_plan: scalePlan,
    volume_title: selectedVolume?.title ?? "第一卷",
    outline_requirement:
      mode === "outline"
        ? "按长篇小说多 Agent 推演系统生成总纲和动态卷纲，不生成具体章纲。"
        : "结合已确认总纲、卷纲和正典上下文，批量生成选中章节的章纲，保证每章有目标、阻力、变化、回报和钩子。",
    custom_input: "",
    use_topology_inference: true,
  };
}

export function buildProjectScalePlan(project?: Project) {
  const chapterWordTarget = Math.max(500, Number(project?.chapter_word_target || 2500));
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

function buildContextSummary(values: LongOutlineForm, outlineContext?: Record<string, unknown> | null) {
  const scale_plan = buildScalePlanFromValues(values);
  const outlineContextText = !outlineContext ? "" : `已确认大纲上下文：${JSON.stringify(outlineContext).slice(0, 12000)}`;
  const contextSummary = [
    `基本信息：${values.title} / ${values.genre} / ${values.target_reader}`,
    `Scale Planner：${scale_plan.target_words}字 / ${scale_plan.volume_count}卷 / ${scale_plan.chapter_count}章 / 每章${scale_plan.chapter_word_min}-${scale_plan.chapter_word_max}字`,
    `世界观：${values.world_setting || values.premise}`,
    `主角：${values.protagonist}`,
    outlineContextText,
    values.custom_input ? `额外自定义输入：${values.custom_input}` : "",
  ]
    .filter(Boolean)
    .join("\n");
  return { contextSummary, targetWords: scale_plan.target_words, scale_plan };
}

export function buildBookOutlineGenerateRequest({ values, projectId }: PlanRequestInput) {
  const { contextSummary, targetWords, scale_plan } = buildContextSummary(values, null);
  return {
    outline_requirement: [values.outline_requirement, contextSummary].filter(Boolean).join("\n\n"),
    target_words: targetWords,
    volume_count: values.volume_count,
    chapters_per_volume: values.chapters_per_volume,
    chapter_word_target: values.chapter_word_target,
    chapter_word_min: values.chapter_word_min,
    chapter_word_max: values.chapter_word_max,
    scale_plan,
    use_topology_inference: values.use_topology_inference,
    idempotency_key: `outline-studio:book-outline:${projectId}:${Date.now()}`,
    async_mode: true,
  };
}

function compactChapterRanges(chapters: Chapter[]) {
  const sorted = [...chapters].sort((left, right) => left.chapter_no - right.chapter_no);
  const ranges: Array<{ volume_no: number; start_chapter_no: number; end_chapter_no: number }> = [];
  sorted.forEach((chapter) => {
    const last = ranges.at(-1);
    if (last && last.volume_no === chapter.volume_no && last.end_chapter_no + 1 === chapter.chapter_no) {
      last.end_chapter_no = chapter.chapter_no;
      return;
    }
    ranges.push({ volume_no: chapter.volume_no, start_chapter_no: chapter.chapter_no, end_chapter_no: chapter.chapter_no });
  });
  return ranges;
}

export function buildChapterOutlineBatchGenerateRequest({
  values,
  projectId,
  selectedVolume,
  selectedChapter,
  selectedChapters = [],
  outlineContext,
}: PlanRequestInput) {
  const { contextSummary, scale_plan } = buildContextSummary(values, outlineContext);
  const chaptersPerVolume = Math.max(1, Number(values.chapters_per_volume || 50));
  const chapterRanges = selectedChapters.length
    ? compactChapterRanges(selectedChapters)
    : selectedChapter
      ? [{ volume_no: selectedChapter.volume_no, start_chapter_no: selectedChapter.chapter_no, end_chapter_no: selectedChapter.chapter_no }]
      : [
          {
            volume_no: selectedVolume?.volume_no || 1,
            start_chapter_no: ((selectedVolume?.volume_no || 1) - 1) * chaptersPerVolume + 1,
            end_chapter_no: (selectedVolume?.volume_no || 1) * chaptersPerVolume,
          },
        ];
  return {
    chapter_ranges: chapterRanges,
    generation_requirement: [values.outline_requirement, contextSummary].filter(Boolean).join("\n\n"),
    target_words: scale_plan.target_words,
    volume_count: scale_plan.volume_count,
    chapters_per_volume: scale_plan.chapters_per_volume,
    chapter_word_target: scale_plan.chapter_word_target,
    chapter_word_min: scale_plan.chapter_word_min,
    chapter_word_max: scale_plan.chapter_word_max,
    scale_plan,
    overwrite_existing: true,
    use_topology_inference: values.use_topology_inference,
    idempotency_key: `outline-studio:chapter-outline-batch:${projectId}:${Date.now()}`,
    async_mode: true,
  };
}

function buildScalePlanFromValues(values: LongOutlineForm) {
  const volumeCount = Math.max(1, Number(values.volume_count || 1));
  const chaptersPerVolume = Math.max(1, Number(values.chapters_per_volume || 1));
  const chapterWordTarget = Math.max(500, Number(values.chapter_word_target || 2500));
  const chapterWordMin = Math.max(500, Number(values.chapter_word_min || chapterWordTarget));
  const chapterWordMax = Math.max(chapterWordMin, Number(values.chapter_word_max || chapterWordTarget));
  const chapterCount = Math.max(1, volumeCount * chaptersPerVolume);
  const targetWords = Math.max(0, chapterCount * chapterWordTarget);
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

export const bookOutlineGenerateRequest = buildBookOutlineGenerateRequest;
export const chapterOutlineBatchGenerateRequest = buildChapterOutlineBatchGenerateRequest;

export function mergeOutlinePlanResult(current: Record<string, unknown> | null, mode: GenerationMode, outlinePlan: Record<string, unknown> | null) {
  if (mode === "outline" || !current || !outlinePlan) return outlinePlan;
  return {
    ...current,
    [`${mode}_last_generated`]: outlinePlan,
    [`${mode}_generated_at`]: new Date().toISOString(),
  };
}

export function isOutlinePlanResultReady(outlinePlan: Record<string, unknown> | null) {
  if (!outlinePlan) return false;
  const bookOutline = outlinePlan.book_outline;
  if (bookOutline && typeof bookOutline === "object" && Object.keys(bookOutline).length > 0) return true;
  const chapterOutlines = outlinePlan.chapter_outlines;
  return Array.isArray(chapterOutlines) && chapterOutlines.length > 0;
}
