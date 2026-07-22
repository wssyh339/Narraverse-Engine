import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Checkbox, Empty, Form, Input, List, Modal, Select, Space, Switch, Tag, Tooltip, Typography, message } from "antd";
import { BookMarked, ClipboardCheck, FileInput, Lightbulb, PackageOpen, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { studioApi, type ImportNovelPayload, type ReferenceAssetPayload, type ReviewPlan, type ReviewPlanPayload } from "../api/studio";
import type { Note } from "../types/api";

const noteTypeLabels: Record<Note["note_type"], string> = {
  note: "笔记",
  folder: "文件夹",
  inspiration: "灵感卡",
  import_report: "导入报告",
  method_pack: "Method Pack",
  reference_asset: "对标资产",
  review_report: "审稿报告",
};

type MethodPackFormValues = {
  name: string;
  source?: string;
  genre?: string;
  principles?: string;
  chapter_recipe?: string;
  style_rules?: string;
  anti_patterns?: string;
};

type ReferenceAssetFormValues = Omit<ReferenceAssetPayload, "tags"> & { tags?: string };

function splitLines(value?: string): string[] {
  return (value ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

export function NotesStudioPage() {
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["notes", projectId], queryFn: () => studioApi.listNotes(projectId), enabled: !!projectId });
  const [selectedId, setSelectedId] = useState("");
  const [content, setContent] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [methodPackOpen, setMethodPackOpen] = useState(false);
  const [referenceAssetOpen, setReferenceAssetOpen] = useState(false);
  const [reviewPlanOpen, setReviewPlanOpen] = useState(false);
  const [reviewPlan, setReviewPlan] = useState<ReviewPlan | null>(null);
  const [createForm] = Form.useForm<{ title: string; note_type: Note["note_type"] }>();
  const [importForm] = Form.useForm<ImportNovelPayload>();
  const [methodPackForm] = Form.useForm<MethodPackFormValues>();
  const [referenceAssetForm] = Form.useForm<ReferenceAssetFormValues>();
  const [reviewPlanForm] = Form.useForm<ReviewPlanPayload>();
  const notes = query.data?.notes ?? [];
  const selected = useMemo(() => notes.find((note) => note.id === selectedId) ?? notes[0], [notes, selectedId]);
  const methodPackOptions = useMemo(
    () => notes
      .filter((note) => note.note_type === "method_pack")
      .map((note) => ({ value: note.id, label: note.title })),
    [notes],
  );

  useEffect(() => {
    if (selected) {
      setSelectedId(selected.id);
      setContent(selected.content);
    }
  }, [selected?.id]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["notes", projectId] });
  const invalidateImportedProjectState = () => {
    invalidate();
    queryClient.invalidateQueries({ queryKey: ["chapters", projectId] });
    queryClient.invalidateQueries({ queryKey: ["project-state", projectId] });
    queryClient.invalidateQueries({ queryKey: ["canon-proposals", projectId] });
  };
  const create = useMutation({
    mutationFn: (values: { title: string; note_type: Note["note_type"] }) => studioApi.createNote(projectId, values),
    onSuccess: ({ note }) => { message.success("笔记已创建"); setSelectedId(note.id); createForm.resetFields(); invalidate(); },
  });
  const importNovel = useMutation({
    mutationFn: (values: ImportNovelPayload) => studioApi.importNovel(projectId, values),
    onSuccess: ({ import_report, reference_note, canon_proposals }) => {
      message.success(`已导入 ${import_report.chapter_count} 章，生成 ${canon_proposals.length} 条正典候选`);
      setSelectedId(reference_note.id);
      setImportOpen(false);
      importForm.resetFields();
      invalidateImportedProjectState();
    },
  });
  const createMethodPack = useMutation({
    mutationFn: (values: MethodPackFormValues) => studioApi.createMethodPack(projectId, {
      name: values.name,
      source: values.source,
      genre: values.genre,
      principles: splitLines(values.principles),
      chapter_recipe: splitLines(values.chapter_recipe),
      style_rules: splitLines(values.style_rules),
      anti_patterns: splitLines(values.anti_patterns),
      is_pinned: true,
    }),
    onSuccess: ({ method_pack }) => {
      message.success("Method Pack 已保存");
      setSelectedId(method_pack.id);
      setMethodPackOpen(false);
      methodPackForm.resetFields();
      invalidate();
    },
  });
  const createReferenceAsset = useMutation({
    mutationFn: (values: ReferenceAssetFormValues) => studioApi.createReferenceAsset(projectId, {
      ...values,
      tags: splitLines(values.tags),
      method_pack_id: values.method_pack_id || null,
    }),
    onSuccess: ({ reference_asset }) => {
      message.success("对标资产已保存");
      setSelectedId(reference_asset.id);
      setReferenceAssetOpen(false);
      referenceAssetForm.resetFields();
      invalidate();
    },
  });
  const buildReviewPlan = useMutation({
    mutationFn: (values: ReviewPlanPayload) => studioApi.buildReviewPlan(projectId, values),
    onSuccess: ({ review_plan }) => {
      setReviewPlan(review_plan);
      message.success("审稿计划已生成");
    },
  });
  const save = useMutation({
    mutationFn: () => studioApi.updateNote(projectId, selected!.id, { content }),
    onSuccess: () => { message.success("笔记已保存"); invalidate(); },
  });
  const remove = useMutation({
    mutationFn: () => studioApi.deleteNote(projectId, selected!.id),
    onSuccess: () => { message.success("笔记已删除"); setSelectedId(""); invalidate(); },
  });

  if (query.isLoading) return <div className="notes-studio-grid"><div className="studio-panel loading-panel" /></div>;
  if (query.error) return <Alert type="error" showIcon message="无法读取写作笔记" />;

  return (
    <div className="notes-studio-grid">
      <aside className="studio-panel notes-directory">
        <div className="panel-heading">
          <Typography.Text strong>写作笔记</Typography.Text>
          <Space size={4}>
            <Tooltip title="导入已有小说"><Button type="text" icon={<FileInput size={15} />} onClick={() => setImportOpen(true)} /></Tooltip>
            <Tooltip title="新建 Method Pack"><Button type="text" icon={<PackageOpen size={15} />} onClick={() => setMethodPackOpen(true)} /></Tooltip>
            <Tooltip title="保存对标资产"><Button type="text" icon={<BookMarked size={15} />} onClick={() => setReferenceAssetOpen(true)} /></Tooltip>
            <Tooltip title="生成审稿计划"><Button type="text" icon={<ClipboardCheck size={15} />} onClick={() => { setReviewPlan(null); setReviewPlanOpen(true); }} /></Tooltip>
            <Tooltip title="新建笔记"><Button type="text" icon={<Plus size={15} />} onClick={() => Modal.confirm({
              title: "新建笔记",
              content: <Form form={createForm} layout="vertical" initialValues={{ note_type: "note" }}><Form.Item name="title" label="标题" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="note_type" label="类型"><Select options={[{ value: "note", label: "笔记" }, { value: "inspiration", label: "灵感卡" }, { value: "folder", label: "文件夹" }]} /></Form.Item></Form>,
              onOk: () => createForm.validateFields().then((values) => create.mutateAsync(values)),
            })} /></Tooltip>
          </Space>
        </div>
        {notes.length === 0 ? <Empty description="暂无笔记" /> : (
          <List
            size="small"
            dataSource={notes}
            renderItem={(note) => <List.Item className={note.id === selected?.id ? "active-list-item" : ""} onClick={() => setSelectedId(note.id)}>
              <List.Item.Meta
                title={<Space>{note.note_type === "inspiration" ? <Lightbulb size={14} /> : null}{note.note_type === "import_report" ? <FileInput size={14} /> : null}{note.title}{note.is_pinned ? <Tag>置顶</Tag> : null}</Space>}
                description={<Space size={6}><Tag>{noteTypeLabels[note.note_type] ?? note.note_type}</Tag><Typography.Text type="secondary">{note.content.slice(0, 44) || "暂无内容"}</Typography.Text></Space>}
              />
            </List.Item>}
          />
        )}
      </aside>
      <main className="studio-panel notes-editor">
        {selected ? (
          <>
            <div className="panel-heading">
              <div><Typography.Title level={4}>{selected.title}</Typography.Title><Typography.Text type="secondary">笔记默认不会覆盖正文，可在 AI 助手中作为上下文引用。</Typography.Text></div>
              <Space>
                <Switch checkedChildren="已置顶" unCheckedChildren="置顶" checked={selected.is_pinned} onChange={(checked) => studioApi.updateNote(projectId, selected.id, { is_pinned: checked }).then(invalidate)} />
                <Button icon={<Save size={15} />} type="primary" loading={save.isPending} onClick={() => save.mutate()}>保存</Button>
                <Button danger icon={<Trash2 size={15} />} loading={remove.isPending} onClick={() => Modal.confirm({ title: "删除笔记？", onOk: () => remove.mutateAsync() })} />
              </Space>
            </div>
            <Input.TextArea
              className="markdown-editor-textarea"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              placeholder="记录设定、灵感、章节备忘或修改意见。支持 Markdown。"
              style={{ height: 640, resize: "none" }}
            />
          </>
        ) : <Empty description="新建一条笔记或灵感卡开始记录" />}
      </main>
      <Modal
        title="导入已有小说"
        open={importOpen}
        width={760}
        okText="导入"
        cancelText="取消"
        confirmLoading={importNovel.isPending}
        onCancel={() => setImportOpen(false)}
        onOk={() => importForm.validateFields().then((values) => importNovel.mutateAsync(values))}
      >
        <Form
          form={importForm}
          layout="vertical"
          initialValues={{ source_name: "已有作品", target_platform: "", create_canon_proposals: true }}
        >
          <Form.Item name="source_name" label="来源名称" rules={[{ required: true, message: "请输入来源名称" }]}>
            <Input maxLength={120} />
          </Form.Item>
          <Form.Item name="target_platform" label="目标平台">
            <Input maxLength={80} />
          </Form.Item>
          <Form.Item name="text" label="正文文本" rules={[{ required: true, message: "请粘贴正文文本" }]}>
            <Input.TextArea
              placeholder="支持“第1章 标题 / 第一章 标题”等章节标题；未识别标题时会作为单章导入。"
              rows={12}
              showCount
            />
          </Form.Item>
          <Form.Item name="create_canon_proposals" valuePropName="checked">
            <Checkbox>生成一条时间线正典候选</Checkbox>
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title="新建 Method Pack"
        open={methodPackOpen}
        width={720}
        okText="保存"
        cancelText="取消"
        confirmLoading={createMethodPack.isPending}
        onCancel={() => setMethodPackOpen(false)}
        onOk={() => methodPackForm.validateFields().then((values) => createMethodPack.mutateAsync(values))}
      >
        <Form form={methodPackForm} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: "请输入名称" }]}><Input maxLength={160} /></Form.Item>
          <Form.Item name="source" label="来源"><Input maxLength={240} /></Form.Item>
          <Form.Item name="genre" label="类型"><Input maxLength={80} /></Form.Item>
          <Form.Item name="principles" label="原则"><Input.TextArea rows={3} placeholder="每行一条" /></Form.Item>
          <Form.Item name="chapter_recipe" label="章节配方"><Input.TextArea rows={3} placeholder="每行一个步骤" /></Form.Item>
          <Form.Item name="style_rules" label="风格规则"><Input.TextArea rows={3} placeholder="每行一条" /></Form.Item>
          <Form.Item name="anti_patterns" label="反模式"><Input.TextArea rows={3} placeholder="每行一条" /></Form.Item>
        </Form>
      </Modal>
      <Modal
        title="保存对标资产"
        open={referenceAssetOpen}
        width={760}
        okText="保存"
        cancelText="取消"
        confirmLoading={createReferenceAsset.isPending}
        onCancel={() => setReferenceAssetOpen(false)}
        onOk={() => referenceAssetForm.validateFields().then((values) => createReferenceAsset.mutateAsync(values))}
      >
        <Form form={referenceAssetForm} layout="vertical" initialValues={{ asset_type: "chapter_excerpt" }}>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: "请输入标题" }]}><Input maxLength={160} /></Form.Item>
          <Form.Item name="asset_type" label="类型"><Select options={[
            { value: "novel_excerpt", label: "小说片段" },
            { value: "chapter_excerpt", label: "章节片段" },
            { value: "outline", label: "大纲" },
            { value: "review", label: "评审" },
            { value: "style_sample", label: "风格样本" },
          ]} /></Form.Item>
          <Form.Item name="source_name" label="来源"><Input maxLength={160} /></Form.Item>
          <Form.Item name="method_pack_id" label="关联 Method Pack"><Select allowClear options={methodPackOptions} /></Form.Item>
          <Form.Item name="tags" label="标签"><Input.TextArea rows={2} placeholder="每行一个标签" /></Form.Item>
          <Form.Item name="text" label="文本" rules={[{ required: true, message: "请粘贴文本" }]}><Input.TextArea rows={10} showCount /></Form.Item>
        </Form>
      </Modal>
      <Modal
        title="审稿计划"
        open={reviewPlanOpen}
        width={760}
        okText="生成"
        cancelText="关闭"
        confirmLoading={buildReviewPlan.isPending}
        onCancel={() => setReviewPlanOpen(false)}
        onOk={() => reviewPlanForm.validateFields().then((values) => buildReviewPlan.mutateAsync(values))}
      >
        <Form form={reviewPlanForm} layout="vertical" initialValues={{ mode: "lean", scope: "chapter" }}>
          <Form.Item name="mode" label="模式"><Select options={[
            { value: "solo", label: "solo" },
            { value: "lean", label: "lean" },
            { value: "full", label: "full" },
          ]} /></Form.Item>
          <Form.Item name="scope" label="范围"><Select options={[
            { value: "chapter", label: "章节" },
            { value: "outline", label: "大纲" },
            { value: "project", label: "项目" },
          ]} /></Form.Item>
          <Form.Item name="chapter_id" label="章节 ID"><Input /></Form.Item>
          <Form.Item name="method_pack_id" label="Method Pack"><Select allowClear options={methodPackOptions} /></Form.Item>
          <Form.Item name="instruction" label="审稿要求"><Input.TextArea rows={3} /></Form.Item>
        </Form>
        {reviewPlan ? (
          <div className="review-plan-preview">
            <Space wrap>{reviewPlan.agents.map((agent) => <Tag key={agent}>{agent}</Tag>)}</Space>
            <Typography.Paragraph type="secondary">{reviewPlan.write_policy}</Typography.Paragraph>
            <pre>{JSON.stringify(reviewPlan, null, 2)}</pre>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
