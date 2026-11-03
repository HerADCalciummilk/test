from __future__ import annotations

from datetime import datetime
from pathlib import Path


def date_replace(template: str, dt_input: datetime, i_valid: int) -> str:
    return (
        template.replace("YYYY", f"{dt_input.year:04d}")
        .replace("YY", f"{dt_input.year:04d}"[2:])
        .replace("MM", f"{dt_input.month:02d}")
        .replace("DD", f"{dt_input.day:02d}")
        .replace("HH", f"{dt_input.hour:02d}")
        .replace("NN", f"{dt_input.minute:02d}")
        .replace("SS", f"{dt_input.second:02d}")
        .replace("VVV", f"{i_valid:03d}")
        .replace("VV", f"{i_valid:02d}")
    )


def write_str_to_txt(path: str | Path, content: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="gb2312", errors="ignore")
