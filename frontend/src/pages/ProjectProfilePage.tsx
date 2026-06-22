import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Col, Descriptions, Empty, Form, Input, InputNumber, Progress, Row, Select, Space, Tag, Typography, message } from "antd";
import { BookOpen, Compass, FileText, Gauge, Layers3, Save, ShieldCheck, Sparkles, Target, UserRound } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { studioApi } from "../api/studio";
import { SettingsSectionNav } from "../components/SettingsSectionNav";
import type { CreationProfileArchive, Project, StoryBible } from "../types/api";

const profileFieldLabels: Record<string, string> = {
  channel: "频道",
  genre: "题材",
  subgenres: "细分类型",
  tags: "标签",
  manual_tags: "手动标签",
  target_reader: "目标读者",
  target_words: "目标字数",
  volume_count: "分卷数",
  chapter_count: "章节数",
  planned_chapter_count: "目标章节数",
  chapters_per_volume: "每卷章节",
  chapter_word_target: "单章字数",
  chapter_word_min: "单章下限",
  chapter_word_max: "单章上限",
  style: "文风",
  initial_idea: "初始想法",
  title: "标题",
  subtitle: "副标题",
  description: "说明",
  core_world_rule: "核心世界规则",
  core_rule: "核心规则",
  social_pressure: "社会压力",
  power_or_resource_system: "力量/资源系统",
  protagonist_entry: "主角入口",
  conflict_engine_seed: "冲突发动机种子",
  long_form_potential: "长篇潜力",
  reader_hooks: "读者钩子",
  selling_point: "卖点",
  risk: "风险提示",
  writing_risk: "创作风险",
  revision_hint: "修改建议",
  name: "姓名",
  identity: "身份",
  opening_situation: "开局处境",
  world_rule_connection: "世界规则连接",
  long_term_desire: "长期欲望",
  long_term_goal: "长期目标",
  immediate_goal: "短期目标",
  inner_wound: "内在伤口",
  ability: "能力",
  ability_cost: "能力代价",
  weakness: "弱点",
  secret: "秘密",
  growth_arc: "成长弧",
  character_arc: "人物弧光",
  relationship_hooks: "关系钩子",
  conflict_seed: "主角侧冲突种子",
  reader_satisfaction: "爽点来源",
  platform_style: "平台风格",
  one_sentence_ad: "一句话广告语",
  core_selling_point: "核心卖点",
  reader_expectation: "读者期待",
  worldview_hook: "世界观钩子",
  protagonist_hook: "主角钩子",
  protagonist_desire: "主角最强欲望",
  world_resistance: "世界阻力",
  core_conflict: "核心矛盾",
  external_resistance: "外部阻力",
  internal_resistance: "内部阻力",
  relationship_resistance: "关系阻力",
  institutional_resistance: "制度阻力",
  typical_cost: "典型代价",
  long_form_engine: "长篇发动机",
  possible_endpoint: "可能终点",
  theme_question: "主题问题",
  status: "状态",
  largest_strength: "最大优势",
  largest_risk: "最大风险",
  blocking_issues: "阻塞问题",
  revision_suggestions: "修订建议",
  recommended_next_stage: "建议下一阶段",
};

const constitutionLabels: Record<string, string> = {
  basic_positioning: "基本定位",
  core_narrative_engine: "核心叙事发动机",
  protagonist_arc: "主角轨迹",
  world_rules: "世界规则",
  character_functions: "人物功能",
  theme_pressure: "主题压力",
  cost_mechanism: "代价机制",
  forbidden_directions: "禁区",
  long_form_sustainability: "长篇可持续性",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatNumber(value: unknown): string {
  if (typeof value !== "number") return formatProfileValue(value);
  return value >= 10000 ? `${Math.round(value / 10000)} 万` : String(value);
}

function formatProfileValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "未生成";
  if (Array.isArray(value)) {
    const formatted = value.map((item) => (isRecord(item) ? formatProfileValue(item.title ?? item.name ?? item.content ?? item.description) : formatProfileValue(item)));
    return formatted.filter((item) => item && item !== "未生成").join("、") || "未生成";
  }
  if (isRecord(value)) {
    const direct = value.title ?? value.name ?? value.core_conflict ?? value.main_conflict ?? value.summary ?? value.description ?? value.content;
    if (direct) return formatProfileValue(direct);
    return Object.entries(value)
      .slice(0, 4)
      .map(([key, item]) => `${profileFieldLabels[key] ?? key}：${formatProfileValue(item)}`)
      .join("；") || "未生成";
  }
  return String(value);
}

