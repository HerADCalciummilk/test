#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""单个二维速度切片的区域退模糊求解逻辑。"""

from __future__ import annotations

import warnings

import numpy as np
import scipy.ndimage as ndimage
import xarray as xr
from scipy.optimize import fmin_l_bfgs_b

from radar_wind_dealiasing.src.grid_gate_filter import _as_2d_array
from radar_wind_dealiasing.src.utils._fast_edge_finder import _fast_edge_finder


class _RegionTracker:
    """追踪区域合并和展开圈数的状态。"""

    def __init__(self, region_sizes):
        nregions = len(region_sizes) + 1
        self.node_size = np.zeros(nregions, dtype="int32")
        self.node_size[1:] = region_sizes[:]

        self.regions_in_node = np.zeros(nregions, dtype="object")
        for i in range(nregions):
            self.regions_in_node[i] = [i]

        self.unwrap_number = np.zeros(nregions, dtype="int32")

    def merge_nodes(self, node_a, node_b):
        """将节点 ``node_b`` 合并到 ``node_a``。"""
        regions_to_merge = self.regions_in_node[node_b]
        self.regions_in_node[node_a].extend(regions_to_merge)
        self.regions_in_node[node_b] = []

        self.node_size[node_a] += self.node_size[node_b]
        self.node_size[node_b] = 0

    def unwrap_node(self, node, nwrap):
        """为节点内所有区域增加展开圈数。"""
        if nwrap == 0:
            return
        regions_to_unwrap = self.regions_in_node[node]
        self.unwrap_number[regions_to_unwrap] += nwrap

    def get_node_size(self, node):
        """返回节点包含的格点数。"""
        return self.node_size[node]


class _EdgeTracker:
    """追踪边的关系、权重和优先级。"""

    def __init__(self, indices, edge_count, velocities, nyquist_interval, nnodes):
        nedges = int(len(indices[0]) / 2)

        self.node_alpha = np.zeros(nedges, dtype=np.int32)
        self.node_beta = np.zeros(nedges, dtype=np.int32)
        self.sum_diff = np.zeros(nedges, dtype=np.float32)
        self.weight = np.zeros(nedges, dtype=np.int32)

        self._common_finder = np.zeros(nnodes, dtype=np.bool_)
        self._common_index = np.zeros(nnodes, dtype=np.int32)
        self._last_base_node = -1

        self.edges_in_node = np.zeros(nnodes, dtype="object")
        for i in range(nnodes):
            self.edges_in_node[i] = []

        edge = 0
        idx1, idx2 = indices
        vel1, vel2 = velocities
        for i, j, count, vel, nvel in zip(idx1, idx2, edge_count, vel1, vel2):
            if i < j:
                continue
            self.node_alpha[edge] = i
            self.node_beta[edge] = j
            self.sum_diff[edge] = (vel - nvel) / nyquist_interval
            self.weight[edge] = count
            self.edges_in_node[i].append(edge)
            self.edges_in_node[j].append(edge)
            edge += 1

        self.priority_queue = []

    def merge_nodes(self, base_node, merge_node, foo_edge):
        """合并两个节点对应的边信息。"""
        self.weight[foo_edge] = -999
        self.edges_in_node[merge_node].remove(foo_edge)
        self.edges_in_node[base_node].remove(foo_edge)
        self._common_finder[merge_node] = False

        edges_in_merge = list(self.edges_in_node[merge_node])

        if self._last_base_node != base_node:
            self._common_finder[:] = False
            edges_in_base = list(self.edges_in_node[base_node])
            for edge_num in edges_in_base:
                if self.node_beta[edge_num] == base_node:
                    self._reverse_edge_direction(edge_num)
                assert self.node_alpha[edge_num] == base_node

                neighbor = self.node_beta[edge_num]
                self._common_finder[neighbor] = True
                self._common_index[neighbor] = edge_num

        for edge_num in edges_in_merge:
            if self.node_beta[edge_num] == merge_node:
                self._reverse_edge_direction(edge_num)
            assert self.node_alpha[edge_num] == merge_node

            self.node_alpha[edge_num] = base_node

            neighbor = self.node_beta[edge_num]
            if self._common_finder[neighbor]:
                base_edge_num = self._common_index[neighbor]
                self._combine_edges(base_edge_num, edge_num, merge_node, neighbor)
            else:
                self._common_finder[neighbor] = True
                self._common_index[neighbor] = edge_num

        edges = self.edges_in_node[merge_node]
        self.edges_in_node[base_node].extend(edges)
        self.edges_in_node[merge_node] = []
        self._last_base_node = int(base_node)

    def _combine_edges(self, base_edge, merge_edge, merge_node, neighbor_node):
        """合并重复边。"""
        self.weight[base_edge] += self.weight[merge_edge]
        self.weight[merge_edge] = -999.0
        self.sum_diff[base_edge] += self.sum_diff[merge_edge]

        self.edges_in_node[merge_node].remove(merge_edge)
        self.edges_in_node[neighbor_node].remove(merge_edge)

    def _reverse_edge_direction(self, edge):
        """反转边的方向。"""
        old_alpha = int(self.node_alpha[edge])
        old_beta = int(self.node_beta[edge])
        self.node_alpha[edge] = old_beta
        self.node_beta[edge] = old_alpha
        self.sum_diff[edge] = -1.0 * self.sum_diff[edge]

    def unwrap_node(self, node, nwrap):
        """节点展开后，更新相关边的差值。"""
        if nwrap == 0:
            return

        for edge in self.edges_in_node[node]:
            weight = self.weight[edge]
            if node == self.node_alpha[edge]:
                self.sum_diff[edge] += weight * nwrap
            else:
                assert self.node_beta[edge] == node
                self.sum_diff[edge] += -weight * nwrap

    def pop_edge(self):
        """取出当前权重最高的边。"""
        edge_num = np.argmax(self.weight)
        node1 = self.node_alpha[edge_num]
        node2 = self.node_beta[edge_num]
        weight = self.weight[edge_num]
        diff = self.sum_diff[edge_num] / float(weight)

        if weight < 0:
            return True, None
        return False, (node1, node2, weight, diff, edge_num)


