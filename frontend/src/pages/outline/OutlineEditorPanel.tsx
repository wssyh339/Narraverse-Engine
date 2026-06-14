import { Button, Empty, Space, Tooltip, Typography } from "antd";
import { ListChecks, RefreshCw } from "lucide-react";
import type { UseMutationResult } from "@tanstack/react-query";
import type { Chapter, Project, StoryBible, Volume } from "../../types/api";
import type { GenerationMode, OutlineView } from "./types";

interface OutlineEditorPanelProps {
  selectedView: OutlineView;
  selectedVolume?: Volume;
  selectedChapter?: Chapter;
  lastOutlinePlan: Record<string, unknown> | null;
  project?: Project;
  storyBible?: StoryBible;
  isPlanning: boolean;
  saveVolume: UseMutationResult<unknown, Error, { title: string; outline: string }, unknown>;
  saveChapter: UseMutationResult<unknown, Error, Partial<Chapter>, unknown>;
  openGenerationPreview: (mode: GenerationMode) => void;
  children?: React.ReactNode;
}

const outlineFieldLabels: Record<string, string> = {
  title: "作品名",
  genre: "类型",
  target_reader: "目标读者",
  premise: "一句话故事",
  world_setting: "世界观",
  main_conflict: "核心冲突",
  themes: "主题",
  style_guide: "风格",
  parameters: "生成参数",
  target_words: "目标总字数",
  volume_count: "卷数",
  chapters_per_volume: "每卷章节数",
  chapter_word_target: "每章字数",
  "世界圣经": "世界圣经",
  "全书10卷总纲": "全书十卷总纲",
  "10卷单元总表": "十卷单元总表",
  "最终修订版纲要": "最终修订版纲要",
  "伏笔账本": "伏笔账本",
  "长篇生成策略": "长篇生成策略",
  volume_title: "分卷名称",
  chapter_title: "章节标题",
  chapter_no: "章节序号",
  volume_no: "所属分卷",
  outline: "大纲正文",
  core_event: "核心事件",
  conflict: "核心冲突",
  turn_point: "转折点",
  cliffhanger: "结尾钩子",
  plot_purpose: "剧情功能",
  pov_character: "视角人物",
  emotional_beats: "情绪节拍",
};

function parseMaybeJson(value: unknown): unknown {
  if (typeof value !== "string") return value;
  const trimmed = value.trim();
  if (!trimmed || (!trimmed.startsWith("{") && !trimmed.startsWith("["))) return value;
  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
}

function isScalar(value: unknown) {
  return ["string", "number", "boolean"].includes(typeof value);
}

function labelFor(key: string) {
  return outlineFieldLabels[key] ?? key.replace(/_/g, " ");
}

function naturalLines(value: unknown, label = "", depth = 0): string[] {
  const normalized = parseMaybeJson(value);
  const indent = depth > 0 ? "  ".repeat(depth - 1) : "";
  const heading = label ? labelFor(label) : "";
  if (normalized === null || normalized === undefined || normalized === "") {
    return heading ? [`${indent}${heading}：暂无`] : [];
  }
  if (isScalar(normalized)) {
    return [`${indent}${heading ? `${heading}：` : ""}${String(normalized)}`];
  }
  if (Array.isArray(normalized)) {
    const lines = heading ? [`${indent}${heading}：`] : [];
    normalized.forEach((item, index) => {
      if (isScalar(item)) {
        lines.push(`${indent}- ${String(item)}`);
        return;
      }
      lines.push(`${indent}- 第 ${index + 1} 项`);
      lines.push(...naturalLines(item, "", depth + 1));
    });
    return lines;
  }
  if (typeof normalized === "object") {
    const entries = Object.entries(normalized as Record<string, unknown>).filter(([key, item]) => {
      if (key.startsWith("outline_swarm") || key.includes("Agent推演链") || key === "agent_outputs" || key === "structured_prompt") return false;
      return item !== null && item !== undefined && item !== "";
    });
    const lines = heading ? [`${indent}${heading}：`] : [];
    entries.forEach(([key, item]) => {
      lines.push(...naturalLines(item, key, depth + 1));
    });
    return lines;
  }
  return heading ? [`${indent}${heading}：${String(normalized)}`] : [String(normalized)];
}

