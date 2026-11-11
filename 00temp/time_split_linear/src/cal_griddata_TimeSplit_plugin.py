# -*- coding: utf-8 -*-
"""粗时效预报场沿预报时效或起报时间做时间降尺度。

职责边界：
- 本插件只处理**已经在内存中**的格点场，不读路径、不解析 ``input_fh``。
- 读文件、``is_fill0``、按起报时间列表拼接，由 CLI 模块级 ``process``
  调用 ``read_multi_griddata`` 完成后再传入 ``TimeSplit.process``。

插值轴：
- ``index="dtime"``：沿预报时效插值；源 ``dtime`` 单位为小时。
- ``index="time"``：沿起报时间插值；预报时效保持原样。

可选能力：``is_Min`` 时输出坐标按分钟；可合成风速；给出 ``delta`` 时做累计
差分并把细场负值裁成 0；``output_fmt`` 写出 nc（写盘不再单独裁负）。空间网格不变。
"""

from datetime import timedelta
import numpy as np
import os
from utils.base_plugin import PostProcessingPlugin
from typing import Optional, Tuple
import meteva_base as meb
import xarray as xr
from utils.grid_combine import concat_griddata


class TimeSplit(PostProcessingPlugin):
    """把粗时间格点插值成细时间格点。

    输出坐标用 ``[起点, 终点, 步长]`` 表示，终点包含在结果中。
    例如 ``[0, 9, 3]`` 得到 ``0, 3, 6, 9``。

    - ``is_Min`` 为真时，输出三元组按**分钟**，例如 ``[0, 360, 10]``。
    - ``index="time"`` 时，输出三元组是相对最早输入起报时间的偏移
      （小时或分钟，取决于 ``is_Min``），不是预报时效本身。
    - 输入时效列表不在本类构造；由调用方先读好场再传入 ``process``。
    """

    def __init__(self,
                 model_id_attr: Optional[str] = None,
                 output_fh_list: list = None,
                 interp_method: Optional[str] = 'slinear',
                 output_fmt: Optional[str] = None,
                 delta: Optional[str] = None,
                 is_Min: Optional[bool] = False,
                 index: Optional[str] = "dtime",
                 ):
        """保存输出坐标和可选的差分、写出设置。

        Args:
            model_id_attr: 来源模式标识，本算法不使用。
            output_fh_list: 输出坐标 ``[起点, 终点, 步长]``，终点包含在结果中。
                ``index="dtime"`` 时这是预报时效；``index="time"`` 时这是相对最早
                输入起报时间的偏移。``is_Min`` 为假时单位是小时，为真时是分钟。
            interp_method: 传给 ``DataArray.interp`` 的插值方法，默认 ``slinear``。
            output_fmt: 输出路径模板。为空时不写文件。
                ``index="dtime"``：每个输出时效写一个文件，``TTT``/``TTTT`` 为该时效；
                起报时间取输入场最早的 ``time``。
                ``index="time"``：每个输出起报时间写一个文件；仅一个时效时 ``TTT``
                用该时效，否则用 0。
                分钟起报时间模板需含 ``FF``，否则同一小时内多时刻会撞路径。
                分钟时效超过 999 时需用 ``TTTT``。
            delta: 累计场差分间隔。为空则不做差分、也不裁负值（瞬时场走此路径）。
                有值时先做差分得到时段增量，再把细场负值裁成 ``0``（与是否写盘无关）。
                **单位与 ``is_Min`` / 输出坐标一致**：``is_Min`` 为假时按小时，为真时按分钟。
                不必等于 ``output_fh`` 的步长（分辨率由输出轴决定，窗长由本参数决定）。
                ``index="dtime"``：原样作为 ``meb.change`` 的 ``delta``（与 ``dtime`` 坐标同单位）。
                ``index="time"``：``meb.change`` 沿起报时间轴且其 ``delta`` 按小时；
                若 ``is_Min`` 为真，先把分钟间隔除以 60 再传入。
            is_Min: 为真时输出坐标按分钟。``index="dtime"`` 时插值前把源时效乘 60；
                ``index="time"`` 时只改变起报偏移的单位，预报时效仍是小时。
            index: 插值轴。``dtime`` 为预报时效，``time`` 为起报时间。
        """
        self.model_id_attr = model_id_attr
        # 右边界 +1：终点进入序列，且不会多走出一个步长（等价于含端点的 arange）。
        self.output_fh_list = np.arange(output_fh_list[0], output_fh_list[1] + 1, output_fh_list[2])
        self.interp_method = interp_method
        self.output_fmt = output_fmt
        self.delta = delta
        self.is_Min = is_Min
        self.index = index or "dtime"
        # 有有效 delta 才做累计差分，并在差分后裁负；否则不裁。
        self.clip_nonnegative = (
            delta is not None and str(delta).strip() != ""
        )

    def _ensure_lead0(self, grd):
        """沿 ``dtime`` 插值前保证存在时效 0。

        已有时效 0 时原样返回。否则复制第一帧形状造全 0 场，``dtime=0``，
        再与原场沿时效拼接。仅 ``index="dtime"`` 路径调用；``index="time"`` 不补。
        """
        leads = np.rint(np.asarray(grd.dtime.values, dtype=float)).astype(np.int64)
        if np.any(leads == 0):
            return grd
        zero = grd.isel(dtime=[0]).copy(deep=True)
        zero.values[:] = 0
        meb.set_griddata_coords(zero, dtime_list=[0])
        combined = concat_griddata([zero, grd])
        return grd if combined is None else combined

    def _output_issue_times(self, grd_all, offsets):
        """把输出偏移加到最早输入起报时间上，得到 ``interp(time=...)`` 的目标时刻。

        ``is_Min`` 为真时 ``offsets`` 按分钟解释，否则按小时。
        """
        anchor = meb.all_type_time_to_datetime(np.asarray(grd_all.time.values)[0])
        if self.is_Min:
            return [anchor + timedelta(minutes=int(offset)) for offset in offsets]
        return [anchor + timedelta(hours=float(offset)) for offset in offsets]

    def process(
        self,
        fcst: xr.DataArray,
        uv: Optional[xr.DataArray] = None,
    ) -> Tuple[Optional[xr.DataArray], Optional[xr.DataArray]]:
        """对内存中的粗时间场插值，并按需要合成风速、做差分和写文件。

        Args:
            fcst: 已读入内存的格点场，维度含
                ``member, level, time, dtime, lat, lon``。
                ``index="dtime"`` 时其 ``dtime`` 单位为小时。
                ``index="time"`` 时沿起报时间轴插值，预报时效保持原样。
            uv: 可选 V 分量，形状/坐标应与 ``fcst`` 一致。
                给出时 ``fcst`` 作 U，插值前只保留风速。默认 ``None``。

        Returns:
            ``(细时间场, 插值前的粗时间场)``。``index`` 非法或插值异常时为 ``(None, None)``。

            - ``index="dtime"`` 且 ``is_Min``：细场 ``dtime`` 为分钟，粗场仍为小时。
            - ``index="dtime"`` 且输入无时效 0：返回的粗场会多一帧全 0 的时效 0。
            - ``index="time"``：细场起报时间为输出偏移对应时刻，预报时效仍为小时。
            - ``clip_nonnegative`` 为真时，返回的细场已将负值裁成 ``0``。
        """
        if self.index not in ("dtime", "time"):
            print("index must be dtime or time")
            return None, None
        fh01_list = self.output_fh_list
        # 传给 meb.change 的间隔：dtime 与坐标同单位；time 轴固定要小时（分钟入参先 /60）。
        change_delta = None
        if self.clip_nonnegative:
            change_delta = float(self.delta)
            if self.index == "time" and self.is_Min:
                change_delta = change_delta / 60.0
        try:
            grd_all = fcst
            print(grd_all)
            # 主场为 U，uv 为 V；只保留风速，风向不参与后续插值。
            if uv is not None:
                print(uv)
                grd_all, _ = meb.u_v_to_speed_angle(grd_all, uv)
            if self.index == "time":
                # 沿起报时间插值：不改 dtime；目标时刻 = 最早起报 + 输出偏移。
                targets = self._output_issue_times(grd_all, fh01_list)
                target = np.array(targets, dtype="datetime64[ns]")
                grd_all_01h = grd_all.interp(
                    time=target, method=self.interp_method, kwargs={"fill_value": "extrapolate"}
                )
                # 沿 time 做差；配不到起点的时刻会被去掉。
                if change_delta is not None:
                    grd_all_01h = meb.change(
                        grd_all_01h, delta=change_delta, used_coords="time"
                    )
            else:
                # 沿 dtime：先补时效 0（若缺失），再按需把源时效换成分钟坐标后插值。
                grd_all = self._ensure_lead0(grd_all)
                interp_source = grd_all
                if self.is_Min:
                    minute_leads = np.rint(np.asarray(grd_all.dtime.values, dtype=float) * 60).astype(np.int64)
                    interp_source = grd_all.assign_coords(dtime=minute_leads)
                    interp_source.attrs = dict(grd_all.attrs)
                    interp_source.attrs["dtime_units"] = "minute"
                # 目标超出源两端时按斜率外推（fill_value=extrapolate）。
                grd_all_01h = interp_source.interp(
                    dtime=fh01_list, method=self.interp_method, kwargs={"fill_value": "extrapolate"}
                )
                # delta 已与 dtime 坐标同单位，直接 change。
                if change_delta is not None:
                    grd_all_01h = meb.change(
                        grd_all_01h, delta=change_delta, used_coords="dtime"
                    )
        except Exception as err:
            print(err)
            return None, None
        # 累计差分后的时段量：负值裁 0（由 clip_nonnegative 控制，与是否写盘无关）。
        if self.clip_nonnegative:
            grd_all_01h = grd_all_01h.copy(deep=True)
            grd_all_01h.values[grd_all_01h.values < 0] = 0
        # 写出：文件已存在则跳过；数值与返回的细场一致。
        if self.output_fmt is not None:
            if self.index == "time":
                self._write_issue_times(grd_all_01h)
            else:
                issue = meb.all_type_time_to_datetime(np.asarray(grd_all.time.values)[0])
                self._write_leads(grd_all_01h, fh01_list, issue)
        return (grd_all_01h, grd_all)

    def _write_leads(self, grd_all_01h, fh01_list, time):
        """``index="dtime"``：按每个输出时效写一个 nc。

        ``time`` 为输入场最早起报；``dt`` 为该输出时效（小时或分钟，与 ``is_Min`` 一致）。
        此处不裁负；非负约束由 ``clip_nonnegative`` 在写盘前统一处理。
        """
        # 差分后部分时效会被 meb.change 丢掉，只写细场里实际存在的时效
        available = set(np.asarray(grd_all_01h.dtime.values).tolist())
        for fh01 in fh01_list:
            if fh01 not in available and int(fh01) not in available:
                continue
            # get_path 的 dt 需为整型时效；arange 可能给出 float64
            dt = int(fh01) if float(fh01).is_integer() else float(fh01)
            out_file = meb.get_path(self.output_fmt, time=time, dt=dt)
            if not os.path.exists(out_file):
                try:
                    sel = int(fh01) if int(fh01) in available else fh01
                    grd_01h = grd_all_01h.sel(dtime=[sel]).astype(np.float32)
                    meb.write_griddata_to_nc(grd_01h, out_file, effectiveNum=2, creat_dir=True)
                    print(out_file)
                except Exception as err:
                    print(err, time, fh01)
                    continue

    def _write_issue_times(self, grd_all_01h):
        """``index="time"``：按每个输出起报时间写一个 nc。

        仅一个 ``dtime`` 时路径用该时效，否则 ``dt=0``。
        此处不裁负；非负约束由 ``clip_nonnegative`` 在写盘前统一处理。
        """
        dtimes = np.asarray(grd_all_01h.dtime.values)
        dt = int(dtimes[0]) if dtimes.size == 1 else 0
        for stamp in np.asarray(grd_all_01h.time.values):
            issue = meb.all_type_time_to_datetime(stamp)
            out_file = meb.get_path(self.output_fmt, time=issue, dt=dt)
            if os.path.exists(out_file):
                continue
            try:
                grd_01h = grd_all_01h.sel(time=[stamp]).astype(np.float32)
                meb.write_griddata_to_nc(grd_01h, out_file, effectiveNum=2, creat_dir=True)
                print(out_file)
            except Exception as err:
                print(err, issue)
                continue