def _dealias_region_based_2d(
    velocity_slice: xr.DataArray,
    gate_excluded,
    nyquist_vel: float,
    ref_velocity: xr.DataArray | None,
    interval_splits: int,
    interval_limits,
    skip_between_rays: int,
    skip_along_ray: int,
    centered: bool,
    rays_wrap_around: bool,
    keep_original: bool,
    sweep_index: int = 0,
) -> np.ndarray:
    """对单个 2D 切片执行区域退模糊。

    Parameters
    ----------
    gate_excluded : array-like of bool
        当前 sweep 的二维排除掩码（与 Py-ART ``sfilter = gfilter[sweep_slice]`` 对齐）。
        体扫级 ``exclude_masked`` / ``exclude_invalid`` 应在调用前完成。
    """
    vdata = _as_2d_array(velocity_slice).view(np.ndarray)
    gfilter = np.asarray(gate_excluded, dtype=bool)
    if gfilter.shape != vdata.shape:
        raise ValueError(
            "gate_excluded shape must match the 2D velocity sweep: "
            f"{gfilter.shape} vs {vdata.shape}"
        )

    ref_vdata = (
        None
        if ref_velocity is None
        else _as_2d_array(ref_velocity).view(np.ndarray)
    )
    data = vdata.copy()

    nyquist_interval = nyquist_vel * 2.0
    if interval_limits is None:
        valid_sdata = vdata[~gfilter]
        s_interval_limits = _find_sweep_interval_splits(
            nyquist_vel,
            interval_splits,
            valid_sdata,
            sweep_index,
        )
    else:
        s_interval_limits = interval_limits

    labels, nfeatures = _find_regions(vdata, gfilter, s_interval_limits)
    if nfeatures >= 2:
        bincount = np.bincount(labels.ravel())
        num_masked_gates = bincount[0]
        region_sizes = bincount[1:]

        indices, edge_count, velos = _edge_sum_and_count(
            labels,
            num_masked_gates,
            vdata,
            rays_wrap_around,
            skip_between_rays,
            skip_along_ray,
        )

        if len(edge_count) != 0:
            region_tracker = _RegionTracker(region_sizes)
            edge_tracker = _EdgeTracker(
                indices,
                edge_count,
                velos,
                nyquist_interval,
                nfeatures + 1,
            )
            while True:
                if _combine_regions(region_tracker, edge_tracker):
                    break

            if centered:
                gates_dealiased = region_sizes.sum()
                total_folds = np.sum(
                    region_sizes * region_tracker.unwrap_number[1:]
                )
                sweep_offset = int(round(float(total_folds) / gates_dealiased))
                if sweep_offset != 0:
                    region_tracker.unwrap_number -= sweep_offset

            nwrap = np.take(region_tracker.unwrap_number, labels)
            data += nwrap * nyquist_interval

            if ref_vdata is not None:
                data = _anchor_to_reference(
                    data,
                    ref_vdata,
                    gfilter,
                    labels,
                    nyquist_interval,
                )

    if np.any(gfilter):
        data = np.ma.array(data, mask=gfilter, fill_value=np.nan)

    if keep_original:
        data[gfilter] = vdata[gfilter]

    values = np.ma.asarray(data, dtype=np.float32)
    if np.ma.isMaskedArray(values):
        return values.filled(np.nan)
    return np.asarray(values, dtype=np.float32)


