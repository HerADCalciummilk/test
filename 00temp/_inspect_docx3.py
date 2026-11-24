# -*- coding: utf-8 -*-
from docx import Document

doc = Document(r"d:\workspace\test\NIMM算法附录.docx")
for i, p in enumerate(doc.paragraphs):
    if 321 <= i <= 339 or (p.text.startswith("import ") or "def grid" in p.text or p.text.startswith("<xarray")):
        xml = p._p.xml
        print(f"{i:04d} [{p.style.name}] shade={'shd' in xml} br={xml.count('w:br')} runs={xml.count('<w:r>')} {p.text[:80]!r}")
