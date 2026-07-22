import { GraphChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
import { init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Descriptions, Empty, Input, Modal, Select, Space, Tag, Typography } from "antd";
import { RotateCcw, Save } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { studioApi, type AgentConfig } from "../api/studio";
import type { DeepAgentToolCall, LLMModelOption, WorkflowDefinition, WorkflowNode } from "../types/api";

const controlConfigKey = "novel-agent-workflow-control-configs";

use([GraphChart, TooltipComponent, CanvasRenderer]);

const toolLabelMap: Record<string, string> = {
  get_project_state: "读取项目状态",
  get_story_bible: "读取故事圣经",
  get_canon_context: "读取正典上下文",
  list_volumes: "读取分卷列表",
  list_chapters: "读取章节列表",
  list_foreshadowing: "读取伏笔账本",
  read_project: "读取项目资料",
  read_story_bible: "读取故事圣经",
  read_reference_assets: "读取对标资产",
  read_method_pack: "读取 Method Pack",
  record_outline_piece: "记录大纲候选片段",
  record_debate_decision: "记录议事决议",
  route_to_agent: "路由到下一席位",
  close_round: "收束本轮讨论",
  build_outline_topology: "构建议事拓扑",
  create_uncertainty_ticket: "创建不确定项",
  create_completion_ticket: "创建补全项",
  create_character_candidate: "创建角色候选",
  create_setting_candidate: "创建设定候选",
  reader_promise_audit: "审计读者承诺",
  hook_density_plan: "规划钩子密度",
  selling_point_risk_list: "列出卖点风险",
};

const validatorLabelMap: Record<string, string> = {
  schema_validator: "结构合同校验",
  impact_analyzer: "影响范围分析",
  market_fit_checker: "类型适配检查",
  promise_payoff_checker: "承诺兑现检查",
  structure_checker: "结构完整性检查",
  continuity_checker: "连续性检查",
  canon_conflict_checker: "正典冲突检查",
  duplicate_checker: "重复候选检查",
};

const jsonFieldLabelMap: Record<string, string> = {
  project_id: "项目 ID",
  session_id: "会话 ID",
  phase: "议事阶段",
  requirement: "用户要求",
  local_preview: "本地预览",
  model: "模型",
  turns: "发言轮次",
  decisions: "决议",
  artifacts: "候选产物",
  outline_topology: "议事拓扑",
  result: "阶段结果",
  message: "发言正文",
  claims: "关键主张",
  risks: "风险",
  uncertainties: "不确定项",
  blocking_items: "阻塞项",
  must_fix_before_confirm: "确认前必修项",
  quality_metrics: "质量指标",
  synthesis_provenance: "合成来源",
  repair_policy: "修复策略",
  character_candidate: "角色候选",
  character_candidates: "角色候选列表",
  setting_candidate: "设定候选",
  setting_candidates: "设定候选列表",
  candidate_source: "候选来源",
  can_materialize_on_confirm: "确认后可物化",
};

function loadControlConfigs(): Record<string, string> {
  try {
    return JSON.parse(window.localStorage.getItem(controlConfigKey) ?? "{}") as Record<string, string>;
  } catch {
    return {};
  }
}

function nodeColor(node: WorkflowNode) {
  if (node.type === "control") {
    return "#fa8c16";
  }
  if (node.type === "prompt") {
    return "#722ed1";
  }
  return "#1677ff";
}

function toChartData(workflow: WorkflowDefinition) {
  return workflow.nodes.map((node, index) => ({
    id: node.id,
    name: node.label,
    value: node.layer,
    x: node.layer * 150 + 60,
    y: (index % 4) * 90 + 60,
    symbolSize: node.type === "control" ? 42 : 54,
    itemStyle: { color: nodeColor(node), borderColor: node.editable ? "#13c2c2" : "#8c8c8c", borderWidth: node.editable ? 3 : 1 },
    label: { show: true, position: "bottom", width: 110, overflow: "break" },
    node,
  }));
}

function configurableAgentForNode(node: WorkflowNode | null, agents: AgentConfig[]) {
  if (!node?.agent_name || node.configurable === false) {
    return null;
  }
  return agents.find((agent) => agent.name === node.agent_name) ?? null;
}

function modelConfigAgentNameForNode(node: WorkflowNode | null) {
  if (!node?.agent_name || node.configurable === false) {
    return null;
  }
  return node.agent_name;
}

function modelLabel(model: LLMModelOption) {
  return `${model.label} (${model.id})`;
}

function selectOptionLabel(text: string) {
  return (
    <span title={text} style={{ display: "block", lineHeight: 1.35, whiteSpace: "normal" }}>
      {text}
    </span>
  );
}

function providerForModel(modelId: string | undefined, models: LLMModelOption[]) {
  if (!modelId) {
    return undefined;
  }
  const catalogProvider = models.find((model) => model.id === modelId)?.provider;
  if (catalogProvider) {
    return catalogProvider;
  }
  const [provider] = modelId.split(":", 1);
  return modelId.includes(":") && provider ? provider : undefined;
}

function eventNode(params: unknown): WorkflowNode | null {
  const data = (params as { data?: { node?: WorkflowNode } | null }).data;
  return data?.node ?? null;
}

function workflowRuntimeColor(status?: WorkflowDefinition["runtime_status"]) {
  return status === "active_runtime" ? "green" : "purple";
}

function workflowRuntimeLabel(status?: WorkflowDefinition["runtime_status"]) {
  return status === "active_runtime" ? "已接入实际执行" : "已通过提示词绑定应用";
}

function onlyRealRuntimeNodes(workflow: WorkflowDefinition) {
  return workflow.runtime_status === "active_runtime";
}

function workflowKindRank(workflow: WorkflowDefinition) {
  if (workflow.runtime_status === "active_runtime") return 0;
  if (workflow.workflow_kind === "prompt_lifecycle") return 1;
  if (workflow.workflow_kind === "prompt_library") return 2;
  return 3;
}

function workflowKindLabel(workflow: WorkflowDefinition) {
  if (workflow.workflow_kind === "prompt_lifecycle") return "提示词参考";
  if (workflow.workflow_kind === "prompt_library") return "提示词库参考";
  return workflow.runtime_status === "active_runtime" ? "运行工作流" : "工作流";
}

function workflowKindColor(workflow: WorkflowDefinition) {
  if (workflow.workflow_kind === "prompt_lifecycle") return "green";
  if (workflow.workflow_kind === "prompt_library") return "purple";
  return workflow.runtime_status === "active_runtime" ? "blue" : "default";
}

function nodeTypeColor(type: WorkflowNode["type"]) {
  if (type === "agent") return "blue";
  if (type === "prompt") return "purple";
  return "orange";
}

function nodeTypeLabel(type: WorkflowNode["type"]) {
  if (type === "agent") return "智能体节点";
  if (type === "prompt") return "提示词节点";
  return "控制节点";
}

function nodeSubtypeLabel(node: WorkflowNode) {
  if (node.node_subtype === "prompt_agent") {
    return "Prompt 任务";
  }
  if (node.node_subtype === "runtime_agent") {
    return "内部运行席位";
  }
  if (node.node_subtype === "formal_agent") {
    return "基础智能体规格";
  }
  return node.node_subtype ?? node.type;
}

function nodeOperationalLabel(node: WorkflowNode) {
  if (node.configurable !== false && node.agent_name && node.type !== "control") {
    return "可配置";
  }
  if (node.node_subtype === "runtime_agent") {
    return "只读运行节点";
  }
  if (node.type === "prompt") {
    return "Prompt 任务";
  }
  return "控制节点";
}

function schemaSummary(schema: WorkflowNode["input_schema"]) {
  if (!schema) {
    return "未声明";
  }
  const fields = Object.keys(schema.properties ?? {});
  const preview = fields.slice(0, 6).map(displayJsonFieldLabel).join("、");
  const suffix = fields.length > 6 ? ` 等 ${fields.length} 个字段` : "";
  return `${schema.title ?? "Schema"}${preview ? `：${preview}${suffix}` : ""}`;
}

function displayContractLabel(value: string, labels: Record<string, string>) {
  const label = labels[value];
  return label ? `${label}（${value}）` : value;
}

function displayJsonFieldLabel(value: string) {
  return displayContractLabel(value, jsonFieldLabelMap);
}

function displayContractList(values: string[] | undefined, labels: Record<string, string>) {
  if (!values?.length) {
    return "未声明";
  }
  return values.map((value) => displayContractLabel(value, labels)).join("、");
}

function schemaFieldNames(schema: WorkflowNode["input_schema"] | undefined) {
  return Object.keys(schema?.properties ?? {});
}

function pendingToolCallsFromSessions(
  sessions: Array<{ state?: { tool_calls?: DeepAgentToolCall[] }; id: string }>,
) {
  return sessions.flatMap((session) =>
    (session.state?.tool_calls ?? [])
      .filter((toolCall) => toolCall.status === "pending_approval")
      .map((toolCall) => ({ ...toolCall, session_id: toolCall.session_id || session.id })),
  );
}

export function AgentsPage() {
  const { message } = AntApp.useApp();
  const { projectId = "" } = useParams();
  const queryClient = useQueryClient();
  const chartRef = useRef<HTMLDivElement | null>(null);
  const agentsQuery = useQuery({ queryKey: ["agents"], queryFn: studioApi.listAgents });
  const workflowsQuery = useQuery({ queryKey: ["workflows"], queryFn: studioApi.listWorkflows });
  const llmModelsQuery = useQuery({ queryKey: ["llm-models"], queryFn: studioApi.listLlmModels });
  const deepAgentConfigQuery = useQuery({ queryKey: ["deep-agent-config"], queryFn: studioApi.getDeepAgentConfig });
  const langSmithStatusQuery = useQuery({ queryKey: ["langsmith-status"], queryFn: studioApi.getLangSmithStatus });
  const deepAgentSessionsQuery = useQuery({
    queryKey: ["deep-agent-sessions", projectId],
    queryFn: () => studioApi.listDeepAgentSessions(projectId),
    enabled: Boolean(projectId),
  });
  const [workflowId, setWorkflowId] = useState("outline_debate_engine");
  const [selectedNode, setSelectedNode] = useState<WorkflowNode | null>(null);
  const [prompt, setPrompt] = useState("");
  const [deepAgentObjective, setDeepAgentObjective] = useState("检查当前项目的大纲、正典和下一步写作风险。");
  const [selectedProvider, setSelectedProvider] = useState<string | undefined>();
  const [selectedModel, setSelectedModel] = useState<string | undefined>();
  const [controlDescription, setControlDescription] = useState("");
  const [controlConfigs, setControlConfigs] = useState<Record<string, string>>(() => loadControlConfigs());
  const [showReferenceWorkflows, setShowReferenceWorkflows] = useState(false);

  const sortedWorkflows = useMemo(() => {
    return [...(workflowsQuery.data?.workflows ?? [])].sort((left, right) => {
      const rankDelta = workflowKindRank(left) - workflowKindRank(right);
      if (rankDelta !== 0) return rankDelta;
      return left.label.localeCompare(right.label, "zh-CN");
    });
  }, [workflowsQuery.data?.workflows]);
  const executableWorkflows = useMemo(() => sortedWorkflows.filter(onlyRealRuntimeNodes), [sortedWorkflows]);
  const referenceWorkflows = useMemo(() => sortedWorkflows.filter((workflow) => !onlyRealRuntimeNodes(workflow)), [sortedWorkflows]);
  const workflows = useMemo(
    () => (showReferenceWorkflows ? [...executableWorkflows, ...referenceWorkflows] : executableWorkflows),
    [executableWorkflows, referenceWorkflows, showReferenceWorkflows],
  );
  const activeWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === workflowId) ?? workflows[0],
    [workflowId, workflows],
  );
  const runtimeNodeList = activeWorkflow?.nodes ?? [];
  const selectedAgent = configurableAgentForNode(selectedNode, agentsQuery.data?.agents ?? []);
  const selectedModelConfigAgentName = modelConfigAgentNameForNode(selectedNode);
  const canConfigureSelectedAgent = Boolean(selectedAgent);
  const canConfigureSelectedModel = Boolean(selectedModelConfigAgentName);
  const canEditControlDescription = selectedNode?.type === "control";
  const allModels = useMemo(() => llmModelsQuery.data?.models ?? [], [llmModelsQuery.data?.models]);
  const providerOptions = useMemo(() => {
    const providerLabels = new Map((llmModelsQuery.data?.providers ?? []).map((provider) => [provider.id, provider.label]));
    return Array.from(new Set(allModels.map((model) => model.provider))).map((provider) => ({
      value: provider,
      label: selectOptionLabel(providerLabels.get(provider) === provider ? provider : `${providerLabels.get(provider) ?? provider} (${provider})`),
      title: providerLabels.get(provider) === provider ? provider : `${providerLabels.get(provider) ?? provider} (${provider})`,
    }));
  }, [allModels, llmModelsQuery.data?.providers]);
  const filteredModelOptions = useMemo(() => {
    return allModels
      .filter((model) => !selectedProvider || model.provider === selectedProvider)
      .map((model) => ({ value: model.id, label: selectOptionLabel(modelLabel(model)), title: modelLabel(model) }));
  }, [allModels, selectedProvider]);
  const pendingToolCalls = useMemo(
    () => pendingToolCallsFromSessions(deepAgentSessionsQuery.data?.sessions ?? []),
    [deepAgentSessionsQuery.data?.sessions],
  );

  useEffect(() => {
    if (workflows.length && !workflows.some((workflow) => workflow.id === workflowId)) {
      setWorkflowId(workflows[0].id);
    }
  }, [workflowId, workflows]);

  useEffect(() => {
    if (selectedModel && !selectedProvider) {
      setSelectedProvider(providerForModel(selectedModel, allModels));
    }
  }, [allModels, selectedModel, selectedProvider]);

  const changeProvider = useCallback((provider: string | undefined) => {
    setSelectedProvider(provider);
    setSelectedModel(undefined);
  }, []);

  const openNode = useCallback((node: WorkflowNode) => {
    setSelectedNode(node);
    const configKey = `${activeWorkflow?.id ?? "workflow"}:${node.id}`;
    setControlDescription(controlConfigs[configKey] ?? node.description);
    const agent = configurableAgentForNode(node, agentsQuery.data?.agents ?? []);
    setPrompt(agent?.prompt ?? "");
    const workflowModel = activeWorkflow?.id && agent?.model_configs ? agent.model_configs[activeWorkflow.id]?.model : undefined;
    const model = node.model ?? workflowModel ?? undefined;
    setSelectedModel(model);
    setSelectedProvider(providerForModel(model, allModels));
  }, [activeWorkflow?.id, agentsQuery.data?.agents, allModels, controlConfigs]);

  const savePrompt = useMutation({
    mutationFn: () => {
      if (!selectedAgent) {
        throw new Error("请选择智能体节点");
      }
      return studioApi.updateAgentPrompt(selectedAgent.name, prompt);
    },
    onSuccess: (data) => {
      message.success("提示词已保存");
      setPrompt(data.agent.prompt);
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "保存失败"),
  });

  const restorePrompt = useMutation({
    mutationFn: () => {
      if (!selectedAgent) {
        throw new Error("请选择智能体节点");
      }
      return studioApi.restoreAgentPrompt(selectedAgent.name);
    },
    onSuccess: (data) => {
      setPrompt(data.agent.prompt);
      message.success("已恢复默认提示词");
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "恢复失败"),
  });

  const saveModelConfig = useMutation({
    mutationFn: () => {
      if (!selectedModelConfigAgentName || !activeWorkflow) {
        throw new Error("请选择工作流中的智能体节点");
      }
      if (!selectedModel) {
        throw new Error("请选择模型版本");
      }
      return studioApi.updateAgentModelConfig({
        workflow_id: activeWorkflow.id,
        agent_name: selectedModelConfigAgentName,
        model: selectedModel,
      });
    },
    onSuccess: (data) => {
      message.success(`模型已保存：${data.config.model}`);
      setSelectedModel(data.config.model);
      setSelectedProvider(providerForModel(data.config.model, allModels));
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "保存模型失败"),
  });

  const restoreModelConfig = useMutation({
    mutationFn: () => {
      if (!selectedModelConfigAgentName || !activeWorkflow) {
        throw new Error("请选择工作流中的智能体节点");
      }
      return studioApi.deleteAgentModelConfig(activeWorkflow.id, selectedModelConfigAgentName);
    },
    onSuccess: () => {
      message.success("已恢复为环境默认模型");
      setSelectedProvider(undefined);
      setSelectedModel(undefined);
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "恢复模型失败"),
  });

  const createDeepAgentSession = useMutation({
    mutationFn: () => {
      if (!projectId) {
        throw new Error("缺少当前项目");
      }
      return studioApi.createDeepAgentSession(projectId, { objective: deepAgentObjective });
    },
    onSuccess: (data) => {
      message.success(`Deep Agent 会话已创建：${data.session.mode}`);
      queryClient.invalidateQueries({ queryKey: ["deep-agent-sessions", projectId] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "创建 Deep Agent 会话失败"),
  });

  const approveDeepAgentToolCall = useMutation({
    mutationFn: (toolCallId: string) => {
      if (!projectId) {
        throw new Error("缺少当前项目");
      }
      return studioApi.approveDeepAgentToolCall(projectId, toolCallId);
    },
    onSuccess: () => {
      message.success("工具调用已审批");
      queryClient.invalidateQueries({ queryKey: ["deep-agent-sessions", projectId] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "审批工具调用失败"),
  });

  const rejectDeepAgentToolCall = useMutation({
    mutationFn: (toolCallId: string) => {
      if (!projectId) {
        throw new Error("缺少当前项目");
      }
      return studioApi.rejectDeepAgentToolCall(projectId, toolCallId);
    },
    onSuccess: () => {
      message.success("工具调用已拒绝");
      queryClient.invalidateQueries({ queryKey: ["deep-agent-sessions", projectId] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "拒绝工具调用失败"),
  });

  const runLangSmithEval = useMutation({
    mutationFn: () => studioApi.runLangSmithEval({ project_id: projectId || undefined }),
    onSuccess: (data) => {
      const reportStatus = (data.eval_report.checks as Record<string, { status?: string }> | undefined)?.privacy_policy?.status ?? "completed";
      message.success(`LangSmith 本地评测完成：${reportStatus}`);
      queryClient.invalidateQueries({ queryKey: ["langsmith-status"] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "运行 LangSmith 评测失败"),
  });

  useEffect(() => {
    if (!chartRef.current || !activeWorkflow) {
      return;
    }
    const chart = init(chartRef.current);
    const chartData = toChartData(activeWorkflow);
    chart.setOption({
      tooltip: {
        formatter: (params: unknown) => {
          const node = eventNode(params);
          return node ? `${node.label}<br/>${nodeTypeLabel(node.type)}` : "";
        },
      },
      series: [
        {
          type: "graph",
          layout: "none",
          roam: true,
          edgeSymbol: ["none", "arrow"],
          edgeSymbolSize: 8,
          data: chartData,
          links: activeWorkflow.edges.map((edge) => ({
            source: edge.source,
            target: edge.target,
            label: { show: true, formatter: edge.label },
            lineStyle: { width: edge.label.includes("passed") ? 3 : 2, curveness: edge.label.includes("needs") ? 0.18 : 0.04 },
          })),
          emphasis: { focus: "adjacency", itemStyle: { shadowBlur: 14, shadowColor: "rgba(19,194,194,0.45)" } },
        },
      ],
    });
    chart.on("click", (params) => {
      const node = eventNode(params);
      if (!node) {
        return;
      }
      openNode(node);
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [activeWorkflow, openNode]);

  const saveControlDescription = () => {
    if (!selectedNode || !activeWorkflow) {
      return;
    }
    const next = { ...controlConfigs, [`${activeWorkflow.id}:${selectedNode.id}`]: controlDescription };
    setControlConfigs(next);
    window.localStorage.setItem(controlConfigKey, JSON.stringify(next));
    message.success("控制节点说明已保存到本地");
  };

  return (
    <Space direction="vertical" size={18} className="page-stack">
      <div className="page-heading">
        <div>
          <Typography.Title level={2}>Agent 配置中心</Typography.Title>
          <Typography.Text type="secondary">点击工作流节点查看输入输出；仅可配置节点支持模型和提示词编辑。</Typography.Text>
        </div>
        <Space wrap>
          <Button onClick={() => setShowReferenceWorkflows((visible) => !visible)}>
            {showReferenceWorkflows ? "隐藏提示词参考" : "显示提示词参考"}
          </Button>
          <Select
            value={activeWorkflow?.id}
            style={{ width: 280 }}
            onChange={setWorkflowId}
            options={workflows.map((workflow) => ({
              value: workflow.id,
              label: `${workflowKindLabel(workflow)} · ${workflow.label}`,
            }))}
          />
        </Space>
      </div>

      {agentsQuery.error || workflowsQuery.error || llmModelsQuery.error ? <Alert type="error" showIcon message="无法读取智能体、模型或工作流配置" /> : null}
      <Card loading={agentsQuery.isLoading || workflowsQuery.isLoading || llmModelsQuery.isLoading}>
        {activeWorkflow ? <div ref={chartRef} className="graph-canvas" /> : <Empty description="暂无工作流结构" />}
      </Card>

      {activeWorkflow ? (
        <Alert
          type="info"
          showIcon
          message={
            <Space wrap>
              <Tag color={workflowKindColor(activeWorkflow)}>{workflowKindLabel(activeWorkflow)}</Tag>
              <Tag color={workflowRuntimeColor(activeWorkflow.runtime_status)}>
                {workflowRuntimeLabel(activeWorkflow.runtime_status)}
              </Tag>
              <Typography.Text>{activeWorkflow.runtime_note}</Typography.Text>
            </Space>
          }
          description={activeWorkflow.entrypoints?.length ? `执行入口：${activeWorkflow.entrypoints.join("、")}` : undefined}
        />
      ) : null}

      {activeWorkflow ? (
        <div className="workflow-node-list" aria-label="工作流节点列表">
          {runtimeNodeList.map((node) => (
            <Button
              key={node.id}
              style={{ borderColor: nodeColor(node) }}
              onClick={() => openNode(node)}
              aria-label={`打开节点配置：${node.label}`}
            >
              <Tag color={nodeTypeColor(node.type)}>{nodeTypeLabel(node.type)}</Tag>
              {node.node_subtype ? <Tag color="purple">{nodeSubtypeLabel(node)}</Tag> : null}
              <Tag color={node.configurable === false ? "default" : "green"}>{nodeOperationalLabel(node)}</Tag>
              {node.tags?.includes("shortcut") ? <Tag color="gold">shortcut</Tag> : null}
              {node.label}
            </Button>
          ))}
        </div>
      ) : null}

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 16 }}>
        <Card title="Deep Agent 管理" loading={deepAgentConfigQuery.isLoading || deepAgentSessionsQuery.isLoading}>
          <Space direction="vertical" size={12} className="full-width">
            <Space wrap>
              <Tag color={deepAgentConfigQuery.data?.config.deep_agent.enabled ? "green" : "default"}>
                {deepAgentConfigQuery.data?.config.deep_agent.enabled ? "deepagents 已启用" : "本地 advisory"}
              </Tag>
              <Tag color={deepAgentConfigQuery.data?.config.deep_agent.allow_write ? "orange" : "blue"}>
                {deepAgentConfigQuery.data?.config.deep_agent.tool_policy ?? "approval_required"}
              </Tag>
              <Tag>模式：{deepAgentConfigQuery.data?.config.deep_agent.mode ?? "advisor"}</Tag>
            </Space>
            <Typography.Text type="secondary">
              Deep Agent 只作为工作室总管层，默认创建建议和待审批工具调用，不直接覆盖正文或设定。
            </Typography.Text>
            <Input.TextArea
              value={deepAgentObjective}
              onChange={(event) => setDeepAgentObjective(event.target.value)}
              rows={3}
              placeholder="输入 Deep Agent 会话目标"
            />
            <Space wrap>
              <Button loading={createDeepAgentSession.isPending} onClick={() => createDeepAgentSession.mutate()}>
                创建 Deep Agent 会话
              </Button>
              <Tag>会话：{deepAgentSessionsQuery.data?.sessions.length ?? 0}</Tag>
              <Tag color={pendingToolCalls.length ? "gold" : "default"}>待审批工具：{pendingToolCalls.length}</Tag>
            </Space>
            {pendingToolCalls.length ? (
              <Space direction="vertical" size={8} className="full-width">
                {pendingToolCalls.map((toolCall) => (
                  <div key={toolCall.id} className="runtime-row">
                    <Space wrap>
                      <Tag color="gold">{toolCall.tool_name}</Tag>
                      <Tag>{toolCall.risk_level}</Tag>
                      <Typography.Text type="secondary">{toolCall.status}</Typography.Text>
                    </Space>
                    <Space>
                      <Button size="small" loading={approveDeepAgentToolCall.isPending} onClick={() => approveDeepAgentToolCall.mutate(toolCall.id)}>
                        审批
                      </Button>
                      <Button size="small" danger loading={rejectDeepAgentToolCall.isPending} onClick={() => rejectDeepAgentToolCall.mutate(toolCall.id)}>
                        拒绝
                      </Button>
                    </Space>
                  </div>
                ))}
              </Space>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无待审批工具" />
            )}
          </Space>
        </Card>

        <Card title="LangSmith 管理" loading={langSmithStatusQuery.isLoading || deepAgentConfigQuery.isLoading}>
          <Space direction="vertical" size={12} className="full-width">
            <Space wrap>
              <Tag color={langSmithStatusQuery.data?.status.configured ? "green" : "default"}>
                {langSmithStatusQuery.data?.status.configured ? "已配置" : "未配置"}
              </Tag>
              <Tag color={langSmithStatusQuery.data?.status.tracing ? "green" : "default"}>
                {langSmithStatusQuery.data?.status.tracing ? "Tracing 开启" : "Tracing 关闭"}
              </Tag>
              <Tag color="blue">隐私模式：{langSmithStatusQuery.data?.status.privacy_mode ?? "metadata_only"}</Tag>
              <Tag>Prompt：{langSmithStatusQuery.data?.status.prompt_sync ?? "manual"}</Tag>
            </Space>
            <Typography.Text type="secondary">
              LangSmith 只由后端读取 Key。metadata_only 模式不会上传正文、完整提示词或用户私密设定。
            </Typography.Text>
            <Descriptions size="small" column={1}>
              <Descriptions.Item label="Project">{langSmithStatusQuery.data?.status.project ?? "novel-agent-local"}</Descriptions.Item>
              <Descriptions.Item label="SDK">
                {langSmithStatusQuery.data?.status.package.installed ? langSmithStatusQuery.data.status.package.version || "installed" : "未安装"}
              </Descriptions.Item>
            </Descriptions>
            <Space wrap>
              <Button loading={runLangSmithEval.isPending} onClick={() => runLangSmithEval.mutate()}>
                运行本地 Eval
              </Button>
              <Button
                onClick={() =>
                  queryClient.invalidateQueries({ queryKey: ["langsmith-status"] })
                }
              >
                刷新状态
              </Button>
            </Space>
          </Space>
        </Card>
      </div>

      <Modal
        title={selectedNode ? selectedNode.label : "节点详情"}
        open={!!selectedNode}
        width={640}
        onCancel={() => setSelectedNode(null)}
        footer={
          canConfigureSelectedModel ? (
            <Space>
              <Button loading={restoreModelConfig.isPending} onClick={() => restoreModelConfig.mutate()}>
                模型恢复默认
              </Button>
              <Button loading={saveModelConfig.isPending} onClick={() => saveModelConfig.mutate()}>
                保存模型
              </Button>
              {canConfigureSelectedAgent ? (
                <>
                  <Button icon={<RotateCcw size={15} />} loading={restorePrompt.isPending} onClick={() => restorePrompt.mutate()}>
                    恢复默认
                  </Button>
                  <Button type="primary" icon={<Save size={15} />} loading={savePrompt.isPending} onClick={() => savePrompt.mutate()}>
                    保存提示词
                  </Button>
                </>
              ) : null}
            </Space>
          ) : canEditControlDescription ? (
            <Button type="primary" icon={<Save size={15} />} onClick={saveControlDescription}>
              保存说明
            </Button>
          ) : null
        }
      >
        {selectedNode ? (
          <Space direction="vertical" size={16} className="full-width">
            <Descriptions bordered size="small" column={1}>
              <Descriptions.Item label="节点类型">
                <Tag color={nodeTypeColor(selectedNode.type)}>{nodeTypeLabel(selectedNode.type)}</Tag>
                {selectedNode.node_subtype ? <Tag color="purple">{nodeSubtypeLabel(selectedNode)}</Tag> : null}
                <Tag color={selectedNode.configurable === false ? "default" : "green"}>{nodeOperationalLabel(selectedNode)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="运行名">{selectedNode.agent_name || "控制节点"}</Descriptions.Item>
              {selectedNode.default_agent_name ? <Descriptions.Item label="默认智能体规格">{selectedNode.default_agent_name}</Descriptions.Item> : null}
              {selectedNode.prompt_id ? <Descriptions.Item label="Prompt ID">{selectedNode.prompt_id}</Descriptions.Item> : null}
              {selectedNode.prompt_filename ? <Descriptions.Item label="Prompt 文件">{selectedNode.prompt_filename}</Descriptions.Item> : null}
              {selectedNode.runtime_note ? <Descriptions.Item label="运行说明">{selectedNode.runtime_note}</Descriptions.Item> : null}
              {canConfigureSelectedModel ? (
                <Descriptions.Item label="模型">
                  {selectedModel ? <Tag color="geekblue">{selectedModel}</Tag> : <Tag>使用环境默认模型</Tag>}
                </Descriptions.Item>
              ) : null}
              <Descriptions.Item label="输入">{selectedNode.inputs.join("、") || "无"}</Descriptions.Item>
              <Descriptions.Item label="输出">{selectedNode.outputs.join("、") || "无"}</Descriptions.Item>
              {selectedNode.input_schema ? <Descriptions.Item label="输入 Schema">{schemaSummary(selectedNode.input_schema)}</Descriptions.Item> : null}
              {selectedNode.output_schema ? <Descriptions.Item label="输出 Schema">{schemaSummary(selectedNode.output_schema)}</Descriptions.Item> : null}
              {selectedNode.allowed_read_tools?.length ? (
                <Descriptions.Item label="读取工具">{displayContractList(selectedNode.allowed_read_tools, toolLabelMap)}</Descriptions.Item>
              ) : null}
              {selectedNode.allowed_candidate_tools?.length ? (
                <Descriptions.Item label="候选工具">{displayContractList(selectedNode.allowed_candidate_tools, toolLabelMap)}</Descriptions.Item>
              ) : null}
              {selectedNode.validators?.length ? (
                <Descriptions.Item label="校验器">{displayContractList(selectedNode.validators, validatorLabelMap)}</Descriptions.Item>
              ) : null}
              {selectedNode.forbidden_tools?.length ? (
                <Descriptions.Item label="禁用工具">{displayContractList(selectedNode.forbidden_tools, toolLabelMap)}</Descriptions.Item>
              ) : null}
              {selectedNode.candidate_policy ? <Descriptions.Item label="候选策略">{selectedNode.candidate_policy}</Descriptions.Item> : null}
              {selectedNode.input_schema || selectedNode.output_schema ? (
                <Descriptions.Item label="JSON 字段">
                  {[...schemaFieldNames(selectedNode.input_schema), ...schemaFieldNames(selectedNode.output_schema)].map(displayJsonFieldLabel).join("、") || "未声明"}
                </Descriptions.Item>
              ) : null}
            </Descriptions>

            {canConfigureSelectedModel ? (
              <Space direction="vertical" size={8} className="full-width">
                <Typography.Text strong>模型选择</Typography.Text>
                <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 12 }}>
                  <Space direction="vertical" size={4} className="full-width" style={{ minWidth: 0 }}>
                    <Typography.Text type="secondary">模型厂商</Typography.Text>
                    <Select
                      allowClear
                      showSearch
                      value={selectedProvider}
                      placeholder="选择厂商"
                      options={providerOptions}
                      optionFilterProp="title"
                      optionLabelProp="title"
                      popupMatchSelectWidth={false}
                      dropdownStyle={{ maxWidth: 520, minWidth: 320 }}
                      onChange={changeProvider}
                    />
                  </Space>
                  <Space direction="vertical" size={4} className="full-width" style={{ minWidth: 0 }}>
                    <Typography.Text type="secondary">模型版本</Typography.Text>
                    <Select
                      allowClear
                      showSearch
                      disabled={!selectedProvider}
                      value={selectedModel}
                      placeholder={selectedProvider ? `使用环境默认模型：${llmModelsQuery.data?.default_model ?? "未配置"}` : "请先选择模型厂商"}
                      options={filteredModelOptions}
                      optionFilterProp="title"
                      optionLabelProp="title"
                      popupMatchSelectWidth={false}
                      dropdownStyle={{ maxWidth: 560, minWidth: 360 }}
                      onChange={setSelectedModel}
                    />
                  </Space>
                </div>
                <Typography.Text type="secondary">
                  仅影响当前工作流的 {selectedModelConfigAgentName}。未选择时使用后端环境变量中的默认模型。
                </Typography.Text>
              </Space>
            ) : null}

            {selectedAgent ? (
              <>
                <Space wrap>
                  <Typography.Text type="secondary">{selectedAgent.role ?? selectedNode.description}</Typography.Text>
                  <Tag color={selectedAgent.is_custom ? "cyan" : "default"}>{selectedAgent.is_custom ? "自定义提示词" : "默认提示词"}</Tag>
                </Space>
                <Input.TextArea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={16} />
              </>
            ) : canEditControlDescription ? (
              <>
                <Typography.Text type="secondary">控制节点说明只保存到当前浏览器本地，不影响后端工作流执行逻辑。</Typography.Text>
                <Input.TextArea value={controlDescription} onChange={(event) => setControlDescription(event.target.value)} rows={10} />
              </>
            ) : canConfigureSelectedModel ? (
              <Alert
                type="info"
                showIcon
                message="Prompt 运行节点"
                description="该节点使用独立运行名保存模型覆盖；提示词正文仍来自后端 Prompt Catalog。"
              />
            ) : (
              <Alert
                type="info"
                showIcon
                message="只读运行节点"
                description="该节点会在后端真实工作流中执行，但不属于 /api/agents 暴露的正式可编辑智能体。请在对应工作流页面调整输入和确认流程。"
              />
            )}
          </Space>
        ) : null}
      </Modal>
    </Space>
  );
}