def _anchor_to_reference(data, ref_vdata, gfilter, labels, nyquist_interval):
    """使用参考速度场调整区域的 Nyquist 圈数。

    实现与 Py-ART ``region_dealias`` 参考场锚定分支保持同构。
    本仓库以 NaN 表示缺测，因此先将非有限值转为掩膜，再使用
    ``MaskedArray.mean``（对应官方雷达场上的掩膜均值）。
    """
    # Py-ART 保留参考场 MaskedArray；此处将 NaN 映射为 mask。
    sref = np.ma.masked_invalid(np.asarray(ref_vdata, dtype=np.float64))
    scorr = np.asarray(data, dtype=np.float64)

    gfold = (sref - scorr).mean() / nyquist_interval
    # 与 Py-ART 相同：直接 round；参考场全无效时 mean 为 masked/NaN，此处会失败。
    gfold = int(round(gfold))

    new_interval_limits = np.linspace(scorr.min(), scorr.max(), 10)
    labels_corr, nfeatures_corr = _find_regions(
        scorr,
        gfilter,
        new_interval_limits,
    )

    if nfeatures_corr < 2:
        return data + gfold * nyquist_interval

    bounds_list = [
        (x, y)
        for (x, y) in zip(
            -6 * np.ones(nfeatures_corr),
            5 * np.ones(nfeatures_corr),
        )
    ]
    data_means = np.zeros(nfeatures_corr)
    ref_means = np.zeros(nfeatures_corr)
    for reg in range(1, nfeatures_corr + 1):
        data_means[reg - 1] = np.ma.mean(scorr[labels_corr == reg])
        ref_means[reg - 1] = np.ma.mean(sref[labels_corr == reg])

    def cost_function(x):
        return _cost_function(
            x,
            data_means,
            ref_means,
            nyquist_interval,
            nfeatures_corr,
        )

    def gradient(x):
        return _gradient(
            x,
            data_means,
            ref_means,
            nyquist_interval,
            nfeatures_corr,
        )

    nyq_adjustments = fmin_l_bfgs_b(
        cost_function,
        gfold * np.ones(nfeatures_corr),
        disp=False,
        fprime=gradient,
        bounds=bounds_list,
        maxiter=200,
        pgtol=nyquist_interval,
    )

    # 与 Py-ART 相同：循环到 nfeatures_corr-1，跳过最后一个区域。
    i = 0
    for reg in range(1, nfeatures_corr):
        data[labels == reg] += nyquist_interval * np.round(
            nyq_adjustments[0][i]
        )
        i += 1
    return data


def _find_sweep_interval_splits(nyquist, interval_splits, velocities, nsweep):
    """根据当前 sweep 的速度范围，决定是否需要扩展 Nyquist 分段。"""
    add_start = add_end = 0
    interval = (2.0 * nyquist) / interval_splits
    if len(velocities) != 0:
        max_vel = velocities.max()
        min_vel = velocities.min()
        if max_vel > nyquist or min_vel < -nyquist:
            msg = (
                f"Velocities outside of the Nyquist interval found in "
                f"sweep {nsweep}."
            )
            warnings.warn(msg, UserWarning)

            add_start = int(np.ceil((max_vel - nyquist) / interval))
            add_end = int(np.ceil(-(min_vel + nyquist) / interval))

    start = -nyquist - add_start * interval
    end = nyquist + add_end * interval
    num = interval_splits + 1 + add_start + add_end
    return np.linspace(start, end, num, endpoint=True)


