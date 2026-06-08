import { GraphChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
import { init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Empty, Space, Typography } from "antd";
import { useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { studioApi } from "../api/studio";

use([GraphChart, TooltipComponent, CanvasRenderer]);

const nodeColors: Record<string, string> = {
  character: "#1677ff",
  entity: "#52c41a",
  world_fact: "#fa8c16",
  chapter: "#722ed1",
  event: "#eb2f96",
  clue: "#13c2c2",
};

export function GraphPage() {
  const { projectId = "" } = useParams();
  const chartRef = useRef<HTMLDivElement | null>(null);
  const query = useQuery({ queryKey: ["graph", projectId], queryFn: () => studioApi.getGraph(projectId), enabled: !!projectId });

  useEffect(() => {
    if (!chartRef.current || !query.data) {
      return;
    }
    const chart = init(chartRef.current);
    chart.setOption({
      tooltip: {},
      series: [
        {
          type: "graph",
          layout: "force",
          roam: true,
          label: { show: true },
          force: { repulsion: 180, edgeLength: 90 },
          data: query.data.graph.nodes.map((node) => ({
            id: node.id,
            name: node.label,
            value: node.importance_score,
            symbolSize: 20 + node.importance_score / 4,
            itemStyle: { color: nodeColors[node.node_type] ?? "#8c8c8c" },
            category: node.node_type,
          })),
          links: query.data.graph.edges.map((edge) => ({
            source: edge.source_node_id,
            target: edge.target_node_id,
            value: edge.importance_score,
            lineStyle: { width: Math.max(1, edge.importance_score / 25) },
            label: { show: true, formatter: edge.label || edge.edge_type },
          })),
        },
      ],
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [query.data]);

  return (
    <Space direction="vertical" size={18} className="page-stack">
      <div className="page-heading">
        <div>
          <Typography.Title level={2}>人物与世界观图谱</Typography.Title>
          <Typography.Text type="secondary">节点大小代表重要度，颜色代表节点类型，边粗细代表关系强度。</Typography.Text>
        </div>
      </div>
      {query.error ? <Alert type="error" message="无法读取图谱" showIcon /> : null}
      <Card loading={query.isLoading}>
        {query.data && query.data.graph.nodes.length > 0 ? <div ref={chartRef} className="graph-canvas" /> : <Empty description="暂无图谱节点，创建项目或生成章节后会更新。" />}
      </Card>
    </Space>
  );
}
