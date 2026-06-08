import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Empty, Form, Input, List, Modal, Select, Space, Switch, Tag, Typography, message } from "antd";
import { Lightbulb, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { studioApi } from "../api/studio";
import type { Note } from "../types/api";

export function NotesStudioPage() {
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["notes", projectId], queryFn: () => studioApi.listNotes(projectId), enabled: !!projectId });
  const [selectedId, setSelectedId] = useState("");
  const [content, setContent] = useState("");
  const [createForm] = Form.useForm<{ title: string; note_type: Note["note_type"] }>();
  const notes = query.data?.notes ?? [];
  const selected = useMemo(() => notes.find((note) => note.id === selectedId) ?? notes[0], [notes, selectedId]);

  useEffect(() => {
    if (selected) {
      setSelectedId(selected.id);
      setContent(selected.content);
    }
  }, [selected?.id]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["notes", projectId] });
  const create = useMutation({
    mutationFn: (values: { title: string; note_type: Note["note_type"] }) => studioApi.createNote(projectId, values),
    onSuccess: ({ note }) => { message.success("笔记已创建"); setSelectedId(note.id); createForm.resetFields(); invalidate(); },
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
          <Button type="text" icon={<Plus size={15} />} onClick={() => Modal.confirm({
            title: "新建笔记",
            content: <Form form={createForm} layout="vertical" initialValues={{ note_type: "note" }}><Form.Item name="title" label="标题" rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="note_type" label="类型"><Select options={[{ value: "note", label: "笔记" }, { value: "inspiration", label: "灵感卡" }, { value: "folder", label: "文件夹" }]} /></Form.Item></Form>,
            onOk: () => createForm.validateFields().then((values) => create.mutateAsync(values)),
          })} />
        </div>
        {notes.length === 0 ? <Empty description="暂无笔记" /> : (
          <List
            size="small"
            dataSource={notes}
            renderItem={(note) => <List.Item className={note.id === selected?.id ? "active-list-item" : ""} onClick={() => setSelectedId(note.id)}>
              <List.Item.Meta title={<Space>{note.note_type === "inspiration" ? <Lightbulb size={14} /> : null}{note.title}{note.is_pinned ? <Tag>置顶</Tag> : null}</Space>} description={note.content.slice(0, 50) || "暂无内容"} />
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
    </div>
  );
}
