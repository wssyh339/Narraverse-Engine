import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Checkbox, Divider, Drawer, Empty, Form, Input, Select, Space, Steps, Tag, Typography, message } from "antd";
import { Check, Edit3, RefreshCw, Sparkles } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { studioApi } from "../api/studio";
import type { CreationBasicSuggestion, CreationSession, CreationStarBasicInfo, CreationStarCard } from "../types/api";

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
const TARGET_READER_PRESETS = [
  "喜欢强爽点、快节奏升级和明确反派压迫的读者",
  "偏爱脑洞设定、规则反转和高概念悬念的读者",
  "喜欢人物羁绊、情感拉扯和成长弧线的读者",
  "偏爱权谋博弈、势力经营和长线伏笔的读者",
  "喜欢轻松吐槽、日常反差和持续新鲜感的读者",
];
const MANUAL_TAG_PRESETS = ["武道高考", "宗门财团", "规则怪谈", "幕后经营", "家族复仇", "灵气复苏", "都市秘境", "群像升级"];
const BASIC_FLOW_REQUIREMENTS = [
  "世界观抽卡读取频道、类型、细分、标签、目标读者、风格和初始想法。",
  "主角人设读取基本信息与已选世界观，确保欲望、能力和伤口服务核心规则。",
  "标题卖点、核心矛盾、小说宪法和正典预览都会继续沿用这组创作种子。",
];
type CardKind = "worldview" | "protagonist";

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

function isGeneratedCard(card?: CreationStarCard) {
  return Boolean(card) && !card?.__streaming && !card?.__placeholder;
}

function selectedGeneratedById(items: CreationStarCard[], id: string) {
  const selected = items.find((item) => item.id === id && isGeneratedCard(item));
  return selected ?? items.find(isGeneratedCard);
}

