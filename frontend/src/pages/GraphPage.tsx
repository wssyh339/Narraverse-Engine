import { GraphChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
import { init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Col, Empty, Row, Space, Statistic, Tag, Typography } from "antd";
import { useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { studioApi } from "../api/studio";
import { SettingsSectionNav } from "../components/SettingsSectionNav";

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
  const nodes = query.data?.graph.nodes ?? [];
  const edges = query.data?.graph.edges ?? [];
  const groupedNodeCounts = nodes.reduce<Record<string, number>>((acc, node) => {
    acc[node.node_type] = (acc[node.node_type] ?? 0) + 1;
    return acc;
  }, {});

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
      <SettingsSectionNav active="graph" />
      <div className="page-heading">
        <div>
          <Typography.Title level={3}>人物与世界观图谱</Typography.Title>
          <Typography.Text type="secondary">节点大小代表重要度，颜色代表节点类型，边粗细代表关系强度。</Typography.Text>
        </div>
      </div>
      {query.error ? <Alert type="error" message="无法读取图谱" showIcon /> : null}
      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <Card loading={query.isLoading} className="settings-stat-card">
            <Statistic title="节点" value={nodes.length} />
            <Typography.Text type="secondary">角色、实体、世界事实与章节节点</Typography.Text>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card loading={query.isLoading} className="settings-stat-card">
            <Statistic title="关系" value={edges.length} />
            <Typography.Text type="secondary">因果、隶属、定义、驱动等连接</Typography.Text>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card loading={query.isLoading} className="settings-stat-card">
            <Space wrap>
              {Object.entries(groupedNodeCounts).length === 0 ? <Typography.Text type="secondary">暂无类型</Typography.Text> : null}
              {Object.entries(groupedNodeCounts).map(([type, count]) => (
                <Tag key={type} color={nodeColors[type] ?? "default"}>{type} {count}</Tag>
              ))}
            </Space>
          </Card>
        </Col>
        <Col span={24}>
          <Card loading={query.isLoading} className="settings-content-card">
            {nodes.length > 0 ? <div ref={chartRef} className="graph-canvas" /> : <Empty description="暂无图谱节点，创建项目或生成章节后会更新。" />}
          </Card>
        </Col>
      </Row>
    </Space>
  );
}
