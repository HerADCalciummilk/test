# -*- coding: utf-8 -*-
"""
TCH 24h 降水 vs 实况 TS 检验（meteva）。

路径约定（与 mait24 一致）
------------------------
- 预报（两种布局均可）：
  - ``{root}/YYYYMMDD/micaps/YYYYMMDDHH.TTT.m4``（tch / tch_now）
  - ``{root}/YYYYMMDD/YYYYMMDDHH.TTT.m4``（output）
- 实况：``{dir_ob}/YYMMDDHH.000``（北京时，对应起报+时效的检验时刻）
  例：起报 2026-05-24 00UTC、时效 36h → 实况 ``26052520.000``

命令行
------
::

    python cli/verify.py
    python cli/verify.py --initial-time=2026052400 --dtimes=36,60,84
    python cli/verify.py --compare
    python -m cli.verify
"""
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from clize.parser import value_converter
from clize.runner import Clize, run


def _bootstrap_paths():
    _cli = Path(__file__).resolve().parent
    _root = _cli.parent
    _src = _root / "src"
    for p in (str(_root), str(_src)):
        while p in sys.path:
            sys.path.remove(p)
    for p in (str(_src), str(_root)):
        sys.path.insert(0, p)


_bootstrap_paths()

import numpy as np
import pandas as pd
import meteva.base as meb
import meteva.method as mem
import meteva.product as mpd


_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA = Path(r"D:/Work/NIMM_pip_testdata/multi_rain_mait24_blending/test_data")
_DEFAULT_TCH = _DEFAULT_DATA / "tch" / "sfc"
_DEFAULT_OB = _DEFAULT_DATA / "Observation" / "r24" / "sfc"
_DEFAULT_OUT = _ROOT / "resource" / "verify_out"
_DEFAULT_GRADES = [0.1, 10, 25, 50, 100]
_DEFAULT_DTIMES = [36, 60, 84]
_DEFAULT_PRODUCTS = ["tch"]
_BJT_OFFSET = 8


def _parse_initial_time(text: str) -> datetime:
    """按长度选格式（Windows 下短串套长格式 ``strptime`` 会误解析）。"""
    text = str(text).strip()
    if len(text) >= 14:
        return datetime.strptime(text[:14], "%Y%m%d%H%M%S")
    if len(text) >= 10:
        return datetime.strptime(text[:10], "%Y%m%d%H")
    if len(text) >= 8:
        return datetime.strptime(text[:8], "%Y%m%d")
    raise ValueError("initial_time 格式应为 YYYYMMDDHH 或 YYYYMMDDHHMMSS，收到: %r" % text)


def _fo_m4_candidates(dir_root: Path, initial_time: datetime, dtime: int):
    day = initial_time.strftime("%Y%m%d")
    name = "%s.%03d.m4" % (initial_time.strftime("%Y%m%d%H"), dtime)
    return (
        dir_root / day / "micaps" / name,
        dir_root / day / name,
    )


def _fo_m4_path(dir_tch: Path, initial_time: datetime, dtime: int) -> Path:
    """优先 micaps 子目录，其次日目录扁平布局；都不存在则返回首选路径。"""
    cands = _fo_m4_candidates(Path(dir_tch), initial_time, dtime)
    for path in cands:
        if path.exists():
            return path
    return cands[0]


def _ob_path(dir_ob: Path, initial_time: datetime, dtime: int, bjt_offset: int = _BJT_OFFSET) -> Path:
    """实况文件时刻 = 起报(UTC) + bjt_offset + dtime（北京时命名）。"""
    valid_bjt = initial_time + timedelta(hours=bjt_offset + int(dtime))
    return dir_ob / ("%s.000" % valid_bjt.strftime("%y%m%d%H"))


_M4_NAME_RE = re.compile(r"^(\d{10})\.(\d{3})\.m4$", re.IGNORECASE)


def discover_fo_cases(product_dirs) -> list:
    """从各产品根目录扫描 ``YYYYMMDDHH.TTT.m4``，返回 ``[(init, dtime), ...]``。"""
    cases = set()
    for root in product_dirs.values():
        root = Path(root)
        if not root.is_dir():
            continue
        for m4 in root.rglob("*.m4"):
            match = _M4_NAME_RE.match(m4.name)
            if not match:
                continue
            init = datetime.strptime(match.group(1), "%Y%m%d%H")
            cases.add((init, int(match.group(2))))
    return sorted(cases, key=lambda x: (x[0], x[1]))