def _find_regions(vel, gfilter, limits):
    """根据速度分段和门限掩码提取 2D 连通区域。"""
    mask = ~gfilter
    label = np.zeros(vel.shape, dtype=np.int32)
    nfeatures = 0
    for lmin, lmax in zip(limits[:-1], limits[1:]):
        inp = (lmin <= vel) & (vel < lmax) & mask
        limit_label, limit_nfeatures = ndimage.label(inp)
        limit_label[np.nonzero(limit_label)] += nfeatures
        label += limit_label
        nfeatures += limit_nfeatures

    return label, nfeatures


def _edge_sum_and_count(
    labels,
    num_masked_gates,
    data,
    rays_wrap_around,
    max_gap_x,
    max_gap_y,
):
    """统计候选边的数量和对应速度和。"""
    total_nodes = labels.shape[0] * labels.shape[1] - num_masked_gates
    if rays_wrap_around:
        total_nodes += labels.shape[0] * 2

    indices, velocities = _fast_edge_finder(
        labels.astype("int32"),
        data.astype("float32"),
        rays_wrap_around,
        max_gap_x,
        max_gap_y,
        total_nodes,
    )
    index1, index2 = indices
    vel1, vel2 = velocities
    count = np.ones_like(vel1, dtype=np.int32)

    if len(vel1) == 0:
        return ([], []), [], ([], [])

    order = np.lexsort((index1, index2))
    index1 = index1[order]
    index2 = index2[order]
    vel1 = vel1[order]
    vel2 = vel2[order]
    count = count[order]

    unique_mask = (index1[1:] != index1[:-1]) | (
        index2[1:] != index2[:-1]
    )
    unique_mask = np.append(True, unique_mask)
    index1 = index1[unique_mask]
    index2 = index2[unique_mask]

    (unique_inds,) = np.nonzero(unique_mask)
    vel1 = np.add.reduceat(vel1, unique_inds, dtype=vel1.dtype)
    vel2 = np.add.reduceat(vel2, unique_inds, dtype=vel2.dtype)
    count = np.add.reduceat(count, unique_inds, dtype=count.dtype)

    return (index1, index2), count, (vel1, vel2)


def _combine_regions(region_tracker, edge_tracker):
    """尝试根据当前最优边继续合并区域。"""
    status, extra = edge_tracker.pop_edge()
    if status:
        return True
    node1, node2, weight, diff, edge_number = extra
    del weight
    rdiff = int(np.round(diff))

    node1_size = region_tracker.get_node_size(node1)
    node2_size = region_tracker.get_node_size(node2)

    if node1_size > node2_size:
        base_node, merge_node = node1, node2
    else:
        base_node, merge_node = node2, node1
        rdiff = -rdiff

    if rdiff != 0:
        region_tracker.unwrap_node(merge_node, rdiff)
        edge_tracker.unwrap_node(merge_node, rdiff)

    region_tracker.merge_nodes(base_node, merge_node)
    edge_tracker.merge_nodes(base_node, merge_node, edge_number)

    return False


def _cost_function(
    nyq_vector,
    vels_slice_means,
    svels_slice_means,
    v_nyq_vel,
    nfeatures,
):
    """计算目标函数值。"""
    cost = 0
    i = 0

    for reg in range(nfeatures):
        add_value = (
            vels_slice_means[reg]
            + np.round(nyq_vector[i]) * v_nyq_vel
            - svels_slice_means[reg]
        ) ** 2

        if np.isfinite(add_value):
            cost += add_value
        i += 1

    return cost


def _gradient(
    nyq_vector,
    vels_slice_means,
    svels_slice_means,
    v_nyq_vel,
    nfeatures,
):
    """计算优化目标的梯度。"""
    gradient_vector = np.zeros(len(nyq_vector))
    i = 0
    for reg in range(nfeatures):
        add_value = (
            vels_slice_means[reg]
            + np.round(nyq_vector[i]) * v_nyq_vel
            - svels_slice_means[reg]
        )
        if np.isfinite(add_value):
            gradient_vector[i] = 2 * add_value * v_nyq_vel

        vels_without_cur = np.delete(vels_slice_means, reg)
        diffs = np.square(vels_slice_means[reg] - vels_without_cur)
        if len(diffs) > 0:
            the_min = np.argmin(diffs)
        else:
            the_min = 0

        if the_min < v_nyq_vel:
            gradient_vector[i] = 0

        i += 1

    return gradient_vector
