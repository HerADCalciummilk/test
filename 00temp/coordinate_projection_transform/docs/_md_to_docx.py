# -*- coding: utf-8 -*-
"""将 坐标投影转换.md 转为 Word。"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).resolve().parent
MD_PATH = HERE / "坐标投影转换.md"
OUT_PATH = HERE / "坐标投影转换.docx"

LATEX_MAP = [
    (r"\((\lambda,\varphi)\)", "(λ, φ)"),
    (r"\(\Delta\lambda\)", "Δλ"),
    (r"\((x,y)\)", "(x, y)"),
    (r"\(25^\circ\mathrm{N}\)", "25°N"),
    (r"\(47^\circ\mathrm{N}\)", "47°N"),
    (r"\(P_t\)", "Pt"),
    (r"\(P_s=(x_s,y_s)\)", "Ps=(xs, ys)"),
    (r"\((\lambda_s,\varphi_s)\)", "(λs, φs)"),
    (r"\((x_\min,y_\min)\)", "(xmin, ymin)"),
    (r"\((x_\max,y_\max)\)", "(xmax, ymax)"),
    (r"\([x_\min,x_\max]\)", "[xmin, xmax]"),
    (r"\([y_\min,y_\max]\)", "[ymin, ymax]"),
    (r"\(x\)", "x"),
    (r"\(y\)", "y"),
]


def set_run_font(run, size=11, bold=False, code=False):
    run.bold = bold
    run.font.size = Pt(size)
    if code:
        run.font.name = "Consolas"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    else:
        run.font.name = "宋体"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")


def clean_inline(s: str) -> str:
    for a, b in LATEX_MAP:
        s = s.replace(a, b)
    return s


def add_runs(paragraph, line: str, base_size: int = 11):
    line = clean_inline(line)
    parts = re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", line)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            set_run_font(run, size=base_size, bold=True)
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            set_run_font(run, size=base_size, code=True)
        else:
            run = paragraph.add_run(part)
            set_run_font(run, size=base_size)


def set_heading_font(paragraph):
    for run in paragraph.runs:
        run.font.name = "黑体"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")


def is_sep_row(cells):
    return all(re.match(r"^:?-+:?$", c.replace(" ", "")) for c in cells if c is not None)


def main():
    text = MD_PATH.read_text(encoding="utf-8")
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(11)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    lines = text.splitlines()
    i = 0
    in_code = False
    code_buf = []
    table_buf = []

    def flush_code():
        nonlocal code_buf
        if not code_buf:
            return
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.left_indent = Cm(0.5)
        run = p.add_run("\n".join(code_buf))
        set_run_font(run, size=9, code=True)
        code_buf = []

    def flush_table():
        nonlocal table_buf
        if not table_buf:
            return
        rows = []
        for row in table_buf:
            cells = [c.strip() for c in row.strip("|").split("|")]
            if is_sep_row(cells):
                continue
            rows.append(cells)
        table_buf = []
        if not rows:
            return
        ncols = max(len(r) for r in rows)
        table = doc.add_table(rows=len(rows), cols=ncols)
        table.style = "Table Grid"
        for ri, row in enumerate(rows):
            for ci in range(ncols):
                cell = table.cell(ri, ci)
                cell.text = ""
                p = cell.paragraphs[0]
                val = row[ci] if ci < len(row) else ""
                add_runs(p, val, base_size=10)
                if ri == 0:
                    for run in p.runs:
                        run.bold = True
        doc.add_paragraph()

    while i < len(lines):
        line = lines[i]
        if in_code:
            if line.startswith("```"):
                in_code = False
                flush_code()
            else:
                code_buf.append(line)
            i += 1
            continue

        if line.startswith("```"):
            flush_table()
            in_code = True
            code_buf = []
            i += 1
            continue

        if line.strip().startswith("|") and "|" in line.strip()[1:]:
            table_buf.append(line)
            i += 1
            if i >= len(lines) or not lines[i].strip().startswith("|"):
                flush_table()
            continue

        flush_table()
        if not line.strip():
            i += 1
            continue

        if line.startswith("# "):
            p = doc.add_heading(line[2:].strip(), level=0)
            set_heading_font(p)
        elif line.startswith("## "):
            p = doc.add_heading(line[3:].strip(), level=1)
            set_heading_font(p)
        elif line.startswith("### "):
            p = doc.add_heading(line[4:].strip(), level=2)
            set_heading_font(p)
        elif re.match(r"^\d+\.\s", line.strip()):
            p = doc.add_paragraph(style="List Number")
            add_runs(p, re.sub(r"^\d+\.\s", "", line.strip()))
        elif line.strip().startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            add_runs(p, line.strip()[2:])
        else:
            p = doc.add_paragraph()
            add_runs(p, line.strip())
        i += 1

    flush_code()
    flush_table()
    doc.save(str(OUT_PATH))
    print("wrote", OUT_PATH)


if __name__ == "__main__":
    main()
