"""算法上传审核脚本包。

目录约定（L1 / L2 对称命名）：

  common.py              共用：包发现、读文件、git diff
  rules.py               L1 规则与评论 marker 等常量
  l1_review.py           L1 静态检查 → l1-review.json
  format_l1_comment.py   L1 PR 评论渲染
  l2_review.py           L2 LLM 检查 → l2-review.json
  format_l2_comment.py   L2 PR 评论渲染
  requirements.txt       CI / 本地依赖

CI 入口：.github/workflows/algorithm-review.yml（job l1 → 成功后 job l2）
"""
