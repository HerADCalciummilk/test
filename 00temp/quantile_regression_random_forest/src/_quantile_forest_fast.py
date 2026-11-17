"""quantile-forest ``_quantile_forest_fast.pyx`` 里预测所用部分的纯 Python 版本。"""

from __future__ import annotations

import numpy as np


class QuantileForest:
    """保存排序后的训练目标和各叶节点样本下标，并据此计算分位数。"""

    def __init__(self, y_train, y_train_leaves, y_bound_leaves=None, sparse_pickle=False):
        self.y_train = np.asarray(y_train, dtype=np.float64)
        self.y_train_leaves = np.asarray(y_train_leaves)
        self.sparse_pickle = bool(sparse_pickle)
        if y_bound_leaves is None:
            self.y_bound_leaves = np.empty((0, 0, 0), dtype=np.float64)
        else:
            self.y_bound_leaves = np.asarray(y_bound_leaves, dtype=np.float64)

    def predict(
        self,
        quantiles,
        X_leaves,
        X_indices=None,
        interpolation=b"linear",
        weighted_quantile=True,
        weighted_leaves=False,
        aggregate_leaves_first=True,
    ):
        if isinstance(interpolation, (bytes, bytearray)):
            interpolation = interpolation.decode()
        quantiles = np.asarray(list(quantiles), dtype=np.float64)
        X_leaves = np.asarray(X_leaves)
        n_samples, n_trees = X_leaves.shape
        n_outputs, n_train = self.y_train.shape
        max_index = self.y_train_leaves.shape[3]
        use_mean = quantiles.size == 1 and quantiles[0] == -1
        if not use_mean and np.any((quantiles < 0) | (quantiles > 1)):
            raise ValueError(f"分位数必须落在 0 到 1，当前为 {quantiles.tolist()}")
        if interpolation not in {"linear", "lower", "higher", "midpoint", "nearest"}:
            raise ValueError(f"不支持的插值方法 {interpolation}")
        if X_indices is not None and np.asarray(X_indices).shape[1] != n_trees:
            raise ValueError("X_indices 的树数量需要和 X_leaves 一致")

        n_quantiles = 1 if use_mean else quantiles.size
        predictions = np.full((n_samples, n_outputs, n_quantiles), np.nan, dtype=np.float64)
        for sample_index in range(n_samples):
            active = (
                np.ones(n_trees, dtype=bool)
                if X_indices is None
                else np.asarray(X_indices[sample_index]).astype(bool)
            )
            leaf_counts = np.zeros(n_trees, dtype=np.int64)
            if weighted_leaves:
                for tree_index in range(n_trees):
                    if active[tree_index]:
                        node = X_leaves[sample_index, tree_index]
                        leaf_counts[tree_index] = np.count_nonzero(
                            self.y_train_leaves[tree_index, node, 0] != 0
                        )
            total_samples = int(leaf_counts.sum())
            total_trees = int(active.sum())
            for output_index in range(n_outputs):
                tree_predictions = []
                grouped_indices = []
                grouped_weights = []
                for tree_index in range(n_trees):
                    if not active[tree_index]:
                        continue
                    node = X_leaves[sample_index, tree_index]
                    indices = self.y_train_leaves[tree_index, node, output_index]
                    weight = 1.0
                    if weighted_leaves:
                        weight = 0.0
                        if leaf_counts[tree_index] > 0:
                            weight = total_samples / (leaf_counts[tree_index] * total_trees)
                    if aggregate_leaves_first:
                        grouped_indices.append(indices)
                        grouped_weights.append(np.full(max_index, weight))
                    else:
                        tree_predictions.append(
                            _leaf_prediction(
                                self.y_train[output_index],
                                indices,
                                np.full(max_index, weight),
                                quantiles,
                                interpolation,
                                weighted_quantile,
                                use_mean,
                            )
                        )
                if aggregate_leaves_first:
                    if not grouped_indices:
                        continue
                    value = _leaf_prediction(
                        self.y_train[output_index],
                        np.concatenate(grouped_indices),
                        np.concatenate(grouped_weights),
                        quantiles,
                        interpolation,
                        weighted_quantile,
                        use_mean,
                    )
                    if value is not None:
                        predictions[sample_index, output_index] = value
                elif tree_predictions:
                    stacked = [item for item in tree_predictions if item is not None]
                    if stacked:
                        predictions[sample_index, output_index] = np.mean(stacked, axis=0)
        return predictions


