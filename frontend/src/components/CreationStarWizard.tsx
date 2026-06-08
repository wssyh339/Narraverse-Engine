import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Divider, Drawer, Empty, Form, Input, InputNumber, Select, Space, Steps, Tag, Typography, message } from "antd";
import { Check, Edit3, RefreshCw, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { studioApi, type CreationStarCommitPayload } from "../api/studio";
import type { CreationStarBasicInfo, CreationStarCard } from "../types/api";

const stepItems = [
  { title: "基本信息" },
  { title: "世界观抽卡" },
  { title: "主角人设" },
  { title: "总设定表" },
  { title: "创建书名" },
  { title: "完成创建" },
];

const bibleKeys = ["核心命题", "核心矛盾", "主角长期目标", "最终结局方向", "主线关键词"];
const ruleKeys = ["力量体系", "社会结构", "资源系统", "势力分布", "禁忌规则", "不可违反设定"];

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

export function CreationStarWizard({ projectId, open, onClose, onCommitted }: CreationStarWizardProps) {
  const [form] = Form.useForm<CreationStarBasicInfo>();
  const [step, setStep] = useState(0);
  const [manualInput, setManualInput] = useState("");
  const [basicInfo, setBasicInfo] = useState<CreationStarBasicInfo>({});
  const [worldviewCards, setWorldviewCards] = useState<CreationStarCard[]>([]);
  const [protagonistCards, setProtagonistCards] = useState<CreationStarCard[]>([]);
  const [titleCards, setTitleCards] = useState<CreationStarCard[]>([]);
  const [customTitle, setCustomTitle] = useState("");
  const [customTitleDescription, setCustomTitleDescription] = useState("作者自定义书名，确认后直接写入作品标题。");
  const [promptSnapshots, setPromptSnapshots] = useState<Record<string, Record<string, unknown>>>({});
  const [selectedWorldviewId, setSelectedWorldviewId] = useState("");
  const [selectedProtagonistId, setSelectedProtagonistId] = useState("");
  const [selectedTitleId, setSelectedTitleId] = useState("");
  const [projectBible, setProjectBible] = useState<Record<string, unknown>>({});
  const [worldRules, setWorldRules] = useState<Record<string, unknown>>({});

  const optionsQuery = useQuery({
    queryKey: ["creation-star-options"],
    queryFn: () => studioApi.getCreationStarOptions(),
    enabled: open,
  });

  const selectedWorldview = useMemo(
    () => worldviewCards.find((card) => card.id === selectedWorldviewId) ?? worldviewCards[0],
    [selectedWorldviewId, worldviewCards],
  );
  const selectedProtagonist = useMemo(
    () => protagonistCards.find((card) => card.id === selectedProtagonistId) ?? protagonistCards[0],
    [selectedProtagonistId, protagonistCards],
  );
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
    () => (selectedTitleId === "custom_title" ? customTitleCard : titleCards.find((card) => card.id === selectedTitleId) ?? titleCards[0] ?? customTitleCard),
    [customTitleCard, selectedTitleId, titleCards],
  );

  const drawWorldview = useMutation({
    mutationFn: (payload: CreationStarBasicInfo) =>
      studioApi.drawCreationStar(projectId, { step: "worldview", basic_info: payload, count: 9, manual_input: manualInput }),
    onSuccess: (result) => {
      const cards = result.cards ?? [];
      setWorldviewCards(cards);
      setSelectedWorldviewId(cards[0]?.id ?? "");
      setPromptSnapshots((current) => ({ ...current, worldview: result.prompt_snapshot ?? {} }));
      message.success("世界观卡牌已生成");
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "世界观抽卡失败"),
  });

  const drawProtagonist = useMutation({
    mutationFn: () =>
      studioApi.drawCreationStar(projectId, {
        step: "protagonist",
        basic_info: basicInfo,
        selected_worldview: selectedWorldview ?? {},
        count: 6,
        manual_input: manualInput,
      }),
    onSuccess: (result) => {
      const cards = result.cards ?? [];
      setProtagonistCards(cards);
      setSelectedProtagonistId(cards[0]?.id ?? "");
      setPromptSnapshots((current) => ({ ...current, protagonist: result.prompt_snapshot ?? {} }));
      message.success("主角人设卡牌已生成");
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "主角人设抽卡失败"),
  });

  const drawBible = useMutation({
    mutationFn: () =>
      studioApi.drawCreationStar(projectId, {
        step: "project_bible",
        basic_info: basicInfo,
        selected_worldview: selectedWorldview ?? {},
        selected_protagonist: selectedProtagonist ?? {},
        count: 3,
        manual_input: manualInput,
      }),
    onSuccess: (result) => {
      setProjectBible(result.project_bible ?? {});
      setWorldRules(result.world_rules ?? {});
      setPromptSnapshots((current) => ({ ...current, project_bible: result.prompt_snapshot ?? {} }));
      message.success("总设定表已生成");
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "总设定抽卡失败"),
  });

  const drawTitle = useMutation({
    mutationFn: () =>
      studioApi.drawCreationStar(projectId, {
        step: "title",
        basic_info: basicInfo,
        selected_worldview: selectedWorldview ?? {},
        selected_protagonist: selectedProtagonist ?? {},
        project_bible: projectBible,
        world_rules: worldRules,
        count: 8,
        manual_input: manualInput,
      }),
    onSuccess: (result) => {
      const cards = result.cards ?? [];
      setTitleCards(cards);
      setSelectedTitleId(cards[0]?.id ?? "");
      setPromptSnapshots((current) => ({ ...current, title: result.prompt_snapshot ?? {} }));
      message.success("书名卡牌已生成");
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "书名抽卡失败"),
  });

  const commit = useMutation({
    mutationFn: (payload: CreationStarCommitPayload) => studioApi.commitCreationStar(projectId, payload),
    onSuccess: () => {
      message.success("创作 Star 已写入作品信息和设定集");
      onCommitted();
      onClose();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "创作 Star 提交失败"),
  });

  const startWorldview = async () => {
    const values = await form.validateFields();
    setBasicInfo(values);
    setStep(1);
    await drawWorldview.mutateAsync(values);
  };

  const enterProtagonist = async () => {
    if (!selectedWorldview) {
      message.warning("请先选择或生成一个世界观卡片");
      return;
    }
    setStep(2);
    await drawProtagonist.mutateAsync();
  };

  const enterBible = async () => {
    if (!selectedProtagonist) {
      message.warning("请先选择一个主角人设");
      return;
    }
    setStep(3);
    await drawBible.mutateAsync();
  };

  const enterTitle = async () => {
    setStep(4);
    await drawTitle.mutateAsync();
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

  const updateBible = (key: string, value: unknown) => setProjectBible((current) => ({ ...current, [key]: value }));
  const updateRule = (key: string, value: unknown) => setWorldRules((current) => ({ ...current, [key]: value }));
  const useCustomTitle = () => {
    if (!customTitle.trim()) {
      message.warning("请先填写自定义书名");
      return;
    }
    setSelectedTitleId("custom_title");
    message.success("已选择自定义书名");
  };

  const submitCommit = () => {
    if (!selectedWorldview || !selectedProtagonist) {
      message.warning("请先完成世界观和主角人设选择");
      return;
    }
    if (!selectedTitle?.title) {
      message.warning("请先选择或填写一个书名");
      return;
    }
    commit.mutate({
      basic_info: basicInfo,
      selected_worldview: selectedWorldview,
      selected_protagonist: selectedProtagonist,
      selected_title: selectedTitle ?? {},
      project_bible: projectBible,
      world_rules: worldRules,
      user_note: "创作 Star 抽卡确认",
    });
  };

  const options = optionsQuery.data?.options;
  const renderPromptSnapshot = (key: string) => {
    const prompt_snapshot = promptSnapshots[key];
    if (!prompt_snapshot) return null;
    return (
      <Alert
        type="success"
        showIcon
        className="creation-star-context-alert"
        message="本轮抽卡已读取前序上下文"
        description={text(prompt_snapshot.context_summary).slice(0, 220)}
      />
    );
  };

  const renderBasicInfo = () => (
    <div className="creation-star-step">
      <Alert type="info" showIcon message="先选赛道，再让创作 Star Agent 生成可抽换的世界观卡片。标签支持手动输入。" />
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
        <Form.Item name="target_reader" label="目标读者">
          <Input placeholder="例如：喜欢都市高武、学院流和宗门财阀化设定的读者" />
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
        <Typography.Text strong>决定你这本小说的天花板</Typography.Text>
        <Button icon={<RefreshCw size={15} />} loading={drawWorldview.isPending} onClick={() => drawWorldview.mutate(basicInfo)}>换一批</Button>
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
              <Space wrap className="creation-card-tags">
                {(card.tags ?? []).map((tag) => <Tag key={tag}>{tag}</Tag>)}
              </Space>
              <Typography.Paragraph type="secondary">卖点：{card.selling_point}</Typography.Paragraph>
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
        <Typography.Text strong>基于世界观生成主角人设</Typography.Text>
        <Button icon={<RefreshCw size={15} />} loading={drawProtagonist.isPending} onClick={() => drawProtagonist.mutate()}>换一批</Button>
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

  const renderBible = () => (
    <div className="creation-star-step">
      <div className="creation-star-action-row">
        <Typography.Text strong>项目总设定表与世界观规则表</Typography.Text>
        <Button icon={<RefreshCw size={15} />} loading={drawBible.isPending} onClick={() => drawBible.mutate()}>重抽设定表</Button>
      </div>
      {renderPromptSnapshot("project_bible")}
      <div className="creation-star-two-columns">
        <Card title="项目总设定表">
          {bibleKeys.map((key) => (
            <Form.Item key={key} label={key}>
              <Input.TextArea
                rows={key === "主线关键词" ? 2 : 3}
                value={text(projectBible[key])}
                onChange={(event) => updateBible(key, key === "主线关键词" ? list(event.target.value) : event.target.value)}
              />
            </Form.Item>
          ))}
        </Card>
        <Card title="世界观规则表">
          {ruleKeys.map((key) => (
            <Form.Item key={key} label={key}>
              <Input.TextArea rows={3} value={list(worldRules[key]).join("\n")} onChange={(event) => updateRule(key, list(event.target.value))} />
            </Form.Item>
          ))}
        </Card>
      </div>
    </div>
  );

  const renderTitle = () => (
    <div className="creation-star-step">
      <div className="creation-star-action-row">
        <Typography.Text strong>创建书名</Typography.Text>
        <Button icon={<RefreshCw size={15} />} loading={drawTitle.isPending} onClick={() => drawTitle.mutate()}>换一批</Button>
      </div>
      {renderPromptSnapshot("title")}
      <Card
        className={`creation-card custom-title-card ${selectedTitleId === "custom_title" ? "is-selected" : ""}`}
        title="自定义书名"
        extra={<Tag color={selectedTitleId === "custom_title" ? "green" : "default"}>{selectedTitleId === "custom_title" ? "已选" : "手写"}</Tag>}
      >
        <Input value={customTitle} onChange={(event) => setCustomTitle(event.target.value)} placeholder="直接输入最终书名" />
        <Input.TextArea
          rows={2}
          value={customTitleDescription}
          onChange={(event) => setCustomTitleDescription(event.target.value)}
          placeholder="可选：写下这个书名的卖点或命名理由"
        />
        <Button type="primary" ghost onClick={useCustomTitle}>使用自定义书名</Button>
      </Card>
      {titleCards.length === 0 ? <Empty description="还没有书名卡片" /> : (
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
    </div>
  );

  const renderFinish = () => (
    <div className="creation-star-step">
      <Alert type="warning" showIcon message="提交后会更新作品信息和正式设定集；之后正文生成 Agent 会读取这些设定。" />
      <div className="creation-star-two-columns">
        <Card title="已选世界观"><Typography.Title level={4}>{selectedWorldview?.title}</Typography.Title><Typography.Paragraph>{selectedWorldview?.description}</Typography.Paragraph></Card>
        <Card title="已选主角"><Typography.Title level={4}>{selectedProtagonist?.name}</Typography.Title><Typography.Paragraph>{selectedProtagonist?.summary}</Typography.Paragraph></Card>
      </div>
      <Divider />
      <Card title="已选书名">
        <Typography.Title level={4}>{selectedTitle?.title}</Typography.Title>
        <Typography.Paragraph>{selectedTitle?.description}</Typography.Paragraph>
      </Card>
      <Divider />
      <Card title="即将写入的核心设定">
        <Typography.Paragraph><strong>核心命题：</strong>{text(projectBible["核心命题"])}</Typography.Paragraph>
        <Typography.Paragraph><strong>核心矛盾：</strong>{text(projectBible["核心矛盾"])}</Typography.Paragraph>
        <Typography.Paragraph><strong>不可违反设定：</strong>{list(worldRules["不可违反设定"]).join("；")}</Typography.Paragraph>
      </Card>
    </div>
  );

  const renderStep = () => {
    if (step === 0) return renderBasicInfo();
    if (step === 1) return renderWorldviews();
    if (step === 2) return renderProtagonists();
    if (step === 3) return renderBible();
    if (step === 4) return renderTitle();
    return renderFinish();
  };

  const footer = (
    <Space className="creation-star-footer">
      <Button onClick={step === 0 ? onClose : () => setStep(step - 1)}>{step === 0 ? "关闭" : "上一步"}</Button>
      {step === 0 ? <Button type="primary" icon={<Sparkles size={15} />} loading={drawWorldview.isPending} onClick={startWorldview}>生成世界观抽卡</Button> : null}
      {step === 1 ? <Button type="primary" loading={drawProtagonist.isPending} onClick={enterProtagonist}>生成主角人设</Button> : null}
      {step === 2 ? <Button type="primary" loading={drawBible.isPending} onClick={enterBible}>生成总设定表</Button> : null}
      {step === 3 ? <Button type="primary" loading={drawTitle.isPending} onClick={enterTitle}>生成书名抽卡</Button> : null}
      {step === 4 ? <Button type="primary" onClick={() => setStep(5)}>进入确认</Button> : null}
      {step === 5 ? <Button type="primary" icon={<Check size={15} />} loading={commit.isPending} onClick={submitCommit}>完成创建并写入设定</Button> : null}
    </Space>
  );

  return (
    <Drawer
      title="创作 Star"
      width="92vw"
      open={open}
      onClose={onClose}
      extra={<Tag color="purple">专用创作 Star Agent</Tag>}
      footer={footer}
      className="creation-star-drawer"
      destroyOnClose={false}
    >
      <Steps current={step} items={stepItems} />
      <Divider />
      {optionsQuery.error ? <Alert type="error" showIcon message="无法加载抽卡选项" description="请确认后端服务是否可用。" /> : renderStep()}
    </Drawer>
  );
}
