import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Checkbox, Divider, Drawer, Empty, Form, Input, InputNumber, Select, Space, Steps, Tag, Typography, message } from "antd";
import { Check, Edit3, RefreshCw, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { studioApi } from "../api/studio";
import type { CreationSession, CreationStarBasicInfo, CreationStarCard } from "../types/api";

const stepItems = [
  { title: "基本信息" },
  { title: "世界观抽卡" },
  { title: "主角人设" },
  { title: "标题与卖点" },
  { title: "立项种子" },
  { title: "核心与宪法" },
  { title: "压力测试" },
  { title: "正典预览" },
  { title: "完成创建" },
];

const titleStepTrace = 'step: "title"';
const DRAW_BATCH_SIZE = 3;
const CANON_APPROVAL_OPTIONS = [
  { label: "作品信息", value: "project" },
  { label: "Story Bible", value: "story_bible" },
  { label: "角色候选", value: "characters" },
  { label: "实体候选", value: "entities" },
  { label: "世界事实", value: "world_facts" },
  { label: "图谱关系", value: "graph" },
];
const REQUIRED_CANON_APPROVAL_SECTIONS = CANON_APPROVAL_OPTIONS.map((item) => item.value);

interface CreationStarWizardProps {
  projectId: string;
  open: boolean;
  onClose: () => void;
  onCommitted: () => void;
}

function text(value: unknown) {
  return typeof value === "string" ? value : Array.isArray(value) ? value.join("、") : value ? String(value) : "";
}

function list(value: unknown) {
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean);
  if (typeof value === "string") return value.split(/[\n,，、；;]/).map((item) => item.trim()).filter(Boolean);
  return [];
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function recordList<T extends Record<string, unknown>>(value: unknown): T[] {
  return Array.isArray(value) ? value.filter((item): item is T => Boolean(item) && typeof item === "object" && !Array.isArray(item)) : [];
}

function selectedById<T extends { id?: string }>(items: T[], id: string) {
  return items.find((item) => item.id === id) ?? items[0];
}

function renderKeyValues(payload: Record<string, unknown>, empty = "暂无内容") {
  const entries = Object.entries(payload).filter(([, value]) => text(value));
  if (!entries.length) return <Typography.Text type="secondary">{empty}</Typography.Text>;
  return (
    <Space direction="vertical" size={6} className="full-width">
      {entries.map(([key, value]) => (
        <Typography.Paragraph key={key} className="compact-paragraph">
          <strong>{key}：</strong>{text(value)}
        </Typography.Paragraph>
      ))}
    </Space>
  );
}

export function CreationStarWizard({ projectId, open, onClose, onCommitted }: CreationStarWizardProps) {
  const [form] = Form.useForm<CreationStarBasicInfo>();
  const [step, setStep] = useState(0);
  const [session, setSession] = useState<CreationSession | null>(null);
  const [manualInput, setManualInput] = useState("");
  const [basicInfo, setBasicInfo] = useState<CreationStarBasicInfo>({});
  const [worldviewCards, setWorldviewCards] = useState<CreationStarCard[]>([]);
  const [protagonistCards, setProtagonistCards] = useState<CreationStarCard[]>([]);
  const [titleCards, setTitleCards] = useState<CreationStarCard[]>([]);
  const [marketCards, setMarketCards] = useState<Array<Record<string, unknown>>>([]);
  const [customTitle, setCustomTitle] = useState("");
  const [customTitleDescription, setCustomTitleDescription] = useState("作者自定义书名，确认后直接写入作品标题。");
  const [promptSnapshots, setPromptSnapshots] = useState<Record<string, Record<string, unknown>>>({});
  const [selectedWorldviewId, setSelectedWorldviewId] = useState("");
  const [selectedProtagonistId, setSelectedProtagonistId] = useState("");
  const [selectedTitleId, setSelectedTitleId] = useState("");
  const [selectedMarketId, setSelectedMarketId] = useState("");
  const [projectSeed, setProjectSeed] = useState<Record<string, unknown>>({});
  const [coreConflict, setCoreConflict] = useState<Record<string, unknown>>({});
  const [novelConstitution, setNovelConstitution] = useState<Record<string, unknown>>({});
  const [constitutionReview, setConstitutionReview] = useState<Record<string, unknown>>({});
  const [canonCandidates, setCanonCandidates] = useState<Record<string, unknown>>({});
  const [approvedCanonSections, setApprovedCanonSections] = useState<string[]>([]);
  const [worldviewBatchLoading, setWorldviewBatchLoading] = useState(false);
  const [protagonistBatchLoading, setProtagonistBatchLoading] = useState(false);
  const [marketBatchLoading, setMarketBatchLoading] = useState(false);

  const optionsQuery = useQuery({
    queryKey: ["creation-star-options"],
    queryFn: () => studioApi.getCreationStarOptions(),
    enabled: open,
  });

  const selectedWorldview = useMemo(() => selectedById(worldviewCards, selectedWorldviewId), [selectedWorldviewId, worldviewCards]);
  const selectedProtagonist = useMemo(() => selectedById(protagonistCards, selectedProtagonistId), [selectedProtagonistId, protagonistCards]);
  const selectedMarket = useMemo(() => selectedById(marketCards, selectedMarketId), [marketCards, selectedMarketId]);
  const customTitleCard = useMemo<CreationStarCard | undefined>(() => {
    const title = customTitle.trim();
    if (!title) return undefined;
    return {
      id: "custom_title",
      title,
      description: customTitleDescription,
      tags: ["自定义书名"],
      selling_point: "完全采用作者手动输入，可覆盖抽卡标题并写入作品信息。",
      risk: "建议确认是否包含题材关键词、主角处境或核心爽点。",
      source: "manual",
    };
  }, [customTitle, customTitleDescription]);
  const selectedTitle = useMemo(
    () => (selectedTitleId === "custom_title" ? customTitleCard : selectedById(titleCards, selectedTitleId) ?? customTitleCard),
    [customTitleCard, selectedTitleId, titleCards],
  );

  const options = optionsQuery.data?.options;
  const sessionId = session?.id ?? "";
  const constitutionReviewStatus = text(constitutionReview.status);
  const constitutionBlockingIssues = list(constitutionReview.blocking_issues);
  const isConstitutionReady =
    ["passed", "passed_with_notes"].includes(constitutionReviewStatus) && constitutionBlockingIssues.length === 0;
  const isCanonApproved = REQUIRED_CANON_APPROVAL_SECTIONS.every((section) => approvedCanonSections.includes(section));

  const createSession = useMutation({
    mutationFn: (payload: CreationStarBasicInfo) => studioApi.createCreationSession(projectId, { basic_info: payload }),
    onSuccess: (result) => setSession(result.session),
    onError: (error) => message.error(error instanceof Error ? error.message : "创作 Star 会话创建失败"),
  });

  const loadWorldview = useMutation({
    mutationFn: ({ targetSessionId, replaceExisting = false }: { targetSessionId: string; replaceExisting?: boolean }) =>
      studioApi.generateCreationWorldview(projectId, targetSessionId, { count: 1, manual_input: manualInput, replace_existing: replaceExisting }),
    onSuccess: (result) => {
      const cards = result.cards ?? [];
      setSession(result.session);
      setWorldviewCards((current) => [...current, ...cards]);
      setSelectedWorldviewId((current) => current || cards[0]?.id || "");
      setPromptSnapshots((current) => ({ ...current, worldview: result.prompt_snapshot ?? {} }));
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "世界观抽卡失败"),
  });

  const loadProtagonist = useMutation({
    mutationFn: ({ targetSessionId, replaceExisting = false }: { targetSessionId: string; replaceExisting?: boolean }) =>
      studioApi.generateCreationProtagonist(projectId, targetSessionId, {
        count: 1,
        manual_input: manualInput,
        selected_worldview: selectedWorldview ?? {},
        replace_existing: replaceExisting,
      }),
    onSuccess: (result) => {
      const cards = result.cards ?? [];
      setSession(result.session);
      setProtagonistCards((current) => [...current, ...cards]);
      setSelectedProtagonistId((current) => current || cards[0]?.id || "");
      setPromptSnapshots((current) => ({ ...current, protagonist: result.prompt_snapshot ?? {} }));
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "主角抽卡失败"),
  });

  const loadMarketPosition = useMutation({
    mutationFn: ({ targetSessionId, replaceExisting = false }: { targetSessionId: string; replaceExisting?: boolean }) =>
      studioApi.generateCreationMarketPosition(projectId, targetSessionId, {
        count: 1,
        manual_input: manualInput,
        selected_worldview: selectedWorldview ?? {},
        selected_protagonist: selectedProtagonist ?? {},
        replace_existing: replaceExisting,
      }),
    onSuccess: (result) => {
      const titles = result.title_candidates ?? [];
      const markets = result.market_position_candidates ?? [];
      setSession(result.session);
      setTitleCards((current) => [...current, ...titles]);
      setMarketCards((current) => [...current, ...markets]);
      setSelectedTitleId((current) => current || titles[0]?.id || "");
      setSelectedMarketId((current) => current || String(markets[0]?.id || ""));
      setPromptSnapshots((current) => ({ ...current, title: result.prompt_snapshot ?? {} }));
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "标题卖点生成失败"),
  });

  const confirmSeed = useMutation({
    mutationFn: (targetSessionId: string) =>
      studioApi.confirmCreationSeed(projectId, targetSessionId, {
        selected_worldview: selectedWorldview ?? {},
        selected_protagonist: selectedProtagonist ?? {},
        selected_title: selectedTitle ?? {},
        market_position: selectedMarket ?? {},
        user_note: "确认创作 Star 立项种子",
      }),
    onSuccess: (result) => {
      setSession(result.session);
      setProjectSeed(result.project_seed);
      setStep(5);
      message.success("立项种子已确认");
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "立项种子确认失败"),
  });

  const generateCoreConflict = useMutation({
    mutationFn: (targetSessionId: string) => studioApi.generateCreationCoreConflict(projectId, targetSessionId),
    onSuccess: (result) => {
      setSession(result.session);
      setCoreConflict(result.core_conflict_system);
    },
  });

  const generateConstitution = useMutation({
    mutationFn: (targetSessionId: string) => studioApi.generateCreationConstitution(projectId, targetSessionId),
    onSuccess: (result) => {
      setSession(result.session);
      setNovelConstitution(result.novel_constitution);
    },
  });

  const reviewConstitution = useMutation({
    mutationFn: (targetSessionId: string) => studioApi.reviewCreationConstitution(projectId, targetSessionId),
    onSuccess: (result) => {
      setSession(result.session);
      setConstitutionReview(result.constitution_review);
    },
  });

  const previewCanon = useMutation({
    mutationFn: (targetSessionId: string) => studioApi.previewCreationCanon(projectId, targetSessionId),
    onSuccess: (result) => {
      setSession(result.session);
      setCanonCandidates(result.canon_candidates);
      setApprovedCanonSections([]);
      message.success("正典候选已生成");
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "正典预览生成失败"),
  });

  const commit = useMutation({
    mutationFn: (targetSessionId: string) =>
      studioApi.commitCreationSession(projectId, targetSessionId, {
        user_note: "解耦创作 Star 确认入库",
        approved_canon_sections: approvedCanonSections,
      }),
    onSuccess: () => {
      message.success("创作 Star 已写入作品信息和设定集");
      onCommitted();
      onClose();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "创作 Star 提交失败"),
  });

  const resetGeneratedState = () => {
    setWorldviewCards([]);
    setProtagonistCards([]);
    setTitleCards([]);
    setMarketCards([]);
    setSelectedWorldviewId("");
    setSelectedProtagonistId("");
    setSelectedTitleId("");
    setSelectedMarketId("");
    setProjectSeed({});
    setCoreConflict({});
    setNovelConstitution({});
    setConstitutionReview({});
    setCanonCandidates({});
    setPromptSnapshots({});
    setApprovedCanonSections([]);
  };

  const resetAfterWorldviewRefresh = () => {
    setProtagonistCards([]);
    setTitleCards([]);
    setMarketCards([]);
    setSelectedProtagonistId("");
    setSelectedTitleId("");
    setSelectedMarketId("");
    setProjectSeed({});
    setCoreConflict({});
    setNovelConstitution({});
    setConstitutionReview({});
    setCanonCandidates({});
    setApprovedCanonSections([]);
  };

  const resetAfterProtagonistRefresh = () => {
    setTitleCards([]);
    setMarketCards([]);
    setSelectedTitleId("");
    setSelectedMarketId("");
    setProjectSeed({});
    setCoreConflict({});
    setNovelConstitution({});
    setConstitutionReview({});
    setCanonCandidates({});
    setApprovedCanonSections([]);
  };

  const resetAfterMarketRefresh = () => {
    setProjectSeed({});
    setCoreConflict({});
    setNovelConstitution({});
    setConstitutionReview({});
    setCanonCandidates({});
    setApprovedCanonSections([]);
  };

  const loadWorldviewBatch = async (targetSessionId: string, replace = false) => {
    if (!targetSessionId || worldviewBatchLoading) return;
    if (replace) {
      setWorldviewCards([]);
      setSelectedWorldviewId("");
      resetAfterWorldviewRefresh();
    }
    setWorldviewBatchLoading(true);
    try {
      for (let index = 0; index < DRAW_BATCH_SIZE; index += 1) {
        await loadWorldview.mutateAsync({ targetSessionId, replaceExisting: replace && index === 0 });
      }
      message.success(replace ? "已刷新 3 张世界观卡" : "已加载 3 张世界观卡");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "世界观批量抽卡失败");
    } finally {
      setWorldviewBatchLoading(false);
    }
  };

  const loadProtagonistBatch = async (targetSessionId: string, replace = false) => {
    if (!targetSessionId || protagonistBatchLoading) return;
    if (!selectedWorldview) {
      message.warning("请先加载并选择世界观卡片");
      return;
    }
    if (replace) {
      setProtagonistCards([]);
      setSelectedProtagonistId("");
      resetAfterProtagonistRefresh();
    }
    setProtagonistBatchLoading(true);
    try {
      for (let index = 0; index < DRAW_BATCH_SIZE; index += 1) {
        await loadProtagonist.mutateAsync({ targetSessionId, replaceExisting: replace && index === 0 });
      }
      message.success(replace ? "已刷新 3 张主角卡" : "已加载 3 张主角卡");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "主角批量抽卡失败");
    } finally {
      setProtagonistBatchLoading(false);
    }
  };

  const loadMarketPositionBatch = async (targetSessionId: string, replace = false) => {
    if (!targetSessionId || marketBatchLoading) return;
    if (!selectedProtagonist) {
      message.warning("请先加载并选择主角卡片");
      return;
    }
    if (replace) {
      setTitleCards([]);
      setMarketCards([]);
      setSelectedTitleId("");
      setSelectedMarketId("");
      resetAfterMarketRefresh();
    }
    setMarketBatchLoading(true);
    try {
      for (let index = 0; index < DRAW_BATCH_SIZE; index += 1) {
        await loadMarketPosition.mutateAsync({ targetSessionId, replaceExisting: replace && index === 0 });
      }
      message.success(replace ? "已刷新 3 个标题与卖点方向" : "已加载 3 个标题与卖点方向");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "标题卖点批量生成失败");
    } finally {
      setMarketBatchLoading(false);
    }
  };

  const startWorldview = async () => {
    const values = await form.validateFields();
    resetGeneratedState();
    setBasicInfo(values);
    const result = await createSession.mutateAsync(values);
    setStep(1);
    await loadWorldviewBatch(result.session.id);
  };

  const enterProtagonist = async () => {
    if (!sessionId || !selectedWorldview) {
      message.warning("请先加载并选择世界观卡片");
      return;
    }
    setStep(2);
    if (!protagonistCards.length) await loadProtagonistBatch(sessionId);
  };

  const enterMarketPosition = async () => {
    if (!sessionId || !selectedProtagonist) {
      message.warning("请先加载并选择主角卡片");
      return;
    }
    setStep(3);
    if (!titleCards.length) await loadMarketPositionBatch(sessionId);
  };

  const enterSeed = () => {
    if (!selectedTitle?.title) {
      message.warning("请先选择或填写一个书名");
      return;
    }
    setStep(4);
  };

  const runCoreConstitutionLane = async () => {
    if (!sessionId) return;
    try {
      const conflict = await generateCoreConflict.mutateAsync(sessionId);
      await generateConstitution.mutateAsync(conflict.session.id);
      setConstitutionReview({});
      setCanonCandidates({});
      message.success("核心矛盾与小说宪法已生成");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "小说宪法生成失败");
    }
  };

  const runConstitutionReview = async () => {
    if (!sessionId) return;
    try {
      const result = await reviewConstitution.mutateAsync(sessionId);
      const status = text(result.constitution_review.status);
      if (["passed", "passed_with_notes"].includes(status)) {
        message.success("小说宪法压力测试已通过");
      } else {
        message.warning("压力测试发现问题，请先修订小说宪法");
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "压力测试生成失败");
    }
  };

  const updateWorldview = (index: number, patch: Partial<CreationStarCard>) => {
    setWorldviewCards((cards) => cards.map((card, itemIndex) => (itemIndex === index ? { ...card, ...patch } : card)));
  };

  const updateProtagonist = (index: number, patch: Partial<CreationStarCard>) => {
    setProtagonistCards((cards) => cards.map((card, itemIndex) => (itemIndex === index ? { ...card, ...patch } : card)));
  };

  const updateTitle = (index: number, patch: Partial<CreationStarCard>) => {
    setTitleCards((cards) => cards.map((card, itemIndex) => (itemIndex === index ? { ...card, ...patch } : card)));
  };

  const updateMarket = (index: number, patch: Record<string, unknown>) => {
    setMarketCards((cards) => cards.map((card, itemIndex) => (itemIndex === index ? { ...card, ...patch } : card)));
  };

  const useCustomTitle = () => {
    if (!customTitle.trim()) {
      message.warning("请先填写自定义书名");
      return;
    }
    setSelectedTitleId("custom_title");
    message.success("已选择自定义书名");
  };

  const renderPromptSnapshot = (key: string) => {
    const promptSnapshot = promptSnapshots[key];
    if (!promptSnapshot) return null;
    return (
      <Alert
        type="success"
        showIcon
        className="creation-star-context-alert"
        message="本轮生成已读取前序上下文"
        description={text(promptSnapshot.context_summary).slice(0, 220)}
      />
    );
  };

  const renderBasicInfo = () => (
    <div className="creation-star-step">
      <Alert type="info" showIcon message="先建立创作会话，每次生成三张世界观、主角和标题卖点卡；单张完成即显示。正式设定会在小说宪法通过后写入。" />
      <Form
        form={form}
        layout="vertical"
        initialValues={{ channel: "男频", genre: "都市", target_words: 1000000, style: "热血爽快" }}
      >
        <div className="creation-star-form-grid">
          <Form.Item name="channel" label="频道" rules={[{ required: true, message: "请选择频道" }]}>
            <Select options={(options?.channels ?? []).map((value) => ({ value, label: value }))} loading={optionsQuery.isLoading} />
          </Form.Item>
          <Form.Item name="genre" label="类型" rules={[{ required: true, message: "请选择类型" }]}>
            <Select options={(options?.genres ?? []).map((value) => ({ value, label: value }))} showSearch />
          </Form.Item>
          <Form.Item name="subgenres" label="细分类型">
            <Select mode="tags" options={(options?.subgenres ?? []).map((value) => ({ value, label: value }))} />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="multiple" options={(options?.tags ?? []).map((value) => ({ value, label: value }))} />
          </Form.Item>
          <Form.Item name="manual_tags" label="手动输入标签">
            <Select mode="tags" placeholder="例如：武道高考、宗门财团、反套路升级" />
          </Form.Item>
          <Form.Item name="target_words" label="目标字数">
            <InputNumber min={30000} max={5000000} step={100000} className="full-width" />
          </Form.Item>
        </div>
        <Form.Item name="target_reader" label="目标读者体验">
          <Input placeholder="填写，例如爽感、压迫感、宿命感、成长感、权谋感、情感拉扯、史诗感" />
        </Form.Item>
        <Form.Item name="style" label="叙事风格">
          <Select mode="tags" options={(options?.styles ?? []).map((value) => ({ value, label: value }))} />
        </Form.Item>
        <Form.Item name="initial_idea" label="初始想法">
          <Input.TextArea rows={4} placeholder="写下你已有的脑洞，Agent 会把它揉进抽卡结果。" />
        </Form.Item>
      </Form>
      <Input.TextArea rows={3} value={manualInput} onChange={(event) => setManualInput(event.target.value)} placeholder="额外约束，可留空。例如：想要现代都市、宗门、武道高考、财阀压迫。" />
      <Divider />
      <Typography.Text type="secondary">标签来源参考：{(options?.sources ?? []).map((source) => source.name).join("、") || "加载中"}</Typography.Text>
    </div>
  );

  const renderWorldviews = () => (
    <div className="creation-star-step">
      <div className="creation-star-action-row">
        <Typography.Text strong>世界观抽卡每次三张，完成一张显示一张</Typography.Text>
        <Space wrap>
          <Button icon={<Sparkles size={15} />} loading={worldviewBatchLoading || loadWorldview.isPending} disabled={!sessionId || worldviewBatchLoading} onClick={() => sessionId && loadWorldviewBatch(sessionId)}>加载三张世界观</Button>
          <Button icon={<RefreshCw size={15} />} loading={worldviewBatchLoading || loadWorldview.isPending} disabled={!sessionId || !worldviewCards.length || worldviewBatchLoading} onClick={() => sessionId && loadWorldviewBatch(sessionId, true)}>刷新三张世界观</Button>
        </Space>
      </div>
      {renderPromptSnapshot("worldview")}
      {worldviewCards.length === 0 ? <Empty description="还没有世界观卡片" /> : (
        <div className="creation-card-grid">
          {worldviewCards.map((card, index) => (
            <Card
              key={card.id}
              className={`creation-card ${card.id === selectedWorldview?.id ? "is-selected" : ""}`}
              onClick={() => setSelectedWorldviewId(card.id)}
              title={<Input value={card.title} onChange={(event) => updateWorldview(index, { title: event.target.value })} onClick={(event) => event.stopPropagation()} />}
              extra={<Tag color={card.id === selectedWorldview?.id ? "green" : "default"}>{card.id === selectedWorldview?.id ? "已选" : "可选"}</Tag>}
            >
              <Input.TextArea value={card.description} rows={4} onChange={(event) => updateWorldview(index, { description: event.target.value })} onClick={(event) => event.stopPropagation()} />
              <Space wrap className="creation-card-tags">{(card.tags ?? []).map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space>
              {list(card.genre_mix).length ? <Typography.Paragraph type="secondary">题材组合：{list(card.genre_mix).join(" / ")}</Typography.Paragraph> : null}
              {card.core_rule ? <Typography.Paragraph><strong>核心规则：</strong>{card.core_rule}</Typography.Paragraph> : null}
              {card.social_pressure ? <Typography.Paragraph><strong>社会压力：</strong>{card.social_pressure}</Typography.Paragraph> : null}
              {card.power_or_resource_system ? <Typography.Paragraph><strong>资源系统：</strong>{card.power_or_resource_system}</Typography.Paragraph> : null}
              {card.protagonist_entry ? <Typography.Paragraph><strong>主角入口：</strong>{card.protagonist_entry}</Typography.Paragraph> : null}
              {card.long_form_potential ? <Typography.Paragraph><strong>长篇潜力：</strong>{card.long_form_potential}</Typography.Paragraph> : null}
              {list(card.reader_hooks).length ? <Typography.Paragraph><strong>读者钩子：</strong>{list(card.reader_hooks).join("；")}</Typography.Paragraph> : null}
              <Typography.Paragraph type="secondary">卖点：{card.selling_point}</Typography.Paragraph>
              {card.revision_hint ? <Typography.Paragraph type="secondary">修改方向：{card.revision_hint}</Typography.Paragraph> : null}
              <Typography.Paragraph type="secondary">风险：{card.risk}</Typography.Paragraph>
            </Card>
          ))}
        </div>
      )}
    </div>
  );

  const renderProtagonists = () => (
    <div className="creation-star-step">
      <div className="creation-star-action-row">
        <Typography.Text strong>主角人设每次三张，完成一张显示一张</Typography.Text>
        <Space wrap>
          <Button icon={<Sparkles size={15} />} loading={protagonistBatchLoading || loadProtagonist.isPending} disabled={!sessionId || protagonistBatchLoading} onClick={() => sessionId && loadProtagonistBatch(sessionId)}>加载三张主角</Button>
          <Button icon={<RefreshCw size={15} />} loading={protagonistBatchLoading || loadProtagonist.isPending} disabled={!sessionId || !protagonistCards.length || protagonistBatchLoading} onClick={() => sessionId && loadProtagonistBatch(sessionId, true)}>刷新三张主角</Button>
        </Space>
      </div>
      {renderPromptSnapshot("protagonist")}
      {protagonistCards.length === 0 ? <Empty description="还没有主角人设卡片" /> : (
        <div className="creation-card-grid protagonist-grid">
          {protagonistCards.map((card, index) => (
            <Card
              key={card.id}
              className={`creation-card ${card.id === selectedProtagonist?.id ? "is-selected" : ""}`}
              onClick={() => setSelectedProtagonistId(card.id)}
              title={<Input value={card.name} onChange={(event) => updateProtagonist(index, { name: event.target.value })} onClick={(event) => event.stopPropagation()} />}
              extra={<Edit3 size={15} />}
            >
              <Input value={card.identity} onChange={(event) => updateProtagonist(index, { identity: event.target.value })} onClick={(event) => event.stopPropagation()} />
              <Divider />
              <Typography.Paragraph><strong>长期目标：</strong>{card.long_term_goal}</Typography.Paragraph>
              <Typography.Paragraph><strong>伤口：</strong>{card.inner_wound}</Typography.Paragraph>
              <Typography.Paragraph><strong>能力：</strong>{card.ability}</Typography.Paragraph>
              <Typography.Paragraph><strong>弱点：</strong>{card.weakness}</Typography.Paragraph>
              <Typography.Paragraph><strong>成长弧：</strong>{card.character_arc}</Typography.Paragraph>
              <Space wrap>{(card.tags ?? []).map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space>
            </Card>
          ))}
        </div>
      )}
    </div>
  );

  const renderMarketPosition = () => (
    <div className="creation-star-step">
      <div className="creation-star-action-row">
        <Typography.Text strong>标题与卖点方向每次三个，完成一个显示一个</Typography.Text>
        <Space wrap>
          <Button icon={<Sparkles size={15} />} loading={marketBatchLoading || loadMarketPosition.isPending} disabled={!sessionId || marketBatchLoading} onClick={() => sessionId && loadMarketPositionBatch(sessionId)}>加载三个方向</Button>
          <Button icon={<RefreshCw size={15} />} loading={marketBatchLoading || loadMarketPosition.isPending} disabled={!sessionId || !titleCards.length || marketBatchLoading} onClick={() => sessionId && loadMarketPositionBatch(sessionId, true)}>刷新三个方向</Button>
        </Space>
      </div>
      {renderPromptSnapshot("title")}
      <Card
        className={`creation-card custom-title-card ${selectedTitleId === "custom_title" ? "is-selected" : ""}`}
        title="自定义书名"
        extra={<Tag color={selectedTitleId === "custom_title" ? "green" : "default"}>{selectedTitleId === "custom_title" ? "已选" : "手写"}</Tag>}
      >
        <Input value={customTitle} onChange={(event) => setCustomTitle(event.target.value)} placeholder="直接输入最终书名" />
        <Input.TextArea rows={2} value={customTitleDescription} onChange={(event) => setCustomTitleDescription(event.target.value)} />
        <Button type="primary" ghost onClick={useCustomTitle}>使用自定义书名</Button>
      </Card>
      {titleCards.length === 0 ? <Empty description="还没有标题卖点卡" /> : (
        <div className="creation-card-grid title-grid">
          {titleCards.map((card, index) => (
            <Card
              key={card.id}
              className={`creation-card ${card.id === selectedTitle?.id ? "is-selected" : ""}`}
              onClick={() => setSelectedTitleId(card.id)}
              title={<Input value={card.title} onChange={(event) => updateTitle(index, { title: event.target.value })} onClick={(event) => event.stopPropagation()} />}
              extra={<Tag color={card.id === selectedTitle?.id ? "green" : "default"}>{card.id === selectedTitle?.id ? "已选" : "可选"}</Tag>}
            >
              <Input.TextArea value={card.description} rows={3} onChange={(event) => updateTitle(index, { description: event.target.value })} onClick={(event) => event.stopPropagation()} />
              <Space wrap className="creation-card-tags">{(card.tags ?? []).map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space>
              <Typography.Paragraph type="secondary">卖点：{card.selling_point}</Typography.Paragraph>
              <Typography.Paragraph type="secondary">风险：{card.risk}</Typography.Paragraph>
            </Card>
          ))}
        </div>
      )}
      {marketCards.length ? (
        <>
          <Divider />
          <div className="creation-card-grid title-grid">
            {marketCards.map((card, index) => (
              <Card
                key={String(card.id)}
                className={`creation-card ${card.id === selectedMarket?.id ? "is-selected" : ""}`}
                onClick={() => setSelectedMarketId(String(card.id))}
                title={<Input value={text(card.title)} onChange={(event) => updateMarket(index, { title: event.target.value })} onClick={(event) => event.stopPropagation()} />}
                extra={<Tag color={card.id === selectedMarket?.id ? "green" : "default"}>{card.id === selectedMarket?.id ? "已选" : "卖点"}</Tag>}
              >
                {renderKeyValues(card)}
              </Card>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );

  const renderSeed = () => (
    <div className="creation-star-step">
      <Alert type="info" showIcon message="从这里开始，系统会把候选卡收敛成一个确定的立项种子。" />
      <div className="creation-star-two-columns">
        <Card title="已选世界观"><Typography.Title level={4}>{selectedWorldview?.title}</Typography.Title><Typography.Paragraph>{selectedWorldview?.description}</Typography.Paragraph></Card>
        <Card title="已选主角"><Typography.Title level={4}>{selectedProtagonist?.name}</Typography.Title><Typography.Paragraph>{selectedProtagonist?.summary}</Typography.Paragraph></Card>
      </div>
      <Divider />
      <div className="creation-star-two-columns">
        <Card title="已选书名"><Typography.Title level={4}>{selectedTitle?.title}</Typography.Title><Typography.Paragraph>{selectedTitle?.description}</Typography.Paragraph></Card>
        <Card title="市场定位">{renderKeyValues(selectedMarket ?? {})}</Card>
      </div>
      {Object.keys(projectSeed).length ? <Alert type="success" showIcon message="立项种子已确认" /> : null}
    </div>
  );

  const renderConstitution = () => (
    <div className="creation-star-step">
      <Alert type="warning" showIcon message="先把立项种子收敛为核心矛盾系统和小说宪法；压力测试将在下一步单独执行。" />
      <div className="creation-star-action-row">
        <Typography.Text strong>核心与宪法</Typography.Text>
        <Button icon={<RefreshCw size={15} />} loading={generateCoreConflict.isPending || generateConstitution.isPending} onClick={runCoreConstitutionLane}>生成/刷新核心与宪法</Button>
      </div>
      <div className="creation-star-two-columns">
        <Card title="核心矛盾系统">{renderKeyValues(coreConflict)}</Card>
        <Card title="小说宪法摘要">{renderKeyValues(novelConstitution)}</Card>
      </div>
      <Divider />
      <Card title="小说宪法">{renderKeyValues(novelConstitution)}</Card>
    </div>
  );

  const renderConstitutionReview = () => (
    <div className="creation-star-step">
      <Alert
        type={isConstitutionReady ? "success" : constitutionReviewStatus ? "warning" : "info"}
        showIcon
        message={isConstitutionReady ? "压力测试已通过，可以进入正典预览。" : "压力测试必须通过后，才能进入正典预览和最终入库。"}
      />
      <div className="creation-star-action-row">
        <Typography.Text strong>小说宪法压力测试</Typography.Text>
        <Button icon={<RefreshCw size={15} />} loading={reviewConstitution.isPending} disabled={!Object.keys(novelConstitution).length} onClick={runConstitutionReview}>生成压力测试</Button>
      </div>
      {constitutionReviewStatus === "needs_revision" || constitutionReviewStatus === "blocked" ? (
        <Alert
          type="error"
          showIcon
          message="质量门未通过"
          description={constitutionBlockingIssues.join("；") || text(constitutionReview.largest_risk) || "请根据修订建议重新生成核心与宪法。"}
        />
      ) : null}
      <Card title="压力测试报告">{renderKeyValues(constitutionReview, "请先生成压力测试")}</Card>
    </div>
  );

  const renderCanonPreview = () => {
    const storyBible = record(canonCandidates.story_bible_candidate);
    const characters = recordList<Record<string, unknown>>(canonCandidates.character_candidates);
    const entities = recordList<Record<string, unknown>>(canonCandidates.entity_candidates);
    const facts = recordList<Record<string, unknown>>(canonCandidates.world_fact_candidates);
    const graphEdges = recordList<Record<string, unknown>>(canonCandidates.graph_candidate_edges);
    return (
      <div className="creation-star-step">
        <Alert type="info" showIcon message="这里仍是候选正典。点击最终提交前，不会写入正式设定集。" />
        <div className="creation-star-action-row">
          <Typography.Text strong>正典候选映射</Typography.Text>
          <Button icon={<RefreshCw size={15} />} loading={previewCanon.isPending} disabled={!isConstitutionReady} onClick={() => sessionId && previewCanon.mutate(sessionId)}>生成正典预览</Button>
        </div>
        <Card
          title="正典审批项"
          extra={<Button size="small" onClick={() => setApprovedCanonSections(REQUIRED_CANON_APPROVAL_SECTIONS)}>全部确认</Button>}
        >
          <Checkbox.Group value={approvedCanonSections} onChange={(values) => setApprovedCanonSections(values.map(String))}>
            <Space wrap>
              {CANON_APPROVAL_OPTIONS.map((item) => (
                <Checkbox key={item.value} value={item.value}>{item.label}</Checkbox>
              ))}
            </Space>
          </Checkbox.Group>
        </Card>
        <Divider />
        <Card title="Story Bible 候选">{renderKeyValues(storyBible)}</Card>
        <Divider />
        <div className="creation-star-two-columns">
          <Card title="角色候选">{characters.length ? characters.map((item) => <Typography.Paragraph key={text(item.name)}>{renderKeyValues(item)}</Typography.Paragraph>) : <Empty description="暂无角色候选" />}</Card>
          <Card title="世界事实候选">{facts.length ? facts.map((item) => <Typography.Paragraph key={text(item.title)}>{renderKeyValues(item)}</Typography.Paragraph>) : <Empty description="暂无世界事实候选" />}</Card>
        </div>
        <Divider />
        <div className="creation-star-two-columns">
          <Card title="实体候选">{entities.length ? entities.map((item) => <Typography.Paragraph key={text(item.name)}>{renderKeyValues(item)}</Typography.Paragraph>) : <Empty description="暂无实体候选" />}</Card>
          <Card title="图谱关系候选">{graphEdges.length ? graphEdges.map((item) => <Typography.Paragraph key={`${text(item.source)}-${text(item.target)}`}>{renderKeyValues(item)}</Typography.Paragraph>) : <Empty description="暂无图谱关系候选" />}</Card>
        </div>
      </div>
    );
  };

  const renderFinish = () => (
    <div className="creation-star-step">
      <Alert type={isCanonApproved ? "warning" : "error"} showIcon message={isCanonApproved ? "提交后会更新作品信息、故事圣经、角色、实体、世界事实和图谱，并创建版本快照。" : "请先在正典预览中勾选全部审批项。"} />
      <div className="creation-star-two-columns">
        <Card title="最终书名"><Typography.Title level={4}>{selectedTitle?.title}</Typography.Title></Card>
        <Card title="会话状态">{renderKeyValues({ session_id: session?.id, current_step: session?.current_step, status: session?.status })}</Card>
      </div>
      <Divider />
      <Card title="即将写入的正典">{renderKeyValues(record(canonCandidates.story_bible_candidate), "请先生成正典预览")}</Card>
    </div>
  );

  const renderStep = () => {
    if (step === 0) return renderBasicInfo();
    if (step === 1) return renderWorldviews();
    if (step === 2) return renderProtagonists();
    if (step === 3) return renderMarketPosition();
    if (step === 4) return renderSeed();
    if (step === 5) return renderConstitution();
    if (step === 6) return renderConstitutionReview();
    if (step === 7) return renderCanonPreview();
    return renderFinish();
  };

  const footer = (
    <Space className="creation-star-footer">
      <Button onClick={step === 0 ? onClose : () => setStep(step - 1)}>{step === 0 ? "关闭" : "上一步"}</Button>
      {step === 0 ? <Button type="primary" icon={<Sparkles size={15} />} loading={createSession.isPending || worldviewBatchLoading || loadWorldview.isPending} onClick={startWorldview}>创建会话并加载世界观</Button> : null}
      {step === 1 ? <Button type="primary" disabled={!selectedWorldview} loading={protagonistBatchLoading || loadProtagonist.isPending} onClick={enterProtagonist}>进入主角抽卡</Button> : null}
      {step === 2 ? <Button type="primary" disabled={!selectedProtagonist} loading={marketBatchLoading || loadMarketPosition.isPending} onClick={enterMarketPosition}>进入标题卖点</Button> : null}
      {step === 3 ? <Button type="primary" disabled={!selectedTitle?.title} onClick={enterSeed}>进入立项种子</Button> : null}
      {step === 4 ? <Button type="primary" loading={confirmSeed.isPending} onClick={() => sessionId && confirmSeed.mutate(sessionId)}>确认立项种子</Button> : null}
      {step === 5 ? <Button type="primary" disabled={!Object.keys(novelConstitution).length} onClick={() => setStep(6)}>进入压力测试</Button> : null}
      {step === 6 ? <Button type="primary" disabled={!isConstitutionReady} onClick={() => setStep(7)}>进入正典预览</Button> : null}
      {step === 7 ? <Button type="primary" disabled={!Object.keys(canonCandidates).length || !isCanonApproved} onClick={() => setStep(8)}>进入最终确认</Button> : null}
      {step === 8 ? <Button type="primary" icon={<Check size={15} />} loading={commit.isPending} disabled={!sessionId || !Object.keys(canonCandidates).length || !isCanonApproved} onClick={() => sessionId && commit.mutate(sessionId)}>完成创建并写入设定</Button> : null}
    </Space>
  );

  return (
    <Drawer
      title="创作 Star"
      width="92vw"
      open={open}
      onClose={onClose}
      extra={<Tag color="purple" title={titleStepTrace}>解耦创作 Star</Tag>}
      footer={footer}
      rootClassName="creation-star-drawer-root"
      className="creation-star-drawer"
      destroyOnClose={false}
    >
      <Steps current={step} items={stepItems} />
      <Divider />
      {optionsQuery.error ? <Alert type="error" showIcon message="无法加载抽卡选项" description="请确认后端服务是否可用。" /> : renderStep()}
    </Drawer>
  );
}
