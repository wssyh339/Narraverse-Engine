import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Divider, Drawer, Empty, Form, Input, InputNumber, Select, Space, Steps, Tag, Typography, message } from "antd";
import { Check, Edit3, RefreshCw, Sparkles, Timer } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { studioApi } from "../api/studio";
import type { CreationBasicSuggestion, CreationSession, CreationStarBasicInfo, CreationStarCard } from "../types/api";

const stepItems = [
  { title: "基本信息" },
  { title: "世界观抽卡" },
  { title: "主角人设" },
  { title: "书名与包装" },
  { title: "核心与宪法" },
  { title: "完成创建" },
];

const titleStepTrace = 'step: "title"';
const creationStarProjectCacheTrace = "creationStarProjectCache";
const DRAW_BATCH_SIZE = 3;
const REQUIRED_CANON_APPROVAL_SECTIONS = ["project", "story_bible", "characters", "entities", "world_facts", "graph"];
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
  "Scale Planner 会把卷数、章数和每章字数传给后续大纲议事。",
  "主角人设读取基本信息与已选世界观，确保欲望、能力和伤口服务核心规则。",
  "书名包装、核心矛盾和小说宪法都会继续沿用这组创作种子。",
];
const CREATION_STAR_FIELD_LABELS: Record<string, string> = {
  ability: "能力",
  ability_cost: "能力代价",
  ally: "盟友",
  antagonist: "主要对手",
  basic_positioning: "小说基本定位",
  category: "分类",
  character_arc: "人物弧线",
  character_candidates: "角色候选",
  character_functions: "主要人物功能",
  confidence: "置信度",
  content: "内容",
  core_conflict: "核心矛盾",
  core_rule: "核心规则",
  core_world_rule: "核心世界规则",
  conflict_engine_seed: "冲突发动机种子",
  conflict_hook: "冲突钩子",
  core_narrative_engine: "核心叙事发动机",
  core_selling_point: "核心卖点",
  current_step: "当前步骤",
  deep_need: "深层需求",
  description: "说明",
  edge_type: "关系类型",
  ending_state: "结尾状态",
  entity_candidates: "实体候选",
  entity_type: "实体类型",
  external_resistance: "外部阻力",
  final_answer: "最终答案",
  forbidden_directions: "禁区",
  genre: "类型",
  goals: "目标",
  graph_candidate_edges: "图谱关系候选",
  hook: "广告钩子",
  id: "ID",
  importance_level: "重要级别",
  importance_score: "重要分",
  institutional_resistance: "制度阻力",
  internal_resistance: "内部阻力",
  label: "标签",
  long_term_desire: "长期欲望",
  long_term_goal: "长期目标",
  long_form_engine: "长篇发动机",
  long_form_sustainability: "长篇可持续性",
  largest_flaw: "最大缺陷",
  main_conflict: "主线冲突",
  mirror: "镜像人物",
  model: "模型",
  name: "名称",
  narrative_pov: "叙事视角",
  opening_state: "开篇状态",
  platform_fit: "平台风格",
  platform_style: "平台风格",
  possible_endpoint: "可能终点",
  power_distribution: "权力分配",
  power_or_resource_system: "力量/资源系统",
  primary_logic: "核心运行逻辑",
  protagonist: "主角",
  protagonist_arc: "主角轨迹",
  protagonist_desire: "主角欲望",
  protagonist_entry: "主角入口",
  protagonist_hook: "主角钩子",
  provider: "模型服务",
  reader_expectation: "读者期待",
  reader_hooks: "读者钩子",
  reason: "原因",
  relationship_resistance: "关系阻力",
  relationship_hook: "关系钩子",
  relationship_hooks: "关系钩子",
  risk: "风险",
  role_type: "角色类型",
  selling_point: "卖点",
  social_pressure: "社会压力",
  session_id: "会话 ID",
  source: "来源",
  source_prompt_id: "来源提示词",
  status: "状态",
  story_keywords: "故事关键词",
  story_bible_candidate: "Story Bible 候选",
  style_guide: "风格指南",
  surface_goal: "表层目标",
  tags: "标签",
  target_reader: "目标读者",
  target_reader_experience: "目标读者体验",
  target_words: "目标字数",
  theme_question: "主题问题",
  theme_pressure: "主题压力",
  themes: "主题",
  title: "标题",
  tone: "基调",
  type_promise: "类型承诺",
  typical_cost: "典型代价",
  used_remote_model: "是否远程模型",
  continuity_rules: "连续性规则",
  cost_mechanism: "代价机制",
  forbidden_elements: "禁用元素",
  rules_not_to_break: "不可破坏规则",
  world_fact_candidates: "世界事实候选",
  worldview_hook: "世界观钩子",
  world_resistance: "世界阻力",
  world_rules: "世界规则",
  wrong_answer: "错误答案",
};
const CREATION_STAR_VALUE_LABELS: Record<string, string> = {
  title_packaging: "书名包装",
  basic: "基本信息",
  worldview: "世界观抽卡",
  protagonist: "主角人设",
  title: "书名包装",
  core_conflict: "核心矛盾",
  constitution: "小说宪法",
  committed: "已完成",
  draft: "草稿",
  active: "进行中",
  completed: "已完成",
  passed: "通过",
  passed_with_notes: "带备注通过",
  needs_revision: "需要修订",
  blocked: "已阻塞",
};
type CardKind = "worldview" | "protagonist" | "title";

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

function boundedNumber(value: unknown, fallback: number, min: number, max: number) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, Math.round(number)));
}

