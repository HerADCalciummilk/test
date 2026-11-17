"""quantile-forest ``_utils.pyx`` 的纯 Python 版本。"""

from __future__ import annotations

import numpy as np


def generate_unsampled_indices(sample_indices, n_total_samples, duplicates):
    """返回没有进入自助样本的下标，并计入功能相同的重复下标。"""
    sampled = {int(index) for index in np.asarray(sample_indices).reshape(-1)}
    for group in duplicates or []:
        group = {int(index) for index in group}
        if sampled.intersection(group):
            sampled.update(group)
    return np.asarray(
        [index for index in range(int(n_total_samples)) if index not in sampled],
        dtype=np.int64,
    )


def group_indices_by_value(values):
    """按取值分组，返回排序后的唯一值和每组原始下标。"""
    values = np.asarray(values, dtype=np.int64)
    if values.size == 0:
        return np.empty(0, dtype=np.int64), []
    order = np.argsort(values, kind="mergesort")
    ordered = values[order]
    starts = np.r_[0, np.flatnonzero(np.diff(ordered)) + 1]
    ends = np.r_[starts[1:], values.size]
    unique = ordered[starts].astype(np.int64, copy=False)
    groups = [order[start:end] for start, end in zip(starts, ends)]
    return unique, groups


def map_indices_to_leaves(y_train_leaves_slice, bootstrap_indices, leaf_indices, leaf_values_list):
    """把训练样本下标填进对应叶节点。下标从 1 开始，0 表示空位。"""
    mapped = np.array(y_train_leaves_slice, copy=True)
    bootstrap_indices = np.asarray(bootstrap_indices)
    for leaf_index, leaf_values in zip(leaf_indices, leaf_values_list):
        for position, leaf_value in enumerate(np.asarray(leaf_values, dtype=np.int64).reshape(-1)):
            for output_index in range(bootstrap_indices.shape[1]):
                sample_index = bootstrap_indices[int(leaf_value), output_index]
                if sample_index > 0:
                    mapped[int(leaf_index), output_index, position] = sample_index
    return mapped