def build_sta_all(
    *,
    dir_tch: str = None,
    dir_ob: str = None,
    initial_time: str = "2026052400",
    dtimes=None,
    bjt_offset: int = _BJT_OFFSET,
    product_name: str = "tch",
):
    """
    读 TCH micaps4 → 插值到实况站，拼成 meteva ``sta_all``（列 ``ob`` + 产品名）。
    """
    return build_sta_all_multi(
        product_dirs={product_name: dir_tch or _DEFAULT_TCH},
        dir_ob=dir_ob,
        initial_times=[initial_time],
        dtimes=dtimes,
        bjt_offset=bjt_offset,
    )


def build_sta_all_multi(
    *,
    product_dirs,
    dir_ob: str = None,
    initial_times=None,
    dtimes=None,
    bjt_offset: int = _BJT_OFFSET,
):
    """
    多产品 vs 实况。``product_dirs``: ``{产品名: 根目录}``。

    每个 (起报, 时效) 只要有实况且至少一个产品文件，就拼进 ``sta_all``；
    缺产品的列填 NaN。
    """
    dir_ob = Path(dir_ob or _DEFAULT_OB)
    product_dirs = {str(k): Path(v) for k, v in dict(product_dirs).items()}
    product_names = list(product_dirs.keys())

    if initial_times is None:
        cases = discover_fo_cases(product_dirs)
        if dtimes is not None:
            dtime_set = set(int(x) for x in dtimes)
            cases = [(t, dt) for t, dt in cases if dt in dtime_set]
    else:
        inits = [_parse_initial_time(t) for t in initial_times]
        if dtimes is None:
            dtimes = list(_DEFAULT_DTIMES)
        cases = [(init, int(dt)) for init in inits for dt in dtimes]

    frames = []
    skipped = []
    for init, dt in cases:
        ob_path = _ob_path(dir_ob, init, dt, bjt_offset=bjt_offset)
        if not ob_path.exists():
            skipped.append(("ob", str(ob_path)))
            continue

        fo_paths = {}
        for name, root in product_dirs.items():
            path = _fo_m4_path(root, init, dt)
            if path.exists():
                fo_paths[name] = path
            else:
                skipped.append(("fo:%s" % name, str(path)))
        if not fo_paths:
            continue

        ob = meb.read_stadata_from_micaps3(str(ob_path))
        ob = ob[ob["data0"] < 9990].copy()
        meb.set_stadata_names(ob, ["ob"])
        meb.set_stadata_coords(ob, time=init, dtime=int(dt))
        sta = ob
        used = []
        for name, fo_path in fo_paths.items():
            grd = meb.read_griddata_from_micaps4(str(fo_path))
            fo = meb.interp_gs_nearest(grd, ob)
            meb.set_stadata_names(fo, [name])
            meb.set_stadata_coords(fo, time=init, dtime=int(dt))
            sta = meb.combine_on_id(sta, fo)
            used.append("%s=%s" % (name, fo_path.name))
        for name in product_names:
            if name not in sta.columns:
                sta[name] = np.nan
        frames.append(sta)
        print(
            "配对 init=%s dtime=%s ob=%s | %s → n=%d"
            % (init.strftime("%Y%m%d%H"), dt, ob_path.name, ", ".join(used), len(sta))
        )

    if skipped:
        # 只摘要打印，避免刷屏
        fo_miss = sum(1 for k, _ in skipped if str(k).startswith("fo"))
        ob_miss = sum(1 for k, _ in skipped if k == "ob")
        print("跳过统计: 缺预报 %d 次, 缺实况 %d 次" % (fo_miss, ob_miss))
    if not frames:
        raise FileNotFoundError(
            "无可用预报/实况配对，请检查产品目录 / 实况 / 起报时效"
        )
    return pd.concat(frames, ignore_index=True)


