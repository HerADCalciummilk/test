"""公共库样例：安全解析，无 eval。"""

import ast


def safe_transform(expr: str):
    """仅接受字面量表达式（如数字、字符串、列表）。"""
    return ast.literal_eval(expr)