function uniqueStrings(values: string[]) {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

function toSelectOptions(values: string[] | undefined) {
  return (values ?? []).map((value) => ({ value, label: value }));
}

function createCardSkeleton(kind: CardKind, index: number, replace = false): CreationStarCard {
  const id = `${kind}-streaming-${Date.now()}-${index}-${replace ? "refresh" : "append"}`;
  if (kind === "worldview") {
    return {
      id,
      title: "生成中",
      description: "已提前生成卡片框架，正在生成世界观内容。",
      tags: ["生成中"],
      genre_mix: [],
      one_sentence_pitch: "",
      core_world_rule: "",
      social_pressure: "",
      power_or_resource_system: "",
      conflict_engine_seed: "",
      protagonist_entry: "",
      long_form_potential: "",
      key_entities: [],
      rules_not_to_break: [],
      reader_hooks: [],
      selling_point: "",
      writing_risk: "",
      revision_hint: "",
      difference_from_previous_batch: "",
      __kind: kind,
      __placeholder: true,
      __streaming: true,
    };
  }
  return {
    id,
    name: "生成中",
    title: "生成中",
    identity: "",
    tags: ["生成中"],
    one_sentence_pitch: "",
    opening_situation: "",
    world_rule_connection: "",
    long_term_desire: "",
    immediate_goal: "",
    inner_wound: "",
    ability: "",
    ability_cost: "",
    weakness: "",
    secret: "",
    growth_arc: "",
    relationship_hooks: [],
    conflict_seed: "",
    reader_satisfaction: "",
    long_form_potential: "",
    writing_risk: "",
    revision_hint: "",
    __kind: kind,
    __placeholder: true,
    __streaming: true,
  };
}

function applyGeneratedCard(
  finalCard: CreationStarCard,
  applyPatch: (patch: Partial<CreationStarCard>) => void,
) {
  applyPatch({
    ...finalCard,
    __placeholder: false,
    __streaming: false,
  });
}

function renderEditableText(
  label: string,
  value: unknown,
  onChange: (value: string) => void,
  multiline = true,
  placeholder = "可编辑",
) {
  return (
    <Form.Item label={label} className="creation-card-field">
      {multiline ? (
        <Input.TextArea
          value={text(value)}
          autoSize={{ minRows: 2, maxRows: 6 }}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
          onClick={(event) => event.stopPropagation()}
        />
      ) : (
        <Input
          value={text(value)}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
          onClick={(event) => event.stopPropagation()}
        />
      )}
    </Form.Item>
  );
}

function renderEditableList(label: string, value: unknown, onChange: (value: string[]) => void) {
  return (
    <Form.Item label={label} className="creation-card-field">
      <Select
        mode="tags"
        value={list(value)}
        tokenSeparators={["，", ",", "、", "；", ";"]}
        placeholder="输入后回车添加"
        onChange={(values) => onChange(values)}
        onClick={(event) => event.stopPropagation()}
      />
    </Form.Item>
  );
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
  const [basicSuggestions, setBasicSuggestions] = useState<CreationBasicSuggestion[]>([]);
  const worldviewBatchTokenRef = useRef(0);
  const protagonistBatchTokenRef = useRef(0);

  const optionsQuery = useQuery({
    queryKey: ["creation-star-options"],
    queryFn: () => studioApi.getCreationStarOptions(),
    enabled: open,
  });

  const selectedWorldview = useMemo(() => selectedGeneratedById(worldviewCards, selectedWorldviewId), [selectedWorldviewId, worldviewCards]);
  const selectedProtagonist = useMemo(() => selectedGeneratedById(protagonistCards, selectedProtagonistId), [selectedProtagonistId, protagonistCards]);
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
  const channelOptions = toSelectOptions(options?.channels);
  const genreOptions = toSelectOptions(uniqueStrings([...(options?.genres ?? []), "都市", "玄幻", "科幻", "古言", "悬疑", "轻小说"]));
  const subgenreOptions = toSelectOptions(options?.subgenres);
  const tagOptions = toSelectOptions(options?.tags);
  const styleOptions = toSelectOptions(options?.styles);
  const manualTagOptions = toSelectOptions(uniqueStrings([...(options?.tags ?? []).slice(0, 12), ...MANUAL_TAG_PRESETS]));
  const targetReaderOptions = toSelectOptions(TARGET_READER_PRESETS);
  const targetWordBands = options?.target_word_bands ?? [];
  const targetWordOptions = targetWordBands.map((item) => ({ value: item.value, label: item.label }));

  const appendIdeaPreset = (value: string) => {
    const current = text(form.getFieldValue("initial_idea")).trim();
    form.setFieldValue("initial_idea", current ? `${current}\n${value}` : value);
  };

  const appendManualConstraint = (value: string) => {
    setManualInput((current) => (current.trim() ? `${current.trim()}；${value}` : value));
  };

  const applyBasicSuggestion = (suggestion: CreationBasicSuggestion) => {
    if (suggestion.target === "initial_idea") {
      appendIdeaPreset(suggestion.content);
      return;
    }
    appendManualConstraint(suggestion.content);
  };

  const renderBasicSuggestionGrid = () => {
    if (!basicSuggestions.length) {
      return (
        <div className="creation-star-ai-suggestion-empty">
          <Typography.Text type="secondary">点击“生成 AI 选项”后，这里会出现可应用到初始想法和额外约束的刷新建议。</Typography.Text>
        </div>
      );
    }
    return (
      <div className="creation-star-ai-suggestion-grid">
        {basicSuggestions.map((suggestion) => (
          <div key={suggestion.id} className="creation-star-ai-suggestion-card">
            <div className="creation-star-ai-suggestion-title">
              <Typography.Text strong>{suggestion.title}</Typography.Text>
              <Tag color={suggestion.target === "initial_idea" ? "green" : "blue"}>
                {suggestion.target === "initial_idea" ? "初始想法" : "额外约束"}
              </Tag>
            </div>
            <Typography.Paragraph>{suggestion.content}</Typography.Paragraph>
            {suggestion.reason ? <Typography.Paragraph type="secondary">{suggestion.reason}</Typography.Paragraph> : null}
            <Space wrap>
              {(suggestion.tags ?? []).map((tag) => <Tag key={tag}>{tag}</Tag>)}
            </Space>
            <Button size="small" type="primary" ghost onClick={() => applyBasicSuggestion(suggestion)}>
              {suggestion.target === "initial_idea" ? "应用到初始想法" : "应用到额外约束"}
            </Button>
          </div>
        ))}
      </div>
    );
  };

  const basicSuggestionMutation = useMutation({
    mutationFn: () =>
      studioApi.generateCreationBasicSuggestions(projectId, {
        basic_info: form.getFieldsValue(true),
        manual_input: manualInput,
        previous_suggestions: basicSuggestions,
        count: 6,
      }),
    onSuccess: (result) => {
      setBasicSuggestions(result.suggestions ?? []);
      setPromptSnapshots((current) => ({ ...current, basic_suggestions: result.prompt_snapshot ?? {} }));
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "AI 选项生成失败"),
  });

  const createSession = useMutation({
    mutationFn: (payload: CreationStarBasicInfo) => studioApi.createCreationSession(projectId, { basic_info: payload }),
    onSuccess: (result) => setSession(result.session),
    onError: (error) => message.error(error instanceof Error ? error.message : "创作 Star 会话创建失败"),
  });

  const loadWorldview = useMutation({
    mutationFn: ({ targetSessionId, replaceExisting = false }: { targetSessionId: string; replaceExisting?: boolean }) =>
      studioApi.generateCreationWorldview(projectId, targetSessionId, { count: 1, manual_input: manualInput, replace_existing: replaceExisting }),
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
    worldviewBatchTokenRef.current += 1;
    protagonistBatchTokenRef.current += 1;
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
    protagonistBatchTokenRef.current += 1;
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

  const patchWorldviewCard = (cardId: string, patch: Partial<CreationStarCard>) => {
    setWorldviewCards((cards) => cards.map((card) => (card.id === cardId ? { ...card, ...patch } : card)));
  };

  const patchProtagonistCard = (cardId: string, patch: Partial<CreationStarCard>) => {
    setProtagonistCards((cards) => cards.map((card) => (card.id === cardId ? { ...card, ...patch } : card)));
  };

  const removeWorldviewCard = (cardId: string) => {
    setWorldviewCards((cards) => cards.filter((card) => card.id !== cardId));
  };

  const removeProtagonistCard = (cardId: string) => {
    setProtagonistCards((cards) => cards.filter((card) => card.id !== cardId));
  };

  const stopWorldviewGeneration = () => {
    worldviewBatchTokenRef.current += 1;
    setWorldviewBatchLoading(false);
    setWorldviewCards((cards) => cards.filter((card) => !card.__streaming));
  };

  const stopProtagonistGeneration = () => {
    protagonistBatchTokenRef.current += 1;
    setProtagonistBatchLoading(false);
    setProtagonistCards((cards) => cards.filter((card) => !card.__streaming));
  };

  const loadWorldviewBatch = async (targetSessionId: string, replace = false) => {
    if (!targetSessionId || worldviewBatchLoading) return;
    const batchToken = worldviewBatchTokenRef.current + 1;
    worldviewBatchTokenRef.current = batchToken;
    if (replace) {
      setWorldviewCards([]);
      setSelectedWorldviewId("");
      resetAfterWorldviewRefresh();
    }
    setWorldviewBatchLoading(true);
    let completedCount = 0;
    try {
      for (let index = 0; index < DRAW_BATCH_SIZE; index += 1) {
        if (worldviewBatchTokenRef.current !== batchToken) break;
        const skeleton = createCardSkeleton("worldview", index, replace);
        setWorldviewCards((cards) => [...cards, skeleton]);
        const result = await loadWorldview.mutateAsync({ targetSessionId, replaceExisting: replace && index === 0 });
        if (worldviewBatchTokenRef.current !== batchToken) {
          removeWorldviewCard(skeleton.id);
          break;
        }
        setSession(result.session);
        setPromptSnapshots((current) => ({ ...current, worldview: result.prompt_snapshot ?? {} }));
        const card = result.cards?.[0];
        if (!card) {
          removeWorldviewCard(skeleton.id);
          continue;
        }
        applyGeneratedCard(card, (patch) => patchWorldviewCard(skeleton.id, patch));
        completedCount += 1;
        setSelectedWorldviewId((current) => current || card.id);
      }
      if (worldviewBatchTokenRef.current === batchToken && completedCount > 0) {
        message.success(replace ? `已刷新 ${completedCount} 张世界观卡` : `已加载 ${completedCount} 张世界观卡`);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "世界观批量抽卡失败");
    } finally {
      if (worldviewBatchTokenRef.current === batchToken) setWorldviewBatchLoading(false);
    }
  };

  const loadProtagonistBatch = async (targetSessionId: string, replace = false) => {
    if (!targetSessionId || protagonistBatchLoading) return;
    if (!selectedWorldview) {
      message.warning("请先加载并选择世界观卡片");
      return;
    }
    const batchToken = protagonistBatchTokenRef.current + 1;
    protagonistBatchTokenRef.current = batchToken;
    if (replace) {
      setProtagonistCards([]);
      setSelectedProtagonistId("");
      resetAfterProtagonistRefresh();
    }
    setProtagonistBatchLoading(true);
    let completedCount = 0;
    try {
      for (let index = 0; index < DRAW_BATCH_SIZE; index += 1) {
        if (protagonistBatchTokenRef.current !== batchToken) break;
        const skeleton = createCardSkeleton("protagonist", index, replace);
        setProtagonistCards((cards) => [...cards, skeleton]);
        const result = await loadProtagonist.mutateAsync({ targetSessionId, replaceExisting: replace && index === 0 });
        if (protagonistBatchTokenRef.current !== batchToken) {
          removeProtagonistCard(skeleton.id);
          break;
        }
        setSession(result.session);
        setPromptSnapshots((current) => ({ ...current, protagonist: result.prompt_snapshot ?? {} }));
        const card = result.cards?.[0];
        if (!card) {
          removeProtagonistCard(skeleton.id);
          continue;
        }
        applyGeneratedCard(card, (patch) => patchProtagonistCard(skeleton.id, patch));
        completedCount += 1;
        setSelectedProtagonistId((current) => current || card.id);
      }
      if (protagonistBatchTokenRef.current === batchToken && completedCount > 0) {
        message.success(replace ? `已刷新 ${completedCount} 张主角卡` : `已加载 ${completedCount} 张主角卡`);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "主角批量抽卡失败");
    } finally {
      if (protagonistBatchTokenRef.current === batchToken) setProtagonistBatchLoading(false);
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
    void loadWorldviewBatch(result.session.id);
  };

  const enterProtagonist = () => {
    if (!sessionId || !selectedWorldview) {
      message.warning("请先加载并选择世界观卡片");
      return;
    }
    stopWorldviewGeneration();
    setStep(2);
    if (!protagonistCards.some(isGeneratedCard)) void loadProtagonistBatch(sessionId);
  };

  const enterMarketPosition = () => {
    if (!sessionId || !selectedProtagonist) {
      message.warning("请先加载并选择主角卡片");
      return;
    }
    stopProtagonistGeneration();
    setStep(3);
    if (!titleCards.length) void loadMarketPositionBatch(sessionId);
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
    <div className="creation-star-step creation-star-brief-shell">
      <div className="creation-star-brief-header">
        <div>
          <Typography.Text type="secondary">创作种子</Typography.Text>
          <Typography.Title level={3}>先把后续流程需要的输入一次收齐</Typography.Title>
          <Typography.Paragraph>
            基本信息会进入世界观抽卡、主角人设、标题卖点、核心矛盾、小说宪法和正典预览。每个可选项都提供预设，也可以继续手动补充。
          </Typography.Paragraph>
        </div>
        <div className="creation-star-flow-checklist">
          <Typography.Text strong>后续流程读取</Typography.Text>
          {BASIC_FLOW_REQUIREMENTS.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      </div>
      <Alert type="info" showIcon message="先建立创作会话，每次生成三张世界观、主角和标题卖点卡；单张完成即显示。正式设定会在小说宪法通过后写入。" />
      <Form
        form={form}
        layout="vertical"
        initialValues={{ channel: "男频", genre: "都市", target_words: 1000000, style: "热血爽快" }}
      >
        <section className="creation-star-basic-section">
          <div className="creation-star-section-copy">
            <Typography.Text type="secondary">01 基本定位</Typography.Text>
            <Typography.Title level={4}>频道、类型和标签决定抽卡边界</Typography.Title>
            <Typography.Paragraph>这里的预设直接来自分类库，并会合并手动标签一起传给创作 Star。</Typography.Paragraph>
          </div>
          <div className="creation-star-form-grid">
            <Form.Item name="channel" label="频道" rules={[{ required: true, message: "请选择频道" }]}>
              <Select options={channelOptions} loading={optionsQuery.isLoading} placeholder="选择频道" />
            </Form.Item>
            <Form.Item name="genre" label="类型" rules={[{ required: true, message: "请选择类型" }]}>
              <Select options={genreOptions} showSearch optionFilterProp="label" placeholder="选择类型" />
            </Form.Item>
            <Form.Item name="subgenres" label="细分类型">
              <Select mode="tags" options={subgenreOptions} showSearch optionFilterProp="label" placeholder="选择或输入细分类型" />
            </Form.Item>
            <Form.Item name="tags" label="标签">
              <Select mode="tags" options={tagOptions} showSearch optionFilterProp="label" placeholder="选择爽点、结构或关系标签" />
            </Form.Item>
            <Form.Item name="manual_tags" label="手动输入标签">
              <Select mode="tags" options={manualTagOptions} showSearch optionFilterProp="label" placeholder="例如：武道高考、宗门财团、反套路升级" />
            </Form.Item>
          </div>
        </section>
        <section className="creation-star-basic-section">
          <div className="creation-star-section-copy">
            <Typography.Text type="secondary">02 读者与规模</Typography.Text>
            <Typography.Title level={4}>读者体验会约束爽点密度和长篇容量</Typography.Title>
            <Typography.Paragraph>目标字数决定后续卷纲和章节规划的空间，叙事风格会写入 story bible。</Typography.Paragraph>
          </div>
          <div className="creation-star-form-grid">
            <Form.Item name="target_reader" label="目标读者体验">
              <Select
                options={targetReaderOptions}
                showSearch
                optionFilterProp="label"
                placeholder="选择爽感、压迫感、宿命感、成长感、权谋感、情感拉扯、史诗感"
              />
            </Form.Item>
            <Form.Item name="target_words" label="目标字数">
              <Select options={targetWordOptions} placeholder="选择目标字数带" />
            </Form.Item>
            <Form.Item name="style" label="叙事风格">
              <Select options={styleOptions} showSearch optionFilterProp="label" placeholder="选择叙事风格" />
            </Form.Item>
          </div>
        </section>
        <section className="creation-star-basic-section">
          <div className="creation-star-section-copy">
            <Typography.Text type="secondary">03 初始想法与抽卡约束</Typography.Text>
            <Typography.Title level={4}>把脑洞和禁区提前交给 Agent</Typography.Title>
            <Typography.Paragraph>初始想法会进入基本信息，额外约束会随每轮抽卡传入，不会直接写入正式设定。</Typography.Paragraph>
            <Button
              icon={<Sparkles size={15} />}
              loading={basicSuggestionMutation.isPending}
              onClick={() => basicSuggestionMutation.mutate()}
            >
              {basicSuggestions.length ? "刷新 AI 选项" : "生成 AI 选项"}
            </Button>
          </div>
          <Form.Item name="initial_idea" label="初始想法">
            <Input.TextArea rows={5} placeholder="写下你已有的脑洞，Agent 会把它揉进抽卡结果。" />
          </Form.Item>
          <Form.Item label="额外自定义输入">
            <Input.TextArea rows={4} value={manualInput} onChange={(event) => setManualInput(event.target.value)} placeholder="额外约束，可留空。例如：想要现代都市、宗门、武道高考、财阀压迫。" />
          </Form.Item>
          {renderBasicSuggestionGrid()}
        </section>
      </Form>
      <Typography.Text type="secondary">标签来源参考：{(options?.sources ?? []).map((source) => source.name).join("、") || "加载中"}</Typography.Text>
    </div>
  );

  const renderWorldviews = () => (
    <div className="creation-star-step">
      <div className="creation-star-action-row">
        <div>
          <Typography.Text strong>世界观抽卡每次三张，完成一张即可选择并进入下一步</Typography.Text>
          <Typography.Paragraph type="secondary" className="compact-paragraph">卡片框架会提前出现，接口返回后一次填充完整内容；进入主角抽卡会自动中断后续世界观生成。</Typography.Paragraph>
        </div>
        <Space wrap>
          {worldviewBatchLoading ? <Button onClick={stopWorldviewGeneration}>中断后续世界观生成</Button> : null}
          <Button icon={<Sparkles size={15} />} loading={worldviewBatchLoading || loadWorldview.isPending} disabled={!sessionId || worldviewBatchLoading} onClick={() => sessionId && loadWorldviewBatch(sessionId)}>加载三张世界观</Button>
          <Button icon={<RefreshCw size={15} />} loading={worldviewBatchLoading || loadWorldview.isPending} disabled={!sessionId || !worldviewCards.length || worldviewBatchLoading} onClick={() => sessionId && loadWorldviewBatch(sessionId, true)}>刷新三张世界观</Button>
        </Space>
      </div>
      {renderPromptSnapshot("worldview")}
      {worldviewCards.length === 0 ? <Empty description="还没有世界观卡片" /> : (
        <div className="creation-card-grid">
          {worldviewCards.map((card, index) => {
            const isSelected = isGeneratedCard(card) && card.id === selectedWorldview?.id;
            const isStreaming = Boolean(card.__streaming);
            return (
              <Card
                key={card.id}
                className={`creation-card ${isSelected ? "is-selected" : ""} ${isStreaming ? "is-streaming" : ""}`}
                onClick={() => isGeneratedCard(card) && setSelectedWorldviewId(card.id)}
                title={<Input value={card.title} onChange={(event) => updateWorldview(index, { title: event.target.value })} onClick={(event) => event.stopPropagation()} />}
                extra={
                  <Space size={6}>
                    <Tag color={isSelected ? "green" : isStreaming ? "blue" : "default"}>{isSelected ? "已选" : isStreaming ? "生成中" : "可选"}</Tag>
                  </Space>
                }
              >
                <div className="creation-card-field-grid">
                  {renderEditableText("简介", card.description, (value) => updateWorldview(index, { description: value }))}
                  {renderEditableList("标签", card.tags, (value) => updateWorldview(index, { tags: value }))}
                  {renderEditableText("一句话立项", card.one_sentence_pitch, (value) => updateWorldview(index, { one_sentence_pitch: value }))}
                  {renderEditableList("题材组合", card.genre_mix, (value) => updateWorldview(index, { genre_mix: value }))}
                  {renderEditableText("核心规则", card.core_world_rule ?? card.core_rule, (value) => updateWorldview(index, { core_world_rule: value, core_rule: value }))}
                  {renderEditableText("社会压力", card.social_pressure, (value) => updateWorldview(index, { social_pressure: value }))}
                  {renderEditableText("资源系统", card.power_or_resource_system, (value) => updateWorldview(index, { power_or_resource_system: value }))}
                  {renderEditableText("冲突发动机种子", card.conflict_engine_seed, (value) => updateWorldview(index, { conflict_engine_seed: value }))}
                  {renderEditableText("主角入口", card.protagonist_entry, (value) => updateWorldview(index, { protagonist_entry: value }))}
                  {renderEditableText("长篇潜力", card.long_form_potential, (value) => updateWorldview(index, { long_form_potential: value }))}
                  {renderEditableList("关键实体", card.key_entities, (value) => updateWorldview(index, { key_entities: value }))}
                  {renderEditableList("不可破坏规则", card.rules_not_to_break, (value) => updateWorldview(index, { rules_not_to_break: value }))}
                  {renderEditableList("读者钩子", card.reader_hooks, (value) => updateWorldview(index, { reader_hooks: value }))}
                  {renderEditableText("卖点", card.selling_point, (value) => updateWorldview(index, { selling_point: value }))}
                  {renderEditableText("创作风险", card.writing_risk ?? card.risk, (value) => updateWorldview(index, { writing_risk: value, risk: value }))}
                  {renderEditableText("修改建议", card.revision_hint, (value) => updateWorldview(index, { revision_hint: value }))}
                  {renderEditableText("差异", card.difference_from_previous_batch, (value) => updateWorldview(index, { difference_from_previous_batch: value }))}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );

  const renderProtagonists = () => (
    <div className="creation-star-step">
      <div className="creation-star-action-row">
        <div>
          <Typography.Text strong>主角人设每次三张，完成一张即可进入标题卖点</Typography.Text>
          <Typography.Paragraph type="secondary" className="compact-paragraph">主角卡读取已选世界观；接口返回后一次填充完整内容，提前进入下一步会中断后续主角卡生成。</Typography.Paragraph>
        </div>
        <Space wrap>
          {protagonistBatchLoading ? <Button onClick={stopProtagonistGeneration}>中断后续主角生成</Button> : null}
          <Button icon={<Sparkles size={15} />} loading={protagonistBatchLoading || loadProtagonist.isPending} disabled={!sessionId || protagonistBatchLoading} onClick={() => sessionId && loadProtagonistBatch(sessionId)}>加载三张主角</Button>
          <Button icon={<RefreshCw size={15} />} loading={protagonistBatchLoading || loadProtagonist.isPending} disabled={!sessionId || !protagonistCards.length || protagonistBatchLoading} onClick={() => sessionId && loadProtagonistBatch(sessionId, true)}>刷新三张主角</Button>
        </Space>
      </div>
      {renderPromptSnapshot("protagonist")}
      {protagonistCards.length === 0 ? <Empty description="还没有主角人设卡片" /> : (
        <div className="creation-card-grid protagonist-grid">
          {protagonistCards.map((card, index) => {
            const isSelected = isGeneratedCard(card) && card.id === selectedProtagonist?.id;
            const isStreaming = Boolean(card.__streaming);
            return (
              <Card
                key={card.id}
                className={`creation-card ${isSelected ? "is-selected" : ""} ${isStreaming ? "is-streaming" : ""}`}
                onClick={() => isGeneratedCard(card) && setSelectedProtagonistId(card.id)}
                title={<Input value={card.name ?? card.title} onChange={(event) => updateProtagonist(index, { name: event.target.value, title: event.target.value })} onClick={(event) => event.stopPropagation()} />}
                extra={
                  <Space size={6}>
                    <Edit3 size={15} />
                    <Tag color={isSelected ? "green" : isStreaming ? "blue" : "default"}>{isSelected ? "已选" : isStreaming ? "生成中" : "可选"}</Tag>
                  </Space>
                }
              >
                <div className="creation-card-field-grid">
                  {renderEditableText("身份", card.identity, (value) => updateProtagonist(index, { identity: value }), false)}
                  {renderEditableText("一句话人设", card.one_sentence_pitch, (value) => updateProtagonist(index, { one_sentence_pitch: value }))}
                  {renderEditableText("开局处境", card.opening_situation, (value) => updateProtagonist(index, { opening_situation: value }))}
                  {renderEditableText("世界规则咬合", card.world_rule_connection, (value) => updateProtagonist(index, { world_rule_connection: value }))}
                  {renderEditableText("长期欲望", card.long_term_desire ?? card.long_term_goal, (value) => updateProtagonist(index, { long_term_desire: value, long_term_goal: value }))}
                  {renderEditableText("开局目标", card.immediate_goal, (value) => updateProtagonist(index, { immediate_goal: value }))}
                  {renderEditableText("内在伤口", card.inner_wound, (value) => updateProtagonist(index, { inner_wound: value }))}
                  {renderEditableText("能力", card.ability, (value) => updateProtagonist(index, { ability: value }))}
                  {renderEditableText("能力代价", card.ability_cost, (value) => updateProtagonist(index, { ability_cost: value }))}
                  {renderEditableText("弱点", card.weakness, (value) => updateProtagonist(index, { weakness: value }))}
                  {renderEditableText("秘密", card.secret, (value) => updateProtagonist(index, { secret: value }))}
                  {renderEditableText("成长弧", card.growth_arc ?? card.character_arc, (value) => updateProtagonist(index, { growth_arc: value, character_arc: value }))}
                  {renderEditableList("关系钩子", card.relationship_hooks ?? card.relationship_hook, (value) => updateProtagonist(index, { relationship_hooks: value, relationship_hook: value.join("；") }))}
                  {renderEditableText("主角侧冲突种子", card.conflict_seed, (value) => updateProtagonist(index, { conflict_seed: value }))}
                  {renderEditableText("爽点来源", card.reader_satisfaction, (value) => updateProtagonist(index, { reader_satisfaction: value }))}
                  {renderEditableText("长篇空间", card.long_form_potential, (value) => updateProtagonist(index, { long_form_potential: value }))}
                  {renderEditableText("创作风险", card.writing_risk ?? card.risk, (value) => updateProtagonist(index, { writing_risk: value, risk: value }))}
                  {renderEditableText("修改建议", card.revision_hint, (value) => updateProtagonist(index, { revision_hint: value }))}
                  {renderEditableList("标签", card.tags, (value) => updateProtagonist(index, { tags: value }))}
                </div>
              </Card>
            );
          })}
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
      {step === 1 ? <Button type="primary" disabled={!selectedWorldview} onClick={enterProtagonist}>进入主角抽卡</Button> : null}
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