function hasRecordContent(value: unknown): value is Record<string, unknown> {
  return isRecord(value) && Object.values(value).some((item) => item !== null && item !== undefined && item !== "" && (!Array.isArray(item) || item.length > 0));
}

function compactFields(source: Record<string, unknown>, keys: string[]) {
  return keys
    .map((key) => ({ key, label: profileFieldLabels[key] ?? key, value: source[key] }))
    .filter((item) => formatProfileValue(item.value) !== "未生成");
}

function tagsFrom(...values: unknown[]): string[] {
  const result: string[] = [];
  values.forEach((value) => {
    if (Array.isArray(value)) {
      value.forEach((item) => {
        const text = formatProfileValue(item);
        if (text !== "未生成") result.push(text);
      });
      return;
    }
    const text = formatProfileValue(value);
    if (text !== "未生成") result.push(text);
  });
  return [...new Set(result)].slice(0, 10);
}

function ProfileArchiveCard({
  icon: Icon,
  title,
  subtitle,
  data,
  fieldKeys,
  tags,
}: {
  icon: LucideIcon;
  title: string;
  subtitle: string;
  data: Record<string, unknown>;
  fieldKeys: string[];
  tags?: string[];
}) {
  const fields = compactFields(data, fieldKeys);
  return (
    <section className="profile-archive-card">
      <div className="profile-archive-card-head">
        <span className="profile-archive-icon"><Icon size={17} /></span>
        <div>
          <Typography.Text strong>{title}</Typography.Text>
          <Typography.Text type="secondary">{subtitle}</Typography.Text>
        </div>
      </div>
      {tags?.length ? (
        <Space wrap size={[6, 6]} className="profile-archive-tags">
          {tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}
        </Space>
      ) : null}
      {fields.length ? (
        <div className="profile-archive-field-list">
          {fields.map((field) => (
            <div key={field.key}>
              <small>{field.label}</small>
              <strong title={formatProfileValue(field.value)}>{formatProfileValue(field.value)}</strong>
            </div>
          ))}
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无创作 Star 生成内容" />
      )}
    </section>
  );
}

