# test

本仓库用于开发 **算法代码上传审核**（机器检查 + 后续人工/LLM）。

## L1 机器检查

提交或更新 Pull Request 后，GitHub Actions 会：

1. 扫描本次变更涉及的 `00temp/<算法>/` 或 `NIMM/<种类>/<算法>/`
2. 输出 `review.json`（Actions Artifact：`l1-review-report`）
3. 在 PR 下自动发/更新一条 **L1 审核结果** 评论（可反复打开 PR 查看）

本地试跑：

```bash
pip install -r .github/scripts/review/requirements.txt
python .github/scripts/review/review.py --path 00temp/demo_algo_issues --json review.json
python .github/scripts/review/format_comment.py --json review.json --out review-comment.md
```
