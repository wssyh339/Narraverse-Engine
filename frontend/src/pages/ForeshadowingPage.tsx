import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Row,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { CheckCircle, Edit3, Plus, Sparkles, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { studioApi, type ForeshadowingPayload, type ForeshadowingSuggestion, type ImportanceLevel } from "../api/studio";
import type { ForeshadowingItem } from "../types/api";

type HookStatus = ForeshadowingItem["payoff_status"];

interface HookFormValues {
  content: string;
  chapter_id?: string;
  planted_chapter_id?: string;
  planned_payoff_chapter_id?: string;
  planned_payoff?: string;
  payoff_status: HookStatus;
  importance_level: ImportanceLevel;
  importance_score: number;
  related_character_ids?: string;
  related_entity_ids?: string;
  source: "manual" | "agent";
}

const statusOptions: Array<{ value: HookStatus | "all"; label: string }> = [
  { value: "all", label: "全部状态" },
  { value: "planned", label: "计划中" },
  { value: "planted", label: "已预埋" },
  { value: "paid_off", label: "已回收" },
  { value: "abandoned", label: "废弃" },
  { value: "candidate", label: "候选" },
];
const importanceOptions = ["all", "core", "major", "medium", "minor"].map((value) => ({ value, label: value }));

function idsToLines(ids?: string[]) {
  return (ids ?? []).join("\n");
}

function linesToIds(value?: string) {
  return (value ?? "")
    .split(/\n|、|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toFormValues(item?: ForeshadowingItem): Partial<HookFormValues> {
  return item
    ? {
        content: item.content,
        chapter_id: item.chapter_id ?? undefined,
        planted_chapter_id: item.planted_chapter_id ?? undefined,
        planned_payoff_chapter_id: item.planned_payoff_chapter_id ?? undefined,
        planned_payoff: item.planned_payoff,
        payoff_status: item.payoff_status,
        importance_level: item.importance_level,
        importance_score: item.importance_score,
        related_character_ids: idsToLines(item.related_character_ids),
        related_entity_ids: idsToLines(item.related_entity_ids),
        source: item.source,
      }
    : { payoff_status: "planned", importance_level: "medium", importance_score: 50, source: "manual" };
}

function toPayload(values: HookFormValues): ForeshadowingPayload {
  return {
    content: values.content,
    chapter_id: values.chapter_id || null,
    planted_chapter_id: values.planted_chapter_id || values.chapter_id || null,
    planned_payoff_chapter_id: values.planned_payoff_chapter_id || null,
    planned_payoff: values.planned_payoff ?? "",
    payoff_status: values.payoff_status,
    importance_level: values.importance_level,
    importance_score: values.importance_score,
    related_character_ids: linesToIds(values.related_character_ids),
    related_entity_ids: linesToIds(values.related_entity_ids),
    source: values.source,
  };
}

export function ForeshadowingPage() {
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<HookStatus | "all">("all");
  const [importance, setImportance] = useState<string>("all");
  const [editing, setEditing] = useState<ForeshadowingItem | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [payoffTarget, setPayoffTarget] = useState<ForeshadowingItem | null>(null);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<ForeshadowingSuggestion[]>([]);
  const [form] = Form.useForm<HookFormValues>();
  const [payoffForm] = Form.useForm<{ actual_payoff_chapter_id: string; payoff_note: string }>();
  const [suggestForm] = Form.useForm<{ chapter_id?: string; instruction: string }>();

  const hooksQuery = useQuery({ queryKey: ["foreshadowing", projectId], queryFn: () => studioApi.listForeshadowing(projectId), enabled: !!projectId });
  const chaptersQuery = useQuery({ queryKey: ["chapters", projectId], queryFn: () => studioApi.listChapters(projectId), enabled: !!projectId });
  const chapterOptions = (chaptersQuery.data?.chapters ?? []).map((chapter) => ({ value: chapter.id, label: `${chapter.chapter_no}. ${chapter.title}` }));

  const filtered = useMemo(() => {
    return (hooksQuery.data?.foreshadowing_items ?? []).filter((item) => {
      const statusMatched = status === "all" || item.payoff_status === status;
      const importanceMatched = importance === "all" || item.importance_level === importance;
      return statusMatched && importanceMatched;
    });
  }, [hooksQuery.data, status, importance]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["foreshadowing", projectId] });
    queryClient.invalidateQueries({ queryKey: ["state", projectId] });
    queryClient.invalidateQueries({ queryKey: ["graph", projectId] });
  };

  const save = useMutation({
    mutationFn: (values: HookFormValues) => {
      const payload = toPayload(values);
      return editing ? studioApi.updateForeshadowing(projectId, editing.id, payload) : studioApi.createForeshadowing(projectId, payload);
    },
    onSuccess: () => {
      message.success(editing ? "伏笔已更新" : "伏笔已创建");
      setDrawerOpen(false);
      setEditing(null);
      form.resetFields();
      invalidate();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "伏笔保存失败"),
  });

  const remove = useMutation({
    mutationFn: (itemId: string) => studioApi.deleteForeshadowing(projectId, itemId),
    onSuccess: () => {
      message.success("伏笔已删除");
      invalidate();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "删除失败"),
  });

  const payoff = useMutation({
    mutationFn: (values: { actual_payoff_chapter_id: string; payoff_note: string }) => {
      if (!payoffTarget) {
        throw new Error("请选择伏笔");
      }
      return studioApi.payoffForeshadowing(projectId, payoffTarget.id, values.actual_payoff_chapter_id, values.payoff_note);
    },
    onSuccess: () => {
      message.success("伏笔已标记回收");
      setPayoffTarget(null);
      payoffForm.resetFields();
      invalidate();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "回收失败"),
  });

  const suggest = useMutation({
    mutationFn: (values: { chapter_id?: string; instruction: string }) => studioApi.suggestForeshadowing(projectId, values.chapter_id, values.instruction),
    onSuccess: (result) => {
      setSuggestions(result.suggestions);
      message.success("Agent 已给出伏笔建议");
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "生成建议失败"),
  });

  const createFromSuggestion = (suggestion: ForeshadowingSuggestion) => {
    studioApi
      .createForeshadowing(projectId, { ...suggestion, payoff_status: "planned" })
      .then(() => {
        message.success("已写入候选伏笔");
        setSuggestOpen(false);
        setSuggestions([]);
        invalidate();
      })
      .catch((error: unknown) => message.error(error instanceof Error ? error.message : "写入失败"));
  };

  const openEditor = (item?: ForeshadowingItem) => {
    setEditing(item ?? null);
    form.setFieldsValue(toFormValues(item));
    setDrawerOpen(true);
  };

  return (
    <Space direction="vertical" size={18} className="page-stack">
      <div className="page-heading">
        <div>
          <Typography.Title level={2}>伏笔管理</Typography.Title>
          <Typography.Text type="secondary">预埋、追踪和回收伏笔；Agent 只提供建议，用户确认后才写入设定。</Typography.Text>
        </div>
        <Space wrap>
          <Select value={status} style={{ width: 140 }} options={statusOptions} onChange={setStatus} />
          <Select value={importance} style={{ width: 140 }} options={importanceOptions} onChange={setImportance} />
          <Button icon={<Sparkles size={15} />} onClick={() => setSuggestOpen(true)}>Agent 建议</Button>
          <Button type="primary" icon={<Plus size={15} />} onClick={() => openEditor()}>新增伏笔</Button>
        </Space>
      </div>

      {hooksQuery.error ? <Alert type="error" message="无法读取伏笔列表" description={(hooksQuery.error as Error).message} showIcon /> : null}
      <Card loading={hooksQuery.isLoading}>
        {filtered.length === 0 ? (
          <Empty description="暂无符合筛选条件的伏笔" />
        ) : (
          <List
            dataSource={filtered}
            renderItem={(item) => (
              <List.Item
                actions={[
                  <Button key="payoff" type="text" icon={<CheckCircle size={15} />} disabled={item.payoff_status === "paid_off"} onClick={() => setPayoffTarget(item)}>回收</Button>,
                  <Button key="edit" type="text" icon={<Edit3 size={15} />} onClick={() => openEditor(item)}>编辑</Button>,
                  <Button
                    key="delete"
                    type="text"
                    danger
                    icon={<Trash2 size={15} />}
                    onClick={() => Modal.confirm({
                      title: "删除伏笔？",
                      content: item.content,
                      okText: "删除",
                      okButtonProps: { danger: true },
                      cancelText: "取消",
                      onOk: () => remove.mutateAsync(item.id),
                    })}
                  >
                    删除
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={<Space><span>{item.content}</span><Tag>{item.payoff_status}</Tag><Tag>{item.importance_level}</Tag></Space>}
                  description={item.planned_payoff || "暂无计划回收说明"}
                />
                <Typography.Text type="secondary">重要度 {item.importance_score}</Typography.Text>
              </List.Item>
            )}
          />
        )}
      </Card>

      <Modal
        title={editing ? "编辑伏笔" : "新增伏笔"}
        open={drawerOpen}
        width={720}
        okText="保存"
        cancelText="取消"
        confirmLoading={save.isPending}
        onCancel={() => setDrawerOpen(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" initialValues={toFormValues()} onFinish={(values) => save.mutate(values)}>
          <Form.Item name="content" label="伏笔内容" rules={[{ required: true, message: "请输入伏笔内容" }]}><Input.TextArea rows={3} /></Form.Item>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="chapter_id" label="关联章节"><Select allowClear options={chapterOptions} /></Form.Item></Col>
            <Col span={12}><Form.Item name="planned_payoff_chapter_id" label="计划回收章节"><Select allowClear options={chapterOptions} /></Form.Item></Col>
          </Row>
          <Form.Item name="planned_payoff" label="计划回收方式"><Input.TextArea rows={3} /></Form.Item>
          <Row gutter={12}>
            <Col span={8}><Form.Item name="payoff_status" label="状态"><Select options={statusOptions.filter((item) => item.value !== "all")} /></Form.Item></Col>
            <Col span={8}><Form.Item name="importance_level" label="重要度"><Select options={importanceOptions.filter((item) => item.value !== "all")} /></Form.Item></Col>
            <Col span={8}><Form.Item name="importance_score" label="重要度分数"><InputNumber min={0} max={100} className="full-width" /></Form.Item></Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="related_character_ids" label="关联角色 ID（每行一个）"><Input.TextArea rows={3} /></Form.Item></Col>
            <Col span={12}><Form.Item name="related_entity_ids" label="关联实体 ID（每行一个）"><Input.TextArea rows={3} /></Form.Item></Col>
          </Row>
          <Form.Item name="source" label="来源"><Select options={[{ value: "manual", label: "manual" }, { value: "agent", label: "agent" }]} /></Form.Item>
        </Form>
      </Modal>

      <Modal
        title="标记伏笔回收"
        open={!!payoffTarget}
        okText="回收"
        cancelText="取消"
        confirmLoading={payoff.isPending}
        onCancel={() => setPayoffTarget(null)}
        onOk={() => payoffForm.submit()}
      >
        <Form form={payoffForm} layout="vertical" onFinish={(values) => payoff.mutate(values)}>
          <Form.Item name="actual_payoff_chapter_id" label="实际回收章节" rules={[{ required: true, message: "请选择实际回收章节" }]}><Select options={chapterOptions} /></Form.Item>
          <Form.Item name="payoff_note" label="回收说明"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Agent 建议伏笔"
        open={suggestOpen}
        width={720}
        okText="生成建议"
        cancelText="关闭"
        confirmLoading={suggest.isPending}
        onCancel={() => setSuggestOpen(false)}
        onOk={() => suggestForm.submit()}
      >
        <Form form={suggestForm} layout="vertical" initialValues={{ instruction: "围绕当前章节预埋三条可公平回收的伏笔。" }} onFinish={(values) => suggest.mutate(values)}>
          <Form.Item name="chapter_id" label="参考章节"><Select allowClear options={chapterOptions} /></Form.Item>
          <Form.Item name="instruction" label="生成要求"><Input.TextArea rows={3} /></Form.Item>
        </Form>
        <List
          style={{ marginTop: 16 }}
          dataSource={suggestions}
          renderItem={(item) => (
            <List.Item actions={[<Button key="use" type="link" onClick={() => createFromSuggestion(item)}>写入伏笔表</Button>]}>
              <List.Item.Meta title={item.content} description={item.planned_payoff} />
              <Tag>{item.importance_level}</Tag>
            </List.Item>
          )}
        />
      </Modal>
    </Space>
  );
}
