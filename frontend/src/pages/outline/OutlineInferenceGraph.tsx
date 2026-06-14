import { GraphChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
import { init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { Card, Descriptions, Empty, Tag, Typography } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import type { InferenceStep, OutlineTopology, OutlineTopologyNode } from "./types";
import { statusTag } from "./outlineUtils";

use([GraphChart, TooltipComponent, CanvasRenderer]);

const EMPTY_TOPOLOGY_EDGES: OutlineTopology["edges"] = [];

interface OutlineInferenceGraphProps {
  inferenceSteps: InferenceStep[];
  outlineTopology?: OutlineTopology | null;
  isPending: boolean;
  hasResult: boolean;
  activeAgentName?: string;
}

interface GraphDetail {
  id: string;
  label: string;
  type: string;
  status: string;
  summary: string;
  agent_name?: string;
  output_key?: string;
  llm?: Record<string, unknown>;
}

function nodeColor(status: string, isActive: boolean, type?: string) {
  if (isActive) return "#08979c";
  if (status === "succeeded") return "#52c41a";
  if (status === "running") return "#1677ff";
  if (status === "failed") return "#ff4d4f";
  if (type === "artifact") return "#d48806";
  if (type === "gate" || type === "decision") return "#722ed1";
  return "#8c8c8c";
}

function eventDetailId(params: unknown): string {
  const data = (params as { data?: { detailId?: string; id?: string } | null }).data;
  return data?.detailId ?? data?.id ?? "";
}

function detailFromStep(step: InferenceStep, index: number): GraphDetail {
  return {
    id: `${step.agent_name}-${index}`,
    label: step.role,
    type: "agent",
    status: step.status,
    summary: step.output_key,
    agent_name: step.agent_name,
    output_key: step.output_key,
  };
}

function detailFromTopologyNode(node: OutlineTopologyNode): GraphDetail {
  const llm = node.payload?.llm && typeof node.payload.llm === "object" ? (node.payload.llm as Record<string, unknown>) : undefined;
  return {
    id: node.id,
    label: node.label,
    type: node.type,
    status: node.status,
    summary: node.summary,
    agent_name: node.agent_name,
    llm,
  };
}

function llmSourceLabel(llm: Record<string, unknown>) {
  if (llm.used_remote_model === true) return "远程模型";
  if (llm.source === "local_fallback" || llm.used_remote_model === false) return "本地降级";
  return String(llm.source || "未知");
}

export function OutlineInferenceGraph({ inferenceSteps, outlineTopology, isPending, hasResult, activeAgentName }: OutlineInferenceGraphProps) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const topologyNodes = outlineTopology?.nodes;
  const topologyEdges = outlineTopology?.edges ?? EMPTY_TOPOLOGY_EDGES;
  const hasTopologyNodes = Boolean(topologyNodes?.length);
  const graphDetails = useMemo(
    () => (hasTopologyNodes ? topologyNodes!.map(detailFromTopologyNode) : inferenceSteps.map(detailFromStep)),
    [hasTopologyNodes, inferenceSteps, topologyNodes],
  );
  const [selectedStepId, setSelectedStepId] = useState("");
  const lastAutoSelectedStepId = useRef("");
  const activeStep = useMemo(
    () => graphDetails.find((step) => step.agent_name === activeAgentName || `outline_swarm/${step.agent_name}` === activeAgentName) ?? null,
    [activeAgentName, graphDetails],
  );
  const autoSelectedStepId = (activeStep ?? graphDetails[0])?.id ?? "";
  const selectedStep = useMemo(
    () => graphDetails.find((step) => step.id === selectedStepId) ?? activeStep ?? graphDetails[0] ?? null,
    [activeStep, graphDetails, selectedStepId],
  );

  useEffect(() => {
    if (lastAutoSelectedStepId.current === autoSelectedStepId) return;
    lastAutoSelectedStepId.current = autoSelectedStepId;
    setSelectedStepId(autoSelectedStepId);
  }, [autoSelectedStepId]);

  useEffect(() => {
    if (!chartRef.current || !graphDetails.length) return;
    const chart = init(chartRef.current);
    const usesTopology = hasTopologyNodes;
    const detailsById = new Map(graphDetails.map((detail) => [detail.id, detail]));
    const graphData = graphDetails.map((detail, index) => {
      const isActive = detail.agent_name === activeAgentName || `outline_swarm/${detail.agent_name}` === activeAgentName;
      return {
        id: detail.id,
        name: isActive ? `${detail.label}\n当前激活` : detail.label,
        value: index + 1,
        x: usesTopology ? (detail.type === "artifact" ? 220 + (index % 4) * 190 : 70 + (index % 5) * 170) : 80 + (index % 6) * 190,
        y: usesTopology ? (detail.type === "artifact" ? 210 + Math.floor(index / 4) * 110 : 70 + Math.floor(index / 5) * 110) : 56 + Math.floor(index / 6) * 74,
        symbolSize: isActive ? 68 : detail.type === "artifact" ? 52 : detail.status === "succeeded" ? 58 : 48,
        itemStyle: { color: nodeColor(detail.status, isActive, detail.type), borderColor: isActive ? "#f6ffed" : "#ffffff", borderWidth: isActive ? 4 : 2 },
        label: { show: true, position: "bottom", width: 120, overflow: "break" },
        detailId: detail.id,
      };
    });
    const graphLinks = usesTopology
      ? topologyEdges.map((edge) => ({ source: edge.source, target: edge.target, lineStyle: { width: edge.type === "emits" ? 1.5 : 2, curveness: edge.type === "depends_on" ? 0.18 : 0.08 }, label: { show: edge.type === "blocks", formatter: edge.label } }))
      : graphDetails.slice(1).map((_, index) => ({ source: graphDetails[index].id, target: graphDetails[index + 1].id, lineStyle: { width: 2, curveness: 0.08 } }));
    chart.setOption({
      tooltip: {
        formatter: (params: unknown) => {
          const detail = detailsById.get(eventDetailId(params));
          return detail ? `${detail.type}<br/>${detail.label}<br/>${detail.summary}` : "";
        },
      },
      series: [
        {
          type: "graph",
          layout: "none",
          roam: true,
          edgeSymbol: ["none", "arrow"],
          edgeSymbolSize: 8,
          data: graphData,
          links: graphLinks,
          emphasis: { focus: "adjacency", itemStyle: { shadowBlur: 14, shadowColor: "rgba(22,119,255,0.35)" } },
        },
      ],
    });
    chart.on("click", (params) => {
      const step = detailsById.get(eventDetailId(params));
      if (step) setSelectedStepId(step.id);
    });
    const resize = () => chart.resize();
    const resizeFrame = window.requestAnimationFrame(resize);
    const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(resize);
    resizeObserver?.observe(chartRef.current);
    window.addEventListener("resize", resize);
    return () => {
      window.cancelAnimationFrame(resizeFrame);
      resizeObserver?.disconnect();
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [activeAgentName, graphDetails, hasTopologyNodes, topologyEdges]);

  const topologyMode = outlineTopology?.mode === "topology" ? "拓扑推演" : outlineTopology?.mode === "linear" ? "线性推演" : "推演链";

  return (
    <section className="outline-inference-panel outline-modal-inference">
      <div className="outline-section-heading">
        <div className="outline-section-title-stack">
          <Typography.Text strong>真实 Agent 推演链</Typography.Text>
          <Typography.Text type="secondary">{activeStep ? `${topologyMode} · 当前节点：${activeStep.label}` : "等待推演链启动"}</Typography.Text>
        </div>
        <Tag color={isPending ? "processing" : hasResult ? "green" : "default"}>{isPending ? "运行中" : hasResult ? "已完成" : "未开始"}</Tag>
      </div>
      {graphDetails.length ? (
        <>
          <div ref={chartRef} className="outline-agent-graph outline-agent-echarts" />
          <Card size="small" title="推演节点详情" className="outline-agent-detail">
            {selectedStep ? (
              <Descriptions bordered size="small" column={1}>
                <Descriptions.Item label="节点">{selectedStep.label}</Descriptions.Item>
                <Descriptions.Item label="类型">{selectedStep.type}</Descriptions.Item>
                <Descriptions.Item label="内部名称">{selectedStep.agent_name ?? selectedStep.id}</Descriptions.Item>
                <Descriptions.Item label="输出">{selectedStep.output_key ?? selectedStep.summary}</Descriptions.Item>
                <Descriptions.Item label="状态">{statusTag(selectedStep.status as InferenceStep["status"])}</Descriptions.Item>
                {selectedStep.llm ? (
                  <>
                    <Descriptions.Item label="LLM 来源">{llmSourceLabel(selectedStep.llm)}</Descriptions.Item>
                    <Descriptions.Item label="Provider">{String(selectedStep.llm.provider || "未知")}</Descriptions.Item>
                    <Descriptions.Item label="模型">{String(selectedStep.llm.model || "未知")}</Descriptions.Item>
                    <Descriptions.Item label="解析结果">{selectedStep.llm.parsed === false ? "解析失败" : "解析成功"}</Descriptions.Item>
                    <Descriptions.Item label="Schema">{selectedStep.llm.schema_valid === false ? "需检查" : "通过"}</Descriptions.Item>
                    {Array.isArray(selectedStep.llm.validation_warnings) && selectedStep.llm.validation_warnings.length ? (
                      <Descriptions.Item label="校验提示">{selectedStep.llm.validation_warnings.map(String).join("；")}</Descriptions.Item>
                    ) : null}
                  </>
                ) : null}
              </Descriptions>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="点击上方节点查看详情" />
            )}
          </Card>
        </>
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
