import { GraphChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
import { init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Descriptions, Empty, Input, Modal, Select, Space, Tag, Typography, message } from "antd";
import { Save } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { studioApi, type AgentConfig } from "../api/studio";
import type { WorkflowDefinition, WorkflowNode } from "../types/api";

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

function eventNode(params: unknown): WorkflowNode | null {
  const data = (params as { data?: { node?: WorkflowNode } | null }).data;
  return data?.node ?? null;
}

export function AgentsPage() {
  const queryClient = useQueryClient();
  const chartRef = useRef<HTMLDivElement | null>(null);
  const agentsQuery = useQuery({ queryKey: ["agents"], queryFn: studioApi.listAgents });
  const workflowsQuery = useQuery({ queryKey: ["workflows"], queryFn: studioApi.listWorkflows });
  const [workflowId, setWorkflowId] = useState("chapter_draft");
  const [selectedNode, setSelectedNode] = useState<WorkflowNode | null>(null);
  const [prompt, setPrompt] = useState("");
  const [controlDescription, setControlDescription] = useState("");
  const [controlConfigs, setControlConfigs] = useState<Record<string, string>>(() => loadControlConfigs());

  const workflows = workflowsQuery.data?.workflows ?? [];
  const activeWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === workflowId) ?? workflows[0],
    [workflowId, workflows],
  );
  const selectedAgent = agentForNode(selectedNode, agentsQuery.data?.agents ?? []);
  const openNode = useCallback((node: WorkflowNode) => {
    setSelectedNode(node);
    const configKey = `${activeWorkflow?.id ?? "workflow"}:${node.id}`;
    setControlDescription(controlConfigs[configKey] ?? node.description);
    const agent = agentForNode(node, agentsQuery.data?.agents ?? []);
    setPrompt(agent?.prompt ?? "");
  }, [activeWorkflow?.id, agentsQuery.data?.agents, controlConfigs]);

  const savePrompt = useMutation({
    mutationFn: () => {
      if (!selectedAgent) {
        throw new Error("请选择 Agent 节点");
      }
      return studioApi.updateAgentPrompt(selectedAgent.name, prompt);
    },
    onSuccess: () => {
      message.success("提示词已保存");
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "保存失败"),
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
          return node ? `${node.label}<br/>${node.type === "agent" ? "Agent 节点" : "控制节点"}` : "";
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

      {agentsQuery.error || workflowsQuery.error ? <Alert type="error" showIcon message="无法读取 Agent 或工作流配置" /> : null}
      <Card loading={agentsQuery.isLoading || workflowsQuery.isLoading}>
        {activeWorkflow ? <div ref={chartRef} className="graph-canvas" /> : <Empty description="暂无工作流结构" />}
      </Card>

      {activeWorkflow ? (
        <div className="workflow-node-list" aria-label="工作流节点列表">
          {activeWorkflow.nodes.map((node) => (
            <Button
              key={node.id}
              style={{ borderColor: nodeColor(node) }}
              onClick={() => openNode(node)}
              aria-label={`打开节点配置：${node.label}`}
            >
              <Tag color={node.type === "agent" ? "blue" : "orange"}>{node.type}</Tag>
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
          selectedNode?.type === "agent" ? (
            <Button type="primary" icon={<Save size={15} />} loading={savePrompt.isPending} onClick={() => savePrompt.mutate()}>
              保存提示词
            </Button>
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
                <Tag color={selectedNode.type === "agent" ? "blue" : "orange"}>{selectedNode.type}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Agent 名称">{selectedNode.agent_name || "控制节点"}</Descriptions.Item>
              <Descriptions.Item label="输入">{selectedNode.inputs.join("、") || "无"}</Descriptions.Item>
              <Descriptions.Item label="输出">{selectedNode.outputs.join("、") || "无"}</Descriptions.Item>
            </Descriptions>

            {selectedNode.type === "agent" ? (
              <>
                <Typography.Text type="secondary">{selectedAgent?.role ?? selectedNode.description}</Typography.Text>
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
