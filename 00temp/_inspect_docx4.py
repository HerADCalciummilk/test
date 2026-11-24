# -*- coding: utf-8 -*-
from docx import Document
from docx.oxml.ns import qn

doc = Document(r"d:\workspace\test\NIMM算法附录.docx")
p = doc.paragraphs[117]
print("FULL", p.text)
print("---RUNS---")
for r in p.runs:
    print(repr(r.text))

img = doc.paragraphs[338]._p
print("---IMG---")
print(img.xml[:2500])
