# -*- coding: utf-8 -*-
"""Inspect appendix headings and the last station section."""
from docx import Document

doc = Document(r"d:\workspace\test\NIMM算法附录.docx")
print("paragraphs", len(doc.paragraphs), "tables", len(doc.tables), "sections", len(doc.sections))
for i, p in enumerate(doc.paragraphs):
    style = p.style.name if p.style is not None else ""
    text = p.text.strip()
    if not text:
        continue
    if style.startswith("Heading") or text.startswith("4.") or text.startswith("图") or text.startswith("本章"):
        print(f"{i:04d} [{style}] {text[:120]}")
