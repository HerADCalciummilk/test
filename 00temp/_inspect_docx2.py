# -*- coding: utf-8 -*-
from docx import Document
from docx.oxml.ns import qn

doc = Document(r"d:\workspace\test\NIMM算法附录.docx")
for i in (116, 117, 165, 179, 247, 261, 321, 339):
    p = doc.paragraphs[i]
    xml = p._p.xml
    print("=" * 20, i, p.style.name, p.text[:40])
    print("drawings", xml.count("w:drawing"), "breaks", xml.count("w:br"), "runs", xml.count("<w:r>"))
    print("shade", "shd" in xml, "len", len(xml))
