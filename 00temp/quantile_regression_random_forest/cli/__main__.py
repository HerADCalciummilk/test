"""命令行：python -m quantile_regression_random_forest train / python -m quantile_regression_random_forest apply。"""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

from quantile_regression_random_forest.src.quantile_regression_random_forest import apply_qrf, train_qrf
from quantile_regression_random_forest.util.meteva_data import load_meteva, save_meteva

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TESTDATA = PACKAGE_ROOT / "testdata"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m quantile_regression_random_forest",
        description="用分位数回归随机森林订正集合预报。输入输出为 meteva 格点或站点数据。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    train = subparsers.add_parser("train", help="用历史预报和实况训练模型")
    train.add_argument(
        "--forecast",
        nargs="+",
        default=[str(TESTDATA / "forecast_sta.csv")],
        help="预报文件，格点 nc 或站点 csv，第一个文件是订正目标",
    )
    train.add_argument(
        "--truth",
        default=str(TESTDATA / "truth_sta.csv"),
        help="实况文件，类型需要和预报一致",
    )
    train.add_argument(
        "--feature-config",
        default=str(TESTDATA / "feature_config.json"),
        help="特征配置 JSON",
    )
    train.add_argument("--target", default="air_temperature", help="订正目标列名或格点变量名")
    train.add_argument("--var-names", default=None, help="多个预报文件时的变量名，逗号分隔")
    train.add_argument("--output", default="quantile_regression_random_forest_model.pkl", help="模型输出路径")
    train.add_argument("--n-estimators", type=int, default=100)
    train.add_argument("--max-depth", type=int, default=None)
    train.add_argument("--max-samples", type=float, default=None)
    train.add_argument("--max-features", type=float, default=None)
    train.add_argument("--random-state", type=int, default=0)
    train.add_argument("--transformation", default=None, choices=["log", "log10", "sqrt", "cbrt"])
    train.add_argument("--pre-transform-addition", type=float, default=0.0)
    train.add_argument(
        "--site-keys",
        default=None,
        help="唯一站点键，例如 id 或 lat,lon。缺省时站点用 id，格点用 lat,lon",
    )

    apply = subparsers.add_parser("apply", help="用已训练模型输出分位数预报")
    apply.add_argument(
        "--forecast",
        nargs="+",
        default=[str(TESTDATA / "forecast_sta.csv")],
        help="待订正预报，格点 nc 或站点 csv",
    )
    apply.add_argument("--model", default="quantile_regression_random_forest_model.pkl", help="train 写出的模型")
    apply.add_argument("--output", default=None, help="订正结果路径。缺省时按输入类型自动命名")
    apply.add_argument("--quantiles", default="0.1,0.5,0.9", help="逗号分隔的分位数，范围 0 到 1")
    apply.add_argument("--var-names", default=None, help="多个预报文件时的变量名，逗号分隔")
    apply.add_argument("--target", default=None, help="目标变量名。缺省时使用模型里保存的名称")
    apply.add_argument("--feature-config", default=None, help="覆盖模型中的特征配置")
    apply.add_argument("--site-keys", default=None, help="覆盖模型中的站点键")

    args = parser.parse_args(argv)
    if args.command == "train":
        _train(args)
    else:
        _apply(args)


def _train(args) -> None:
    forecasts = _load_many(args.forecast, _split(args.var_names))
    truth = load_meteva(args.truth)
    kwargs = {
        "n_estimators": args.n_estimators,
        "max_depth": args.max_depth,
        "random_state": args.random_state,
        "transformation": args.transformation,
        "pre_transform_addition": args.pre_transform_addition,
    }
    if args.max_samples is not None:
        kwargs["max_samples"] = args.max_samples
    if args.max_features is not None:
        kwargs["max_features"] = args.max_features
    if args.site_keys:
        kwargs["unique_site_id_keys"] = _split(args.site_keys)
    bundle = train_qrf(
        forecasts,
        truth,
        feature_config=_read_json(args.feature_config),
        target_name=args.target,
        **kwargs,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        pickle.dump(bundle, handle)
    print(f"已写出模型 {output}")


def _apply(args) -> None:
    model_path = Path(args.model)
    if not model_path.is_file():
        raise FileNotFoundError(f"找不到模型文件 {model_path}，请先运行 python -m quantile_regression_random_forest train")
    with model_path.open("rb") as handle:
        bundle = pickle.load(handle)
    forecasts = _load_many(args.forecast, _split(args.var_names))
    quantiles = [float(item) for item in args.quantiles.split(",") if item.strip()]
    kwargs = {}
    if args.target:
        kwargs["target_name"] = args.target
    if args.feature_config:
        kwargs["feature_config"] = _read_json(args.feature_config)
    if args.site_keys:
        kwargs["unique_site_id_keys"] = _split(args.site_keys)
    result = apply_qrf(bundle, forecasts, quantiles=quantiles, **kwargs)
    output = Path(args.output) if args.output else _default_output(args.forecast[0])
    save_meteva(result, output)
    print(f"已写出订正结果 {output}")


def _load_many(paths: list[str], names: list[str] | None):
    loaded = [load_meteva(path) for path in paths]
    if names:
        if len(names) != len(loaded):
            raise ValueError("var-names 的数量需要和预报文件数量一致")
        for item, name in zip(loaded, names):
            if hasattr(item, "name"):
                item.name = name
    if len(loaded) == 1:
        return loaded[0]
    return loaded


def _default_output(forecast_path: str) -> Path:
    suffix = Path(forecast_path).suffix.lower()
    if suffix in {".nc", ".nc4"}:
        return Path("quantile_regression_random_forest_calibrated.nc")
    return Path("quantile_regression_random_forest_calibrated.csv")


def _read_json(path: str) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _split(text: str | None) -> list[str] | None:
    if text is None:
        return None
    return [item.strip() for item in text.split(",") if item.strip()]


if __name__ == "__main__":
    main()
