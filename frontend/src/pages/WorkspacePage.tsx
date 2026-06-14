import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Divider,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Progress,
  Segmented,
  Select,
  Space,
  Switch,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  ArrowDown,
  ArrowUp,
  Bookmark,
  Bot,
  Check,
  CheckCircle,
  Clipboard,
  FileClock,
  FilePlus2,
  FileText,
  History,
  Plus,
  RefreshCw,
  Replace,
  Save,
  Send,
  Sparkles,
  Trash2,
  WandSparkles,
  X,
} from "lucide-react";
import { ThreadPrimitive } from "@assistant-ui/react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { MarkdownPreview } from "../components/MarkdownPreview";
import {
  streamChapterChat,
  studioApi,
  type ChapterChatMode,
  type ChapterChatSelection,
  type ChapterChatStreamEvent,
  type ForeshadowingSuggestion,
  type ImportanceLevel,
} from "../api/studio";
import type { Chapter, EditorProposal, Volume } from "../types/api";

const aiTools = [
  ["opening", "开篇"],
  ["continue", "续写"],
  ["optimize", "优化"],
  ["polish", "润色"],
  ["review", "审稿"],
  ["rewrite", "重写"],
  ["inspiration", "灵感"],
  ["setting_update", "设定更新"],
] as const;

const chatModeOptions: Array<{ label: string; value: ChapterChatMode }> = [
  { label: "改写", value: "revise" },
  { label: "润色", value: "polish" },
  { label: "扩写", value: "expand" },
  { label: "压缩", value: "tighten" },
  { label: "续写", value: "continue" },
];

interface EditorSelection {
  start: number | null;
  end: number | null;
  text: string;
}

interface AssistantChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
  replacement?: string;
  reasoning?: string;
  checklist?: string[];
  selection?: ChapterChatSelection;
  usedRemoteModel?: boolean;
}

function smartFormat(text: string) {
  return text
    .replace(/\r\n/g, "\n")
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .flatMap((line) => line.split(/(?<=[。！？!?])\s*/).filter(Boolean))
    .map((line) => `　　${line}`)
    .join("\n\n");
}

function frequentWords(text: string) {
  const words = text.match(/[\u4e00-\u9fff]{2,4}|[A-Za-z]{3,}/g) ?? [];
  const counts = new Map<string, number>();
  words.forEach((word) => counts.set(word, (counts.get(word) ?? 0) + 1));
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 24);
}