function ConstitutionGrid({ constitution }: { constitution: Record<string, unknown> }) {
  const entries = Object.entries(constitution).filter(([key, value]) => key !== "_llm" && formatProfileValue(value) !== "未生成");
  if (!entries.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未生成小说宪法" />;
  return (
    <div className="profile-constitution-grid">
      {entries.map(([key, value]) => (
        <div key={key} className="profile-constitution-cell">
          <small>{constitutionLabels[key] ?? profileFieldLabels[key] ?? key}</small>
          <strong title={formatProfileValue(value)}>{formatProfileValue(value)}</strong>
        </div>
      ))}
    </div>
  );
}

function CreationArchivePanel({ archive, confirmed, sessionStatus }: { archive: CreationProfileArchive; confirmed: boolean; sessionStatus: string }) {
  const basic = (archive.basic_info ?? {}) as Record<string, unknown>;
  const worldview = archive.selected_worldview ?? {};
  const protagonist = archive.selected_protagonist ?? {};
  const title = archive.selected_title ?? {};
  const market = archive.market_position ?? {};
  const core = archive.core_conflict_system ?? {};
  const constitution = archive.novel_constitution ?? {};
  const review = archive.constitution_review ?? {};
  const canon = archive.canon_candidates ?? {};
  const hasArchive = [basic, worldview, protagonist, title, market, core, constitution, review, canon].some(hasRecordContent);
  const canonSectionCount = Object.keys(canon).length;
  const qualityPercent = Math.min(
    100,
    [worldview, protagonist, title, core, constitution, review, archive.confirmed_canon].filter(hasRecordContent).length * 14 + (hasRecordContent(basic) ? 2 : 0),
  );
  const metrics: Array<[string, unknown]> = [
    ["目标规模", `${formatNumber(basic.target_words)}字 · ${formatProfileValue(basic.chapter_count ?? basic.planned_chapter_count)}章`],
    ["单章节奏", `${formatProfileValue(basic.chapter_word_min)}-${formatProfileValue(basic.chapter_word_max)}字 / 目标 ${formatProfileValue(basic.chapter_word_target)}`],
    ["读者承诺", market.reader_expectation ?? title.reader_expectation ?? basic.target_reader],
    ["核心卖点", market.core_selling_point ?? title.core_selling_point ?? title.selling_point],
  ];

  if (!hasArchive) {
    return (
      <section className="profile-creation-archive is-empty">
        <Empty description="暂无创作 Star 立项档案。完成创作 Star 并确认入库后，这里会汇总所有生成信息。" />
      </section>
    );
  }

  return (
    <section className="profile-creation-archive">
      <div className="profile-archive-hero">
        <div>
          <Typography.Text type="secondary">Creation Star Archive</Typography.Text>
          <Typography.Title level={3}>创作 Star 立项档案</Typography.Title>
          <Typography.Paragraph>
            {formatProfileValue(title.title || title.one_sentence_ad || worldview.title || core.core_conflict || "这里汇总创作 Star 从抽卡到正典入库的全部立项信息。")}
          </Typography.Paragraph>
          <Space wrap>
            {tagsFrom(basic.channel, basic.genre, basic.subgenres, basic.tags, basic.manual_tags).map((tag) => <Tag key={tag}>{tag}</Tag>)}
          </Space>
        </div>
        <div className="profile-archive-score">
          <Progress type="circle" percent={qualityPercent} size={92} />
          <Typography.Text strong>{confirmed ? "已写入正典" : sessionStatus || "草稿档案"}</Typography.Text>
          <Typography.Text type="secondary">覆盖 {canonSectionCount} 个正典候选分区</Typography.Text>
        </div>
      </div>

      <div className="profile-archive-metrics">
        {metrics.map(([label, value]) => (
          <div key={label} className="profile-archive-metric">
            <small>{label}</small>
            <strong title={formatProfileValue(value)}>{formatProfileValue(value)}</strong>
          </div>
        ))}
      </div>

      <div className="profile-archive-grid">
        <ProfileArchiveCard
          icon={Compass}
          title="基本定位"
          subtitle="频道、题材、读者、规模和初始约束"
          data={basic}
          fieldKeys={["channel", "genre", "subgenres", "target_reader", "target_words", "volume_count", "chapter_count", "chapters_per_volume", "style", "initial_idea"]}
          tags={tagsFrom(basic.tags, basic.manual_tags)}
        />
        <ProfileArchiveCard
          icon={BookOpen}
          title="世界观抽卡"
          subtitle="题材组合、核心规则、社会压力和长篇空间"
          data={worldview}
          fieldKeys={["title", "description", "core_world_rule", "core_rule", "social_pressure", "power_or_resource_system", "protagonist_entry", "conflict_engine_seed", "long_form_potential", "reader_hooks", "selling_point", "risk", "revision_hint"]}
          tags={tagsFrom(worldview.tags, worldview.genre_mix)}
        />
        <ProfileArchiveCard
          icon={UserRound}
          title="主角人设抽卡"
          subtitle="主角身份、欲望、伤口、能力代价和关系钩子"
          data={protagonist}
          fieldKeys={["name", "title", "identity", "opening_situation", "world_rule_connection", "long_term_desire", "long_term_goal", "ability", "ability_cost", "inner_wound", "weakness", "secret", "relationship_hooks", "conflict_seed", "growth_arc", "reader_satisfaction"]}
          tags={tagsFrom(protagonist.tags)}
        />
        <ProfileArchiveCard
          icon={Target}
          title="书名与包装"
          subtitle="平台命名方向、广告句、卖点和读者期待"
          data={{ ...market, ...title }}
          fieldKeys={["title", "subtitle", "platform_style", "one_sentence_ad", "core_selling_point", "selling_point", "reader_expectation", "worldview_hook", "protagonist_hook", "risk", "revision_hint"]}
          tags={tagsFrom(title.tags)}
        />
        <ProfileArchiveCard
          icon={Gauge}
          title="核心矛盾系统"
          subtitle="主角欲望、世界阻力、持续升级和典型代价"
          data={core}
          fieldKeys={["protagonist_desire", "world_resistance", "core_conflict", "external_resistance", "internal_resistance", "relationship_resistance", "institutional_resistance", "typical_cost", "long_form_engine", "possible_endpoint", "theme_question"]}
        />
        <ProfileArchiveCard
          icon={ShieldCheck}
          title="压力测试"
          subtitle="小说宪法审查状态、风险和修订建议"
          data={review}
          fieldKeys={["status", "largest_strength", "largest_risk", "blocking_issues", "revision_suggestions", "recommended_next_stage"]}
        />
      </div>

      <section className="profile-archive-card profile-archive-wide">
        <div className="profile-archive-card-head">
          <span className="profile-archive-icon"><Layers3 size={17} /></span>
          <div>
            <Typography.Text strong>小说宪法</Typography.Text>
            <Typography.Text type="secondary">从立项种子收敛出的最高创作规则</Typography.Text>
          </div>
        </div>
        <ConstitutionGrid constitution={constitution} />
      </section>

      <section className="profile-archive-card profile-archive-wide">
        <div className="profile-archive-card-head">
          <span className="profile-archive-icon"><FileText size={17} /></span>
          <div>
            <Typography.Text strong>正典入库摘要</Typography.Text>
            <Typography.Text type="secondary">创作 Star 最终映射到作品资料、故事圣经、角色、实体、世界事实和图谱的候选分区</Typography.Text>
          </div>
        </div>
        <Space wrap>
          {Object.keys(canon).length ? Object.keys(canon).map((key) => <Tag key={key}>{constitutionLabels[key] ?? profileFieldLabels[key] ?? key}</Tag>) : <Tag>暂无正典候选</Tag>}
          {confirmed ? <Tag color="green">confirmed_canon 已保存</Tag> : <Tag>未确认入库</Tag>}
        </Space>
      </section>
    </section>
  );
}

export function ProjectProfilePage() {
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["project-profile", projectId], queryFn: () => studioApi.getCreationProfile(projectId), enabled: !!projectId });
  const [projectForm] = Form.useForm<Partial<Project>>();
  const [bibleForm] = Form.useForm<Partial<StoryBible>>();

  useEffect(() => {
    if (query.data) {
      projectForm.setFieldsValue(query.data.project);
      bibleForm.setFieldsValue(query.data.story_bible ?? {});
    }
  }, [query.data, projectForm, bibleForm]);

  const invalidateProfile = () => {
    queryClient.invalidateQueries({ queryKey: ["project-profile", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-shell", projectId] });
    queryClient.invalidateQueries({ queryKey: ["state", projectId] });
  };

  const saveProject = useMutation({
    mutationFn: (values: Partial<Project>) => studioApi.updateProject(projectId, values),
    onSuccess: () => {
      message.success("作品信息已保存");
      invalidateProfile();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "保存失败"),
  });
  const saveBible = useMutation({
    mutationFn: (values: Partial<StoryBible>) => studioApi.updateStoryBible(projectId, values),
    onSuccess: () => {
      message.success("核心构架已保存");
      invalidateProfile();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "保存失败"),
  });
  const generate = useMutation({
    mutationFn: () => studioApi.generateStoryBible(projectId, query.data?.project.initial_idea ?? ""),
    onSuccess: () => {
      message.success("总策划 Agent 已生成核心构架");
      invalidateProfile();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "生成失败"),
  });

  if (query.isLoading) return <Card loading />;
  if (query.error || !query.data) return <Alert type="error" showIcon message="无法读取作品资料" />;

  const { project, story_bible: storyBible, creation_profile: archive, profile_summary: summary } = query.data;

  return (
    <div className="studio-document-page settings-document-page">
      <SettingsSectionNav active="profile" />
      <div className="profile-command-bar">
        <div>
          <Typography.Text type="secondary">Project Constitution</Typography.Text>
          <Typography.Title level={3}>作品资料与故事圣经</Typography.Title>
          <Typography.Text type="secondary">这里维护书名、卖点、读者画像、主线冲突和连续性规则。所有 Agent 生成前都会读取这组正典资料。</Typography.Text>
        </div>
        <Space wrap className="profile-command-actions">
          <Tag>{project.genre}</Tag>
          <Tag>{project.planned_chapter_count} 章</Tag>
          <Tag>{project.chapter_word_target} 字/章</Tag>
          <Tag>{summary.confirmed ? "创作 Star 已入库" : "创作 Star 未确认"}</Tag>
          <Button icon={<Sparkles size={15} />} loading={generate.isPending} onClick={() => generate.mutate()}>总策划 Agent 辅助生成</Button>
        </Space>
      </div>

      <CreationArchivePanel archive={archive} confirmed={summary.confirmed} sessionStatus={summary.session_status} />

      <section className="profile-editor-shell">
        <div className="profile-editor-shell-head">
          <div>
            <Typography.Title level={4}>正式资料编辑区</Typography.Title>
            <Typography.Text type="secondary">保存后会更新 Agent 读取的正式上下文</Typography.Text>
          </div>
        </div>
        <div className="profile-editor-grid">
          <Card className="profile-editor-card" title="作品身份" extra={<Typography.Text type="secondary">面向读者与市场定位</Typography.Text>}>
            <Form form={projectForm} layout="vertical" onFinish={(values) => saveProject.mutate(values)}>
              <div className="form-grid-2">
                <Form.Item name="title" label="书名" rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="genre" label="题材赛道" rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="planned_chapter_count" label="目标章节数"><InputNumber min={1} max={1000} className="full-width" /></Form.Item>
                <Form.Item name="chapter_word_target" label="单章目标字数"><InputNumber min={500} max={20000} className="full-width" /></Form.Item>
              </div>
              <Form.Item name="target_reader" label="目标读者"><Input.TextArea rows={3} /></Form.Item>
              <Form.Item name="premise" label="作品简介 / 核心卖点"><Input.TextArea rows={5} /></Form.Item>
              <Form.Item name="initial_idea" label="初始创意"><Input.TextArea rows={5} /></Form.Item>
              <Form.Item name="style_guide" label="文风说明"><Input.TextArea rows={4} /></Form.Item>
              <Button type="primary" htmlType="submit" icon={<Save size={15} />} loading={saveProject.isPending}>保存作品信息</Button>
            </Form>
          </Card>
          <Card className="profile-editor-card" title="故事圣经" extra={<Typography.Text type="secondary">面向 Agent 的正典约束</Typography.Text>}>
            {storyBible ? (
              <Form form={bibleForm} layout="vertical" onFinish={(values) => saveBible.mutate(values)}>
                <Descriptions column={2} size="small" className="profile-bible-meta">
                  <Descriptions.Item label="版本">v{storyBible.version}</Descriptions.Item>
                  <Descriptions.Item label="更新">{storyBible.updated_at}</Descriptions.Item>
                </Descriptions>
                <Form.Item name="world_setting" label="世界观设定"><Input.TextArea rows={7} /></Form.Item>
                <Form.Item name="main_conflict" label="主线冲突"><Input.TextArea rows={5} /></Form.Item>
                <Form.Item name="themes" label="主题"><Select mode="tags" /></Form.Item>
                <Form.Item name="narrative_pov" label="叙事视角">
                  <Select options={[
                    { value: "first_person", label: "第一人称" },
                    { value: "third_person_limited", label: "第三人称有限" },
                    { value: "third_person_omniscient", label: "第三人称全知" },
                  ]} />
                </Form.Item>
                <Form.Item name="continuity_rules" label="连续性规则"><Select mode="tags" /></Form.Item>
                <Form.Item name="forbidden_elements" label="禁止元素"><Select mode="tags" /></Form.Item>
                <Button type="primary" htmlType="submit" icon={<Save size={15} />} loading={saveBible.isPending}>保存核心构架</Button>
              </Form>
            ) : (
              <Empty description="暂无故事圣经，请先生成或创建项目资料" />
            )}
          </Card>
        </div>
      </section>
    </div>
  );
}
