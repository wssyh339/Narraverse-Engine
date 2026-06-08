import { useMutation } from "@tanstack/react-query";
import { Alert, Button, Card, Radio, Space, Typography, message } from "antd";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { studioApi } from "../api/studio";

export function ExportPage() {
  const { projectId = "" } = useParams();
  const [format, setFormat] = useState("markdown");
  const mutation = useMutation({
    mutationFn: () => studioApi.exportProject(projectId, format),
    onSuccess: () => message.success("导出完成"),
  });

  return (
    <Space direction="vertical" size={18} className="page-stack">
      <div className="page-heading">
        <div>
          <Typography.Title level={2}>导出与发布格式</Typography.Title>
          <Typography.Text type="secondary">支持整书或章节范围导出，1.0 提供本地文件生成。</Typography.Text>
        </div>
      </div>
      <Card title="格式选择">
        <Space direction="vertical">
          <Radio.Group
            value={format}
            onChange={(event) => setFormat(event.target.value)}
            options={[
              { value: "markdown", label: "Markdown" },
              { value: "txt", label: "TXT" },
              { value: "html", label: "HTML" },
              { value: "pdf", label: "PDF" },
              { value: "epub", label: "EPUB" },
              { value: "word", label: "Word" },
            ]}
          />
          <Button type="primary" loading={mutation.isPending} onClick={() => mutation.mutate()}>导出</Button>
        </Space>
      </Card>
      {mutation.error ? <Alert type="error" message="导出失败" showIcon /> : null}
      {mutation.data ? (
        <Card title="导出结果">
          <Typography.Paragraph>文件路径：{mutation.data.export_job.output_path}</Typography.Paragraph>
          <pre className="json-panel">{mutation.data.preview}</pre>
        </Card>
      ) : null}
    </Space>
  );
}
