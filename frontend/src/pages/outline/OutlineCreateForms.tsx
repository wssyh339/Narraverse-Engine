import { forwardRef, useImperativeHandle } from "react";
import { Form, Input } from "antd";

export interface OutlineCreateFormHandle<T> {
  validate: () => Promise<T>;
}

export interface VolumeCreateValues {
  title: string;
  outline: string;
}

export interface ChapterCreateValues {
  title: string;
  outline: string;
}

export const CreateVolumeForm = forwardRef<OutlineCreateFormHandle<VolumeCreateValues>>(function CreateVolumeForm(_, ref) {
  const [form] = Form.useForm<VolumeCreateValues>();
  useImperativeHandle(ref, () => ({ validate: () => form.validateFields() }), [form]);
  return (
    <Form form={form} layout="vertical">
      <Form.Item name="title" label="分卷名称" rules={[{ required: true }]}>
        <Input />
      </Form.Item>
      <Form.Item name="outline" label="卷纲">
        <Input.TextArea rows={4} />
      </Form.Item>
    </Form>
  );
});

export const CreateChapterForm = forwardRef<OutlineCreateFormHandle<ChapterCreateValues>>(function CreateChapterForm(_, ref) {
  const [form] = Form.useForm<ChapterCreateValues>();
  useImperativeHandle(ref, () => ({ validate: () => form.validateFields() }), [form]);
  return (
    <Form form={form} layout="vertical">
      <Form.Item name="title" label="章节标题" rules={[{ required: true }]}>
        <Input />
      </Form.Item>
      <Form.Item name="outline" label="章纲">
        <Input.TextArea rows={4} />
      </Form.Item>
    </Form>
  );
});
