import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Descriptions, Empty, List, Progress, Space, Tag, Typography } from "antd";
import { useParams } from "react-router-dom";
import { studioApi } from "../api/studio";
import type { AgentRun } from "../types/api";

const terminal = new Set(["succeeded", "failed", "cancelled"]);

type JsonRecord = Record<string, unknown>;

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function textValue(value: unknown, fallback = "未知") {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function payloadJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function isOutlineDebateRun(run: AgentRun) {
  return run.agent_name.startsWith("outline_debate/") || asRecord(run.input_payload).source === "outline_debate";
}

function llmFallbackLabel(meta: JsonRecord) {
  const source = textValue(meta.source, "");
  if (typeof meta.used_remote_model === "boolean") return meta.used_remote_model ? "否" : "是";
  if (source === "local_fallback") return "是";
  if (source === "remote_api") return "否";
  return "未知";
}

function llmSourceColor(source: string) {
  if (source === "remote_api") return "green";
  if (source === "local_fallback") return "gold";
  return "default";
}

function renderTraceEvent(event: unknown, index: number) {
  const item = asRecord(event);
  return (
    <List.Item>
      <Space direction="vertical" size={2}>
        <Space wrap>
          <Tag>{textValue(item.event_type, `事件 ${index + 1}`)}</Tag>
          <Typography.Text type="secondary">{textValue(item.created_at, "")}</Typography.Text>
        </Space>
        <Typography.Text>{textValue(item.message, "无消息")}</Typography.Text>
      </Space>
    </List.Item>
  );
}

function renderAgentRunDetails(run: AgentRun) {
  const output = asRecord(run.output_payload);
  const input = asRecord(run.input_payload);
  const llm = asRecord(output._llm);
  const source = textValue(llm.source, "unknown");
  const traceEvents = asArray(output.trace_events);
  const debateRun = isOutlineDebateRun(run);

  return (
    <Space direction="vertical" size={12} className="agent-run-details">
      <Space wrap>
        <Tag color={debateRun ? "purple" : "blue"}>{debateRun ? "outline_debate" : "agent"}</Tag>
        <Tag color={llmSourceColor(source)}>LLM 来源：{source}</Tag>
        <Tag color={llmFallbackLabel(llm) === "是" ? "gold" : "green"}>本地降级：{llmFallbackLabel(llm)}</Tag>
      </Space>

      <Descriptions size="small" column={{ xs: 1, sm: 2, md: 3 }} className="agent-run-meta">
        <Descriptions.Item label="Agent 名称">{run.agent_name}</Descriptions.Item>
        <Descriptions.Item label="Provider">{textValue(llm.provider)}</Descriptions.Item>
        <Descriptions.Item label="模型">{textValue(llm.model)}</Descriptions.Item>
        <Descriptions.Item label="解析结果">{textValue(llm.parsed)}</Descriptions.Item>
        {debateRun ? <Descriptions.Item label="回合数">{textValue(output.turn_count ?? output.iteration_count)}</Descriptions.Item> : null}
        {debateRun ? <Descriptions.Item label="当前角色">{textValue(output.active_agent ?? output.agent_name)}</Descriptions.Item> : null}
        <Descriptions.Item label="输入来源">{textValue(input.source, "standard_agent_run")}</Descriptions.Item>
      </Descriptions>

      {debateRun ? (
        <div className="agent-run-trace">
          <Typography.Text strong>议事轨迹</Typography.Text>
          {traceEvents.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无议事轨迹事件" />
          ) : (
            <List
              size="small"
              dataSource={traceEvents.slice(0, 4)}
              renderItem={renderTraceEvent}
              footer={traceEvents.length > 4 ? <Typography.Text type="secondary">还有 {traceEvents.length - 4} 条事件可在原始载荷中查看</Typography.Text> : null}
            />
          )}
        </div>
      ) : null}

      <details className="agent-run-raw">
        <summary>原始载荷</summary>
        <pre className="run-summary">{payloadJson({ input_payload: run.input_payload, output_payload: run.output_payload })}</pre>
      </details>
    </Space>
  );
}

export function JobPage() {
  const { jobId = "" } = useParams();
  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => studioApi.getJob(jobId),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const job = query.state.data?.job;
      return job && !terminal.has(job.status) ? 2000 : false;
    },
  });
  const runsQuery = useQuery({ queryKey: ["agent-runs", jobId], queryFn: () => studioApi.getAgentRuns(jobId), enabled: !!jobId });
  const job = jobQuery.data?.job;
  const total = job?.progress.total_steps ?? 1;
  const done = job?.progress.completed_steps ?? (job?.status === "succeeded" ? total : 0);

  return (
    <Space direction="vertical" size={18} className="page-stack">
      <div className="page-heading">
        <div>
          <Typography.Title level={2}>任务状态</Typography.Title>
          <Typography.Text type="secondary">查看 Job 状态、当前 Agent 和所有 Agent 执行轨迹。</Typography.Text>
        </div>
      </div>
      {jobQuery.error ? <Alert type="error" message="无法读取任务" showIcon /> : null}
      <Card loading={jobQuery.isLoading}>
        {job ? (
          <Space direction="vertical" className="full-width">
            <Space><Tag>{job.status}</Tag><Typography.Text>{job.job_type}</Typography.Text><Typography.Text type="secondary">{job.id}</Typography.Text></Space>
            <Progress percent={Math.round((done / total) * 100)} />
            <Typography.Text>当前 Agent：{job.current_agent || "无"}</Typography.Text>
            <Typography.Text>{job.progress.message}</Typography.Text>
          </Space>
        ) : <Empty description="暂无任务数据" />}
      </Card>
      <Card title="Agent 执行轨迹" loading={runsQuery.isLoading}>
        {(runsQuery.data?.agent_runs ?? []).length === 0 ? <Empty description="暂无 Agent Run" /> : (
          <List
            dataSource={runsQuery.data?.agent_runs ?? []}
            renderItem={(run) => (
              <List.Item>
                <List.Item.Meta
                  title={<Space wrap><Tag>{run.status}</Tag><Typography.Text strong>{run.agent_name}</Typography.Text><Typography.Text type="secondary">{run.agent_role}</Typography.Text></Space>}
                  description={run.finished_at ?? run.started_at}
                />
                {renderAgentRunDetails(run)}
              </List.Item>
            )}
          />
        )}
      </Card>
    </Space>
  );
}
