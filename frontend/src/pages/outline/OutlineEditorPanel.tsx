import { Button, Descriptions, Empty, Form, Input, Space, Tooltip, Typography } from "antd";
import { Layers, ListChecks, RefreshCw, Save } from "lucide-react";
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
  generateFromExistingOutline: (mode: Extract<GenerationMode, "volume" | "chapter">) => void;
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
  generateFromExistingOutline,
  children,
}: OutlineEditorPanelProps) {
  const canGenerateDetails = Boolean(lastOutlinePlan);
  const renderOutlineView = () => {
    if (selectedView === "outline") {
      return (
        <div className="outline-document">
          <Typography.Title level={3}>总纲</Typography.Title>
          <div className="outline-prose">
            {formatOutlineDocument(lastOutlinePlan, storyBible, project)
              .split("\n")
              .filter((line) => line.trim())
              .map((line, index) => (
                <Typography.Paragraph key={`${line}-${index}`}>{line}</Typography.Paragraph>
              ))}
          </div>
        </div>
      );
    }
    if (selectedView === "volume" && selectedVolume) {
      return (
        <Form key={selectedVolume.id} layout="vertical" initialValues={selectedVolume} onFinish={(values) => saveVolume.mutate(values)}>
          <Typography.Title level={3}>卷纲</Typography.Title>
          <Form.Item name="title" label="分卷名称">
            <Input />
          </Form.Item>
          <Form.Item name="outline" label="卷纲">
            <Input.TextArea rows={20} />
          </Form.Item>
          <Button type="primary" htmlType="submit" icon={<Save size={15} />} loading={saveVolume.isPending}>
            保存卷纲
          </Button>
        </Form>
      );
    }
    if (selectedView === "chapter" && selectedChapter) {
      return (
        <div className="outline-document">
          <Typography.Title level={3}>章节</Typography.Title>
          <Descriptions bordered column={1} size="small">
            <Descriptions.Item label="章节">{`第${selectedChapter.chapter_no}章 ${selectedChapter.title}`}</Descriptions.Item>
            <Descriptions.Item label="剧情功能">{selectedChapter.plot_purpose || "未设置"}</Descriptions.Item>
            <Descriptions.Item label="核心事件">{selectedChapter.core_event || "未设置"}</Descriptions.Item>
            <Descriptions.Item label="核心冲突">{selectedChapter.conflict || "未设置"}</Descriptions.Item>
            <Descriptions.Item label="结尾钩子">{selectedChapter.cliffhanger || "未设置"}</Descriptions.Item>
          </Descriptions>
        </div>
      );
    }
    if (selectedView === "chapterOutline" && selectedChapter) {
      return (
        <Form key={selectedChapter.id} layout="vertical" initialValues={selectedChapter} onFinish={(values) => saveChapter.mutate(values)}>
          <Typography.Title level={3}>章纲</Typography.Title>
          <Form.Item name="title" label="章节标题">
            <Input />
          </Form.Item>
          <Form.Item name="outline" label="章纲">
            <Input.TextArea rows={8} />
          </Form.Item>
          <div className="form-grid-2">
            <Form.Item name="core_event" label="核心事件">
              <Input.TextArea rows={3} />
            </Form.Item>
            <Form.Item name="conflict" label="核心冲突">
              <Input.TextArea rows={3} />
            </Form.Item>
            <Form.Item name="turn_point" label="转折点">
              <Input.TextArea rows={3} />
            </Form.Item>
            <Form.Item name="cliffhanger" label="结尾钩子">
              <Input.TextArea rows={3} />
            </Form.Item>
          </div>
          <Button type="primary" htmlType="submit" icon={<Save size={15} />} loading={saveChapter.isPending}>
            保存章纲
          </Button>
        </Form>
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
          <Tooltip title={canGenerateDetails ? "根据已生成总纲继续生成卷纲" : "请先生成总纲"}>
            <Button icon={<Layers size={15} />} disabled={!canGenerateDetails} loading={isPlanning} onClick={() => generateFromExistingOutline("volume")}>生成卷纲</Button>
          </Tooltip>
          <Tooltip title={canGenerateDetails ? "根据已生成总纲继续生成章纲" : "请先生成总纲"}>
            <Button type="primary" icon={<ListChecks size={15} />} disabled={!canGenerateDetails} loading={isPlanning} onClick={() => generateFromExistingOutline("chapter")}>生成章纲</Button>
          </Tooltip>
        </Space>
      </div>
      {renderOutlineView()}
      {children}
    </main>
  );
}
