import { Form, Input, InputNumber, Modal, Typography } from "antd";
import type { FormInstance } from "antd";
import type { GenerationMode, InferenceStep, LongOutlineForm } from "./types";
import { OutlineInferenceGraph } from "./OutlineInferenceGraph";

interface OutlineGenerationModalProps {
  open: boolean;
  generationMode: GenerationMode;
  generationStarted: boolean;
  form: FormInstance<LongOutlineForm>;
  inferenceSteps: InferenceStep[];
  isPending: boolean;
  hasResult: boolean;
  onOk: () => void;
  onCancel: () => void;
}

export function OutlineGenerationModal({
  open,
  generationMode,
  generationStarted,
  form,
  inferenceSteps,
  isPending,
  hasResult,
  onOk,
  onCancel,
}: OutlineGenerationModalProps) {
  return (
    <Modal
      title={generationMode === "outline" ? "生成大纲" : generationMode === "volume" ? "生成卷纲" : "生成章纲"}
      open={open}
      width={1120}
      okText={isPending ? "推演中" : generationStarted ? "重新推演" : "确认并开始推演"}
      confirmLoading={isPending}
      onOk={onOk}
      onCancel={onCancel}
    >
      <Form form={form} layout="vertical" className="outline-preview-form">
        <Typography.Title level={5}>基本信息</Typography.Title>
        <div className="form-grid-2">
          <Form.Item name="title" label="作品名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="genre" label="类型" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="target_reader" label="目标读者">
            <Input />
          </Form.Item>
          <Form.Item name="volume_title" label="当前分卷">
            <Input />
          </Form.Item>
        </div>
        <Form.Item name="premise" label="一句话故事">
          <Input.TextArea rows={2} />
        </Form.Item>
        <Form.Item name="world_setting" label="世界观">
          <Input.TextArea rows={4} />
        </Form.Item>
        <Form.Item name="protagonist" label="主角">
          <Input.TextArea rows={3} />
        </Form.Item>
        <div className="form-grid-2">
          <Form.Item name="target_words" label="目标总字数">
            <InputNumber disabled min={0} className="full-width" />
          </Form.Item>
          <Form.Item name="volume_count" label="卷数" rules={[{ required: true }]}>
            <InputNumber min={1} max={30} className="full-width" />
          </Form.Item>
          <Form.Item name="chapters_per_volume" label="每卷章节数" rules={[{ required: true }]}>
            <InputNumber min={1} max={200} className="full-width" />
          </Form.Item>
          <Form.Item name="chapter_word_target" label="每章字数" rules={[{ required: true }]}>
            <InputNumber min={500} max={20000} step={500} className="full-width" />
          </Form.Item>
        </div>
        <Form.Item name="outline_requirement" label="生成要求">
          <Input.TextArea rows={3} />
        </Form.Item>
        <Form.Item name="custom_input" label="额外自定义输入">
          <Input.TextArea rows={3} />
        </Form.Item>
      </Form>
      {generationStarted ? <OutlineInferenceGraph inferenceSteps={inferenceSteps} isPending={isPending} hasResult={hasResult} /> : null}
    </Modal>
  );
}
