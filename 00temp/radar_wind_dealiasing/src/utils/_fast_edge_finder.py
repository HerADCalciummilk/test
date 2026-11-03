#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""查找连通区域边缘的轻量实现。"""

from __future__ import annotations

import numpy as np


def _fast_edge_finder(
    labels: np.ndarray,
    data: np.ndarray,
    rays_wrap_around: bool,
    max_gap_x: int,
    max_gap_y: int,
    total_nodes: int,
):
    """返回所有区域边缘的索引与速度值。"""
    collector = _EdgeCollector(total_nodes)
    right = labels.shape[0] - 1
    bottom = labels.shape[1] - 1

    for x_index in range(labels.shape[0]):
        for y_index in range(labels.shape[1]):
            label = labels[x_index, y_index]
            if label == 0:
                continue

            vel = data[x_index, y_index]

            # 依次检查左右和上下方向，收集不同区域之间的边缘关系。
            x_check = x_index - 1
            if x_check == -1 and rays_wrap_around:
                x_check = right
            if x_check != -1:
                neighbor, nvel = _find_neighbor_x(
                    labels,
                    data,
                    x_check,
                    y_index,
                    right,
                    max_gap_x,
                    rays_wrap_around,
                    direction=-1,
                )
                collector.add_edge(label, neighbor, vel, nvel)

            x_check = x_index + 1
            if x_check == right + 1 and rays_wrap_around:
                x_check = 0
            if x_check != right + 1:
                neighbor, nvel = _find_neighbor_x(
                    labels,
                    data,
                    x_check,
                    y_index,
                    right,
                    max_gap_x,
                    rays_wrap_around,
                    direction=1,
                )
                collector.add_edge(label, neighbor, vel, nvel)

            y_check = y_index - 1
            if y_check != -1:
                neighbor, nvel = _find_neighbor_y(
                    labels,
                    data,
                    x_index,
                    y_check,
                    bottom,
                    max_gap_y,
                    direction=-1,
                )
                collector.add_edge(label, neighbor, vel, nvel)

            y_check = y_index + 1
            if y_check != bottom + 1:
                neighbor, nvel = _find_neighbor_y(
                    labels,
                    data,
                    x_index,
                    y_check,
                    bottom,
                    max_gap_y,
                    direction=1,
                )
                collector.add_edge(label, neighbor, vel, nvel)

    return collector.get_indices_and_velocities()


def _find_neighbor_x(
    labels: np.ndarray,
    data: np.ndarray,
    x_check: int,
    y_index: int,
    right: int,
    max_gap_x: int,
    rays_wrap_around: bool,
    direction: int,
):
    """沿 x 方向寻找邻接有效格点。"""
    neighbor = labels[x_check, y_index]
    nvel = data[x_check, y_index]

    if neighbor != 0:
        return neighbor, nvel

    for _ in range(max_gap_x):
        x_check += direction
        if x_check == -1:
            if rays_wrap_around:
                x_check = right
            else:
                break
        if x_check == right + 1:
            if rays_wrap_around:
                x_check = 0
            else:
                break

        neighbor = labels[x_check, y_index]
        nvel = data[x_check, y_index]
        if neighbor != 0:
            break

    return neighbor, nvel


def _find_neighbor_y(
    labels: np.ndarray,
    data: np.ndarray,
    x_index: int,
    y_check: int,
    bottom: int,
    max_gap_y: int,
    direction: int,
):
    """沿 y 方向寻找邻接有效格点。"""
    neighbor = labels[x_index, y_check]
    nvel = data[x_index, y_check]

    if neighbor != 0:
        return neighbor, nvel

    for _ in range(max_gap_y):
        y_check += direction
        if y_check == -1 or y_check == bottom + 1:
            break

        neighbor = labels[x_index, y_check]
        nvel = data[x_index, y_check]
        if neighbor != 0:
            break

    return neighbor, nvel


class _EdgeCollector:
    """收集边缘信息。"""

    def __init__(self, total_nodes: int):
        self.l_index = np.zeros(total_nodes * 4, dtype=np.int32)
        self.n_index = np.zeros(total_nodes * 4, dtype=np.int32)
        self.l_velo = np.zeros(total_nodes * 4, dtype=np.float64)
        self.n_velo = np.zeros(total_nodes * 4, dtype=np.float64)
        self.idx = 0

    def add_edge(self, label: int, neighbor: int, vel: float, nvel: float):
        """记录一条有效边。"""
        if neighbor == label or neighbor == 0:
            return

        self.l_index[self.idx] = label
        self.n_index[self.idx] = neighbor
        self.l_velo[self.idx] = vel
        self.n_velo[self.idx] = nvel
        self.idx += 1

    def get_indices_and_velocities(self):
        """返回已收集的边缘索引和速度。"""
        indices = (self.l_index[: self.idx], self.n_index[: self.idx])
        velocities = (self.l_velo[: self.idx], self.n_velo[: self.idx])
        return indices, velocities
