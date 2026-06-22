import { Empty, Typography } from "antd";
import type { Chapter, Project, StoryBible, Volume } from "../../types/api";
import type { OutlineView } from "./types";

interface OutlineEditorPanelProps {
  selectedView: OutlineView;
  selectedVolume?: Volume;
  selectedChapter?: Chapter;
  lastOutlinePlan: Record<string, unknown> | null;
  project?: Project;
  storyBible?: StoryBible;
  children?: React.ReactNode;
}

const outlineFieldLabels: Record<string, string> = {
  title: "标题",
  genre: "类型",
  target_reader: "目标读者",
  premise: "一句话故事",
  world_setting: "世界观",
  main_conflict: "主线冲突",
  core_conflict: "核心冲突",
  mainline: "主线",
  core_promise: "作品承诺",
  reader_experience: "读者体验",
  ending_direction: "终局方向",
  subtitle: "副标题",
  theme: "主题问题",
  volume_plan: "分卷规划",
  escalation_engine: "升级发动机",
  reader_expectation: "读者期待",
  forbidden_rules_ref: "禁忌规则引用",
  themes: "主题",
  style_guide: "风格",
  name: "名称",
  chapters: "章节范围",
  phase_1: "阶段一",
  phase_2: "阶段二",
  phase_3: "阶段三",
  phase_4: "阶段四",
  phase_5: "阶段五",
  stage_goal: "阶段目标",
  boundary: "边界选择",
  cost: "代价",
  pressure: "压力",
  hook: "钩子",
  act: "幕",
  act_name: "幕名",
  act_breakdown: "阶段拆分",
  chapter_group: "章节组",
  chapter_ranges: "章节范围",
  start_chapter_no: "起始章节",
  end_chapter_no: "结束章节",
  decisions: "决议",
  artifacts: "候选产物",
  uncertainty_items: "不确定项",
  confidence: "置信度",
  antagonist_pressure: "反派压力",
  long_line_setup: "长线铺垫",
  parameters: "生成参数",
  target_words: "目标总字数",
  volume_count: "卷数",
  chapters_per_volume: "每卷章节数",
  chapter_word_target: "每章字数",
  chapter_word_min: "每章最少字数",
  chapter_word_max: "每章最多字数",
  scale_plan: "规模计划",
  "世界圣经": "世界圣经",
  "全书10卷总纲": "全书十卷总纲",
  "10卷单元总表": "十卷单元总表",
  "最终修订版纲要": "最终修订版纲要",
  "伏笔账本": "伏笔账本",
  "长篇生成策略": "长篇生成策略",
  volume_title: "分卷名称",
  summary: "摘要",
  chapter_range: "章节区间",
  volume_function: "本卷功能",
  rhythm_model: "节奏模型",
  model_name: "模型",
  why_this_model: "选择理由",
  phase_count: "阶段数",
  chapter_distribution: "章节分配",
  core_goal: "核心目标",
  main_track: "主线",
  hidden_track: "暗线",
  character_track: "人物线",
  world_reveal: "世界揭示",
  opposition_pressure: "阻力压力",
  volume_hook: "卷末钩子",
  risks: "风险",
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

type OutlineTextSection = { kind: "text"; text: string } | { kind: "structured"; label: string; value: unknown };

function normalizePythonLikeJson(text: string) {
  return text
    .trim()
    .replace(/\bNone\b/g, "null")
    .replace(/\bTrue\b/g, "true")
    .replace(/\bFalse\b/g, "false")
    .replace(/'([^'\\]*(?:\\.[^'\\]*)*)'/g, (_, content: string) => JSON.stringify(content.replace(/\\'/g, "'")));
}

function safeParseStructuredText(text: string): unknown {
  const trimmed = text.trim();
  if (!trimmed || (!trimmed.startsWith("{") && !trimmed.startsWith("["))) return text;
  try {
    return JSON.parse(trimmed);
  } catch {
    try {
      return JSON.parse(normalizePythonLikeJson(trimmed));
    } catch {
      return text;
    }
  }
}

function parseMaybeJson(value: unknown): unknown {
  if (typeof value !== "string") return value;
  const trimmed = value.trim();
  if (!trimmed || (!trimmed.startsWith("{") && !trimmed.startsWith("["))) return value;
  return safeParseStructuredText(trimmed);
}

function isScalar(value: unknown) {
  return ["string", "number", "boolean"].includes(typeof value);
}

function labelFor(key: string) {
  const normalizedKey = key.trim().replace(/^[\s_]+/, "").replace(/[\s-]+/g, "_");
  const phaseMatch = normalizedKey.match(/^phase_(\d+)$/i);
  if (phaseMatch) return `阶段${phaseMatch[1]}`;
  const actMatch = normalizedKey.match(/^act_(\d+)$/i);
  if (actMatch) return `第${actMatch[1]}幕`;
  return outlineFieldLabels[normalizedKey] ?? normalizedKey;
}

function localizeInlineLabel(line: string) {
  const match = line.match(/^(\s*)([-*]\s*)?([A-Za-z][A-Za-z0-9_\s-]{1,64})([：:])(.*)$/);
  if (!match) return line;
  const [, leading, bullet = "", key, separator, rest] = match;
  return `${leading}${bullet}${labelFor(key)}${separator}${rest}`;
}

function extractStructuredOutlineSections(text: string): OutlineTextSection[] {
  const sections = text.split("\n").map((line) => {
    const match = line.match(/^(\s*)(?:[-*]\s*)?([^：:\n]{1,64})[：:]\s*([\[{].*)$/);
    if (!match) return { kind: "text", text: localizeInlineLabel(line) } as OutlineTextSection;
    const parsed = safeParseStructuredText(match[3]);
    if (typeof parsed === "string") return { kind: "text", text: localizeInlineLabel(line) } as OutlineTextSection;
    return { kind: "structured", label: match[2].trim(), value: parsed } as OutlineTextSection;
  });
  return sections.some((section) => section.kind === "structured") ? sections : [];
}

function naturalLines(value: unknown, label = "", depth = 0): string[] {
  const normalized = parseMaybeJson(value);
  const indent = depth > 0 ? "  ".repeat(depth - 1) : "";
  const heading = label ? labelFor(label) : "";
  if (normalized === null || normalized === undefined || normalized === "") {
    return heading ? [`${indent}${heading}：暂无`] : [];
  }
  if (typeof normalized === "string") {
    const structuredSections = extractStructuredOutlineSections(normalized);
    if (structuredSections.length) {
      const lines = heading ? [`${indent}${heading}：`] : [];
      structuredSections.forEach((section) => {
        if (section.kind === "structured") {
          lines.push(...naturalLines(section.value, section.label, depth + 1));
          return;
        }
        const text = section.text.trim();
        if (text) lines.push(`${indent}${text}`);
      });
      return lines;
    }
    return [`${indent}${heading ? `${heading}：` : ""}${localizeInlineLabel(normalized)}`];
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
      if (key.startsWith("outline_debate_debug") || key.includes("Agent推演链") || key === "agent_outputs" || key === "structured_prompt") return false;
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
  return naturalLines(project ?? {}).join("\n") || "暂无大纲正文。请在右侧议事引擎中讨论并确认大纲，或在左侧选择卷纲/章纲。";
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
      crisis: chapter.crisis,
      climax: chapter.climax,
      outcome: chapter.outcome,
      turn_point: chapter.turn_point,
      chapter_hook: chapter.chapter_hook || chapter.cliffhanger,
      foreshadowing_plants: chapter.foreshadowing_plants,
      foreshadowing_payoffs: chapter.foreshadowing_payoffs,
      canon_updates: chapter.canon_updates,
      continuity_risks: chapter.continuity_risks,
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
          <Typography.Text type="secondary">大纲正文</Typography.Text>
          <Typography.Title level={3}>{selectedView === "outline" ? "总纲" : selectedView === "volume" ? "卷纲" : selectedView === "chapter" ? "章节" : "章纲"}</Typography.Title>
        </div>
      </div>
      {renderOutlineView()}
      {children}
    </main>
  );
}