def get_ts(sta_all, grade_list, product_list, h5_file, plot="bar", show=False, save_path=None):
    """按时效×产品算 TS；每产品先 dropna，避免多产品缺测污染 mpd.score。"""
    if save_path is None:
        save_path = str(Path(h5_file).with_name("ts_%s.png" % plot))
    dtimes = sorted(int(x) for x in sta_all["dtime"].unique())
    rows = []
    # (时效, 产品, 阈值)
    res_array = np.full((len(dtimes), len(product_list), len(grade_list)), np.nan)
    for i, shixiao in enumerate(dtimes):
        sub = sta_all[sta_all["dtime"] == shixiao]
        for j, product in enumerate(product_list):
            pair = sub[["ob", product]].dropna()
            if pair.empty:
                rows.append([shixiao, product] + [np.nan] * len(grade_list))
                continue
            ts = np.asarray(
                mem.ts(pair["ob"].values, pair[product].values, grade_list=grade_list),
                dtype=float,
            )
            res_array[i, j, :] = ts
            rows.append([shixiao, product] + ts.tolist())

    df = pd.DataFrame(rows, columns=["时效", "产品名称"] + list(grade_list))
    df.to_hdf(h5_file, key="ts", mode="a")

    # 用 meteva 柱状图：按产品聚合各阈值（多时效时取各时效均值再画总图）
    if plot:
        # 总图：各产品在所有时效上的样本合并后再算一次更直观；这里用表内数值按产品对时效平均
        product_names = list(product_list)
        mean_by_product = []
        for product in product_names:
            sub = df[df["产品名称"] == product][list(grade_list)]
            mean_by_product.append(sub.mean(axis=0, skipna=True).values)
        ts_mat = np.asarray(mean_by_product, dtype=float)
        meb.bar(
            ts_mat,
            name_list_dict={"预报成员": product_names, "分级(单位：mm)": list(grade_list)},
            ylabel="TS评分",
            title="产品TS评分对比",
            save_path=save_path,
            grid=True,
            show=show,
        )
        # 兼容原单产品 mpd.score 出图路径提示
        print("检验结果已以图片形式保存至%s" % save_path)

    print(df)
    print("TS 图: %s" % save_path)
    return df


def get_dt_ts(ts, dt, grade_list, save_path=None, show=False):
    df_dt = ts[ts["时效"] == dt]
    if df_dt.empty:
        print("无时效 %s 的 TS 结果，跳过出图" % dt)
        return
    ts_values = df_dt[grade_list].values
    product_names = df_dt["产品名称"].tolist()
    if save_path is None:
        save_path = "ts_%s.png" % dt
    meb.bar(
        ts_values,
        name_list_dict={"预报成员": product_names, "分级(单位：mm)": list(grade_list)},
        ylabel="TS评分",
        title="%s时效TS评分" % dt,
        save_path=save_path,
        grid=True,
        show=show,
    )
    print("时效图: %s" % save_path)


def get_verify_table(sta_all, grade_list, product_list):
    """按时效输出 hit/miss/over/ts（与 mait24 get_verify_result 同口径）。"""
    dtimes = sorted(int(x) for x in sta_all["dtime"].unique())
    rows = []
    for dtime in dtimes:
        sub = sta_all[sta_all["dtime"] == dtime]
        row = {"dtime": dtime}
        for name in product_list:
            pair = sub[["ob", name]].dropna()
            if pair.empty:
                for grade in grade_list:
                    row["%s_hit_%s" % (name, grade)] = np.nan
                    row["%s_miss_%s" % (name, grade)] = np.nan
                    row["%s_over_%s" % (name, grade)] = np.nan
                    row["%s_ts_%s" % (name, grade)] = np.nan
                continue
            ob = pair["ob"].values
            fo = pair[name].values
            hfmc = mem.hfmc(ob, fo, grade_list=grade_list)
            ts = mem.ts(ob, fo, grade_list=grade_list)
            for gi, grade in enumerate(grade_list):
                row["%s_hit_%s" % (name, grade)] = hfmc[gi][0]
                row["%s_miss_%s" % (name, grade)] = hfmc[gi][1]
                row["%s_over_%s" % (name, grade)] = hfmc[gi][2]
                row["%s_ts_%s" % (name, grade)] = ts[gi]
        rows.append(row)
    return pd.DataFrame(rows)


_DEFAULT_COMPARE_DIRS = {
    "mait": _DEFAULT_DATA / "output",
    "tch": _DEFAULT_DATA / "tch" / "sfc",
    "tch_now": _DEFAULT_DATA / "tch_now" / "sfc",
}


