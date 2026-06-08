import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, App, Button, Card, Empty, List, Modal, Select, Space, Tag, Typography } from "antd";
import { studioApi } from "../api/studio";
import { useState } from "react";

export function VersionsPage() {
  const { message } = App.useApp();
  const query = useQuery({ queryKey: ["versions"], queryFn: () => studioApi.listVersions() });
  const [left, setLeft] = useState<string>();
  const [right, setRight] = useState<string>();
  const compare = useMutation({
    mutationFn: () => studioApi.compareVersions(left!, right!),
    onError: (error) => message.error(error instanceof Error ? error.message : "版本对比失败"),
  });
  const rollback = useMutation({
    mutationFn: (versionId: string) => studioApi.rollbackVersion(versionId, "从版本管理页回滚"),
    onSuccess: () => {
      message.success("回滚成功，已同时保存新的版本快照");
      query.refetch();
    },
    onError: (error) => message.error(error instanceof Error ? error.message : "版本回滚失败"),
  });
  const versions = query.data?.versions ?? [];
  const options = versions.map((item) => ({ value: item.id, label: `${item.agent_name} · ${item.created_at}` }));

  const confirmRollback = (versionId: string) => {
    Modal.confirm({
      title: "确认回滚到这个版本？",
      content: "当前章节正文会被该快照替换，系统会保留新的回滚快照。",
      okText: "确认回滚",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: () => rollback.mutateAsync(versionId),
    });
  };

  return (
    <Space direction="vertical" size={18} className="page-stack">
      <div className="page-heading">
        <div>
          <Typography.Title level={2}>版本管理</Typography.Title>
          <Typography.Text type="secondary">每个 Agent 完成后自动留下快照，可对比、回滚或创建分支。</Typography.Text>
        </div>
      </div>
      {query.error ? <Alert type="error" message="无法读取版本列表" showIcon /> : null}
      <Card title="版本对比">
        <Space wrap>
          <Select placeholder="左侧版本" style={{ width: 280 }} options={options} value={left} onChange={setLeft} />
          <Select placeholder="右侧版本" style={{ width: 280 }} options={options} value={right} onChange={setRight} />
          <Button type="primary" disabled={!left || !right} loading={compare.isPending} onClick={() => compare.mutate()}>对比</Button>
        </Space>
        {compare.data ? <pre className="diff-panel">{compare.data.diff.join("\n") || "两个版本没有差异"}</pre> : null}
      </Card>
      <Card title="版本时间线" loading={query.isLoading}>
        {versions.length === 0 ? (
          <Empty description="还没有版本快照，生成章节后会自动出现。" />
        ) : (
          <List
            dataSource={versions}
            renderItem={(item) => (
              <List.Item
                actions={[
                  <Button
                    key="rollback"
                    type="link"
                    danger
                    disabled={!item.chapter_id}
                    loading={rollback.isPending}
                    onClick={() => confirmRollback(item.id)}
                  >
                    回滚
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={<Space><Tag>{item.agent_name}</Tag><span>{item.content_type}</span></Space>}
                  description={`${item.created_at} · 分支 ${item.branch_name} · ${item.user_note || "无备注"}`}
                />
                <Typography.Text type="secondary">{item.content.slice(0, 80)}</Typography.Text>
              </List.Item>
            )}
          />
        )}
      </Card>
    </Space>
  );
}
