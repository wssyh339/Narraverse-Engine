import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Collapse,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Progress,
  Select,
  Space,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import { Edit3, Plus, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { studioApi, type EntityPayload, type GenerateSettingPayload, type ImportanceLevel, type WorldFactPayload } from "../api/studio";
import type { StoryEntity, WorldFact } from "../types/api";

type GenerateTarget = GenerateSettingPayload["target"];

const importanceOptions = ["core", "major", "medium", "minor"].map((value) => ({ value, label: value }));
const entityTypeOptions = ["location", "organization", "item", "event", "concept", "rule", "clue", "timeline_event"].map((value) => ({ value, label: value }));
const worldFactCategoryOptions = ["geography", "history", "magic_rule", "technology", "politics", "culture", "economy", "religion", "organization", "timeline", "taboo"].map((value) => ({ value, label: value }));

interface FactFormValues {
  category: WorldFactPayload["category"];
  title: string;
  content?: string;
  importance_level: ImportanceLevel;
  importance_score: number;
  confidence: number;
  related_entity_ids?: string;
}

interface EntityFormValues {
  entity_type: EntityPayload["entity_type"];
  name: string;
  importance_level: ImportanceLevel;
  importance_score: number;
  description?: string;
  current_status?: string;
  source?: string;
}

function splitIds(value?: string) {
  return (value ?? "")
    .split(/\n|、|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function factToForm(fact?: WorldFact): Partial<FactFormValues> {
  return fact
    ? {
        category: fact.category as WorldFactPayload["category"],
        title: fact.title,
        content: fact.content,
        importance_level: fact.importance_level as ImportanceLevel,
        importance_score: fact.importance_score,
        confidence: fact.confidence,
        related_entity_ids: fact.related_entity_ids.join("\n"),
      }
    : { category: "timeline", importance_level: "medium", importance_score: 50, confidence: 0.8 };
}

function entityToForm(entity?: StoryEntity): Partial<EntityFormValues> {
  return entity
    ? {
        entity_type: entity.entity_type as EntityPayload["entity_type"],
        name: entity.name,
        importance_level: entity.importance_level as ImportanceLevel,
        importance_score: entity.importance_score,
        description: entity.description,
        current_status: entity.current_status,
        source: entity.source,
      }
    : { entity_type: "item", importance_level: "medium", importance_score: 50, current_status: "active", source: "manual" };
}

function factPayload(values: FactFormValues): WorldFactPayload {
  return {
    category: values.category,
    title: values.title,
    content: values.content ?? "",
    importance_level: values.importance_level,
    importance_score: values.importance_score,
    confidence: values.confidence,
    related_entity_ids: splitIds(values.related_entity_ids),
  };
}

function entityPayload(values: EntityFormValues): EntityPayload {
  return {
    entity_type: values.entity_type,
    name: values.name,
    importance_level: values.importance_level,
    importance_score: values.importance_score,
    description: values.description ?? "",
    current_status: values.current_status || "active",
    source: values.source || "manual",
  };
}

export function WorldPage() {
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const factsQuery = useQuery({ queryKey: ["world", projectId], queryFn: () => studioApi.listWorldFacts(projectId), enabled: !!projectId });
  const entitiesQuery = useQuery({ queryKey: ["entities", projectId], queryFn: () => studioApi.listEntities(projectId), enabled: !!projectId });
  const [editingFact, setEditingFact] = useState<WorldFact | null>(null);
  const [editingEntity, setEditingEntity] = useState<StoryEntity | null>(null);
  const [factOpen, setFactOpen] = useState(false);
  const [entityOpen, setEntityOpen] = useState(false);
  const [generateTarget, setGenerateTarget] = useState<GenerateTarget | null>(null);
  const [factForm] = Form.useForm<FactFormValues>();
  const [entityForm] = Form.useForm<EntityFormValues>();
  const [generateForm] = Form.useForm<{ instruction: string; count: number }>();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["world", projectId] });
    queryClient.invalidateQueries({ queryKey: ["entities", projectId] });
    queryClient.invalidateQueries({ queryKey: ["graph", projectId] });
  };

  const refresh = useMutation({
    mutationFn: () => studioApi.refreshCanon(projectId),
    onSuccess: () => {
      message.success("设定集已刷新");
      invalidate();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "刷新失败"),
  });

  const saveFact = useMutation({
    mutationFn: (values: FactFormValues) => {
      const payload = factPayload(values);
      return editingFact ? studioApi.updateWorldFact(projectId, editingFact.id, payload) : studioApi.createWorldFact(projectId, payload);
    },
    onSuccess: () => {
      message.success(editingFact ? "世界观事实已更新" : "世界观事实已创建");
      setFactOpen(false);
      setEditingFact(null);
      factForm.resetFields();
      invalidate();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "保存失败"),
  });

  const saveEntity = useMutation({
    mutationFn: (values: EntityFormValues) => {
      const payload = entityPayload(values);
      return editingEntity ? studioApi.updateEntity(projectId, editingEntity.id, payload) : studioApi.createEntity(projectId, payload);
    },
    onSuccess: () => {
      message.success(editingEntity ? "实体已更新" : "实体已创建");
      setEntityOpen(false);
      setEditingEntity(null);
      entityForm.resetFields();
      invalidate();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "保存失败"),
  });

  const deleteFact = useMutation({
    mutationFn: (factId: string) => studioApi.deleteWorldFact(projectId, factId),
    onSuccess: () => {
      message.success("世界观事实已删除");
      invalidate();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "删除失败"),
  });

  const deleteEntity = useMutation({
    mutationFn: (entityId: string) => studioApi.deleteEntity(projectId, entityId),
    onSuccess: () => {
      message.success("实体已删除");
      invalidate();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "删除失败"),
  });

  const generate = useMutation({
    mutationFn: (values: { instruction: string; count: number }) =>
      studioApi.generateSettings(projectId, { target: generateTarget ?? "all", instruction: values.instruction, count: values.count }),
    onSuccess: (result) => {
      const total = result.characters.length + result.entities.length + result.world_facts.length;
      message.success(`Agent 已生成 ${total} 条候选设定`);
      setGenerateTarget(null);
      generateForm.resetFields();
      invalidate();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "Agent 生成失败"),
  });

  const groupedFacts = useMemo(() => {
    const map = new Map<string, WorldFact[]>();
    for (const fact of factsQuery.data?.world_facts ?? []) {
      const list = map.get(fact.category) ?? [];
      list.push(fact);
      map.set(fact.category, list);
    }
    return Array.from(map.entries());
  }, [factsQuery.data]);

  const groupedEntities = useMemo(() => {
    const map = new Map<string, StoryEntity[]>();
    for (const entity of entitiesQuery.data?.entities ?? []) {
      const list = map.get(entity.entity_type) ?? [];
      list.push(entity);
      map.set(entity.entity_type, list);
    }
    return Array.from(map.entries());
  }, [entitiesQuery.data]);

  const openFact = (fact?: WorldFact) => {
    setEditingFact(fact ?? null);
    factForm.setFieldsValue(factToForm(fact));
    setFactOpen(true);
  };

  const openEntity = (entity?: StoryEntity) => {
    setEditingEntity(entity ?? null);
    entityForm.setFieldsValue(entityToForm(entity));
    setEntityOpen(true);
  };

  const openGenerate = (target: GenerateTarget) => {
    setGenerateTarget(target);
    generateForm.setFieldsValue({
      count: 3,
      instruction: target === "world_facts" ? "补充第一卷需要遵守的历史、禁忌和能力规则。" : "补充第一卷可复用的重要地点、组织、物件和线索。",
    });
  };

  return (
    <Space direction="vertical" size={18} className="page-stack">
      <div className="page-heading">
        <div>
          <Typography.Title level={2}>世界观与实体</Typography.Title>
          <Typography.Text type="secondary">提前编辑世界规则、地点、组织、物件和线索；创作 Agent 会把它们作为 canon_context 使用。</Typography.Text>
        </div>
        <Space wrap>
          <Button icon={<RefreshCw size={15} />} loading={refresh.isPending} onClick={() => refresh.mutate()}>刷新设定集</Button>
          <Button icon={<Sparkles size={15} />} onClick={() => openGenerate("all")} loading={generate.isPending}>Agent 生成设定</Button>
        </Space>
      </div>

      {factsQuery.error ? <Alert type="error" message="无法读取世界观事实" description={(factsQuery.error as Error).message} showIcon /> : null}
      {entitiesQuery.error ? <Alert type="error" message="无法读取剧情实体" description={(entitiesQuery.error as Error).message} showIcon /> : null}

      <Tabs
        items={[
          {
            key: "facts",
            label: "世界观事实",
            children: (
              <Card
                loading={factsQuery.isLoading}
                title="规则、历史、文化与禁忌"
                extra={<Space><Button icon={<Sparkles size={15} />} onClick={() => openGenerate("world_facts")}>Agent 生成</Button><Button type="primary" icon={<Plus size={15} />} onClick={() => openFact()}>新增事实</Button></Space>}
              >
                {groupedFacts.length === 0 ? (
                  <Empty description="暂无世界观事实，可手动新增或让 Agent 生成候选规则" />
                ) : (
                  <Collapse
                    defaultActiveKey={groupedFacts.map(([category]) => category)}
                    items={groupedFacts.map(([category, facts]) => ({
                      key: category,
                      label: <Space><Tag>{category}</Tag><span>{facts.length} 条</span></Space>,
                      children: (
                        <List
                          dataSource={facts}
                          renderItem={(fact) => (
                            <List.Item
                              actions={[
                                <Button key="edit" type="text" icon={<Edit3 size={15} />} onClick={() => openFact(fact)}>编辑</Button>,
                                <Button
                                  key="delete"
                                  type="text"
                                  danger
                                  icon={<Trash2 size={15} />}
                                  onClick={() => {
                                    Modal.confirm({
                                      title: "删除世界观事实？",
                                      content: `确认删除「${fact.title}」吗？`,
                                      okText: "删除",
                                      okButtonProps: { danger: true },
                                      cancelText: "取消",
                                      onOk: () => deleteFact.mutate(fact.id),
                                    });
                                  }}
                                >
                                  删除
                                </Button>,
                              ]}
                            >
                              <List.Item.Meta title={<Space><span>{fact.title}</span><Tag>{fact.importance_level}</Tag></Space>} description={fact.content || "暂无内容"} />
                              <Space direction="vertical" align="end">
                                <Progress percent={Math.round(fact.confidence * 100)} size="small" />
                                <Typography.Text type="secondary">重要度 {fact.importance_score}</Typography.Text>
                              </Space>
                            </List.Item>
                          )}
                        />
                      ),
                    }))}
                  />
                )}
              </Card>
            ),
          },
          {
            key: "entities",
            label: "实体/物件",
            children: (
              <Card
                loading={entitiesQuery.isLoading}
                title="地点、组织、物件、事件、线索"
                extra={<Space><Button icon={<Sparkles size={15} />} onClick={() => openGenerate("entities")}>Agent 生成</Button><Button type="primary" icon={<Plus size={15} />} onClick={() => openEntity()}>新增实体</Button></Space>}
              >
                {groupedEntities.length === 0 ? (
                  <Empty description="暂无实体，可先新增关键地点、组织、物件或线索" />
                ) : (
                  <Collapse
                    defaultActiveKey={groupedEntities.map(([type]) => type)}
                    items={groupedEntities.map(([type, entities]) => ({
                      key: type,
                      label: <Space><Tag>{type}</Tag><span>{entities.length} 个</span></Space>,
                      children: (
                        <List
                          dataSource={entities}
                          renderItem={(entity) => (
                            <List.Item
                              actions={[
                                <Button key="edit" type="text" icon={<Edit3 size={15} />} onClick={() => openEntity(entity)}>编辑</Button>,
                                <Button
                                  key="delete"
                                  type="text"
                                  danger
                                  icon={<Trash2 size={15} />}
                                  onClick={() => {
                                    Modal.confirm({
                                      title: "删除实体？",
                                      content: `确认删除「${entity.name}」吗？`,
                                      okText: "删除",
                                      okButtonProps: { danger: true },
                                      cancelText: "取消",
                                      onOk: () => deleteEntity.mutate(entity.id),
                                    });
                                  }}
                                >
                                  删除
                                </Button>,
                              ]}
                            >
                              <List.Item.Meta title={<Space><span>{entity.name}</span><Tag>{entity.importance_level}</Tag></Space>} description={entity.description || "暂无描述"} />
                              <Space direction="vertical" align="end">
                                <Typography.Text type="secondary">重要度 {entity.importance_score}</Typography.Text>
                                <Tag>{entity.current_status}</Tag>
                              </Space>
                            </List.Item>
                          )}
                        />
                      ),
                    }))}
                  />
                )}
              </Card>
            ),
          },
        ]}
      />

      <Modal
        title={editingFact ? `编辑事实：${editingFact.title}` : "新增世界观事实"}
        open={factOpen}
        okText="保存"
        cancelText="取消"
        confirmLoading={saveFact.isPending}
        onCancel={() => setFactOpen(false)}
        onOk={() => factForm.submit()}
      >
        <Form form={factForm} layout="vertical" initialValues={factToForm()} onFinish={(values) => saveFact.mutate(values)}>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: "请输入标题" }]}><Input /></Form.Item>
          <Form.Item name="category" label="分类"><Select options={worldFactCategoryOptions} /></Form.Item>
          <Form.Item name="content" label="内容"><Input.TextArea rows={4} /></Form.Item>
          <Space className="full-width" align="start">
            <Form.Item name="importance_level" label="重要度等级"><Select options={importanceOptions} style={{ width: 150 }} /></Form.Item>
            <Form.Item name="importance_score" label="重要度分数"><InputNumber min={0} max={100} /></Form.Item>
            <Form.Item name="confidence" label="置信度"><InputNumber min={0} max={1} step={0.05} /></Form.Item>
          </Space>
          <Form.Item name="related_entity_ids" label="关联实体 ID（每行一个）"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>

      <Modal
        title={editingEntity ? `编辑实体：${editingEntity.name}` : "新增剧情实体"}
        open={entityOpen}
        okText="保存"
        cancelText="取消"
        confirmLoading={saveEntity.isPending}
        onCancel={() => setEntityOpen(false)}
        onOk={() => entityForm.submit()}
      >
        <Form form={entityForm} layout="vertical" initialValues={entityToForm()} onFinish={(values) => saveEntity.mutate(values)}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: "请输入名称" }]}><Input /></Form.Item>
          <Form.Item name="entity_type" label="类型"><Select options={entityTypeOptions} /></Form.Item>
          <Form.Item name="description" label="描述"><Input.TextArea rows={4} /></Form.Item>
          <Space className="full-width" align="start">
            <Form.Item name="importance_level" label="重要度等级"><Select options={importanceOptions} style={{ width: 150 }} /></Form.Item>
            <Form.Item name="importance_score" label="重要度分数"><InputNumber min={0} max={100} /></Form.Item>
          </Space>
          <Form.Item name="current_status" label="当前状态"><Input /></Form.Item>
          <Form.Item name="source" label="来源"><Input /></Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Agent 辅助生成设定"
        open={!!generateTarget}
        okText="生成"
        cancelText="取消"
        confirmLoading={generate.isPending}
        onCancel={() => setGenerateTarget(null)}
        onOk={() => generateForm.submit()}
      >
        <Form form={generateForm} layout="vertical" initialValues={{ count: 3 }} onFinish={(values) => generate.mutate(values)}>
          <Form.Item name="instruction" label="生成要求"><Input.TextArea rows={4} /></Form.Item>
          <Form.Item name="count" label="数量"><InputNumber min={1} max={12} className="full-width" /></Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
