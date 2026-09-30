"""发现项与报告数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

Severity = Literal["blocker", "warning", "info"]


@dataclass
class Finding:
    rule_id: str
    severity: Severity
    path: str
    message: str
    line: int | None = None
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class SectionResult:
    name: str
    findings: list[Finding] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    skipped: bool = False
    skip_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "findings": [f.to_dict() for f in self.findings],
            "metrics": self.metrics,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }


@dataclass
class ReviewReport:
    package_id: str
    sections: list[SectionResult] = field(default_factory=list)
    llm: dict[str, Any] = field(default_factory=dict)
    # 检查发起时间：报告写在文档里，便于对上是哪一轮的结果
    generated_at: datetime = field(default_factory=datetime.now)

    def generated_at_text(self) -> str:
        return self.generated_at.strftime("%Y-%m-%d %H:%M:%S")

    def all_findings(self) -> list[Finding]:
        out: list[Finding] = []
        for sec in self.sections:
            out.extend(sec.findings)
        return out

    def has_blocker(self) -> bool:
        return any(f.severity == "blocker" for f in self.all_findings())

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "sections": [s.to_dict() for s in self.sections],
            "llm": self.llm,
            "summary": {
                "blocker_count": sum(
                    1 for f in self.all_findings() if f.severity == "blocker"
                ),
                "warning_count": sum(
                    1 for f in self.all_findings() if f.severity == "warning"
                ),
            },
        }