function buildCreationScalePlan(values: Partial<CreationStarBasicInfo>) {
  const volumeCount = boundedNumber(values.volume_count, 10, 1, 30);
  const chapterCount = boundedNumber(values.chapter_count ?? values.planned_chapter_count, 400, 1, 6000);
  const legacyMin = Number(values.chapter_word_min);
  const legacyMax = Number(values.chapter_word_max);
  const legacyFallback = Number.isFinite(legacyMin) && Number.isFinite(legacyMax) ? Math.round((legacyMin + legacyMax) / 2) : 2500;
  const chapterWordTarget = boundedNumber(values.chapter_word_target, legacyFallback, 500, 20000);
  const chapterWordMin = chapterWordTarget;
  const chapterWordMax = chapterWordTarget;
  const chaptersPerVolume = Math.max(1, Math.ceil(chapterCount / volumeCount));
  const targetWords = chapterCount * chapterWordTarget;
  return {
    target_words: targetWords,
    volume_count: volumeCount,
    chapter_count: chapterCount,
    planned_chapter_count: chapterCount,
    chapters_per_volume: chaptersPerVolume,
    chapter_word_target: chapterWordTarget,
    chapter_word_min: chapterWordMin,
    chapter_word_max: chapterWordMax,
    scale_plan: {
      target_words: targetWords,
      volume_count: volumeCount,
      chapter_count: chapterCount,
      chapters_per_volume: chaptersPerVolume,
      chapter_word_target: chapterWordTarget,
      chapter_word_min: chapterWordMin,
      chapter_word_max: chapterWordMax,
    },
  };
}

function withComputedScalePlan(values: CreationStarBasicInfo): CreationStarBasicInfo {
  return { ...values, ...buildCreationScalePlan(values) };
}

function labelForKey(key: string) {
  return CREATION_STAR_FIELD_LABELS[key] ?? key.replace(/_/g, " ");
}

function hasDisplayValue(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (Array.isArray(value)) return value.some((item) => hasDisplayValue(item));
  if (typeof value === "object") return Object.values(record(value)).some((item) => hasDisplayValue(item));
  return Boolean(value);
}

function displayValue(key: string, value: unknown): string {
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "string") return CREATION_STAR_VALUE_LABELS[value] ?? value;
  if (Array.isArray(value)) return value.map((item) => displayValue(key, item)).join("、");
  return text(value);
}

function renderDisplayValue(key: string, value: unknown): ReactNode {
  if (Array.isArray(value)) {
    const hasNested = value.some((item) => item && typeof item === "object");
    if (!hasNested) return displayValue(key, value);
    return (
      <Space direction="vertical" size={6} className="full-width creation-nested-fields">
        {value.filter(hasDisplayValue).map((item, index) => (
          item && typeof item === "object" ? (
            <div key={`${key}-${index}`} className="creation-nested-object">
              {renderKeyValues(record(item))}
            </div>
          ) : (
            <Typography.Text key={`${key}-${index}`}>{displayValue(key, item)}</Typography.Text>
          )
        ))}
      </Space>
    );
  }
  if (value && typeof value === "object") {
    return <div className="creation-nested-fields">{renderKeyValues(record(value))}</div>;
  }
  return displayValue(key, value);
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
  if (kind === "title") {
    return {
      id,
      title: "生成中",
      description: "已提前生成卡片框架，正在生成书名与包装方向。",
      tags: ["生成中"],
      advertisement_line: "",
      core_selling_point: "",
      reader_expectation: "",
      platform_style: "",
      risk: "",
      revision_hint: "",
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
  const entries = Object.entries(payload).filter(([, value]) => hasDisplayValue(value));
  if (!entries.length) return <Typography.Text type="secondary">{empty}</Typography.Text>;
  return (
    <Space direction="vertical" size={6} className="full-width">
      {entries.map(([key, value]) => (
        <div key={key} className="compact-paragraph creation-key-value-row">
          <strong>{labelForKey(key)}：</strong>{renderDisplayValue(key, value)}
        </div>
      ))}
    </Space>
  );
}

function setNestedRecordValue(source: Record<string, unknown>, path: string[], value: unknown): Record<string, unknown> {
  if (!path.length) return source;
  const [head, ...rest] = path;
  if (!rest.length) return { ...source, [head]: value };
  return {
    ...source,
    [head]: setNestedRecordValue(record(source[head]), rest, value),
  };
}

function renderEditableKeyValues(
  payload: Record<string, unknown>,
  onChange: (path: string[], value: unknown) => void,
  empty = "暂无内容",
  path: string[] = [],
): ReactNode {
  const entries = Object.entries(payload).filter(([, value]) => hasDisplayValue(value));
  if (!entries.length) return <Typography.Text type="secondary">{empty}</Typography.Text>;
  return (
    <Space direction="vertical" size={8} className="full-width creation-editable-key-values">
      {entries.map(([key, value]) => {
        const fieldPath = [...path, key];
        if (value && typeof value === "object" && !Array.isArray(value)) {
          return (
            <div key={fieldPath.join(".")} className="creation-nested-fields">
              <Typography.Text strong>{labelForKey(key)}</Typography.Text>
              {renderEditableKeyValues(record(value), onChange, empty, fieldPath)}
            </div>
          );
        }
        if (Array.isArray(value)) {
          return renderEditableList(labelForKey(key), value, (nextValue) => onChange(fieldPath, nextValue));
        }
        return renderEditableText(labelForKey(key), value, (nextValue) => onChange(fieldPath, nextValue));
      })}
    </Space>
  );
}

function formatElapsedTime(totalSeconds: number) {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;
  const paddedMinutes = hours > 0 ? String(minutes).padStart(2, "0") : String(minutes).padStart(2, "0");
  const paddedSeconds = String(seconds).padStart(2, "0");
  return hours > 0 ? `${hours}:${paddedMinutes}:${paddedSeconds}` : `${paddedMinutes}:${paddedSeconds}`;
}

function useElapsedSeconds(active: boolean) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!active) {
      setElapsedSeconds(0);
      return undefined;
    }
    const startedAt = Date.now();
    const updateElapsed = () => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    updateElapsed();
    const timerId = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timerId);
  }, [active]);

  return elapsedSeconds;
}

function GenerationTimer({ active }: { active: boolean }) {
  const elapsedSeconds = useElapsedSeconds(active);
  if (!active) return null;
  return (
    <Tag color="blue" className="generation-timer">
      <Timer size={13} />
      <span>用时 {formatElapsedTime(elapsedSeconds)}</span>
    </Tag>
  );
}

function buildMarketPositionFromTitle(card?: CreationStarCard, basic?: CreationStarBasicInfo) {
  if (!card) return {};
  const sellingPoint = text(card.core_selling_point) || text(card.selling_point);
  return {
    id: card.id,
    title: card.title,
    target_reader: basic?.target_reader,
    platform_fit: text(card.platform_style) || basic?.channel,
    selling_point: sellingPoint,
    core_selling_point: sellingPoint,
    hook: text(card.one_sentence_ad) || text(card.worldview_hook) || text(card.protagonist_hook),
    reader_expectation: card.reader_expectation,
    risk: card.risk,
    tags: card.tags,
    source: "title_packaging",
  };
}

