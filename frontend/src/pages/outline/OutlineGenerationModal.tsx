import { Alert, Button, Form, Input, InputNumber, Modal, Switch, Typography } from "antd";
import type { FormInstance } from "antd";
import type { GenerationMode, InferenceStep, LongOutlineForm, OutlineTopology } from "./types";
import { OutlineInferenceGraph } from "./OutlineInferenceGraph";

interface OutlineGenerationModalProps {
  open: boolean;
  generationMode: GenerationMode;
  generationStarted: boolean;
  form: FormInstance<LongOutlineForm>;
  inferenceSteps: InferenceStep[];
  outlineTopology?: OutlineTopology | null;
  outlinePlan?: Record<string, unknown> | null;
  activeAgentName?: string;
  isPending: boolean;
  hasResult: boolean;
  resultText: string;
  onOk: () => void;
  onConfirmUpdate: () => void;
  onCancel: () => void;
}

export function OutlineGenerationModal({
  open,
  generationMode,
  generationStarted,
  form,
  inferenceSteps,
  outlineTopology,
  outlinePlan,
  activeAgentName,
  isPending,
  hasResult,
  resultText,
  onOk,
  onConfirmUpdate,
  onCancel,
}: OutlineGenerationModalProps) {
  const titleText = generationMode === "outline" ? "生成大纲" : "批量生成章纲";
  const activeStep = inferenceSteps.find((step) => step.agent_name === activeAgentName);
  const change_summary = outlinePlan?.change_summary && typeof outlinePlan.change_summary === "object" ? (outlinePlan.change_summary as Record<string, unknown>) : null;
  const summaryUpdates = Array.isArray(change_summary?.will_update) ? change_summary.will_update.map(String) : [];
  const summaryPreserved = Array.isArray(change_summary?.preserved_manual_settings) ? change_summary.preserved_manual_settings.map(String) : [];
  const createdVolumes = Array.isArray(change_summary?.will_create_volume_numbers) ? change_summary.will_create_volume_numbers.map(String) : [];
  const overwrittenVolumes = Array.isArray(change_summary?.will_overwrite_volume_numbers) ? change_summary.will_overwrite_volume_numbers.map(String) : [];
  return (
    <Modal
      title={generationStarted ? `${titleText} · 推演工作台` : titleText}
      open={open}
      width={generationStarted ? 1260 : 1120}
      transitionName=""
      maskTransitionName=""
      okText={isPending ? "推演中" : generationStarted ? "重新推演" : "确认并开始推演"}
      confirmLoading={isPending}
      okButtonProps={{ disabled: isPending }}
      onOk={onOk}
      onCancel={onCancel}
    >
      {!generationStarted ? (
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
          <Form.Item
            name="use_topology_inference"
            label="拓扑推演"
            valuePropName="checked"
            extra="开启后按 Agent 交接、依赖、产物和审查关系组织推演图；关闭后使用线性 Agent 链，但输出字段和内容量保持一致。"
          >
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
          </Form.Item>
        </Form>
      ) : (
        <div className="outline-generation-workbench">
          <div className="outline-generation-stage">
            <div>
              <Typography.Text type="secondary">推演工作台</Typography.Text>
              <Typography.Title level={4}>{generationMode === "outline" ? "总纲 / 卷纲生成图谱" : "章纲批量生成图谱"}</Typography.Title>
            </div>
            <div className="outline-active-agent">
              <Typography.Text type="secondary">当前激活 Agent</Typography.Text>
              <Typography.Text strong>{activeStep?.role ?? "等待 Agent 启动"}</Typography.Text>
            </div>
          </div>
          <Alert
            type={isPending ? "info" : hasResult ? "success" : "warning"}
            showIcon
            message={isPending ? "多 Agent 正在推演结构" : hasResult ? "推演完成，结果已写入右侧预览区" : "推演链已打开，等待生成结果"}
            description={generationMode === "outline" ? "总纲和卷纲会一起生成；确认更新前不会写入正式卷纲或章节。" : "章纲会根据已确认总纲、卷纲和选中范围生成；确认更新前不会写入章节目录。"}
          />
          <OutlineInferenceGraph inferenceSteps={inferenceSteps} outlineTopology={outlineTopology} activeAgentName={activeAgentName} isPending={isPending} hasResult={hasResult} />
          {hasResult ? (
            <>
              {change_summary ? (
                <section className="outline-change-summary">
                  <div className="outline-section-heading">
                    <Typography.Text strong>确认写入摘要</Typography.Text>
                    <Typography.Text type="secondary">用于确认前检查覆盖范围</Typography.Text>
                  </div>
                  <div className="outline-change-summary-grid">
                    <Typography.Text>将更新：{summaryUpdates.length ? summaryUpdates.join("、") : "暂无字段变更"}</Typography.Text>
                    <Typography.Text>新建卷：{createdVolumes.length ? createdVolumes.join("、") : "无"}</Typography.Text>
                    <Typography.Text>覆盖卷：{overwrittenVolumes.length ? overwrittenVolumes.join("、") : "无"}</Typography.Text>
                    <Typography.Text>保留：{summaryPreserved.length ? summaryPreserved.join("；") : "不覆盖用户手动设定"}</Typography.Text>
                  </div>
                </section>
              ) : null}
              <section className="outline-generation-result">
                <div className="outline-section-heading">
                  <Typography.Text strong>推演结果文本</Typography.Text>
                  <Typography.Text type="secondary">确认后写入正式数据</Typography.Text>
                </div>
                <pre>{resultText || "暂无可显示的生成结果文本。"}</pre>
              </section>
              <div className="outline-generation-confirm">
                <Typography.Text type="secondary">确认后写入正式数据，关闭推演窗口并刷新目录。</Typography.Text>
                <Button type="primary" onClick={onConfirmUpdate}>
                  确认更新
                </Button>
              </div>
            </>
          ) : null}
        </div>
      )}
    </Modal>
  );
}
