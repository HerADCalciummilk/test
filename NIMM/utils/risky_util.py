"""公共库样例：不当算法包；触发 L1 DANGEROUS_API，并由 L2 按变更文件审。"""


def risky_transform(expr: str):
    # 故意：eval → DANGEROUS_API warning
    return eval(expr)
