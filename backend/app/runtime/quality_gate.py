from __future__ import annotations

import re
from collections import Counter
from typing import Any


class QualityGate:
    """Deterministic prose quality gate for generated chapters.

    This guard intentionally focuses on model-independent failures that LLM
    reviewers often miss: refusal text, truncation markers, repeated output,
    engineering metadata leaking into prose, and hard length bounds.
    """

    REFUSAL_PATTERNS = (
        "作为AI",
        "作为 AI",
        "我无法继续",
        "无法继续写作",
        "不能继续写作",
        "抱歉，我无法",
    )
    TRUNCATION_PATTERNS = (
        "（此处省略）",
        "(此处省略)",
        "未完待续",
        "以下省略",
        "后续略",
    )
    BLOCKING_ENGINEERING_TERMS = ("细纲", "情节点", "任务描述", "功能标签", "卷纲")
    ADVISORY_ENGINEERING_TERMS = ("本章", "下一章", "上一章", "前文", "后文", "伏笔", "读者")

    def evaluate_text(
        self,
        text: str,
        *,
        chapter_title: str = "",
        minimum_words: int = 0,
        target_words: int = 0,
        maximum_words: int = 0,
    ) -> dict[str, Any]:
        visible_text = text or ""
        prose = self._prose_without_heading(visible_text, chapter_title)
        compact = re.sub(r"\s+", "", prose)
        issues: list[dict[str, Any]] = []

        if minimum_words > 0 and len(compact) < minimum_words:
            issues.append(
                self._issue(
                    "blocking",
                    "length_guard",
                    f"正文 {len(compact)} 字，低于最低要求 {minimum_words} 字。",
                    evidence=f"target={target_words}, minimum={minimum_words}",
                    suggestion="补足计划内情节点和场景细节后再进入定稿。",
                )
            )

        if maximum_words > 0 and len(compact) > maximum_words:
            issues.append(
                self._issue(
                    "warning",
                    "length_guard",
                    f"正文 {len(compact)} 字，超过建议上限 {maximum_words} 字。",
                    evidence=f"target={target_words}, maximum={maximum_words}",
                    suggestion="压缩过场、合并疏点，不删主线兑现。",
                )
            )

        for pattern in self.REFUSAL_PATTERNS:
            if pattern in prose:
                issues.append(
                    self._issue(
                        "blocking",
                        "model_refusal",
                        "正文含模型拒绝或自我声明文本。",
                        evidence=pattern,
                        suggestion="重写受影响章节，禁止把模型拒绝语写入正文。",
                    )
                )
                break

        for pattern in self.TRUNCATION_PATTERNS:
            if pattern in prose:
                issues.append(
                    self._issue(
                        "blocking",
                        "truncation",
                        "正文含截断、省略或未完成标记。",
                        evidence=pattern,
                        suggestion="续写或重写到完整章节收束，不得用占位语代替正文。",
                    )
                )
                break

        blocking_terms = [term for term in self.BLOCKING_ENGINEERING_TERMS if term in prose]
        advisory_terms = [term for term in self.ADVISORY_ENGINEERING_TERMS if term in prose]
        if blocking_terms:
            issues.append(
                self._issue(
                    "blocking",
                    "engineering_metadata",
                    "正文泄漏写作工程元信息。",
                    evidence="、".join(blocking_terms[:8]),
                    suggestion="把工程词改成角色当下可感知的事件、物件、动作或相对时间。",
                )
            )
        elif advisory_terms:
            issues.append(
                self._issue(
                    "warning",
                    "engineering_metadata",
                    "正文疑似泄漏章节或读者视角元信息。",
                    evidence="、".join(advisory_terms[:8]),
                    suggestion="若不是故事内真实文本或人物认知，请改为场景内表达。",
                )
            )

        repeated = self._repeated_sentence(prose)
        if repeated:
            sentence, count = repeated
            severity = "blocking" if count >= 8 else "warning"
            issues.append(
                self._issue(
                    severity,
                    "repetition",
                    f"检测到相同短句连续或高频重复 {count} 次。",
                    evidence=sentence,
                    suggestion="重写重复段落，补具体行动、信息变化或删除打转内容。",
                )
            )

        punctuation_hits = []
        for pattern in ("……", "——", "--"):
            if pattern in prose:
                punctuation_hits.append(pattern)
        if punctuation_hits:
            issues.append(
                self._issue(
                    "warning",
                    "punctuation_pattern",
                    "正文含需要按语义改写的长停顿或横线标点。",
                    evidence="、".join(punctuation_hits),
                    suggestion="打断改动作 beat，拖长音改短句或动作，插入说明改逗号/冒号。",
                )
            )

        long_paragraphs = [line.strip() for line in prose.splitlines() if len(line.strip()) > 220]
        if long_paragraphs:
            issues.append(
                self._issue(
                    "warning",
                    "long_paragraph",
                    "存在过长段落，移动端阅读可能断气。",
                    evidence=long_paragraphs[0][:80],
                    suggestion="按镜头、新动作、新线索或视线切换断段。",
                )
            )

        blocking_count = sum(1 for issue in issues if issue["severity"] == "blocking")
        warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
        status = "needs_revision" if blocking_count else "passed"
        score = max(0, 100 - blocking_count * 30 - warning_count * 8)
        return {
            "status": status,
            "score": score,
            "summary": "需要修订后再定稿。" if blocking_count else "通过确定性质量门。",
            "blocking_issue_count": blocking_count,
            "warning_issue_count": warning_count,
            "issues": issues,
            "metrics": {
                "word_count": len(compact),
                "target_words": target_words,
                "minimum_words": minimum_words,
                "maximum_words": maximum_words,
            },
        }

    @staticmethod
    def _issue(severity: str, category: str, message: str, *, evidence: str = "", suggestion: str = "") -> dict[str, str]:
        return {
            "severity": severity,
            "category": category,
            "message": message,
            "evidence": evidence,
            "suggestion": suggestion,
        }

    @staticmethod
    def _prose_without_heading(text: str, chapter_title: str) -> str:
        lines = text.splitlines()
        if not lines:
            return ""
        first = lines[0].strip().lstrip("#").strip()
        if chapter_title and first == chapter_title.strip():
            return "\n".join(lines[1:])
        if re.match(r"^第\s*(?:\d+|[零一二三四五六七八九十百千万两]+)\s*章", first):
            return "\n".join(lines[1:])
        return text

    @staticmethod
    def _repeated_sentence(text: str) -> tuple[str, int] | None:
        sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", text) if item.strip()]
        short_sentences = [item for item in sentences if 1 <= len(item) <= 24]
        counts = Counter(short_sentences)
        if not counts:
            return None
        sentence, count = counts.most_common(1)[0]
        if count >= 4:
            return sentence, count
        return None
