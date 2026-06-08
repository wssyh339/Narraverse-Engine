import { Empty, Tag, Typography } from "antd";
import type { InferenceStep } from "./types";
import { statusTag } from "./outlineUtils";

interface OutlineInferenceGraphProps {
  inferenceSteps: InferenceStep[];
  isPending: boolean;
  hasResult: boolean;
}

export function OutlineInferenceGraph({ inferenceSteps, isPending, hasResult }: OutlineInferenceGraphProps) {
  return (
    <section className="outline-inference-panel outline-modal-inference">
      <div className="outline-section-heading">
        <Typography.Text strong>真实 Agent 推演链</Typography.Text>
        <Tag color={isPending ? "processing" : hasResult ? "green" : "default"}>{isPending ? "运行中" : hasResult ? "已完成" : "未开始"}</Tag>
      </div>
      {inferenceSteps.length ? (
        <div className="outline-agent-graph">
          {inferenceSteps.map((step, index) => (
            <div key={`${step.agent_name}-${index}`} className={`outline-agent-node is-${step.status}`}>
              <span className="outline-step-index">{index + 1}</span>
              <div className="outline-agent-copy">
                <Typography.Text strong>{step.role}</Typography.Text>
                <Typography.Text type="secondary">{step.output_key}</Typography.Text>
              </div>
              <div className="outline-agent-state">{statusTag(step.status)}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="outline-agent-empty">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={isPending ? "等待后端返回真实推演记录，完成后展示 outline_swarm.agent_trace" : "暂无真实推演记录"}
          />
        </div>
      )}
    </section>
  );
}