def _leaf_prediction(targets, indices, slot_weights, quantiles, interpolation, weighted, use_mean):
    indices = np.asarray(indices, dtype=np.int64).reshape(-1)
    slot_weights = np.asarray(slot_weights, dtype=np.float64).reshape(-1)
    selected = indices != 0
    if not np.any(selected):
        return None
    if weighted:
        weights = np.zeros(targets.shape[0], dtype=np.float64)
        np.add.at(weights, indices[selected] - 1, slot_weights[selected])
        if use_mean:
            total = weights.sum()
            if total <= 0:
                return None
            return np.array([(targets * weights).sum() / total])
        values = _weighted_quantile(targets, weights, quantiles, interpolation, issorted=True)
        return None if values.size == 0 else values
    samples = targets[indices[selected] - 1]
    if use_mean:
        return np.array([samples.mean()]) if samples.size else None
    return _quantile(samples, quantiles, interpolation, issorted=False)


def _interpolate(lower, upper, fraction, method):
    if method == "lower" or fraction <= 0:
        return lower
    if method == "higher" or fraction >= 1:
        return upper
    if method == "midpoint":
        return 0.5 * (lower + upper)
    if method == "nearest":
        return lower if fraction < 0.5 else upper
    return lower + fraction * (upper - lower)


def _quantile(values, quantiles, interpolation="linear", issorted=False):
    values = np.asarray(values, dtype=np.float64)
    quantiles = np.asarray(quantiles, dtype=np.float64)
    count = values.size
    if count < 1:
        return np.array([])
    if count == 1:
        return np.full(quantiles.shape, values[0])
    ordered = values if issorted else np.sort(values)
    scale = count + 1 - 2
    result = np.empty(quantiles.shape, dtype=np.float64)
    for index, quantile in enumerate(quantiles):
        position = quantile * scale
        if position >= count - 1:
            result[index] = ordered[-1]
            continue
        if position <= 0:
            result[index] = ordered[0]
            continue
        lower_index = int(np.floor(position))
        upper_index = int(np.ceil(position))
        lower = ordered[lower_index]
        upper = ordered[upper_index]
        if lower == upper:
            result[index] = lower
            continue
        fraction = position - lower_index
        result[index] = _interpolate(lower, upper, fraction, interpolation)
    return result


def _weighted_quantile(values, weights, quantiles, interpolation="linear", issorted=True):
    values = np.asarray(values, dtype=np.float64).copy()
    weights = np.asarray(weights, dtype=np.float64).copy()
    quantiles = np.asarray(quantiles, dtype=np.float64).copy()
    count = values.size
    if count < 1:
        return np.array([])
    if not issorted:
        order = np.argsort(values, kind="mergesort")
        values = values[order]
        weights = weights[order]
    cumulative = np.cumsum(weights)
    if cumulative[-1] <= 0:
        return np.array([])
    correction = 1.0
    scale = cumulative[-1] + 1 - 2 * correction
    result = np.empty(quantiles.shape, dtype=np.float64)
    floor_index = 0
    ceil_index = 1
    for position in np.argsort(quantiles, kind="mergesort"):
        quantile = float(quantiles[position])
        proportion = quantile * scale + correction
        for cursor in range(floor_index, count):
            if proportion >= cumulative[cursor]:
                if weights[cursor] > 0:
                    floor_index = cursor
                    ceil_index = cursor + 1
            else:
                break
        if ceil_index > count - 1:
            ceil_index = count - 1
        while weights[ceil_index] == 0:
            ceil_index += 1
            if ceil_index > count - 1:
                ceil_index = floor_index
                break
        if floor_index >= count - 1:
            result[position] = values[-1]
            continue
        if ceil_index <= 0:
            result[position] = values[0]
            continue
        if floor_index == ceil_index:
            result[position] = values[floor_index]
            continue
        lower = values[floor_index]
        upper = values[ceil_index]
        if lower == upper:
            result[position] = lower
            continue
        lower_proportion = min(quantile, (cumulative[floor_index] - correction) / scale)
        upper_proportion = max(quantile, (cumulative[ceil_index] - correction) / scale)
        if weights[ceil_index] != 0:
            upper_proportion = lower_proportion + (
                (upper_proportion - lower_proportion) / weights[ceil_index]
            )
        if quantile >= upper_proportion:
            result[position] = upper
            continue
        width = upper_proportion - lower_proportion
        fraction = 0.0 if width == 0 else (quantile - lower_proportion) / width
        result[position] = _interpolate(lower, upper, fraction, interpolation)
    return result
