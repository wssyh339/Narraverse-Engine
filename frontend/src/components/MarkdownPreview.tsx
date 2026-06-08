import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownPreviewProps {
  source: string;
  className?: string;
}

export function MarkdownPreview({ source, className = "" }: MarkdownPreviewProps) {
  return (
    <div className={`markdown-preview ${className}`.trim()}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{source || "暂无内容"}</ReactMarkdown>
    </div>
  );
}
