"""本地一键检查入口。

正式流程：静态检查 → 动态（venv + pytest）→ 代码 LLM（补充审 + 合并总结写 MD）

用法:
  python -m local_review --path 00temp/<pkg> --out local-review-report.md
  python -m local_review --path 00temp/<pkg> --skip-run          # 调试：跳过 pytest
  python -m local_review --path 00temp/<pkg> --venv .cache/venv  # 复用 venv（不删除）
  python -m local_review --path 00temp/<pkg> --allow-skip-llm    # 调试
  python -m local_review --path 00temp/<pkg> --dry-run           # 调试：只静态
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .dependency_check import check_dependencies
from .docstring_check import check_docstrings
from .llm_review import run_llm_or_skip
from .meb_check import check_meb_grid
from .models import ReviewReport
from .package import load_meb_required_flag, parse_package_path
from .report import write_outputs
from .run_check import run_execution_checks
from .static_checks import run_static_checks


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="独立本地算法包检查（与 GitHub L1/L2 无关）",
    )
    p.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="仓库根目录（默认当前目录）",
    )
    p.add_argument(
        "--path",
        type=Path,
        required=True,
        help="算法包路径，如 00temp/demo 或 NIMM/02diagnostic/demo",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("local-review-report.md"),
        help="Markdown 报告路径",
    )
    p.add_argument(
        "--json",
        type=Path,
        default=Path("local-review-report.json"),
        help="JSON 报告路径",
    )
    p.add_argument(
        "--venv",
        type=Path,
        default=None,
        help=(
            "动态检查用虚拟环境目录；指定后可复用且不会被删除。"
            "默认建在系统临时目录并在跑完删除"
        ),
    )
    p.add_argument(
        "--keep-venv",
        action="store_true",
        help="保留默认创建的临时虚拟环境（调试用；正常流程跑完即删）",
    )
    p.add_argument(
        "--isolated-venv",
        action="store_true",
        help=(
            "venv 不继承本机已装库（默认继承，便于用上 numpy/meb 等内部依赖）；"
            "开启后缺依赖会导致 pytest 收集失败"
        ),
    )
    p.add_argument(
        "--allow-skip-llm",
        action="store_true",
        help="允许跳过代码 LLM（仅本地调试；正式流程不应使用）",
    )
    p.add_argument(
        "--skip-llm",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    p.add_argument(
        "--skip-run",
        action="store_true",
        help="跳过动态检查（venv + pytest；仅调试）",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="演练：只跑静态，跳过动态检查与 LLM",
    )
    p.add_argument(
        "--llm-config",
        type=Path,
        default=None,
        help="LLM 配置文件路径（默认查找仓库根 local_review.llm.toml）",
    )
    p.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="存在 warning 时也以退出码 1 结束",
    )
    return p


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root: Path = args.root.resolve()
    target: Path = args.path
    if not target.is_absolute():
        target = (root / target).resolve()
    else:
        target = target.resolve()

    package = parse_package_path(root, target)
    if package is None:
        print(f"无法将路径识别为算法包: {args.path}", file=sys.stderr)
        return 2

    # 任一步发现问题不中断后续；全部跑完再写报告。
    meb_required = load_meb_required_flag(root, package)
    sections = run_static_checks(root, package)
    sections.append(check_docstrings(root, package))
    sections.append(check_dependencies(root, package))
    sections.append(check_meb_grid(root, package, required=meb_required))

    skip_run = bool(args.skip_run or args.dry_run)
    sections.append(
        run_execution_checks(
            root,
            package,
            report_md_path=args.out,
            venv_dir=args.venv.resolve() if args.venv else None,
            keep_venv=bool(args.keep_venv),
            isolated_venv=bool(args.isolated_venv),
            skip_run=skip_run,
        )
    )

    report = ReviewReport(package_id=package.package_id, sections=sections)
    allow_skip = bool(args.allow_skip_llm or args.skip_llm or args.dry_run)
    report.llm = run_llm_or_skip(
        root,
        package,
        report,
        allow_skip_llm=allow_skip,
        dry_run=False,
        llm_config_path=args.llm_config,
    )
    if args.dry_run:
        report.llm["skip_reason"] = "dry-run"
        report.llm["model"] = "dry-run"
        report.llm["skipped"] = True

    write_outputs(report, json_path=args.json, md_path=args.out)
    print(f"已写入 {args.out} 与 {args.json} （package={package.package_id}）")

    exit_code = 0
    if report.has_blocker():
        print("存在 blocker，退出码 1（流水线仍会跑完并写报告）", file=sys.stderr)
        exit_code = 1
    if args.fail_on_warning and any(
        f.severity == "warning" for f in report.all_findings()
    ):
        print("存在 warning（--fail-on-warning），退出码 1", file=sys.stderr)
        exit_code = 1

    llm_skipped = bool(report.llm.get("skipped"))
    if llm_skipped and not allow_skip:
        print(
            f"代码 LLM 为必选但未成功：{report.llm.get('skip_reason')}",
            file=sys.stderr,
        )
        exit_code = 1
    return exit_code


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
