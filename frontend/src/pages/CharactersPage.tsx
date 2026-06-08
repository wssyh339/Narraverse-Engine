import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { Edit3, Plus, Sparkles, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { studioApi, type CharacterPayload, type ImportanceLevel, type RoleType } from "../api/studio";
import type { Character } from "../types/api";

interface CharacterFormValues {
  name: string;
  role_type: RoleType;
  importance_level: ImportanceLevel;
  importance_score: number;
  summary?: string;
  appearance?: string;
  personality?: string;
  goals?: string;
  motivations?: string;
  secrets?: string;
  abilities?: string;
  weaknesses?: string;
  character_arc?: string;
  current_status?: string;
  updated_reason?: string;
}

const importanceOptions = ["all", "core", "major", "medium", "minor"].map((value) => ({ value, label: value }));
const roleOptions = ["protagonist", "antagonist", "supporting", "minor"].map((value) => ({ value, label: value }));

function linesToArray(value?: string) {
  return (value ?? "")
    .split(/\n|、|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function arrayToLines(value?: string[]) {
  return (value ?? []).join("\n");
}

function toPayload(values: CharacterFormValues): CharacterPayload {
  return {
    ...values,
    summary: values.summary ?? "",
    appearance: values.appearance ?? "",
    personality: values.personality ?? "",
    goals: linesToArray(values.goals),
    motivations: linesToArray(values.motivations),
    secrets: linesToArray(values.secrets),
    abilities: linesToArray(values.abilities),
    weaknesses: linesToArray(values.weaknesses),
    current_status: values.current_status || "active",
    updated_reason: values.updated_reason || "manual",
  };
}

function toFormValues(character?: Character): Partial<CharacterFormValues> {
  if (!character) {
    return {
      role_type: "supporting",
      importance_level: "medium",
      importance_score: 50,
      current_status: "active",
    };
  }
  return {
    name: character.name,
    role_type: character.role_type as RoleType,
    importance_level: character.importance_level,
    importance_score: character.importance_score,
    summary: character.summary,
    appearance: character.appearance,
    personality: character.personality,
    goals: arrayToLines(character.goals),
    motivations: arrayToLines(character.motivations),
    secrets: arrayToLines(character.secrets),
    abilities: arrayToLines(character.abilities),
    weaknesses: arrayToLines(character.weaknesses),
    character_arc: character.character_arc,
    current_status: character.current_status,
    updated_reason: character.updated_reason,
  };
}

export function CharactersPage() {
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const [importance, setImportance] = useState<string>("all");
  const [editing, setEditing] = useState<Character | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [form] = Form.useForm<CharacterFormValues>();
  const [generateForm] = Form.useForm<{ instruction: string; count: number }>();

  const query = useQuery({ queryKey: ["characters", projectId], queryFn: () => studioApi.listCharacters(projectId), enabled: !!projectId });
  const characters = useMemo(() => {
    const rows = query.data?.characters ?? [];
    return importance === "all" ? rows : rows.filter((item) => item.importance_level === importance);
  }, [query.data, importance]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["characters", projectId] });
    queryClient.invalidateQueries({ queryKey: ["graph", projectId] });
  };

  const saveMutation = useMutation({
    mutationFn: (values: CharacterFormValues) => {
      const payload = toPayload(values);
      return editing ? studioApi.updateCharacter(projectId, editing.id, payload) : studioApi.createCharacter(projectId, payload);
    },
    onSuccess: () => {
      message.success(editing ? "角色卡已更新" : "角色卡已创建");
      setDrawerOpen(false);
      setEditing(null);
      form.resetFields();
      invalidate();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "角色卡保存失败"),
  });

  const deleteMutation = useMutation({
    mutationFn: (characterId: string) => studioApi.deleteCharacter(projectId, characterId),
    onSuccess: () => {
      message.success("角色卡已删除");
      invalidate();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "删除失败"),
  });

  const generateMutation = useMutation({
    mutationFn: (values: { instruction: string; count: number }) =>
      studioApi.generateSettings(projectId, { target: "characters", instruction: values.instruction, count: values.count }),
    onSuccess: (result) => {
      message.success(`Agent 已生成 ${result.characters.length} 张候选角色卡`);
      setGenerateOpen(false);
      generateForm.resetFields();
      invalidate();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "Agent 生成失败"),
  });

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue(toFormValues());
    setDrawerOpen(true);
  };

  const openEdit = (character: Character) => {
    setEditing(character);
    form.setFieldsValue(toFormValues(character));
    setDrawerOpen(true);
  };

  return (
    <Space direction="vertical" size={18} className="page-stack">
      <div className="page-heading">
        <div>
          <Typography.Title level={2}>角色卡</Typography.Title>
          <Typography.Text type="secondary">先建立角色重要度、目标、关系和成长弧；创作 Agent 会在生成前读取这些设定。</Typography.Text>
        </div>
        <Space wrap>
          <Select value={importance} style={{ width: 150 }} onChange={setImportance} options={importanceOptions} />
          <Button icon={<Sparkles size={15} />} onClick={() => setGenerateOpen(true)} loading={generateMutation.isPending}>
            Agent 生成
          </Button>
          <Button type="primary" icon={<Plus size={15} />} onClick={openCreate}>
            新增角色
          </Button>
        </Space>
      </div>

      {query.error ? <Alert type="error" message="无法读取角色卡" description={(query.error as Error).message} showIcon /> : null}

      <Row gutter={[16, 16]}>
        {query.isLoading ? <Col span={24}><Card loading /></Col> : null}
        {!query.isLoading && characters.length === 0 ? <Col span={24}><Card><Empty description="暂无角色，可手动新增或让 Agent 先生成候选角色卡" /></Card></Col> : null}
        {characters.map((character) => (
          <Col key={character.id} xs={24} lg={12}>
            <Card
              title={<Space><span>{character.name}</span><Tag>{character.role_type}</Tag></Space>}
              extra={<Tag color={character.importance_level === "core" ? "red" : "blue"}>{character.importance_level}</Tag>}
              actions={[
                <Button key="edit" type="text" icon={<Edit3 size={15} />} onClick={() => openEdit(character)}>编辑</Button>,
                <Button
                  key="delete"
                  type="text"
                  danger
                  icon={<Trash2 size={15} />}
                  loading={deleteMutation.isPending}
                  onClick={() => {
                    Modal.confirm({
                      title: "删除角色卡？",
                      content: `确认删除「${character.name}」吗？对应图谱节点也会移除。`,
                      okText: "删除",
                      okButtonProps: { danger: true },
                      cancelText: "取消",
                      onOk: () => deleteMutation.mutate(character.id),
                    });
                  }}
                >
                  删除
                </Button>,
              ]}
            >
              <Space direction="vertical" className="full-width">
                <Typography.Paragraph>{character.summary || "暂无摘要"}</Typography.Paragraph>
                <Progress percent={character.importance_score} size="small" />
                <List
                  size="small"
                  dataSource={[
                    ["目标", character.goals.join("、") || "暂无"],
                    ["动机", character.motivations.join("、") || "暂无"],
                    ["性格", character.personality || "暂无"],
                    ["成长弧", character.character_arc || "暂无"],
                    ["状态", character.current_status || "暂无"],
                  ]}
                  renderItem={([label, value]) => <List.Item><strong>{label}</strong><span>{value}</span></List.Item>}
                />
              </Space>
            </Card>
          </Col>
        ))}
      </Row>

      <Drawer
        title={editing ? `编辑角色：${editing.name}` : "新增角色卡"}
        open={drawerOpen}
        width={620}
        onClose={() => setDrawerOpen(false)}
        extra={<Button type="primary" loading={saveMutation.isPending} onClick={() => form.submit()}>保存</Button>}
      >
        <Form form={form} layout="vertical" onFinish={(values) => saveMutation.mutate(values)} initialValues={toFormValues()}>
          <Row gutter={12}>
            <Col span={14}><Form.Item name="name" label="姓名" rules={[{ required: true, message: "请输入角色姓名" }]}><Input /></Form.Item></Col>
            <Col span={10}><Form.Item name="role_type" label="角色类型"><Select options={roleOptions} /></Form.Item></Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="importance_level" label="重要度等级"><Select options={importanceOptions.filter((item) => item.value !== "all")} /></Form.Item></Col>
            <Col span={12}><Form.Item name="importance_score" label="重要度分数"><InputNumber min={0} max={100} className="full-width" /></Form.Item></Col>
          </Row>
          <Form.Item name="summary" label="角色摘要"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="appearance" label="外貌/标志"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="personality" label="性格"><Input.TextArea rows={2} /></Form.Item>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="goals" label="目标（每行一条）"><Input.TextArea rows={4} /></Form.Item></Col>
            <Col span={12}><Form.Item name="motivations" label="动机（每行一条）"><Input.TextArea rows={4} /></Form.Item></Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="secrets" label="秘密（每行一条）"><Input.TextArea rows={3} /></Form.Item></Col>
            <Col span={12}><Form.Item name="weaknesses" label="弱点（每行一条）"><Input.TextArea rows={3} /></Form.Item></Col>
          </Row>
          <Form.Item name="abilities" label="能力/资源（每行一条）"><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="character_arc" label="成长轨迹"><Input.TextArea rows={3} /></Form.Item>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="current_status" label="当前状态"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="updated_reason" label="更新原因"><Input /></Form.Item></Col>
          </Row>
        </Form>
      </Drawer>

      <Modal
        title="Agent 辅助生成角色卡"
        open={generateOpen}
        confirmLoading={generateMutation.isPending}
        okText="生成"
        cancelText="取消"
        onCancel={() => setGenerateOpen(false)}
        onOk={() => generateForm.submit()}
      >
        <Form
          form={generateForm}
          layout="vertical"
          initialValues={{ count: 3, instruction: "补充第一卷可用的核心盟友、隐秘对手和线索见证人。" }}
          onFinish={(values) => generateMutation.mutate(values)}
        >
          <Form.Item name="instruction" label="生成要求"><Input.TextArea rows={4} /></Form.Item>
          <Form.Item name="count" label="数量"><InputNumber min={1} max={12} className="full-width" /></Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
