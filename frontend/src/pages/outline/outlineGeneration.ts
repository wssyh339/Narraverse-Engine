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
  outlineContext?: Record<string, unknown> | null;
}

export function buildInitialOutlineValues({ mode, project, storyBible, protagonistSummary, selectedVolume }: InitialValuesInput): LongOutlineForm {
  const chaptersPerVolume = 50;
  const chapterWordTarget = project?.chapter_word_target || 2000;
  const volumeCount = Math.max(1, Math.ceil((project?.planned_chapter_count || 500) / chaptersPerVolume));
  return {
    title: project?.title ?? "",
    genre: project?.genre ?? "",
    target_reader: project?.target_reader ?? "",
    premise: project?.premise ?? "",
    world_setting: storyBible?.world_setting ?? project?.premise ?? "",
    protagonist: protagonistSummary,
    target_words: volumeCount * chaptersPerVolume * chapterWordTarget,
    volume_count: volumeCount,
    chapters_per_volume: chaptersPerVolume,
    chapter_word_target: chapterWordTarget,
    volume_title: selectedVolume?.title ?? "第一卷",
    outline_requirement:
      mode === "outline"
        ? "按长篇小说多 Agent 推演系统生成总纲、卷纲、章节节拍、伏笔账本和逻辑审计。"
        : mode === "volume"
          ? "基于已生成总纲继续细化当前分卷，生成50章高密度卷纲，包含5个Phase、卷末钩子和全卷逻辑审计。"
          : "基于已生成总纲和卷纲继续细化本次章纲，保证每章有目标、阻力、变化、回报和钩子。",
    custom_input: "",
  };
}

export function buildOutlinePlanRequest({ mode, values, projectId, selectedVolume, selectedChapter, outlineContext }: PlanRequestInput) {
  const chapterCount = Math.max(1, Math.min(100, Number(values.chapters_per_volume || 50)));
  const startChapterNo =
    mode === "volume" && selectedVolume
      ? (selectedVolume.volume_no - 1) * Number(values.chapters_per_volume || 50) + 1
      : mode === "chapter" && selectedChapter
        ? selectedChapter.chapter_no
        : 1;
  const targetWords = Number(values.volume_count || 1) * Number(values.chapters_per_volume || 1) * Number(values.chapter_word_target || 1);
  const outlineContextText = mode === "outline" || !outlineContext ? "" : `已生成总纲上下文：${JSON.stringify(outlineContext).slice(0, 12000)}`;
  const contextSummary = [
    `基本信息：${values.title} / ${values.genre} / ${values.target_reader}`,
    `世界观：${values.world_setting || values.premise}`,
    `主角：${values.protagonist}`,
    outlineContextText,
    values.custom_input ? `额外自定义输入：${values.custom_input}` : "",
  ]
    .filter(Boolean)
    .join("\n");
  return {
    volume_title: values.volume_title || selectedVolume?.title || "第一卷",
    start_chapter_no: startChapterNo,
    chapter_count: chapterCount,
    outline_requirement: [values.outline_requirement, contextSummary].filter(Boolean).join("\n\n"),
    overwrite_existing: false,
    target_words: targetWords,
    volume_count: values.volume_count,
    chapters_per_volume: values.chapters_per_volume,
    chapter_word_target: values.chapter_word_target,
    idempotency_key: `outline-studio:${mode}:${projectId}:${Date.now()}`,
  };
}

export function mergeOutlinePlanResult(current: Record<string, unknown> | null, mode: GenerationMode, outlinePlan: Record<string, unknown> | null) {
  if (mode === "outline" || !current || !outlinePlan) return outlinePlan;
  return {
    ...current,
    [`${mode}_last_generated`]: outlinePlan,
    [`${mode}_generated_at`]: new Date().toISOString(),
  };
}
