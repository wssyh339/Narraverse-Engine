import { GraphChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
import { init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Descriptions, Empty, Input, Modal, Select, Space, Tag, Typography } from "antd";
import { RotateCcw, Save } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { studioApi, type AgentConfig } from "../api/studio";
import type { LLMModelOption, WorkflowDefinition, WorkflowNode } from "../types/api";

const controlConfigKey = "novel-agent-workflow-control-configs";

use([GraphChart, TooltipComponent, CanvasRenderer]);

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

function agentForNode(node: WorkflowNode | null, agents: AgentConfig[]) {
  return node?.agent_name ? agents.find((agent) => agent.name === node.agent_name) ?? null : null;
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

function nodeTypeColor(type: WorkflowNode["type"]) {
  if (type === "agent") return "blue";
  if (type === "prompt") return "purple";
  return "orange";
}

function nodeTypeLabel(type: WorkflowNode["type"]) {
  if (type === "agent") return "Agent 节点";
  if (type === "prompt") return "提示词节点";
  return "控制节点";
}

function nodeSubtypeLabel(node: WorkflowNode) {
  if (node.node_subtype === "prompt_agent") {
    return "prompt_agent";
  }
  return node.node_subtype ?? node.type;
}

function schemaSummary(schema: WorkflowNode["input_schema"]) {
  if (!schema) {
    return "未声明";
  }
  const fields = Object.keys(schema.properties ?? {});
  const preview = fields.slice(0, 6).join("、");
  const suffix = fields.length > 6 ? ` 等 ${fields.length} 个字段` : "";
  return `${schema.title ?? "Schema"}${preview ? `：${preview}${suffix}` : ""}`;
}

export function AgentsPage() {
  const { message } = AntApp.useApp();
  const queryClient = useQueryClient();
  const chartRef = useRef<HTMLDivElement | null>(null);
  const agentsQuery = useQuery({ queryKey: ["agents"], queryFn: studioApi.listAgents });
  const workflowsQuery = useQuery({ queryKey: ["workflows"], queryFn: studioApi.listWorkflows });
  const llmModelsQuery = useQuery({ queryKey: ["llm-models"], queryFn: studioApi.listLlmModels });
  const [workflowId, setWorkflowId] = useState("chapter_draft");
  const [selectedNode, setSelectedNode] = useState<WorkflowNode | null>(null);
  const [prompt, setPrompt] = useState("");
  const [selectedProvider, setSelectedProvider] = useState<string | undefined>();
  const [selectedModel, setSelectedModel] = useState<string | undefined>();
  const [controlDescription, setControlDescription] = useState("");
  const [controlConfigs, setControlConfigs] = useState<Record<string, string>>(() => loadControlConfigs());

  const workflows = workflowsQuery.data?.workflows ?? [];
  const activeWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === workflowId) ?? workflows[0],
    [workflowId, workflows],
  );
  const selectedAgent = agentForNode(selectedNode, agentsQuery.data?.agents ?? []);
  const canEditPrompt = Boolean(selectedAgent);
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
    const agent = agentForNode(node, agentsQuery.data?.agents ?? []);
    setPrompt(agent?.prompt ?? "");
    const workflowModel = activeWorkflow?.id && agent?.model_configs ? agent.model_configs[activeWorkflow.id]?.model : undefined;
    const model = node.model ?? workflowModel ?? undefined;
    setSelectedModel(model);
    setSelectedProvider(providerForModel(model, allModels));
  }, [activeWorkflow?.id, agentsQuery.data?.agents, allModels, controlConfigs]);

  const savePrompt = useMutation({
    mutationFn: () => {
      if (!selectedAgent) {
        throw new Error("请选择 Agent 节点");
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
        throw new Error("请选择 Agent 节点");
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
      if (!selectedAgent || !activeWorkflow) {
        throw new Error("请选择工作流中的 Agent 节点");
      }
      if (!selectedModel) {
        throw new Error("请选择模型版本");
      }
      return studioApi.updateAgentModelConfig({
        workflow_id: activeWorkflow.id,
        agent_name: selectedAgent.name,
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
      if (!selectedAgent || !activeWorkflow) {
        throw new Error("请选择工作流中的 Agent 节点");
      }
      return studioApi.deleteAgentModelConfig(activeWorkflow.id, selectedAgent.name);
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
          <Typography.Text type="secondary">点击工作流节点查看输入输出；Agent 节点可直接编辑系统提示词。</Typography.Text>
        </div>
        <Select
          value={activeWorkflow?.id}
          style={{ width: 220 }}
          onChange={setWorkflowId}
          options={workflows.map((workflow) => ({ value: workflow.id, label: workflow.label }))}
        />
      </div>

      {agentsQuery.error || workflowsQuery.error || llmModelsQuery.error ? <Alert type="error" showIcon message="无法读取 Agent、模型或工作流配置" /> : null}
      <Card loading={agentsQuery.isLoading || workflowsQuery.isLoading || llmModelsQuery.isLoading}>
        {activeWorkflow ? <div ref={chartRef} className="graph-canvas" /> : <Empty description="暂无工作流结构" />}
      </Card>

      {activeWorkflow ? (
        <Alert
          type="info"
          showIcon
          message={
            <Space wrap>
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
          {activeWorkflow.nodes.map((node) => (
            <Button
              key={node.id}
              style={{ borderColor: nodeColor(node) }}
              onClick={() => openNode(node)}
              aria-label={`打开节点配置：${node.label}`}
            >
              <Tag color={nodeTypeColor(node.type)}>{node.type}</Tag>
              {node.node_subtype ? <Tag color="purple">{nodeSubtypeLabel(node)}</Tag> : null}
              {node.label}
            </Button>
          ))}
        </div>
      ) : null}

      <Modal
        title={selectedNode ? selectedNode.label : "节点详情"}
        open={!!selectedNode}
        width={640}
        onCancel={() => setSelectedNode(null)}
        footer={
          canEditPrompt ? (
            <Space>
              <Button loading={restoreModelConfig.isPending} onClick={() => restoreModelConfig.mutate()}>
                模型恢复默认
              </Button>
              <Button loading={saveModelConfig.isPending} onClick={() => saveModelConfig.mutate()}>
                保存模型
              </Button>
              <Button icon={<RotateCcw size={15} />} loading={restorePrompt.isPending} onClick={() => restorePrompt.mutate()}>
                恢复默认
              </Button>
              <Button type="primary" icon={<Save size={15} />} loading={savePrompt.isPending} onClick={() => savePrompt.mutate()}>
                保存提示词
              </Button>
            </Space>
          ) : selectedNode ? (
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
                <Tag color={nodeTypeColor(selectedNode.type)}>{selectedNode.type}</Tag>
                {selectedNode.node_subtype ? <Tag color="purple">{nodeSubtypeLabel(selectedNode)}</Tag> : null}
              </Descriptions.Item>
              <Descriptions.Item label="Agent 名称">{selectedNode.agent_name || "控制节点"}</Descriptions.Item>
              {selectedNode.prompt_id ? <Descriptions.Item label="Prompt ID">{selectedNode.prompt_id}</Descriptions.Item> : null}
              {selectedNode.prompt_filename ? <Descriptions.Item label="Prompt 文件">{selectedNode.prompt_filename}</Descriptions.Item> : null}
              {selectedAgent ? (
                <Descriptions.Item label="模型">
                  {selectedModel ? <Tag color="geekblue">{selectedModel}</Tag> : <Tag>使用环境默认模型</Tag>}
                </Descriptions.Item>
              ) : null}
              <Descriptions.Item label="输入">{selectedNode.inputs.join("、") || "无"}</Descriptions.Item>
              <Descriptions.Item label="输出">{selectedNode.outputs.join("、") || "无"}</Descriptions.Item>
              {selectedNode.input_schema ? <Descriptions.Item label="输入 Schema">{schemaSummary(selectedNode.input_schema)}</Descriptions.Item> : null}
              {selectedNode.output_schema ? <Descriptions.Item label="输出 Schema">{schemaSummary(selectedNode.output_schema)}</Descriptions.Item> : null}
            </Descriptions>

            {selectedAgent ? (
              <>
                <Space wrap>
                  <Typography.Text type="secondary">{selectedAgent.role ?? selectedNode.description}</Typography.Text>
                  <Tag color={selectedAgent.is_custom ? "cyan" : "default"}>{selectedAgent.is_custom ? "自定义提示词" : "默认提示词"}</Tag>
                </Space>
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
                    仅影响当前工作流的 {selectedAgent.role}。未选择时使用后端环境变量中的默认模型。
                  </Typography.Text>
                </Space>
                <Input.TextArea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={16} />
              </>
            ) : (
              <>
                <Typography.Text type="secondary">控制节点说明只保存到当前浏览器本地，不影响后端工作流执行逻辑。</Typography.Text>
                <Input.TextArea value={controlDescription} onChange={(event) => setControlDescription(event.target.value)} rows={10} />
              </>
            )}
          </Space>
        ) : null}
      </Modal>
    </Space>
  );
}