interface CreationStarProjectCache {
  version: 1;
  step: number;
  session: CreationSession | null;
  manualInput: string;
  basicInfo: CreationStarBasicInfo;
  worldviewCards: CreationStarCard[];
  protagonistCards: CreationStarCard[];
  titleCards: CreationStarCard[];
  promptSnapshots: Record<string, Record<string, unknown>>;
  selectedWorldviewId: string;
  selectedProtagonistId: string;
  selectedTitleId: string;
  projectSeed: Record<string, unknown>;
  coreConflict: Record<string, unknown>;
  novelConstitution: Record<string, unknown>;
  constitutionReview: Record<string, unknown>;
  basicSuggestions: CreationBasicSuggestion[];
}

function creationStarProjectCacheKey(projectId: string) {
  return `creation-star-cache:${projectId}`;
}

function cacheGeneratedCards(cards: CreationStarCard[]) {
  return cards.filter((card) => !card.__streaming && !card.__placeholder);
}

function normalizeCachedStep(step: unknown) {
  const numericStep = typeof step === "number" && Number.isFinite(step) ? step : 0;
  return Math.max(0, Math.min(stepItems.length - 1, numericStep));
}

function loadCachedCreationStar(projectId: string): CreationStarProjectCache | null {
  try {
    const raw = localStorage.getItem(creationStarProjectCacheKey(projectId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<CreationStarProjectCache>;
    if (parsed.version !== 1) return null;
    return {
      version: 1,
      step: normalizeCachedStep(parsed.step),
      session: parsed.session ?? null,
      manualInput: parsed.manualInput ?? "",
      basicInfo: parsed.basicInfo ?? {},
      worldviewCards: cacheGeneratedCards(parsed.worldviewCards ?? []),
      protagonistCards: cacheGeneratedCards(parsed.protagonistCards ?? []),
      titleCards: cacheGeneratedCards(parsed.titleCards ?? []),
      promptSnapshots: parsed.promptSnapshots ?? {},
      selectedWorldviewId: parsed.selectedWorldviewId ?? "",
      selectedProtagonistId: parsed.selectedProtagonistId ?? "",
      selectedTitleId: parsed.selectedTitleId ?? "",
      projectSeed: parsed.projectSeed ?? {},
      coreConflict: parsed.coreConflict ?? {},
      novelConstitution: parsed.novelConstitution ?? {},
      constitutionReview: parsed.constitutionReview ?? {},
      basicSuggestions: parsed.basicSuggestions ?? [],
    };
  } catch {
    return null;
  }
}

function saveCreationStarCache(projectId: string, cache: CreationStarProjectCache) {
  localStorage.setItem(creationStarProjectCacheKey(projectId), JSON.stringify({
    ...cache,
    step: normalizeCachedStep(cache.step),
    worldviewCards: cacheGeneratedCards(cache.worldviewCards),
    protagonistCards: cacheGeneratedCards(cache.protagonistCards),
    titleCards: cacheGeneratedCards(cache.titleCards),
  }));
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
  const [promptSnapshots, setPromptSnapshots] = useState<Record<string, Record<string, unknown>>>({});
  const [selectedWorldviewId, setSelectedWorldviewId] = useState("");
  const [selectedProtagonistId, setSelectedProtagonistId] = useState("");
  const [selectedTitleId, setSelectedTitleId] = useState("");
  const [projectSeed, setProjectSeed] = useState<Record<string, unknown>>({});
  const [coreConflict, setCoreConflict] = useState<Record<string, unknown>>({});
  const [novelConstitution, setNovelConstitution] = useState<Record<string, unknown>>({});
  const [constitutionReview, setConstitutionReview] = useState<Record<string, unknown>>({});
  const [worldviewBatchLoading, setWorldviewBatchLoading] = useState(false);
  const [protagonistBatchLoading, setProtagonistBatchLoading] = useState(false);
  const [titlePackagingBatchLoading, setTitlePackagingBatchLoading] = useState(false);
  const [basicSuggestions, setBasicSuggestions] = useState<CreationBasicSuggestion[]>([]);
  const worldviewBatchTokenRef = useRef(0);
  const protagonistBatchTokenRef = useRef(0);
  const titlePackagingBatchTokenRef = useRef(0);
  const cacheHydratedRef = useRef(false);

  const optionsQuery = useQuery({
    queryKey: ["creation-star-options"],
    queryFn: () => studioApi.getCreationStarOptions(),
    enabled: open,
  });

  const selectedWorldview = useMemo(() => selectedGeneratedById(worldviewCards, selectedWorldviewId), [selectedWorldviewId, worldviewCards]);
  const selectedProtagonist = useMemo(() => selectedGeneratedById(protagonistCards, selectedProtagonistId), [selectedProtagonistId, protagonistCards]);
  const selectedTitle = useMemo(
    () => selectedById(titleCards, selectedTitleId),
    [selectedTitleId, titleCards],
  );

  const options = optionsQuery.data?.options;
  const sessionId = session?.id ?? "";
  const channelOptions = toSelectOptions(options?.channels);
  const genreOptions = toSelectOptions(uniqueStrings([...(options?.genres ?? []), "都市", "玄幻", "科幻", "古言", "悬疑", "轻小说"]));
  const subgenreOptions = toSelectOptions(options?.subgenres);
  const tagOptions = toSelectOptions(options?.tags);
  const styleOptions = toSelectOptions(options?.styles);
  const manualTagOptions = toSelectOptions(uniqueStrings([...(options?.tags ?? []).slice(0, 12), ...MANUAL_TAG_PRESETS]));
  const targetReaderOptions = toSelectOptions(TARGET_READER_PRESETS);
  const targetWordBands = options?.target_word_bands ?? [];
  const targetWordOptions = targetWordBands.map((item) => ({ value: item.value, label: item.label }));
  const watchedVolumeCount = Form.useWatch("volume_count", form);
  const watchedChapterCount = Form.useWatch("chapter_count", form);
  const watchedChapterWordTarget = Form.useWatch("chapter_word_target", form);
  const scalePlannerValues = useMemo(
    () =>
      buildCreationScalePlan({
        volume_count: watchedVolumeCount,
        chapter_count: watchedChapterCount,
        chapter_word_target: watchedChapterWordTarget,
      }),
    [watchedChapterCount, watchedChapterWordTarget, watchedVolumeCount],
  );
  const computedTargetWords = scalePlannerValues.target_words;

  useEffect(() => {
    form.setFieldsValue({
      target_words: computedTargetWords,
      planned_chapter_count: scalePlannerValues.planned_chapter_count,
      chapters_per_volume: scalePlannerValues.chapters_per_volume,
      chapter_word_target: scalePlannerValues.chapter_word_target,
      chapter_word_min: scalePlannerValues.chapter_word_min,
      chapter_word_max: scalePlannerValues.chapter_word_max,
      scale_plan: scalePlannerValues.scale_plan,
    });
  }, [
    computedTargetWords,
    form,
    scalePlannerValues.chapter_word_max,
    scalePlannerValues.chapter_word_min,
    scalePlannerValues.chapter_word_target,
    scalePlannerValues.chapters_per_volume,
    scalePlannerValues.planned_chapter_count,
    scalePlannerValues.scale_plan,
  ]);

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
        basic_info: withComputedScalePlan(form.getFieldsValue(true)),
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
    mutationFn: ({
      targetSessionId,
      replaceExisting = false,
      count = 1,
    }: {
      targetSessionId: string;
      replaceExisting?: boolean;
      count?: number;
    }) =>
      studioApi.generateCreationWorldview(projectId, targetSessionId, { count, manual_input: manualInput, replace_existing: replaceExisting }),
  });

  const loadProtagonist = useMutation({
    mutationFn: ({
      targetSessionId,
      replaceExisting = false,
      count = 1,
    }: {
      targetSessionId: string;
      replaceExisting?: boolean;
      count?: number;
    }) =>
      studioApi.generateCreationProtagonist(projectId, targetSessionId, {
        count,
        manual_input: manualInput,
        selected_worldview: selectedWorldview ?? {},
        replace_existing: replaceExisting,
      }),
  });

  const loadTitlePackaging = useMutation({
    mutationFn: ({
      targetSessionId,
      replaceExisting = false,
      count = 1,
    }: {
      targetSessionId: string;
      replaceExisting?: boolean;
      count?: number;
    }) =>
      studioApi.generateCreationMarketPosition(projectId, targetSessionId, {
        count,
        manual_input: manualInput,
        selected_worldview: selectedWorldview ?? {},
        selected_protagonist: selectedProtagonist ?? {},
        replace_existing: replaceExisting,
      }),
  });

  const confirmSeed = useMutation({
    mutationFn: (targetSessionId: string) =>
      studioApi.confirmCreationSeed(projectId, targetSessionId, {
        selected_worldview: selectedWorldview ?? {},
        selected_protagonist: selectedProtagonist ?? {},
        selected_title: selectedTitle ?? {},
        market_position: buildMarketPositionFromTitle(selectedTitle, basicInfo),
        user_note: "确认创作 Star 已选卡片",
      }),
    onSuccess: (result) => {
      setSession(result.session);
      setProjectSeed(result.project_seed);
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "选择确认失败"),
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
    mutationFn: ({
      targetSessionId,
      coreConflictSystem = coreConflict,
      novelConstitutionPayload = novelConstitution,
    }: {
      targetSessionId: string;
      coreConflictSystem?: Record<string, unknown>;
      novelConstitutionPayload?: Record<string, unknown>;
    }) =>
      studioApi.reviewCreationConstitution(projectId, targetSessionId, {
        core_conflict_system: coreConflictSystem,
        novel_constitution: novelConstitutionPayload,
      }),
    onSuccess: (result) => {
      setSession(result.session);
      setConstitutionReview(result.constitution_review);
    },
  });

  const commit = useMutation({
    mutationFn: (targetSessionId: string) =>
      studioApi.commitCreationSession(projectId, targetSessionId, {
        user_note: "创作 Star 确认入库",
        approved_canon_sections: REQUIRED_CANON_APPROVAL_SECTIONS,
      }),
    onSuccess: () => {
      message.success("创作 Star 已写入作品信息和设定集");
      localStorage.removeItem(creationStarProjectCacheKey(projectId));
      onCommitted();
      onClose();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "创作 Star 提交失败"),
  });

  const worldviewGenerationActive = worldviewBatchLoading || loadWorldview.isPending;
  const protagonistGenerationActive = protagonistBatchLoading || loadProtagonist.isPending;
  const titlePackagingGenerationActive = titlePackagingBatchLoading || loadTitlePackaging.isPending;
  const coreConstitutionGenerationActive =
    confirmSeed.isPending || generateCoreConflict.isPending || generateConstitution.isPending || reviewConstitution.isPending;

  const resetGeneratedState = () => {
    worldviewBatchTokenRef.current += 1;
    protagonistBatchTokenRef.current += 1;
    titlePackagingBatchTokenRef.current += 1;
    setWorldviewCards([]);
    setProtagonistCards([]);
    setTitleCards([]);
    setSelectedWorldviewId("");
    setSelectedProtagonistId("");
    setSelectedTitleId("");
    setProjectSeed({});
    setCoreConflict({});
    setNovelConstitution({});
    setConstitutionReview({});
    setPromptSnapshots({});
  };

  const resetAfterWorldviewRefresh = () => {
    protagonistBatchTokenRef.current += 1;
    titlePackagingBatchTokenRef.current += 1;
    setProtagonistCards([]);
    setTitleCards([]);
    setSelectedProtagonistId("");
    setSelectedTitleId("");
    setProjectSeed({});
    setCoreConflict({});
    setNovelConstitution({});
    setConstitutionReview({});
  };

  const resetAfterProtagonistRefresh = () => {
    titlePackagingBatchTokenRef.current += 1;
    setTitleCards([]);
    setSelectedTitleId("");
    setProjectSeed({});
    setCoreConflict({});
    setNovelConstitution({});
    setConstitutionReview({});
  };

  const resetAfterTitlePackagingRefresh = () => {
    setProjectSeed({});
    setCoreConflict({});
    setNovelConstitution({});
    setConstitutionReview({});
  };

  useEffect(() => {
    cacheHydratedRef.current = false;
    const cached = loadCachedCreationStar(projectId);
    if (!cached) {
      setStep(0);
      setSession(null);
      setManualInput("");
      setBasicInfo({});
      form.resetFields();
      resetGeneratedState();
      setBasicSuggestions([]);
      queueMicrotask(() => {
        cacheHydratedRef.current = true;
      });
      return;
    }
    setStep(cached.step);
    setSession(cached.session);
    setManualInput(cached.manualInput);
    setBasicInfo(withComputedScalePlan(cached.basicInfo));
    form.setFieldsValue(withComputedScalePlan(cached.basicInfo));
    setWorldviewCards(cached.worldviewCards);
    setProtagonistCards(cached.protagonistCards);
    setTitleCards(cached.titleCards);
    setPromptSnapshots(cached.promptSnapshots);
    setSelectedWorldviewId(cached.selectedWorldviewId);
    setSelectedProtagonistId(cached.selectedProtagonistId);
    setSelectedTitleId(cached.selectedTitleId);
    setProjectSeed(cached.projectSeed);
    setCoreConflict(cached.coreConflict);
    setNovelConstitution(cached.novelConstitution);
    setConstitutionReview(cached.constitutionReview);
    setBasicSuggestions(cached.basicSuggestions);
    queueMicrotask(() => {
      cacheHydratedRef.current = true;
    });
  }, [form, projectId]);

  useEffect(() => {
    if (!cacheHydratedRef.current) return;
    saveCreationStarCache(projectId, {
      version: 1,
      step,
      session,
      manualInput,
      basicInfo,
      worldviewCards,
      protagonistCards,
      titleCards,
      promptSnapshots,
      selectedWorldviewId,
      selectedProtagonistId,
      selectedTitleId,
      projectSeed,
      coreConflict,
      novelConstitution,
      constitutionReview,
      basicSuggestions,
    });
  }, [
    projectId,
    step,
    session,
    manualInput,
    basicInfo,
    worldviewCards,
    protagonistCards,
    titleCards,
    promptSnapshots,
    selectedWorldviewId,
    selectedProtagonistId,
    selectedTitleId,
    projectSeed,
    coreConflict,
    novelConstitution,
    constitutionReview,
    basicSuggestions,
  ]);

  const patchWorldviewCard = (cardId: string, patch: Partial<CreationStarCard>) => {
    setWorldviewCards((cards) => cards.map((card) => (card.id === cardId ? { ...card, ...patch } : card)));
  };

  const patchProtagonistCard = (cardId: string, patch: Partial<CreationStarCard>) => {
    setProtagonistCards((cards) => cards.map((card) => (card.id === cardId ? { ...card, ...patch } : card)));
  };

  const patchTitleCard = (cardId: string, patch: Partial<CreationStarCard>) => {
    setTitleCards((cards) => cards.map((card) => (card.id === cardId ? { ...card, ...patch } : card)));
  };

  const removeWorldviewCard = (cardId: string) => {
    setWorldviewCards((cards) => cards.filter((card) => card.id !== cardId));
  };

  const removeProtagonistCard = (cardId: string) => {
    setProtagonistCards((cards) => cards.filter((card) => card.id !== cardId));
  };

  const removeTitleCard = (cardId: string) => {
    setTitleCards((cards) => cards.filter((card) => card.id !== cardId));
  };

  async function loadProgressiveCardBatch<TResult extends { session: CreationSession; prompt_snapshot?: Record<string, unknown> }>({
    skeletons,
    replace,
    requestOne,
    extractCards,
    patchCard,
    removeCard,
    isCurrent,
    onResult,
    onCard,
  }: {
    skeletons: CreationStarCard[];
    replace: boolean;
    requestOne: (replaceExisting: boolean) => Promise<TResult>;
    extractCards: (result: TResult) => CreationStarCard[];
    patchCard: (cardId: string, patch: Partial<CreationStarCard>) => void;
    removeCard: (cardId: string) => void;
    isCurrent: () => boolean;
    onResult: (result: TResult) => void;
    onCard: (card: CreationStarCard, index: number) => void;
  }) {
    const errors: unknown[] = [];
    const runOne = async (skeleton: CreationStarCard, index: number, replaceExisting: boolean) => {
      try {
        const result = await requestOne(replaceExisting);
        if (!isCurrent()) return null;
        onResult(result);
        const card = extractCards(result)[0];
        if (!card) {
          removeCard(skeleton.id);
          return null;
        }
        applyGeneratedCard(card, (patch) => patchCard(skeleton.id, patch));
        onCard(card, index);
        return card;
      } catch (error) {
        if (isCurrent()) removeCard(skeleton.id);
        errors.push(error);
        return null;
      }
    };

    const loadedCards: Array<CreationStarCard | null> = [];
    if (replace && skeletons.length > 0) {
      loadedCards.push(await runOne(skeletons[0], 0, true));
      loadedCards.push(
        ...(await Promise.all(skeletons.slice(1).map((skeleton, index) => runOne(skeleton, index + 1, false)))),
      );
    } else {
      loadedCards.push(...(await Promise.all(skeletons.map((skeleton, index) => runOne(skeleton, index, false)))));
    }
    return {
      cards: loadedCards.filter((card): card is CreationStarCard => Boolean(card)),
      failedCount: errors.length,
      firstError: errors[0],
    };
  }

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
    let skeletons: CreationStarCard[] = [];
    try {
      skeletons = Array.from({ length: DRAW_BATCH_SIZE }, (_, index) => createCardSkeleton("worldview", index, replace));
      setWorldviewCards((cards) => [...cards, ...skeletons]);
      const batchResult = await loadProgressiveCardBatch({
        skeletons,
        replace,
        requestOne: (replaceExisting) =>
          loadWorldview.mutateAsync({
            targetSessionId,
            replaceExisting,
            count: 1,
          }),
        extractCards: (result) => result.cards ?? [],
        patchCard: patchWorldviewCard,
        removeCard: removeWorldviewCard,
        isCurrent: () => worldviewBatchTokenRef.current === batchToken,
        onResult: (result) => {
          setSession(result.session);
          setPromptSnapshots((current) => ({ ...current, worldview: result.prompt_snapshot ?? {} }));
        },
        onCard: (card) => setSelectedWorldviewId((current) => current || card.id || ""),
      });
      if (worldviewBatchTokenRef.current !== batchToken) return;
      const completedCount = batchResult.cards.length;
      if (worldviewBatchTokenRef.current === batchToken && completedCount > 0) {
        message.success(replace ? `已刷新 ${completedCount} 张世界观卡` : `已加载 ${completedCount} 张世界观卡`);
      }
      if (batchResult.failedCount > 0 && completedCount === 0) {
        throw batchResult.firstError;
      }
    } catch (error) {
      skeletons.forEach((skeleton) => removeWorldviewCard(skeleton.id));
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
    let skeletons: CreationStarCard[] = [];
    try {
      skeletons = Array.from({ length: DRAW_BATCH_SIZE }, (_, index) => createCardSkeleton("protagonist", index, replace));
      setProtagonistCards((cards) => [...cards, ...skeletons]);
      const batchResult = await loadProgressiveCardBatch({
        skeletons,
        replace,
        requestOne: (replaceExisting) =>
          loadProtagonist.mutateAsync({
            targetSessionId,
            replaceExisting,
            count: 1,
          }),
        extractCards: (result) => result.cards ?? [],
        patchCard: patchProtagonistCard,
        removeCard: removeProtagonistCard,
        isCurrent: () => protagonistBatchTokenRef.current === batchToken,
        onResult: (result) => {
          setSession(result.session);
          setPromptSnapshots((current) => ({ ...current, protagonist: result.prompt_snapshot ?? {} }));
        },
        onCard: (card) => setSelectedProtagonistId((current) => current || card.id || ""),
      });
      if (protagonistBatchTokenRef.current !== batchToken) return;
      const completedCount = batchResult.cards.length;
      if (protagonistBatchTokenRef.current === batchToken && completedCount > 0) {
        message.success(replace ? `已刷新 ${completedCount} 张主角卡` : `已加载 ${completedCount} 张主角卡`);
      }
      if (batchResult.failedCount > 0 && completedCount === 0) {
        throw batchResult.firstError;
      }
    } catch (error) {
      skeletons.forEach((skeleton) => removeProtagonistCard(skeleton.id));
      message.error(error instanceof Error ? error.message : "主角批量抽卡失败");
    } finally {
      if (protagonistBatchTokenRef.current === batchToken) setProtagonistBatchLoading(false);
    }
  };

  const loadTitlePackagingBatch = async (targetSessionId: string, replace = false) => {
    if (!targetSessionId || titlePackagingBatchLoading) return;
    if (!selectedProtagonist) {
      message.warning("请先加载并选择主角卡片");
      return;
    }
    if (replace) {
      setTitleCards([]);
      setSelectedTitleId("");
      resetAfterTitlePackagingRefresh();
    }
    const batchToken = titlePackagingBatchTokenRef.current + 1;
    titlePackagingBatchTokenRef.current = batchToken;
    setTitlePackagingBatchLoading(true);
    let skeletons: CreationStarCard[] = [];
    try {
      skeletons = Array.from({ length: DRAW_BATCH_SIZE }, (_, index) => createCardSkeleton("title", index, replace));
      setTitleCards((cards) => [...cards, ...skeletons]);
      const batchResult = await loadProgressiveCardBatch({
        skeletons,
        replace,
        requestOne: (replaceExisting) =>
          loadTitlePackaging.mutateAsync({
            targetSessionId,
            replaceExisting,
            count: 1,
          }),
        extractCards: (result) => result.title_candidates ?? [],
        patchCard: patchTitleCard,
        removeCard: removeTitleCard,
        isCurrent: () => titlePackagingBatchTokenRef.current === batchToken,
        onResult: (result) => {
          setSession(result.session);
          setPromptSnapshots((current) => ({ ...current, title: result.prompt_snapshot ?? {} }));
        },
        onCard: (card) => setSelectedTitleId((current) => current || card.id || ""),
      });
      if (titlePackagingBatchTokenRef.current !== batchToken) return;
      const completedCount = batchResult.cards.length;
      if (completedCount > 0) message.success(replace ? `已刷新 ${completedCount} 张书名包装卡` : `已加载 ${completedCount} 张书名包装卡`);
      if (batchResult.failedCount > 0 && completedCount === 0) {
        throw batchResult.firstError;
      }
    } catch (error) {
      skeletons.forEach((skeleton) => removeTitleCard(skeleton.id));
      message.error(error instanceof Error ? error.message : "标题包装生成失败");
    } finally {
      if (titlePackagingBatchTokenRef.current === batchToken) setTitlePackagingBatchLoading(false);
    }
  };

  const ensureCreationSession = async () => {
    if (sessionId) return sessionId;
    const values = withComputedScalePlan(await form.validateFields());
    form.setFieldsValue(values);
    setBasicInfo(values);
    const result = await createSession.mutateAsync(values);
    return result.session.id;
  };

  const ensureProjectSeed = async (targetSessionId: string) => {
    if (Object.keys(projectSeed).length) return projectSeed;
    if (!selectedWorldview || !selectedProtagonist || !selectedTitle?.title) {
      message.warning("请先选择世界观、主角和书名包装卡片");
      throw new Error("missing creation selections");
    }
    const result = await confirmSeed.mutateAsync(targetSessionId);
    return result.project_seed;
  };

  const previousCreationStep = () => {
    if (step === 0) return;
    setStep((current) => Math.max(0, current - 1));
  };

  const nextCreationStep = async () => {
    if (step === 0) {
      try {
        await ensureCreationSession();
        setStep(1);
      } catch (error) {
        message.error(error instanceof Error ? error.message : "创作 Star 会话创建失败");
      }
      return;
    }
    if (step < stepItems.length - 1) setStep((current) => Math.min(stepItems.length - 1, current + 1));
  };

  const runCoreConstitutionLane = async () => {
    try {
      const targetSessionId = await ensureCreationSession();
      await ensureProjectSeed(targetSessionId);
      const conflict = await generateCoreConflict.mutateAsync(targetSessionId);
      const constitution = await generateConstitution.mutateAsync(conflict.session.id);
      await reviewConstitution.mutateAsync({
        targetSessionId: constitution.session.id,
        coreConflictSystem: conflict.core_conflict_system,
        novelConstitutionPayload: constitution.novel_constitution,
      });
      message.success("核心矛盾与小说宪法已生成");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "小说宪法生成失败");
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

  const updateCoreConflictField = (path: string[], value: unknown) => {
    setCoreConflict((current) => setNestedRecordValue(current, path, value));
    setConstitutionReview({});
  };

  const updateNovelConstitutionField = (path: string[], value: unknown) => {
    setNovelConstitution((current) => setNestedRecordValue(current, path, value));
    setConstitutionReview({});
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
            基本信息会进入世界观抽卡、主角人设、书名包装、核心矛盾和小说宪法。每个可选项都提供预设，也可以继续手动补充。
          </Typography.Paragraph>
        </div>
        <div className="creation-star-flow-checklist">
          <Typography.Text strong>后续流程读取</Typography.Text>
          {BASIC_FLOW_REQUIREMENTS.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      </div>
      <Alert type="info" showIcon message="底部只负责上一步和下一步；世界观、主角、书名包装以及核心与宪法，都需要通过本步骤里的生成按钮手动开始。" />
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          channel: "男频",
          genre: "都市",
          volume_count: 10,
          chapter_count: 400,
          target_words: 1000000,
          chapters_per_volume: 40,
          chapter_word_target: 2500,
          chapter_word_min: 2500,
          chapter_word_max: 2500,
          style: "热血爽快",
        }}
      >
        <Form.Item name="target_words" hidden><Input type="hidden" /></Form.Item>
        <Form.Item name="planned_chapter_count" hidden><Input type="hidden" /></Form.Item>
        <Form.Item name="chapters_per_volume" hidden><Input type="hidden" /></Form.Item>
        <Form.Item name="chapter_word_min" hidden><Input type="hidden" /></Form.Item>
        <Form.Item name="chapter_word_max" hidden><Input type="hidden" /></Form.Item>
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
            <Typography.Paragraph>Scale Planner 会计算总字数，并把卷数、章数和单章字数传入后续大纲议事。</Typography.Paragraph>
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
            <Form.Item name="volume_count" label="卷数" rules={[{ required: true, message: "请输入卷数" }]}>
              <InputNumber min={1} max={30} className="full-width" />
            </Form.Item>
            <Form.Item name="chapter_count" label="章数" rules={[{ required: true, message: "请输入章数" }]}>
              <InputNumber min={1} max={6000} className="full-width" />
            </Form.Item>
            <Form.Item name="chapter_word_target" label="每章字数" rules={[{ required: true, message: "请输入每章字数" }]}>
              <InputNumber min={500} max={20000} step={100} className="full-width" />
            </Form.Item>
            <Form.Item name="style" label="叙事风格">
              <Select options={styleOptions} showSearch optionFilterProp="label" placeholder="选择叙事风格" />
            </Form.Item>
            <div className="creation-scale-planner">
              <Typography.Text type="secondary">Scale Planner</Typography.Text>
              <Typography.Title level={4}>{computedTargetWords.toLocaleString()} 字</Typography.Title>
              <Typography.Text>总字数不可手动填写，由卷数、章数和每章字数自动计算。</Typography.Text>
              <Typography.Text type="secondary">
                每卷约 {scalePlannerValues.chapters_per_volume} 章 · 单章目标 {scalePlannerValues.chapter_word_target} 字
              </Typography.Text>
              {targetWordOptions.length ? (
                <Typography.Text type="secondary">
                  参考规模带：{targetWordOptions.slice(0, 4).map((item) => item.label).join(" / ")}
                </Typography.Text>
              ) : null}
            </div>
          </div>
        </section>
        <section className="creation-star-basic-section">
          <div className="creation-star-section-copy">
            <Typography.Text type="secondary">03 初始想法与抽卡约束</Typography.Text>
            <Typography.Title level={4}>把脑洞和禁区提前交给 Agent</Typography.Title>
            <Typography.Paragraph>初始想法会进入基本信息，额外约束会随每轮抽卡传入，不会直接写入正式设定。</Typography.Paragraph>
            <Space wrap className="generation-action-inline">
              <Button
                icon={<Sparkles size={15} />}
                loading={basicSuggestionMutation.isPending}
                onClick={() => basicSuggestionMutation.mutate()}
              >
                {basicSuggestions.length ? "刷新 AI 选项" : "生成 AI 选项"}
              </Button>
              <GenerationTimer active={basicSuggestionMutation.isPending} />
            </Space>
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
          <Typography.Paragraph type="secondary" className="compact-paragraph">卡片框架会提前出现，三张并行生成；不点击刷新时，本项目会一直保留已生成缓存。</Typography.Paragraph>
        </div>
        <Space wrap>
          <Button icon={<Sparkles size={15} />} loading={worldviewGenerationActive} disabled={!sessionId || worldviewBatchLoading} onClick={() => sessionId && loadWorldviewBatch(sessionId)}>加载三张世界观</Button>
          <Button icon={<RefreshCw size={15} />} loading={worldviewGenerationActive} disabled={!sessionId || !worldviewCards.length || worldviewBatchLoading} onClick={() => sessionId && loadWorldviewBatch(sessionId, true)}>刷新三张世界观</Button>
          <GenerationTimer active={worldviewGenerationActive} />
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
          <Typography.Text strong>主角人设每次三张，完成一张即可继续到书名包装</Typography.Text>
          <Typography.Paragraph type="secondary" className="compact-paragraph">主角卡读取已选世界观；三张并行生成，返回上一页不会清空已有卡片。</Typography.Paragraph>
        </div>
        <Space wrap>
          <Button icon={<Sparkles size={15} />} loading={protagonistGenerationActive} disabled={!sessionId || protagonistBatchLoading} onClick={() => sessionId && loadProtagonistBatch(sessionId)}>加载三张主角</Button>
          <Button icon={<RefreshCw size={15} />} loading={protagonistGenerationActive} disabled={!sessionId || !protagonistCards.length || protagonistBatchLoading} onClick={() => sessionId && loadProtagonistBatch(sessionId, true)}>刷新三张主角</Button>
          <GenerationTimer active={protagonistGenerationActive} />
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

  const renderTitlePackaging = () => (
    <div className="creation-star-step">
      <div className="creation-star-action-row">
        <div>
          <Typography.Text strong>书名与包装每次三张，完成一个显示一个</Typography.Text>
          <Typography.Paragraph type="secondary" className="compact-paragraph">书名、广告句、核心卖点、读者期待和风险提示合并在同一张可编辑卡里。</Typography.Paragraph>
        </div>
        <Space wrap>
          <Button icon={<Sparkles size={15} />} loading={titlePackagingGenerationActive} disabled={!sessionId || titlePackagingBatchLoading} onClick={() => sessionId && loadTitlePackagingBatch(sessionId)}>加载三张书名包装</Button>
          <Button icon={<RefreshCw size={15} />} loading={titlePackagingGenerationActive} disabled={!sessionId || !titleCards.length || titlePackagingBatchLoading} onClick={() => sessionId && loadTitlePackagingBatch(sessionId, true)}>刷新三张书名包装</Button>
          <GenerationTimer active={titlePackagingGenerationActive} />
        </Space>
      </div>
      {renderPromptSnapshot("title")}
      {titleCards.length === 0 ? <Empty description="还没有书名包装卡" /> : (
        <div className="creation-card-grid title-grid">
          {titleCards.map((card, index) => (
            <Card
              key={card.id}
              className={`creation-card ${card.id === selectedTitle?.id ? "is-selected" : ""}`}
              onClick={() => setSelectedTitleId(card.id)}
              title={<Input value={card.title} onChange={(event) => updateTitle(index, { title: event.target.value })} onClick={(event) => event.stopPropagation()} />}
              extra={<Tag color={card.id === selectedTitle?.id ? "green" : "default"}>{card.id === selectedTitle?.id ? "已选" : "可选"}</Tag>}
            >
              <div className="creation-card-field-grid">
                {renderEditableText("副标题/包装方向", card.subtitle, (value) => updateTitle(index, { subtitle: value }), false)}
                {renderEditableText("说明", card.description, (value) => updateTitle(index, { description: value }))}
                {renderEditableText("平台风格", card.platform_style, (value) => updateTitle(index, { platform_style: value }), false)}
                {renderEditableText("一句话广告", card.one_sentence_ad, (value) => updateTitle(index, { one_sentence_ad: value }))}
                {renderEditableText("核心卖点", card.core_selling_point ?? card.selling_point, (value) => updateTitle(index, { core_selling_point: value, selling_point: value }))}
                {renderEditableText("读者期待", card.reader_expectation, (value) => updateTitle(index, { reader_expectation: value }))}
                {renderEditableText("世界观钩子", card.worldview_hook, (value) => updateTitle(index, { worldview_hook: value }))}
                {renderEditableText("主角钩子", card.protagonist_hook, (value) => updateTitle(index, { protagonist_hook: value }))}
                {renderEditableText("风险", card.risk, (value) => updateTitle(index, { risk: value }))}
                {renderEditableText("修改建议", card.revision_hint, (value) => updateTitle(index, { revision_hint: value }))}
                {renderEditableList("标签", card.tags, (value) => updateTitle(index, { tags: value }))}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );

  const renderConstitution = () => (
    <div className="creation-star-step">
      <Alert type="warning" showIcon message="请先选择世界观、主角和书名包装卡；核心与宪法只会通过本页按钮生成，底部下一步只负责导航。" />
      <div className="creation-star-action-row">
        <Typography.Text strong>核心与宪法</Typography.Text>
        <Space wrap>
          <Button
            icon={<RefreshCw size={15} />}
            loading={coreConstitutionGenerationActive}
            onClick={runCoreConstitutionLane}
          >
            生成/刷新核心与宪法
          </Button>
          <GenerationTimer active={coreConstitutionGenerationActive} />
        </Space>
      </div>
      <div className="creation-star-two-columns">
        <Card title="核心矛盾系统">{renderEditableKeyValues(coreConflict, updateCoreConflictField, "请先生成核心矛盾系统")}</Card>
        <Card title="小说宪法">{renderEditableKeyValues(novelConstitution, updateNovelConstitutionField, "请先生成小说宪法")}</Card>
      </div>
    </div>
  );

  const renderFinish = () => (
    <div className="creation-star-step">
      <Alert type="warning" showIcon message="提交后会更新作品信息、故事圣经、角色、实体、世界事实和图谱，并创建版本快照。" />
      <div className="creation-star-two-columns">
        <Card title="最终书名"><Typography.Title level={4}>{selectedTitle?.title}</Typography.Title></Card>
        <Card title="会话状态">{renderKeyValues({ session_id: session?.id, current_step: session?.current_step, status: session?.status })}</Card>
      </div>
      <Divider />
      <div className="creation-star-two-columns">
        <Card title="核心矛盾系统">{renderKeyValues(coreConflict, "请先生成核心矛盾系统")}</Card>
        <Card title="小说宪法">{renderKeyValues(novelConstitution, "请先生成小说宪法")}</Card>
      </div>
    </div>
  );

  const renderStep = () => {
    if (step === 0) return renderBasicInfo();
    if (step === 1) return renderWorldviews();
    if (step === 2) return renderProtagonists();
    if (step === 3) return renderTitlePackaging();
    if (step === 4) return renderConstitution();
    return renderFinish();
  };

  const footer = (
    <Space className="creation-star-footer">
      <Button disabled={step === 0} onClick={previousCreationStep}>上一步</Button>
      {step < stepItems.length - 1 ? (
        <Button type="primary" onClick={nextCreationStep}>下一步</Button>
      ) : (
        <Button
          type="primary"
          icon={<Check size={15} />}
          loading={commit.isPending}
          disabled={!sessionId || !Object.keys(novelConstitution).length}
          onClick={() => sessionId && commit.mutate(sessionId)}
        >
          完成创建并写入设定
        </Button>
      )}
    </Space>
  );

  return (
    <Drawer
      title="创作 Star"
      width="92vw"
      open={open}
      onClose={onClose}
      extra={<Tag color="purple" title={`${titleStepTrace} · ${creationStarProjectCacheTrace}`}>解耦创作 Star</Tag>}
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