export function WorkspacePage() {
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const stateQuery = useQuery({ queryKey: ["state", projectId], queryFn: () => studioApi.getState(projectId), enabled: !!projectId });
  const volumesQuery = useQuery({ queryKey: ["volumes", projectId], queryFn: () => studioApi.listVolumes(projectId), enabled: !!projectId });
  const trashQuery = useQuery({ queryKey: ["chapter-trash", projectId], queryFn: () => studioApi.listTrash(projectId), enabled: !!projectId });
  const [chapterId, setChapterId] = useState("");
  const [editorValue, setEditorValue] = useState("");
  const [dirty, setDirty] = useState(false);
  const [activeProposal, setActiveProposal] = useState<EditorProposal | null>(null);
  const [replaceOpen, setReplaceOpen] = useState(false);
  const [frequencyOpen, setFrequencyOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [trashOpen, setTrashOpen] = useState(false);
  const [plantOpen, setPlantOpen] = useState(false);
  const [payoffOpen, setPayoffOpen] = useState(false);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<ForeshadowingSuggestion[]>([]);
  const [editorSelection, setEditorSelection] = useState<EditorSelection>({ start: null, end: null, text: "" });
  const [chatMode, setChatMode] = useState<ChapterChatMode>("revise");
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<AssistantChatMessage[]>([]);
  const [chatStreaming, setChatStreaming] = useState(false);
  const [replaceForm] = Form.useForm<{ find: string; replace: string; regex: boolean }>();
  const [chapterForm] = Form.useForm<{ title: string; volume_no: number; outline: string }>();
  const [volumeForm] = Form.useForm<{ title: string; outline: string }>();
  const [plantForm] = Form.useForm<{ content: string; planned_payoff: string; importance_level: ImportanceLevel; importance_score: number }>();
  const [payoffForm] = Form.useForm<{ item_id: string; actual_payoff_chapter_id: string; payoff_note: string }>();
  const [suggestForm] = Form.useForm<{ instruction: string }>();

  const chapters = stateQuery.data?.state.chapters ?? [];
  const volumes = volumesQuery.data?.volumes ?? [];
  const selectedChapter = useMemo(() => chapters.find((chapter) => chapter.id === chapterId) ?? chapters[0], [chapterId, chapters]);
  const proposalsQuery = useQuery({
    queryKey: ["proposals", projectId, selectedChapter?.id],
    queryFn: () => studioApi.listProposals(projectId, selectedChapter?.id),
    enabled: !!selectedChapter,
  });
  const versionsQuery = useQuery({
    queryKey: ["versions", selectedChapter?.id],
    queryFn: () => studioApi.listVersions(selectedChapter?.id),
    enabled: !!selectedChapter,
  });

  const foreshadowingItems = stateQuery.data?.state.foreshadowing_items ?? [];
  const unresolvedHooks = foreshadowingItems.filter((item) => !["paid_off", "abandoned"].includes(item.payoff_status));
  const pendingProposals = (proposalsQuery.data?.proposals ?? []).filter((item) => item.status === "pending");

  const invalidateWorkbench = () => {
    queryClient.invalidateQueries({ queryKey: ["state", projectId] });
    queryClient.invalidateQueries({ queryKey: ["volumes", projectId] });
    queryClient.invalidateQueries({ queryKey: ["chapter-trash", projectId] });
    queryClient.invalidateQueries({ queryKey: ["proposals", projectId] });
    queryClient.invalidateQueries({ queryKey: ["versions"] });
  };

  useEffect(() => {
    if (selectedChapter) {
      setChapterId(selectedChapter.id);
      setEditorValue(selectedChapter.final_text || selectedChapter.draft_text || selectedChapter.outline);
      setDirty(false);
      setEditorSelection({ start: null, end: null, text: "" });
      setChatMessages([
        {
          id: `assistant-welcome-${selectedChapter.id}`,
          role: "assistant",
          content: "选中正文里的具体段落，告诉我你想怎么改。我会先流式生成建议，确认后才会应用到正文。",
        },
      ]);
    }
  }, [selectedChapter?.id]);

  const saveMutation = useMutation({
    mutationFn: (content?: string) => studioApi.updateChapter(projectId, selectedChapter!.id, { final_text: content ?? editorValue, status: "drafted" }),
    onSuccess: () => {
      setDirty(false);
      queryClient.invalidateQueries({ queryKey: ["state", projectId] });
      queryClient.invalidateQueries({ queryKey: ["versions", selectedChapter?.id] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "自动保存失败"),
  });
  const draftMutation = useMutation({
    mutationFn: () => studioApi.draftChapter(projectId, selectedChapter!.id, "请根据当前章纲生成首版正文，保持设定连续、冲突清晰，并保留结尾钩子。"),
    onSuccess: ({ chapter }) => {
      message.success("章节正文已生成");
      setEditorValue(chapter.final_text || chapter.draft_text || "");
      setDirty(false);
      invalidateWorkbench();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "生成正文失败"),
  });

  useEffect(() => {
    if (!dirty || !selectedChapter || saveMutation.isPending) return;
    const timer = window.setTimeout(() => saveMutation.mutate(undefined), 1800);
    return () => window.clearTimeout(timer);
  }, [dirty, editorValue, selectedChapter?.id]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (selectedChapter && !saveMutation.isPending) saveMutation.mutate(undefined);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedChapter?.id, editorValue, saveMutation.isPending]);

  const createChapter = useMutation({
    mutationFn: (values: { title: string; volume_no: number; outline: string }) => studioApi.createChapter(projectId, values),
    onSuccess: ({ chapter }) => { message.success("章节已创建"); setChapterId(chapter.id); chapterForm.resetFields(); invalidateWorkbench(); },
    onError: (error) => message.error(error instanceof Error ? error.message : "创建章节失败"),
  });
  const createVolume = useMutation({
    mutationFn: (values: { title: string; outline: string }) => studioApi.createVolume(projectId, values),
    onSuccess: () => { message.success("分卷已创建"); volumeForm.resetFields(); invalidateWorkbench(); },
  });
  const reorder = useMutation({
    mutationFn: (ids: string[]) => studioApi.reorderChapters(projectId, ids),
    onSuccess: () => invalidateWorkbench(),
  });
  const proposalMutation = useMutation({
    mutationFn: (toolName: string) => studioApi.createProposal(projectId, selectedChapter!.id, { tool_name: toolName, instruction: "保持设定连续并服务当前章节目标。" }),
    onSuccess: ({ proposal }) => {
      message.success("AI 提案已生成，确认后才会写入正文");
      setActiveProposal(proposal);
      queryClient.invalidateQueries({ queryKey: ["proposals", projectId] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "生成提案失败"),
  });
  const applyProposal = useMutation({
    mutationFn: (proposalId: string) => studioApi.applyProposal(projectId, proposalId),
    onSuccess: ({ chapter }) => {
      message.success("提案已应用，并保存了应用前快照");
      setEditorValue(chapter.final_text);
      setActiveProposal(null);
      invalidateWorkbench();
    },
  });
  const rejectProposal = useMutation({
    mutationFn: (proposalId: string) => studioApi.rejectProposal(projectId, proposalId),
    onSuccess: () => { message.success("提案已拒绝"); setActiveProposal(null); invalidateWorkbench(); },
  });
  const rollback = useMutation({
    mutationFn: (versionId: string) => studioApi.rollbackVersion(versionId, "从正文工作台恢复"),
    onSuccess: () => { message.success("历史版本已恢复"); setHistoryOpen(false); invalidateWorkbench(); },
  });
  const plantMutation = useMutation({
    mutationFn: (values: { content: string; planned_payoff: string; importance_level: ImportanceLevel; importance_score: number }) =>
      studioApi.createForeshadowing(projectId, {
        chapter_id: selectedChapter!.id,
        planted_chapter_id: selectedChapter!.id,
        content: values.content,
        planned_payoff: values.planned_payoff,
        payoff_status: "planted",
        importance_level: values.importance_level,
        importance_score: values.importance_score,
        source: "manual",
      }),
    onSuccess: () => { message.success("伏笔已预埋"); setPlantOpen(false); plantForm.resetFields(); invalidateWorkbench(); },
  });
  const payoffMutation = useMutation({
    mutationFn: (values: { item_id: string; actual_payoff_chapter_id: string; payoff_note: string }) =>
      studioApi.payoffForeshadowing(projectId, values.item_id, values.actual_payoff_chapter_id, values.payoff_note),
    onSuccess: () => { message.success("伏笔已回收"); setPayoffOpen(false); payoffForm.resetFields(); invalidateWorkbench(); },
  });
  const suggestMutation = useMutation({
    mutationFn: (values: { instruction: string }) => studioApi.suggestForeshadowing(projectId, selectedChapter?.id, values.instruction),
    onSuccess: (result) => { setSuggestions(result.suggestions); message.success("Agent 已生成伏笔建议"); },
  });

  const moveChapter = (direction: -1 | 1) => {
    if (!selectedChapter) return;
    const index = chapters.findIndex((item) => item.id === selectedChapter.id);
    const target = index + direction;
    if (target < 0 || target >= chapters.length) return;
    const ids = chapters.map((item) => item.id);
    [ids[index], ids[target]] = [ids[target], ids[index]];
    reorder.mutate(ids);
  };
  const applyReplace = (values: { find: string; replace: string; regex: boolean }) => {
    try {
      const next = values.regex ? editorValue.replace(new RegExp(values.find, "g"), values.replace) : editorValue.split(values.find).join(values.replace);
      setEditorValue(next);
      setDirty(true);
      setReplaceOpen(false);
      message.success("替换已应用到当前正文");
    } catch {
      message.error("正则表达式不合法");
    }
  };

  const captureEditorSelection = (target: HTMLTextAreaElement) => {
    const start = target.selectionStart;
    const end = target.selectionEnd;
    setEditorSelection({ start, end, text: start === end ? "" : target.value.slice(start, end) });
  };

  const updateAssistantMessage = (messageId: string, updater: (message: AssistantChatMessage) => AssistantChatMessage) => {
    setChatMessages((items) => items.map((item) => (item.id === messageId ? updater(item) : item)));
  };

  const sendChapterChat = async () => {
    if (!selectedChapter || !chatInput.trim() || chatStreaming) return;
    const instruction = chatInput.trim();
    const selectionSnapshot = { ...editorSelection };
    const userId = `user-${Date.now()}`;
    const assistantId = `assistant-${Date.now()}`;
    setChatMessages((items) => [
      ...items,
      { id: userId, role: "user", content: instruction },
      {
        id: assistantId,
        role: "assistant",
        content: "正在连接 FastAPI SSE，读取选区上下文…",
        pending: true,
      },
    ]);
    setChatInput("");
    setChatStreaming(true);
    try {
      await streamChapterChat(
        projectId,
        selectedChapter.id,
        {
          mode: chatMode,
          instruction,
          selected_text: selectionSnapshot.text,
          chapter_text: editorValue,
          selection_start: selectionSnapshot.start,
          selection_end: selectionSnapshot.end,
        },
        (event: ChapterChatStreamEvent) => {
          if (event.type === "meta") {
            updateAssistantMessage(assistantId, (item) => ({
              ...item,
              content: event.message,
              selection: event.selection,
            }));
          }
          if (event.type === "delta") {
            updateAssistantMessage(assistantId, (item) => ({
              ...item,
              content: item.content.startsWith("已读取当前章节") || item.content.startsWith("正在连接") ? event.text : item.content + event.text,
            }));
          }
          if (event.type === "result") {
            updateAssistantMessage(assistantId, (item) => ({
              ...item,
              content: event.replacement,
              pending: false,
              replacement: event.replacement,
              reasoning: event.reasoning,
              checklist: event.checklist,
              selection: event.selection,
              usedRemoteModel: event.used_remote_model,
            }));
          }
          if (event.type === "done") {
            updateAssistantMessage(assistantId, (item) => ({ ...item, pending: false }));
          }
        },
      );
    } catch (error) {
      updateAssistantMessage(assistantId, (item) => ({
        ...item,
        pending: false,
        content: error instanceof Error ? error.message : "流式对话失败，请稍后重试。",
      }));
      message.error("AI 对话失败");
    } finally {
      setChatStreaming(false);
    }
  };

  const applyAssistantReplacement = (item: AssistantChatMessage) => {
    const replacement = item.replacement || item.content;
    if (!replacement) return;
    const start = item.selection?.start ?? editorSelection.start;
    const end = item.selection?.end ?? editorSelection.end;
    const hasSelection = item.selection?.has_selection && typeof start === "number" && typeof end === "number" && end > start;
    const next = hasSelection
      ? editorValue.slice(0, start) + replacement + editorValue.slice(end)
      : `${editorValue}${editorValue ? "\n\n" : ""}${replacement}`;
    setEditorValue(next);
    setDirty(true);
    setEditorSelection({ start: null, end: null, text: "" });
    saveMutation.mutate(next);
    message.success(hasSelection ? "已应用到选区，并触发保存" : "已追加到正文，并触发保存");
  };

  if (stateQuery.isLoading || volumesQuery.isLoading) return <div className="workbench-shell"><div className="studio-panel loading-panel" /></div>;
  if (stateQuery.error || !stateQuery.data) return <Alert type="error" message="无法载入工作台" description="请确认后端服务已启动，或项目 ID 是否存在。" showIcon />;

  const { project, story_bible: storyBible, characters, world_facts: worldFacts, continuity_issues: issues } = stateQuery.data.state;
  const chapterOptions = chapters.map((chapter) => ({ value: chapter.id, label: `${chapter.chapter_no}. ${chapter.title}` }));
  const unresolvedOptions = unresolvedHooks.map((item) => ({ value: item.id, label: item.content }));

  return (
    <div className="workbench-shell">
      <aside className="workbench-directory studio-panel">
        <div className="panel-heading">
          <div><Typography.Text strong>卷章目录</Typography.Text><Typography.Text type="secondary">{chapters.length} 章 · {chapters.reduce((sum, item) => sum + item.word_count, 0)} 字</Typography.Text></div>
          <Space size={2}>
            <Tooltip title="新建分卷"><Button type="text" icon={<Plus size={15} />} onClick={() => Modal.confirm({
              title: "新建分卷",
              content: <Form form={volumeForm} layout="vertical"><Form.Item name="title" label="分卷名称" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="outline" label="卷纲"><Input.TextArea rows={3} /></Form.Item></Form>,
              onOk: () => volumeForm.validateFields().then((values) => createVolume.mutateAsync(values)),
            })} /></Tooltip>
            <Tooltip title="新建章节"><Button type="text" icon={<FilePlus2 size={15} />} onClick={() => Modal.confirm({
              title: "新建章节",
              content: <Form form={chapterForm} layout="vertical" initialValues={{ volume_no: volumes[0]?.volume_no ?? 1 }}><Form.Item name="title" label="章节标题" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="volume_no" label="所属分卷"><Select options={volumes.map((item) => ({ value: item.volume_no, label: item.title }))} /></Form.Item><Form.Item name="outline" label="章纲"><Input.TextArea rows={3} /></Form.Item></Form>,
              onOk: () => chapterForm.validateFields().then((values) => createChapter.mutateAsync(values)),
            })} /></Tooltip>
            <Tooltip title="回收站"><Button type="text" icon={<Trash2 size={15} />} onClick={() => setTrashOpen(true)} /></Tooltip>
          </Space>
        </div>
        <div className="chapter-directory-scroll">
          {volumes.map((volume: Volume) => (
            <div key={volume.id} className="volume-group">
              <div className="volume-heading"><Typography.Text strong>{volume.title}</Typography.Text><Tag>{chapters.filter((item) => item.volume_no === volume.volume_no).length}</Tag></div>
              {chapters.filter((item) => item.volume_no === volume.volume_no).map((chapter) => (
                <button key={chapter.id} className={`chapter-directory-item ${chapter.id === selectedChapter?.id ? "is-active" : ""}`} onClick={() => setChapterId(chapter.id)}>
                  <span>{chapter.chapter_no}. {chapter.title}</span><small>{chapter.word_count} 字</small>
                </button>
              ))}
            </div>
          ))}
          {chapters.length === 0 ? <Empty description="还没有章节，先新建章节或生成大纲" /> : null}
        </div>
        <Divider />
        <div className="directory-utilities">
          <Button size="small" icon={<ArrowUp size={14} />} disabled={!selectedChapter} onClick={() => moveChapter(-1)}>上移</Button>
          <Button size="small" icon={<ArrowDown size={14} />} disabled={!selectedChapter} onClick={() => moveChapter(1)}>下移</Button>
          <Button size="small" danger icon={<Trash2 size={14} />} disabled={!selectedChapter} onClick={() => selectedChapter && studioApi.trashChapter(projectId, selectedChapter.id).then(() => { setChapterId(""); invalidateWorkbench(); })}>删除</Button>
        </div>
        <div className="resource-peek">
          <Typography.Text strong>创作资源</Typography.Text>
          <Typography.Text type="secondary">角色 {characters.length} · 世界事实 {worldFacts.length} · 未回收伏笔 {unresolvedHooks.length}</Typography.Text>
        </div>
      </aside>

      <main className="workbench-editor studio-panel">
        <div className="editor-chapter-header">
          <div>
            <Typography.Title level={3}>{selectedChapter?.title ?? project.title}</Typography.Title>
            <Space size={6}><Tag>{selectedChapter?.status ?? "未规划"}</Tag><Typography.Text type="secondary">{dirty ? "正在自动保存…" : saveMutation.isPending ? "保存中…" : "已自动保存"}</Typography.Text></Space>
          </div>
          <Space>
            <Select value={selectedChapter?.id} options={chapterOptions} onChange={setChapterId} style={{ width: 220 }} placeholder="选择章节" />
            <Button icon={<Save size={15} />} disabled={!selectedChapter} loading={saveMutation.isPending} onClick={() => saveMutation.mutate(undefined)}>保存</Button>
          </Space>
        </div>
        <div className="editor-toolbar">
          <Space wrap size={4}>
            <Button icon={<WandSparkles size={14} />} type="primary" disabled={!selectedChapter || dirty} loading={draftMutation.isPending} onClick={() => draftMutation.mutate()}>生成正文</Button>
            <Button icon={<WandSparkles size={14} />} disabled={!selectedChapter} onClick={() => { setEditorValue(smartFormat(editorValue)); setDirty(true); message.success("智能排版已应用"); }}>智能排版</Button>
            <Button icon={<Replace size={14} />} disabled={!selectedChapter} onClick={() => setReplaceOpen(true)}>查找替换</Button>
            <Button icon={<FileText size={14} />} disabled={!selectedChapter} onClick={() => setFrequencyOpen(true)}>高频词</Button>
            <Button icon={<History size={14} />} disabled={!selectedChapter} onClick={() => setHistoryOpen(true)}>历史版本</Button>
            <Button icon={<FileClock size={14} />} disabled={!selectedChapter} onClick={() => selectedChapter && studioApi.snapshotChapter(projectId, selectedChapter.id, "工作台手动快照").then(() => { message.success("快照已保存"); invalidateWorkbench(); })}>保存快照</Button>
            <Button icon={<Clipboard size={14} />} disabled={!editorValue} onClick={() => navigator.clipboard.writeText(editorValue).then(() => message.success("正文已复制"))}>复制正文</Button>
          </Space>
          <Space><Typography.Text type="secondary">{editorValue.replace(/\s/g, "").length} 字</Typography.Text><Progress percent={selectedChapter ? Math.min(100, Math.round(editorValue.replace(/\s/g, "").length / selectedChapter.word_target * 100)) : 0} size="small" style={{ width: 90 }} /></Space>
        </div>
        {selectedChapter ? (
          <Tabs
            className="editor-tabs"
            items={[
              {
                key: "edit",
                label: "正文编辑",
                children: (
                  <Input.TextArea
                    className="markdown-editor-textarea"
                    value={editorValue}
                    onChange={(event) => { setEditorValue(event.target.value); setDirty(true); }}
                    onKeyUp={(event) => captureEditorSelection(event.currentTarget)}
                    onMouseUp={(event) => captureEditorSelection(event.currentTarget)}
                    onSelect={(event) => captureEditorSelection(event.currentTarget)}
                    placeholder="开始撰写正文。支持 Markdown。"
                    style={{ height: 620, resize: "none" }}
                  />
                ),
              },
              { key: "preview", label: "阅读预览", children: <MarkdownPreview source={editorValue || "暂无正文"} className="reading-preview" /> },
              { key: "outline", label: "章纲与目标", children: <div className="chapter-intent-panel"><Typography.Title level={4}>{selectedChapter.outline || "暂无章纲"}</Typography.Title><p><strong>核心事件：</strong>{selectedChapter.core_event || "未设置"}</p><p><strong>冲突：</strong>{selectedChapter.conflict || "未设置"}</p><p><strong>转折：</strong>{selectedChapter.turn_point || "未设置"}</p><p><strong>结尾钩子：</strong>{selectedChapter.cliffhanger || "未设置"}</p></div> },
            ]}
          />
        ) : <Empty description="从左侧新建或选择一个章节开始写作" />}
      </main>

      <aside className="workbench-assistant studio-panel">
        <div className="panel-heading">
          <div><Typography.Text strong>AI 协作助手</Typography.Text><Typography.Text type="secondary">assistant-ui + FastAPI SSE</Typography.Text></div>
          <Tag color={pendingProposals.length ? "gold" : "green"}>{pendingProposals.length} 待审批</Tag>
        </div>
        <div className="assistant-chat-context">
          <Space align="center" size={6}>
            <Typography.Text strong>选区上下文</Typography.Text>
            {editorSelection.text ? <Tag color="cyan">{editorSelection.text.length} 字</Tag> : <Tag>未选择</Tag>}
          </Space>
          <Typography.Paragraph ellipsis={{ rows: 3 }}>
            {editorSelection.text || "在正文编辑器里选中一段文字，然后让助手润色、扩写、压缩或按要求改写。未选择时会生成可追加建议。"}
          </Typography.Paragraph>
        </div>
        <ThreadPrimitive.Root className="assistant-ui-thread" data-runtime="fastapi-sse">
          <div className="assistant-chat-log">
            {chatMessages.map((item) => (
              <div key={item.id} className={`assistant-chat-message is-${item.role}`}>
                <Space className="assistant-chat-message-meta" size={6}>
                  <Tag color={item.role === "assistant" ? "green" : "blue"}>{item.role === "assistant" ? "Assistant" : "你"}</Tag>
                  {item.pending ? <Tag color="processing">streaming</Tag> : null}
                  {item.role === "assistant" && item.usedRemoteModel === false ? <Tag color="orange">本地降级</Tag> : null}
                </Space>
                <Typography.Paragraph className="assistant-chat-message-content">
                  {item.content}
                </Typography.Paragraph>
                {item.reasoning ? <Typography.Paragraph className="assistant-chat-reasoning" type="secondary">{item.reasoning}</Typography.Paragraph> : null}
                {item.checklist?.length ? (
                  <div className="assistant-chat-checklist">
                    {item.checklist.map((entry) => <Tag key={entry}>{entry}</Tag>)}
                  </div>
                ) : null}
                {item.role === "assistant" && item.replacement ? (
                  <Button size="small" type="primary" icon={<Check size={14} />} disabled={!selectedChapter || saveMutation.isPending} onClick={() => applyAssistantReplacement(item)}>
                    应用到选区
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
          <div className="assistant-chat-composer">
            <Segmented value={chatMode} options={chatModeOptions} onChange={(value) => setChatMode(value as ChapterChatMode)} />
            <Input.TextArea
              value={chatInput}
              rows={3}
              placeholder="例如：把这段改得更紧张，但不要新增设定。"
              onChange={(event) => setChatInput(event.target.value)}
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  sendChapterChat();
                }
              }}
            />
            <Button type="primary" icon={<Send size={14} />} disabled={!selectedChapter || !chatInput.trim()} loading={chatStreaming} onClick={sendChapterChat}>
              发送
            </Button>
          </div>
        </ThreadPrimitive.Root>
        <Typography.Text className="assistant-flow-note" type="secondary">
          生成提案 → 展示差异 → 用户确认 → 应用前快照 → 写入正文
        </Typography.Text>
        <Divider />
        <Typography.Text strong>传统提案工具</Typography.Text>
        <div className="assistant-tools">
          {aiTools.map(([key, label]) => <Button key={key} icon={<Sparkles size={14} />} disabled={!selectedChapter} loading={proposalMutation.isPending} onClick={() => proposalMutation.mutate(key)}>{label}</Button>)}
        </div>
        <Divider />
        <Typography.Text strong>提案审批</Typography.Text>
        {pendingProposals.length === 0 ? <Empty description="AI 修改会先出现在这里，不会直接覆盖正文" image={Empty.PRESENTED_IMAGE_SIMPLE} /> : (
          <List size="small" dataSource={pendingProposals} renderItem={(proposal) => (
            <List.Item actions={[<Button key="preview" type="link" onClick={() => setActiveProposal(proposal)}>查看 Diff</Button>]}>
              <List.Item.Meta title={<Space><Tag color="gold">{proposal.tool_name}</Tag><span>待审批</span></Space>} description={proposal.instruction || "保持设定连续"} />
            </List.Item>
          )} />
        )}
        <Divider />
        <Space wrap>
          <Button icon={<Bookmark size={14} />} disabled={!selectedChapter} onClick={() => setPlantOpen(true)}>预埋伏笔</Button>
          <Button icon={<CheckCircle size={14} />} disabled={!selectedChapter || unresolvedOptions.length === 0} onClick={() => setPayoffOpen(true)}>回收伏笔</Button>
          <Button icon={<Bot size={14} />} disabled={!selectedChapter} onClick={() => setSuggestOpen(true)}>Agent 建议伏笔</Button>
        </Space>
        <Divider />
        <Typography.Text strong>当前上下文</Typography.Text>
        <div className="context-summary">
          <Tag>{characters.length} 角色</Tag><Tag>{worldFacts.length} 世界事实</Tag><Tag>{issues.length} 连续性问题</Tag>
          <Typography.Paragraph ellipsis={{ rows: 5 }}>{storyBible?.world_setting || project.premise}</Typography.Paragraph>
        </div>
      </aside>

      <Modal
        title="AI 提案预览"
        open={!!activeProposal}
        width={760}
        onCancel={() => setActiveProposal(null)}
        footer={activeProposal ? <Space><Button danger icon={<X size={14} />} loading={rejectProposal.isPending} onClick={() => rejectProposal.mutate(activeProposal.id)}>拒绝</Button><Button type="primary" icon={<Check size={14} />} loading={applyProposal.isPending} onClick={() => applyProposal.mutate(activeProposal.id)}>应用提案</Button></Space> : null}
      >
        {activeProposal ? <><Alert type="info" showIcon message="应用前会自动保存当前正文快照" /><pre className="diff-panel">{activeProposal.diff.join("\n") || "提案未产生逐行差异"}</pre><Divider /><Typography.Title level={5}>建议稿</Typography.Title><MarkdownPreview source={activeProposal.proposed_content} /></> : null}
      </Modal>

      <Modal title="查找替换" open={replaceOpen} onCancel={() => setReplaceOpen(false)} onOk={() => replaceForm.submit()} okText="替换当前正文">
        <Form form={replaceForm} layout="vertical" initialValues={{ regex: false }} onFinish={applyReplace}>
          <Form.Item name="find" label="查找" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="replace" label="替换为"><Input /></Form.Item>
          <Form.Item name="regex" label="使用正则" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Modal>
      <Modal title="高频词分析" open={frequencyOpen} footer={null} onCancel={() => setFrequencyOpen(false)}>
        <List dataSource={frequentWords(editorValue)} renderItem={([word, count]) => <List.Item><Typography.Text>{word}</Typography.Text><Tag>{count} 次</Tag></List.Item>} locale={{ emptyText: "正文中暂无可统计词语" }} />
      </Modal>
      <Modal title="历史版本" open={historyOpen} footer={null} width={760} onCancel={() => setHistoryOpen(false)}>
        <List loading={versionsQuery.isLoading} dataSource={versionsQuery.data?.versions ?? []} locale={{ emptyText: "暂无历史版本" }} renderItem={(version) => <List.Item actions={[<Button key="restore" type="link" loading={rollback.isPending} onClick={() => rollback.mutate(version.id)}>恢复</Button>]}><List.Item.Meta title={<Space><Tag>{version.agent_name}</Tag>{version.user_note || version.content_type}</Space>} description={version.created_at} /></List.Item>} />
      </Modal>
      <Modal title="章节回收站" open={trashOpen} footer={null} onCancel={() => setTrashOpen(false)}>
        <List loading={trashQuery.isLoading} dataSource={trashQuery.data?.chapters ?? []} locale={{ emptyText: "回收站为空" }} renderItem={(chapter) => <List.Item actions={[<Button key="restore" type="link" onClick={() => studioApi.restoreChapter(projectId, chapter.id).then(invalidateWorkbench)}>恢复</Button>]}><List.Item.Meta title={chapter.title} description={`删除时间：${chapter.deleted_at}`} /></List.Item>} />
      </Modal>
      <Modal title="预埋伏笔" open={plantOpen} okText="保存" confirmLoading={plantMutation.isPending} onCancel={() => setPlantOpen(false)} onOk={() => plantForm.submit()}>
        <Form form={plantForm} layout="vertical" initialValues={{ importance_level: "medium", importance_score: 60 }} onFinish={(values) => plantMutation.mutate(values)}>
          <Form.Item name="content" label="伏笔内容" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item><Form.Item name="planned_payoff" label="计划回收"><Input.TextArea rows={3} /></Form.Item><Form.Item name="importance_level" label="重要度"><Select options={["core", "major", "medium", "minor"].map((value) => ({ value, label: value }))} /></Form.Item><Form.Item name="importance_score" label="重要度分数"><InputNumber min={0} max={100} className="full-width" /></Form.Item>
        </Form>
      </Modal>
      <Modal title="回收伏笔" open={payoffOpen} okText="标记回收" confirmLoading={payoffMutation.isPending} onCancel={() => setPayoffOpen(false)} onOk={() => payoffForm.submit()}>
        <Form form={payoffForm} layout="vertical" initialValues={{ actual_payoff_chapter_id: selectedChapter?.id }} onFinish={(values) => payoffMutation.mutate(values)}>
          <Form.Item name="item_id" label="选择伏笔" rules={[{ required: true }]}><Select options={unresolvedOptions} /></Form.Item><Form.Item name="actual_payoff_chapter_id" label="实际回收章节" rules={[{ required: true }]}><Select options={chapterOptions} /></Form.Item><Form.Item name="payoff_note" label="回收说明"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>
      <Modal title="Agent 建议伏笔" open={suggestOpen} width={720} okText="生成建议" confirmLoading={suggestMutation.isPending} onCancel={() => setSuggestOpen(false)} onOk={() => suggestForm.submit()}>
        <Form form={suggestForm} layout="vertical" initialValues={{ instruction: "基于当前章节和设定集，给出 3 条可公平回收的伏笔。" }} onFinish={(values) => suggestMutation.mutate(values)}><Form.Item name="instruction" label="生成要求"><Input.TextArea rows={3} /></Form.Item></Form>
        <List dataSource={suggestions} renderItem={(item) => <List.Item actions={[<Button key="use" type="link" onClick={() => studioApi.createForeshadowing(projectId, { ...item, chapter_id: selectedChapter?.id, planted_chapter_id: selectedChapter?.id, payoff_status: "planted" }).then(() => { message.success("建议已写入伏笔表"); setSuggestOpen(false); invalidateWorkbench(); })}>写入伏笔表</Button>]}><List.Item.Meta title={item.content} description={item.planned_payoff} /></List.Item>} />
      </Modal>
    </div>
  );
}
