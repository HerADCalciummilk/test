"""Generalized Additive Model fitting and prediction (pyGAM wrapper)."""

from __future__ import annotations

import warnings
from copy import deepcopy
from typing import List

import numpy as np


class GAMFit:
    """Fit pyGAM models for SAMOS climatological mean / standard deviation."""

    def __init__(
        self,
        model_specification: List,
        max_iter: int = 100,
        tol: float = 0.0001,
        distribution: str = "normal",
        link: str = "identity",
        fit_intercept: bool = True,
    ):
        self.model_specification = model_specification
        self.max_iter = max_iter
        self.tol = tol
        self.distribution = distribution
        self.link = link
        self.fit_intercept = fit_intercept

    def create_pygam_model(self):
        from pygam import f, l, s, te

        term = {"factor": f, "linear": l, "spline": s, "tensor": te}
        eqn = None
        for index, config in enumerate(self.model_specification):
            if config[0] not in term:
                raise ValueError(
                    f"Unrecognised GAM term {config[0]!r}; "
                    "expected linear, spline, tensor, or factor."
                )
            new_term = term[config[0]](*config[1], **config[2])
            eqn = deepcopy(new_term) if index == 0 else eqn + new_term
        return eqn

    def process(self, predictors: np.ndarray, targets: np.ndarray):
        import scipy.sparse
        from pygam import GAM

        def to_array(self):
            return self.toarray()

        scipy.sparse.spmatrix.A = property(to_array)

        predictors = predictors[~np.isnan(targets)]
        targets = targets[~np.isnan(targets)]
        if len(predictors) == 0 or len(targets) == 0:
            warnings.warn(
                "No valid data remain after removing NaNs; GAM was not fitted.",
                stacklevel=2,
            )
            return None

        gam = GAM(
            self.create_pygam_model(),
            max_iter=self.max_iter,
            tol=self.tol,
            distribution=self.distribution,
            link=self.link,
            fit_intercept=self.fit_intercept,
        ).fit(predictors, targets)
        return gam


class GAMPredict:
    """Predict from a fitted pyGAM model."""

    def process(self, gam, predictors: np.ndarray) -> np.ndarray:
        return gam.predict(predictors)
