"""把不同起报时次、同一有效时间的集合成员合并成时间滞后集合。"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import xarray as xr

from time_lagging.util.meteva_data import (
    cycle_shift,
    ensure_grid,
    ensure_station,
    lead_units,
    validity_times,
)


class GenerateTimeLaggedEnsemble:
    """合并多个起报时次的集合预报。

    meteva 里 time 是起报时间，dtime 是时效，二者相加是有效时间。
    各输入的有效时间必须一致。合并时把起报时间统一到最新时次，并重算时效，
    使有效时间保持不变。member 是集合成员；编号重复时按输入顺序重新编号。
    """

    def process(self, *datasets):
        datasets = _flatten(datasets)
        if not datasets:
            raise ValueError("至少需要一份预报")
        if all(isinstance(item, xr.DataArray) for item in datasets):
            return self._process_grids(datasets)
        if all(isinstance(item, pd.DataFrame) for item in datasets):
            return self._process_stations(datasets)
        raise TypeError("时间滞后只接受同一类数据：全部为格点，或全部为站点表")

    def _process_grids(self, datasets: list[xr.DataArray]) -> xr.DataArray:
        # 按起报时次拆成单时次切片
        slices = []
        for grid in datasets:
            prepared = ensure_grid(grid)
            for index in range(prepared.sizes["time"]):
                slices.append(prepared.isel(time=[index]))
        if len(slices) == 1:
            warnings.warn("只有一个起报时次，时间滞后不会改变成员。")
            return slices[0]

        units = _common_units(slices)
        # 校验有效时间一致，并按有效时间排序时效
        ordered = []
        validity_reference = None
        for item in slices:
            item = _sort_grid_by_validity(item, units)
            validity = tuple(pd.to_datetime(_grid_validity(item, units)).astype("datetime64[ns]"))
            if validity_reference is None:
                validity_reference = validity
            elif validity != validity_reference:
                raise ValueError("各起报时次的有效时间不一致，不能做时间滞后")
            ordered.append(item)

        # 统一到最新起报，并重算时效使有效时间不变
        latest = max(pd.Timestamp(item.time.values[0]) for item in ordered)
        latest_item = max(ordered, key=lambda item: pd.Timestamp(item.time.values[0]))
        rebadged = [_rebadge_grid(item, latest, units) for item in ordered]
        _assert_same_space(rebadged)
        # 成员编号重复时顺延，再沿 member 拼接
        rebadged = _renumber_grid_members(rebadged)
        reference = rebadged[0]
        aligned = []
        for item in rebadged:
            aligned.append(
                item.assign_coords(
                    time=reference.time,
                    dtime=reference.dtime,
                    level=reference.level,
                    lat=reference.lat,
                    lon=reference.lon,
                )
            )
        merged = xr.concat(aligned, dim="member")
        merged.attrs = dict(latest_item.attrs)
        merged.attrs["dtime_units"] = units
        merged.attrs["model_var"] = "time_lagged"
        merged.name = latest_item.name
        return ensure_grid(merged)

    def _process_stations(self, datasets: list[pd.DataFrame]) -> pd.DataFrame:
        slices = []
        for frame in datasets:
            prepared = ensure_station(frame)
            for _, part in prepared.groupby("time", sort=False):
                slices.append(part.copy())
        if len(slices) == 1:
            warnings.warn("只有一个起报时次，时间滞后不会改变成员。")
            return ensure_station(slices[0])

        units = _common_station_units(slices)
        prepared_slices = []
        key_reference = None
        for item in slices:
            item = item.copy()
            item["valid_time"] = validity_times(item["time"], item["dtime"], units)
            keys = _station_case_keys(item)
            if key_reference is None:
                key_reference = keys
            elif keys != key_reference:
                raise ValueError("各起报时次的站点或有效时间不一致，不能做时间滞后")
            prepared_slices.append(item)

        latest = max(pd.Timestamp(item["time"].max()) for item in prepared_slices)
        latest_attrs = dict(max(prepared_slices, key=lambda item: pd.Timestamp(item["time"].max())).attrs)
        rebadged = [_rebadge_station(item, latest, units) for item in prepared_slices]
        rebadged = _renumber_station_members(rebadged)
        merged = pd.concat(rebadged, ignore_index=True)
        merged = merged.drop(columns=["valid_time"])
        merged.attrs = latest_attrs
        merged.attrs["dtime_units"] = units
        merged.attrs["model_var"] = "time_lagged"
        if "member" in merged.columns:
            merged["member"] = _tidy_member(merged["member"])
        front = ["level", "time", "dtime", "id", "lon", "lat"]
        if "member" in merged.columns:
            front.append("member")
        others = [column for column in merged.columns if column not in front]
        merged = merged[front + others].sort_values(front).reset_index(drop=True)
        return ensure_station(merged)


def time_lag(*datasets):
    """合并时间滞后集合，返回格点或站点表。"""
    from time_lagging.src.time_lagging_plugin import TimeLaggingPlugin

    return TimeLaggingPlugin().process(*datasets)


def _flatten(datasets) -> list:
    if len(datasets) == 1 and isinstance(datasets[0], (list, tuple)):
        return list(datasets[0])
    return list(datasets)


def _common_units(slices: list[xr.DataArray]) -> str:
    units = {lead_units(item.attrs.get("dtime_units", "hour")) for item in slices}
    if len(units) != 1:
        raise ValueError(f"各输入的 dtime_units 不一致: {sorted(units)}")
    return units.pop()


def _common_station_units(slices: list[pd.DataFrame]) -> str:
    units = {lead_units(item.attrs.get("dtime_units", "hour")) for item in slices}
    if len(units) != 1:
        raise ValueError(f"各输入的 dtime_units 不一致: {sorted(units)}")
    return units.pop()


def _grid_validity(grid: xr.DataArray, units: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(validity_times(grid.time.values[0], grid.dtime.values, units))


def _sort_grid_by_validity(grid: xr.DataArray, units: str) -> xr.DataArray:
    order = np.argsort(pd.to_datetime(_grid_validity(grid, units)).to_numpy())
    return grid.isel(dtime=order)


def _rebadge_grid(grid: xr.DataArray, latest: pd.Timestamp, units: str) -> xr.DataArray:
    shift = cycle_shift(grid.time.values[0], latest, units)
    dtime = grid.dtime.values.astype(np.int64) - shift
    updated = grid.copy()
    updated = updated.assign_coords(
        time=np.asarray([pd.Timestamp(latest).to_numpy()], dtype="datetime64[ns]"),
        dtime=dtime.astype(np.int32),
    )
    return updated


def _assert_same_space(grids: list[xr.DataArray]) -> None:
    reference = grids[0]
    for grid in grids[1:]:
        if not np.array_equal(grid.dtime.values, reference.dtime.values):
            raise ValueError("统一起报时间后时效仍不一致")
        if not np.allclose(grid.lat.values, reference.lat.values) or not np.allclose(
            grid.lon.values, reference.lon.values
        ):
            raise ValueError("各输入的经纬度坐标不一致")
        if not np.allclose(grid.level.values, reference.level.values):
            raise ValueError("各输入的层次坐标不一致")
        if grid.shape[1:] != reference.shape[1:]:
            raise ValueError("各输入除集合成员外的数据形状不一致")


def _member_label(value) -> str:
    number = float(value)
    if abs(number - round(number)) < 1e-6:
        return str(int(round(number)))
    return str(value)


def _renumber_grid_members(grids: list[xr.DataArray]) -> list[xr.DataArray]:
    labels = [[_member_label(value) for value in grid.member.values] for grid in grids]
    flat = [label for group in labels for label in group]
    if len(set(flat)) == len(flat):
        return grids
    start = 0
    renumbered = []
    for grid in grids:
        count = grid.sizes["member"]
        updated = grid.assign_coords(member=[str(index) for index in range(start, start + count)])
        renumbered.append(updated)
        start += count
    return renumbered


def _station_case_keys(frame: pd.DataFrame) -> set[tuple]:
    table = pd.DataFrame(
        {
            "id": frame["id"].to_numpy(),
            "level": np.round(frame["level"].to_numpy(dtype=float), 5),
            "valid_time": pd.to_datetime(frame["valid_time"]).astype("datetime64[ns]").to_numpy(),
        }
    ).drop_duplicates()
    return set(map(tuple, table.to_numpy()))


def _rebadge_station(frame: pd.DataFrame, latest: pd.Timestamp, units: str) -> pd.DataFrame:
    updated = frame.copy()
    shift = np.array(
        [cycle_shift(value, latest, units) for value in updated["time"]],
        dtype=np.int64,
    )
    updated["dtime"] = updated["dtime"].to_numpy(dtype=np.int64) - shift
    updated["time"] = pd.Timestamp(latest)
    updated.attrs = dict(frame.attrs)
    return updated


def _appearance_labels(frame: pd.DataFrame) -> list[str]:
    if "member" not in frame.columns:
        return ["0"]
    labels = []
    for value in frame["member"]:
        label = _member_label(value)
        if label not in labels:
            labels.append(label)
    return labels


def _renumber_station_members(frames: list[pd.DataFrame]) -> list[pd.DataFrame]:
    grouped = [_appearance_labels(frame) for frame in frames]
    flat = [label for group in grouped for label in group]
    duplicated = len(set(flat)) < len(flat)
    updated_frames = []
    start = 0
    for frame, labels in zip(frames, grouped):
        updated = frame.copy()
        if "member" not in updated.columns:
            updated["member"] = start if duplicated else 0
            start += 1
        elif duplicated:
            mapping = {}
            for label in labels:
                mapping[label] = start
                start += 1
            updated["member"] = [_member_label(value) for value in updated["member"]]
            updated["member"] = updated["member"].map(mapping)
        updated.attrs = dict(frame.attrs)
        updated_frames.append(updated)
    if not duplicated:
        for frame in updated_frames:
            if "member" not in frame.columns:
                frame["member"] = 0
    return updated_frames


def _tidy_member(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().all() and np.allclose(numeric, np.round(numeric)):
        return np.round(numeric).astype(np.int32)
    return values