export function formatOutlineDocument(lastOutlinePlan: Record<string, unknown> | null, storyBible?: StoryBible, project?: Project) {
  if (lastOutlinePlan) {
    const sections = ["最终修订版纲要", "世界圣经", "全书10卷总纲", "10卷单元总表", "伏笔账本", "长篇生成策略"]
      .filter((key) => key in lastOutlinePlan)
      .flatMap((key) => naturalLines(lastOutlinePlan[key], key, 0));
    return sections.length ? sections.join("\n") : naturalLines(lastOutlinePlan).join("\n");
  }
  if (storyBible) {
    return naturalLines({
      world_setting: storyBible.world_setting,
      main_conflict: storyBible.main_conflict,
      themes: storyBible.themes,
      style_guide: storyBible.style_guide,
    }).join("\n");
  }
  return naturalLines(project ?? {}).join("\n") || "暂无大纲正文。请先生成大纲，或在左侧选择卷纲/章纲。";
}

export function formatVolumeOutlineDocument(volume: Volume) {
  return (
    naturalLines({
      volume_title: volume.title,
      volume_no: `第${volume.volume_no}卷`,
      outline: volume.outline,
    }).join("\n") || "暂无卷纲正文。"
  );
}

export function formatChapterOutlineDocument(chapter: Chapter) {
  return (
    naturalLines({
      chapter_title: `第${chapter.chapter_no}章 ${chapter.title}`,
      volume_no: `第${chapter.volume_no}卷`,
      outline: chapter.outline,
      plot_purpose: chapter.plot_purpose,
      pov_character: chapter.pov_character,
      core_event: chapter.core_event,
      conflict: chapter.conflict,
      turn_point: chapter.turn_point,
      cliffhanger: chapter.cliffhanger,
      emotional_beats: chapter.emotional_beats,
    }).join("\n") || "暂无章纲正文。"
  );
}

function renderOutlineParagraphs(text: string) {
  return (
    <div className="outline-prose">
      {text
        .split("\n")
        .filter((line) => line.trim())
        .map((line, index) => (
          <Typography.Paragraph key={`${line}-${index}`}>{line}</Typography.Paragraph>
        ))}
    </div>
  );
}

export function OutlineEditorPanel({
  selectedView,
  selectedVolume,
  selectedChapter,
  lastOutlinePlan,
  project,
  storyBible,
  isPlanning,
  saveVolume,
  saveChapter,
  openGenerationPreview,
  children,
}: OutlineEditorPanelProps) {
  const renderOutlineView = () => {
    if (selectedView === "outline") {
      return (
        <div className="outline-document">
          <Typography.Title level={3}>总纲</Typography.Title>
          {renderOutlineParagraphs(formatOutlineDocument(lastOutlinePlan, storyBible, project))}
        </div>
      );
    }
    if (selectedView === "volume" && selectedVolume) {
      return (
        <div className="outline-document">
          <Typography.Title level={3}>卷纲</Typography.Title>
          {renderOutlineParagraphs(formatVolumeOutlineDocument(selectedVolume))}
        </div>
      );
    }
    if (selectedView === "chapter" && selectedChapter) {
      return (
        <div className="outline-document">
          <Typography.Title level={3}>章节</Typography.Title>
          {renderOutlineParagraphs(formatChapterOutlineDocument(selectedChapter))}
        </div>
      );
    }
    if (selectedView === "chapterOutline" && selectedChapter) {
      return (
        <div className="outline-document">
          <Typography.Title level={3}>章纲</Typography.Title>
          {renderOutlineParagraphs(formatChapterOutlineDocument(selectedChapter))}
        </div>
      );
    }
    return <Empty description="请选择左侧目录项" />;
  };

  return (
    <main className="studio-panel outline-editor-panel">
      <div className="outline-editor-header">
        <div>
          <Typography.Text type="secondary">大纲工作台</Typography.Text>
          <Typography.Title level={3}>{selectedView === "outline" ? "总纲" : selectedView === "volume" ? "卷纲" : selectedView === "chapter" ? "章节" : "章纲"}</Typography.Title>
        </div>
        <Space>
          <Button icon={<RefreshCw size={15} />} loading={isPlanning} onClick={() => openGenerationPreview("outline")}>生成大纲</Button>
          <Tooltip title="根据已确认总纲、卷纲和勾选范围批量生成章纲">
            <Button type="primary" icon={<ListChecks size={15} />} loading={isPlanning} onClick={() => openGenerationPreview("chapter")}>批量生成章纲</Button>
          </Tooltip>
        </Space>
      </div>
      {renderOutlineView()}
      {children}
    </main>
  );
}