def process(
    *,
    dir_tch: str = None,
    dir_ob: str = None,
    initial_time: str = "2026052400",
    dtimes=None,
    grade_list=None,
    product_list=None,
    output_dir: str = None,
    plot: str = "bar",
    show: bool = False,
    bjt_offset: int = _BJT_OFFSET,
    product_dirs=None,
    compare: bool = False,
):
    """准备配对数据 → TS 评分 → 出图（全时效 + 分时效）。

    ``compare=True`` 时对比 output / tch / tch_now（或自定义 ``product_dirs``）。
    """
    if dtimes is None:
        dtimes = list(_DEFAULT_DTIMES)
    if grade_list is None:
        grade_list = list(_DEFAULT_GRADES)

    out = Path(output_dir or (_DEFAULT_OUT / "compare" if compare or product_dirs else _DEFAULT_OUT))
    out.mkdir(parents=True, exist_ok=True)
    h5_file = str(out / "verify_results.h5")

    if product_dirs or compare:
        dirs = dict(product_dirs) if product_dirs else dict(_DEFAULT_COMPARE_DIRS)
        product_list = list(dirs.keys())
        # compare 默认扫全部起报；若显式给了 initial_time 则只评该时次
        init_list = None
        if not compare and initial_time:
            init_list = [initial_time]
        sta_all = build_sta_all_multi(
            product_dirs=dirs,
            dir_ob=dir_ob,
            initial_times=init_list,
            dtimes=dtimes,
            bjt_offset=bjt_offset,
        )
    else:
        if product_list is None:
            product_list = list(_DEFAULT_PRODUCTS)
        sta_all = build_sta_all(
            dir_tch=dir_tch,
            dir_ob=dir_ob,
            initial_time=initial_time,
            dtimes=dtimes,
            bjt_offset=bjt_offset,
            product_name=product_list[0],
        )

    # 评分时去掉全 NaN 产品列
    product_list = [p for p in product_list if p in sta_all.columns and sta_all[p].notna().any()]
    if not product_list:
        raise RuntimeError("sta_all 中无有效产品列")

    sta_all.to_hdf(h5_file, key="sta_all", mode="w")

    table = get_verify_table(sta_all, grade_list, product_list)
    table.to_csv(out / "verify_results.csv", index=False)
    table.to_hdf(h5_file, key="verify_table", mode="a")
    print(table)

    ts_df = get_ts(
        sta_all,
        grade_list,
        product_list,
        h5_file,
        plot=plot,
        show=show,
        save_path=str(out / ("ts_%s.png" % plot)),
    )
    for dt in sorted(int(x) for x in ts_df["时效"].unique()):
        get_dt_ts(ts_df, dt, grade_list, save_path=str(out / ("ts_%s.png" % dt)), show=show)

    print("结果目录: %s" % out)
    return out


def _cli_converters():
    @value_converter
    def comma_float_list(s):
        if s is None or not str(s).strip():
            return None
        return [float(x.strip()) for x in str(s).split(",") if x.strip()]

    @value_converter
    def comma_int_list(s):
        if s is None or not str(s).strip():
            return None
        return [int(float(x.strip())) for x in str(s).split(",") if x.strip()]

    @value_converter
    def comma_str_list(s):
        if s is None or not str(s).strip():
            return None
        return [x.strip() for x in str(s).split(",") if x.strip()]

    @value_converter
    def optional_str(s):
        if s is None or not str(s).strip():
            return None
        return str(s)

    return comma_float_list, comma_int_list, comma_str_list, optional_str


def _make_cli():
    comma_float_list, comma_int_list, comma_str_list, optional_str = _cli_converters()

    def run_cli(
        *,
        dir_tch: optional_str = None,
        dir_ob: optional_str = None,
        initial_time: optional_str = "2026052400",
        dtimes: comma_int_list = None,
        grade_list: comma_float_list = None,
        product_list: comma_str_list = None,
        output_dir: optional_str = None,
        plot: optional_str = "bar",
        show: bool = False,
        compare: bool = False,
    ):
        """
        TCH 对实况 TS 检验并出图

        :param dir_tch: TCH 产品根目录（含 YYYYMMDD/micaps）
        :param dir_ob: 实况 Micaps3 目录（r24/sfc）
        :param initial_time: 起报 UTC，YYYYMMDDHH（单产品模式）
        :param dtimes: 时效，逗号分隔，默认 36,60,84
        :param grade_list: 降水阈值 mm，默认 0.1,10,25,50,100
        :param product_list: 产品列名，默认 tch
        :param output_dir: 图/表输出目录
        :param plot: mpd.score 图类型，默认 bar
        :param show: 是否弹窗显示
        :param compare: 对比 output / tch / tch_now 三套产品
        """
        process(
            dir_tch=dir_tch,
            dir_ob=dir_ob,
            initial_time=initial_time or "2026052400",
            dtimes=dtimes,
            grade_list=grade_list,
            product_list=product_list,
            output_dir=output_dir,
            plot=plot or "bar",
            show=show,
            compare=compare,
        )

    return Clize(run_cli)


def main():
    run(_make_cli())


if __name__ == "__main__":
    main()
