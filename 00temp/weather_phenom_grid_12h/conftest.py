# -*- coding: utf-8 -*-
"""
pytest 根级配置：将项目根目录加入 sys.path，
确保 src / resource 等包可被所有测试文件直接导入，
无需在各测试文件中重复写 sys.path.insert。
"""
import sys
import os

# 项目根目录（conftest.py 所在目录）
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
