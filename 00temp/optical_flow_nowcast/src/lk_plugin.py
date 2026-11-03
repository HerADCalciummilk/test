# -*- coding: utf-8 -*-
"""
Created on Tue Sep 26 15:44:26 2023

@author: cheny
"""

import scipy
from .base_plugin import PostProcessingPlugin
from typing import Optional, Tuple
from .utils import *
from scipy.interpolate import Rbf
from scipy.spatial import cKDTree
from scipy.spatial.distance import cdist


import datetime
import sys
from pathlib import Path

import pandas as pd
import xarray as xr
import meteva_base as meb

_TEMP_ROOT = Path(__file__).resolve().parents[2]
if str(_TEMP_ROOT) not in sys.path:
    sys.path.insert(0, str(_TEMP_ROOT))
from db_trans.src import dB_trans

def forecast(
        input_images,
        lk_kwargs: dict = None,
        fd_method: str = "shitomasi",
        fd_kwargs: dict = None,
        interp_method: str = "idwinterp2d",
        interp_kwargs: dict = None,
        dense: bool = True,
        nr_std_outlier: int = 3,
        k_outlier: int = 30,
        size_opening: int = 3,
        decl_scale: int = 20,
        verbose: bool = False):

    input_images = input_images.copy()
    if verbose:
        print("Computing the motion field with the Lucas-Kanade method.")
        t0 = time.time()

    nr_fields = input_images.shape[0]
    domain_size = (input_images.shape[1], input_images.shape[2])

    feature_detection_method = _detection
    interpolation_method = _idwinterp2d

    if fd_kwargs is None:
        fd_kwargs = dict()
    if fd_method == "tstorm":
        fd_kwargs.update({"output_feat": True})

    if lk_kwargs is None:
        lk_kwargs = dict()

    if interp_kwargs is None:
        interp_kwargs = dict()

    xy = np.empty(shape=(0, 2))
    uv = np.empty(shape=(0, 2))
    for n in range(nr_fields - 1):

        # extract consecutive images
        prvs_img = input_images[n, :, :].copy()
        next_img = input_images[n + 1, :, :].copy()

        # Check if a MaskedArray is used. If not, mask the ndarray
        if not isinstance(prvs_img, MaskedArray):
            prvs_img = np.ma.masked_invalid(prvs_img)
        np.ma.set_fill_value(prvs_img, prvs_img.min())

        if not isinstance(next_img, MaskedArray):
            next_img = np.ma.masked_invalid(next_img)
        np.ma.set_fill_value(next_img, next_img.min())

        # remove small noise with a morphological operator (opening)
        if size_opening > 0:
            prvs_img = _morph_opening(prvs_img, prvs_img.min(), size_opening)
            next_img = _morph_opening(next_img, next_img.min(), size_opening)

        # features detection
        points = feature_detection_method(prvs_img, **fd_kwargs).astype(np.float32)

        # skip loop if no features to track
        if points.shape[0] == 0:
            continue

        # get sparse u, v vectors with Lucas-Kanade tracking
        xy_, uv_ = _track_features(prvs_img, next_img, points, **lk_kwargs)

        # skip loop if no vectors
        if xy_.shape[0] == 0:
            continue

        # stack vectors
        xy = np.append(xy, xy_, axis=0)
        uv = np.append(uv, uv_, axis=0)

    # return zero motion field is no sparse vectors are found
    if xy.shape[0] == 0:
        if dense:
            return np.zeros((2, domain_size[0], domain_size[1]))
        else:
            return xy, uv

    # detect and remove outliers
    outliers = _detect_outliers(uv, nr_std_outlier, xy, k_outlier, verbose)
    xy = xy[~outliers, :]
    uv = uv[~outliers, :]

    if verbose:
        print("--- LK found %i sparse vectors ---" % xy.shape[0])

    # return sparse vectors if required
    if not dense:
        return xy, uv

    # decluster sparse motion vectors
    if decl_scale > 1:
        xy, uv = _decluster(xy, uv, decl_scale, 1, verbose)

    # return zero motion field if no sparse vectors are left for interpolation
    if xy.shape[0] == 0:
        return np.zeros((2, domain_size[0], domain_size[1]))

    xgrid = np.arange(domain_size[1])
    ygrid = np.arange(domain_size[0])
    uvgrid = interpolation_method(xy, uv, xgrid, ygrid, **interp_kwargs)

    if verbose:
        print("--- total time: %.2f seconds ---" % (time.time() - t0))

    return uvgrid


def _detection(

    input_image,
    max_corners=1000,
    max_num_features=None,
    quality_level=0.01,
    min_distance=10,
    block_size=5,
    buffer_mask=5,
    use_harris=False,
    k=0.04,
    verbose=False,
    **kwargs,
):
    if not CV2_IMPORTED:
        raise MissingOptionalDependency(
            "opencv package is required for the goodFeaturesToTrack() "
            "routine but it is not installed"
        )

    input_image = input_image.copy()

    if input_image.ndim != 2:
        raise ValueError("input_image must be a two-dimensional array")

    # Check if a MaskedArray is used. If not, mask the ndarray
    if not isinstance(input_image, MaskedArray):
        input_image = np.ma.masked_invalid(input_image)

    np.ma.set_fill_value(input_image, input_image.min())

    # buffer the quality mask to ensure that no vectors are computed nearby
    # the edges of the radar mask
    mask = np.ma.getmaskarray(input_image).astype("uint8")
    if buffer_mask > 0:
        mask = cv2.dilate(
            mask, np.ones((int(buffer_mask), int(buffer_mask)), np.uint8), 1
        )
        input_image[mask] = np.ma.masked

    # scale image between 0 and 255
    im_min = input_image.min()
    im_max = input_image.max()
    if im_max - im_min > 1e-8:
        input_image = (input_image.filled() - im_min) / (im_max - im_min) * 255
    else:
        input_image = input_image.filled() - im_min

    # convert to 8-bit
    input_image = np.ndarray.astype(input_image, "uint8")
    mask = (-1 * mask + 1).astype("uint8")

    params = dict(
        maxCorners=max_num_features if max_num_features is not None else max_corners,
        qualityLevel=quality_level,
        minDistance=min_distance,
        blockSize=block_size,
        useHarrisDetector=use_harris,
        k=k,
    )
    points = cv2.goodFeaturesToTrack(input_image, mask=mask, **params)
    if points is None:
        points = np.empty(shape=(0, 2))
    else:
        points = points[:, 0, :]

    if verbose:
        print(f"--- {points.shape[0]} good features to track detected ---")

    return points


def _idwinterp2d(
    xy_coord, values, xgrid, ygrid, power=0.5, k=20, dist_offset=0.5, **kwargs
):
    """
    Inverse distance weighting interpolation of a sparse (multivariate) array.

    .. _ndarray:\
    https://docs.scipy.org/doc/numpy/reference/generated/numpy.ndarray.html

    Parameters
    ----------
    xy_coord: ndarray_
        Array of shape (n, 2) containing the coordinates of the data points in
        a 2-dimensional space.
    values: ndarray_
        Array of shape (n) or (n, m) containing the values of the data points,
        where *n* is the number of data points and *m* the number of co-located
        variables. All elements in ``values`` are required to be finite.
    xgrid, ygrid: ndarray_
        1-D arrays representing the coordinates of the 2-D output grid.
    power: positive float, optional
        The power parameter used to compute the distance weights as
        ``weight = distance ** (-power)``.
    k: positive int or None, optional
        The number of nearest neighbours used for each target location.
        If set to None, it interpolates using all the data points at once.
    dist_offset: float, optional
        A small, positive constant that is added to distances to avoid zero
        values. It has units of pixels.

    Other Parameters
    ----------------
    {extra_kwargs_doc}

    Returns
    -------
    output_array: ndarray_
        The interpolated field(s) having shape (``ygrid.size``, ``xgrid.size``)
        or (*m*, ``ygrid.size``, ``xgrid.size``).
    """
    if values.ndim == 1:
        nvar = 1
        values = values[:, None]

    elif values.ndim == 2:
        nvar = values.shape[1]

    npoints = values.shape[0]

    # generate the target grid
    xgridv, ygridv = np.meshgrid(xgrid, ygrid)
    gridv = np.column_stack((xgridv.ravel(), ygridv.ravel()))

    if k is not None:
        k = int(np.min((k, npoints)))
        tree = _cKDTree_cached(xy_coord, hkey=kwargs.get("hkey", None))
        dist, inds = tree.query(gridv, k=k)
        if dist.ndim == 1:
            dist = dist[..., None]
            inds = inds[..., None]
    else:
        # use all points
        dist = cdist(xy_coord, gridv, "euclidean").transpose()
        inds = np.arange(npoints)[None, :] * np.ones((gridv.shape[0], npoints)).astype(
            int
        )

    # convert geographical distances to number of pixels
    x_res = np.gradient(xgrid)
    y_res = np.gradient(ygrid)
    mean_res = np.mean(np.abs([x_res.mean(), y_res.mean()]))
    dist /= mean_res

    # compute distance-based weights
    dist += dist_offset  # avoid zero distances
    weights = 1 / np.power(dist, power)
    weights = weights / np.sum(weights, axis=1, keepdims=True)

    # interpolate
    output_array = np.sum(
        values[inds, :] * weights[..., None],
        axis=1,
    )

    # reshape to final grid size
    output_array = output_array.reshape(ygrid.size, xgrid.size, nvar)

    return np.moveaxis(output_array, -1, 0).squeeze()


@memoize()
def _cKDTree_cached(*args, **kwargs):
    """Add LRU cache to cKDTree class."""
    return cKDTree(*args)


# from pysteps.tracking.lucaskanade import track_features

def _track_features(

    prvs_image,
    next_image,
    points,
    winsize=(50, 50),
    nr_levels=3,
    criteria=(3, 10, 0),
    flags=0,
    min_eig_thr=1e-4,
    verbose=False,
):
    """
    Interface to the OpenCV `Lucas-Kanade`_ feature tracking algorithm
    (cv.calcOpticalFlowPyrLK).

    .. _`Lucas-Kanade`:\
        https://docs.opencv.org/3.4/dc/d6b/group__video__track.html#ga473e4b886d0bcc6b65831eb88ed93323

    .. _calcOpticalFlowPyrLK:\
        https://docs.opencv.org/3.4/dc/d6b/group__video__track.html#ga473e4b886d0bcc6b65831eb88ed93323


    .. _MaskedArray:\
        https://docs.scipy.org/doc/numpy/reference/maskedarray.baseclass.html#numpy.ma.MaskedArray

    .. _ndarray:\
    https://docs.scipy.org/doc/numpy/reference/generated/numpy.ndarray.html

    Parameters
    ----------
    prvs_image: ndarray_ or MaskedArray_
        Array of shape (m, n) containing the first image.
        Invalid values (Nans or infs) are replaced with the min value.
    next_image: ndarray_ or MaskedArray_
        Array of shape (m, n) containing the successive image.
        Invalid values (Nans or infs) are replaced with the min value.
    points: array_like
        Array of shape (p, 2) indicating the pixel coordinates of the
        tracking points (corners).
    winsize: tuple of int, optional
        The **winSize** parameter in calcOpticalFlowPyrLK_.
        It represents the size of the search window that it is used at each
        pyramid level. The default is (50, 50).
    nr_levels: int, optional
        The **maxLevel** parameter in calcOpticalFlowPyrLK_.
        It represents the 0-based maximal pyramid level number.
        The default is 3.
    criteria: tuple of int, optional
        The **TermCriteria** parameter in calcOpticalFlowPyrLK_ ,
        which specifies the termination criteria of the iterative search
        algorithm. The default is (3, 10, 0).
    flags: int, optional
        Operation flags, see documentation calcOpticalFlowPyrLK_. The
        default is 0.
    min_eig_thr: float, optional
        The **minEigThreshold** parameter in calcOpticalFlowPyrLK_. The
        default is 1e-4.
    verbose: bool, optional
        Print the number of vectors that have been found. The default
        is False.

    Returns
    -------
    xy: ndarray_
        Array of shape (d, 2) with the x- and y-coordinates of *d* <= *p*
        detected sparse motion vectors.
    uv: ndarray_
        Array of shape (d, 2) with the u- and v-components of *d* <= *p*
        detected sparse motion vectors.

    Notes
    -----
    The tracking points can be obtained with the
    :py:func:`pysteps.utils.images.ShiTomasi_detection` routine.

    See also
    --------
    pysteps.motion.lucaskanade.dense_lucaskanade

    References
    ----------
    Bouguet,  J.-Y.:  Pyramidal  implementation  of  the  affine  Lucas Kanade
    feature tracker description of the algorithm, Intel Corp., 5, 4, 2001

    Lucas, B. D. and Kanade, T.: An iterative image registration technique with
    an application to stereo vision, in: Proceedings of the 1981 DARPA Imaging
    Understanding Workshop, pp. 121–130, 1981.
    """

    if not CV2_IMPORTED:
        raise MissingOptionalDependency(
            "opencv package is required for the calcOpticalFlowPyrLK() "
            "routine but it is not installed"
        )

    prvs_img = prvs_image.copy()
    next_img = next_image.copy()
    p0 = np.copy(points)

    # Check if a MaskedArray is used. If not, mask the ndarray
    if not isinstance(prvs_img, MaskedArray):
        prvs_img = np.ma.masked_invalid(prvs_img)
    np.ma.set_fill_value(prvs_img, prvs_img.min())

    if not isinstance(next_img, MaskedArray):
        next_img = np.ma.masked_invalid(next_img)
    np.ma.set_fill_value(next_img, next_img.min())

    # scale between 0 and 255
    im_min = prvs_img.min()
    im_max = prvs_img.max()
    if (im_max - im_min) > 1e-8:
        prvs_img = (prvs_img.filled() - im_min) / (im_max - im_min) * 255
    else:
        prvs_img = prvs_img.filled() - im_min

    im_min = next_img.min()
    im_max = next_img.max()
    if (im_max - im_min) > 1e-8:
        next_img = (next_img.filled() - im_min) / (im_max - im_min) * 255
    else:
        next_img = next_img.filled() - im_min

    # convert to 8-bit
    prvs_img = np.ndarray.astype(prvs_img, "uint8")
    next_img = np.ndarray.astype(next_img, "uint8")

    # Lucas-Kanade
    # TODO: use the error returned by the OpenCV routine
    params = dict(
        winSize=winsize,
        maxLevel=nr_levels,
        criteria=criteria,
        flags=flags,
        minEigThreshold=min_eig_thr,
    )
    p1, st, __ = cv2.calcOpticalFlowPyrLK(prvs_img, next_img, p0, None, **params)

    # keep only features that have been found
    st = np.atleast_1d(st.squeeze()) == 1
    if np.any(st):
        p1 = p1[st, :]
        p0 = p0[st, :]

        # extract vectors
        xy = p0
        uv = p1 - p0

    else:
        xy = uv = np.empty(shape=(0, 2))

    if verbose:
        print(f"--- {xy.shape[0]} sparse vectors found ---")

    return xy, uv


# from pysteps.utils.cleansing import decluster, detect_outliers


def _decluster(coord, input_array, scale, min_samples=1, verbose=False):
    """
    Decluster a set of sparse data points by aggregating, that is, taking
    the median value of all values lying within a certain distance (i.e., a
    cluster).

    Parameters
    ----------
    coord: array_like
        Array of shape (n, d) containing the coordinates of the input data into
        a space of *d* dimensions.
    input_array: array_like
        Array of shape (n) or (n, m), where *n* is the number of samples and
        *m* the number of variables.
        All values in ``input_array`` are required to have finite values.
    scale: float or array_like
        The ``scale`` parameter in the same units of ``coord``.
        It can be a scalar or an array_like of shape (d).
        Data points within the declustering ``scale`` are aggregated.
    min_samples: int, optional
        The minimum number of samples for computing the median within a given
        cluster.
    verbose: bool, optional
        Print out information.

    Returns
    -------
    out: tuple of ndarrays
        A two-element tuple (``out_coord``, ``output_array``) containing the
        declustered coordinates (l, d) and input array (l, m), where *l* is
        the new number of samples with *l* <= *n*.
    """

    coord = np.copy(coord)
    input_array = np.copy(input_array)

    # check inputs
    if np.any(~np.isfinite(input_array)):
        raise ValueError("input_array contains non-finite values")

    if input_array.ndim == 1:
        nvar = 1
        input_array = input_array[:, None]
    elif input_array.ndim == 2:
        nvar = input_array.shape[1]
    else:
        raise ValueError(
            "input_array must have 1 (n) or 2 dimensions (n, m), but it has %i"
            % input_array.ndim
        )

    if coord.ndim != 2:
        raise ValueError(
            "coord must have 2 dimensions (n, d), but it has %i" % coord.ndim
        )
    if coord.shape[0] != input_array.shape[0]:
        raise ValueError(
            "the number of samples in the input_array does not match the " +
            "number of coordinates %i!=%i" % (input_array.shape[0], coord.shape[0])
        )

    if np.isscalar(scale):
        scale = float(scale)
    else:
        scale = np.copy(scale)
        if scale.ndim != 1:
            raise ValueError(
                "scale must have 1 dimension (d), but it has %i" % scale.ndim
            )
        if scale.shape[0] != coord.shape[1]:
            raise ValueError(
                "scale must have %i elements, but it has %i"
                % (coord.shape[1], scale.shape[0])
            )
        scale = scale[None, :]

    # reduce original coordinates
    coord_ = np.floor(coord / scale)

    # keep only unique pairs of the reduced coordinates
    ucoord_ = np.unique(coord_, axis=0)

    # loop through these unique values and average data points which belong to
    # the same cluster
    dinput = np.empty(shape=(0, nvar))
    dcoord = np.empty(shape=(0, coord.shape[1]))
    for i in range(ucoord_.shape[0]):
        idx = np.all(coord_ == ucoord_[i, :], axis=1)
        npoints = np.sum(idx)
        if npoints >= min_samples:
            dinput = np.append(
                dinput, np.median(input_array[idx, :], axis=0)[None, :], axis=0
            )
            dcoord = np.append(
                dcoord, np.median(coord[idx, :], axis=0)[None, :], axis=0
            )

    if verbose:
        print("--- %i samples left after declustering ---" % dinput.shape[0])

    return dcoord, dinput


def _detect_outliers(input_array, thr, coord=None, k=None, verbose=False):
    """
    Detect outliers in a (multivariate and georeferenced) dataset.

    Assume a (multivariate) Gaussian distribution and detect outliers based on
    the number of standard deviations from the mean.

    If spatial information is provided through coordinates, the outlier
    detection can be localized by considering only the k-nearest neighbours
    when computing the local mean and standard deviation.

    Parameters
    ----------
    input_array: array_like
        Array of shape (n) or (n, m), where *n* is the number of samples and
        *m* the number of variables. If *m* > 1, the Mahalanobis distance
        is used.
        All values in ``input_array`` are required to have finite values.
    thr: float
        The number of standard deviations from the mean used to define an outlier.
    coord: array_like or None, optional
        Array of shape (n, d) containing the coordinates of the input data into
        a space of *d* dimensions.
        Passing ``coord`` requires that ``k`` is not None.
    k: int or None, optional
        The number of nearest neighbours used to localize the outlier
        detection. If set to None (the default), it employs all the data points (global
        detection). Setting ``k`` requires that ``coord`` is not None.
    verbose: bool, optional
        Print out information.

    Returns
    -------
    out: array_like
        A 1-D boolean array of shape (n) with True values indicating the outliers
        detected in ``input_array``.
    """

    input_array = np.copy(input_array)

    if np.any(~np.isfinite(input_array)):
        raise ValueError("input_array contains non-finite values")

    if input_array.ndim == 1:
        nsamples = input_array.size
        nvar = 1
    elif input_array.ndim == 2:
        nsamples = input_array.shape[0]
        nvar = input_array.shape[1]
    else:
        raise ValueError(
            f"input_array must have 1 (n) or 2 dimensions (n, m), "
            f"but it has {input_array.ndim}"
        )

    if nsamples < 2:
        return np.zeros(nsamples, dtype=bool)

    if coord is not None and k is not None:

        coord = np.copy(coord)
        if coord.ndim == 1:
            coord = coord[:, None]

        elif coord.ndim > 2:
            raise ValueError(
                "coord must have 2 dimensions (n, d)," f"but it has {coord.ndim}"
            )

        if coord.shape[0] != nsamples:
            raise ValueError(
                "the number of samples in input_array does not match the "
                f"number of coordinates {nsamples}!={coord.shape[0]}"
            )

        k = np.min((nsamples, k + 1))

    # global

    if k is None or coord is None:

        if nvar == 1:
            # univariate
            zdata = np.abs(input_array - np.mean(input_array)) / np.std(input_array)
            outliers = zdata > thr
        else:
            # multivariate (mahalanobis distance)
            zdata = input_array - np.mean(input_array, axis=0)
            V = np.cov(zdata.T)
            try:
                VI = np.linalg.inv(V)
                MD = np.sqrt(np.dot(np.dot(zdata, VI), zdata.T).diagonal())
            except np.linalg.LinAlgError as err:
                warnings.warn(f"{err} during outlier detection")
                MD = np.zeros(nsamples)
            outliers = MD > thr

    # local
    else:

        tree = scipy.spatial.cKDTree(coord)
        __, inds = tree.query(coord, k=k)
        outliers = np.empty(shape=0, dtype=bool)
        for i in range(inds.shape[0]):

            if nvar == 1:
                # univariate
                thisdata = input_array[i]
                neighbours = input_array[inds[i, 1:]]
                thiszdata = np.abs(thisdata - np.mean(neighbours)) / np.std(neighbours)
                outliers = np.append(outliers, thiszdata > thr)
            else:
                # multivariate (mahalanobis distance)
                thisdata = input_array[i, :]
                neighbours = input_array[inds[i, 1:], :].copy()
                thiszdata = thisdata - np.mean(neighbours, axis=0)
                neighbours = neighbours - np.mean(neighbours, axis=0)
                V = np.cov(neighbours.T)
                try:
                    VI = np.linalg.inv(V)
                    MD = np.sqrt(np.dot(np.dot(thiszdata, VI), thiszdata.T))
                except np.linalg.LinAlgError as err:
                    warnings.warn(f"{err} during outlier detection")
                    MD = 0
                outliers = np.append(outliers, MD > thr)

    if verbose:
        print(f"--- {np.sum(outliers)} outliers detected ---")

    return outliers

# from pysteps.utils.images import morph_opening


def _morph_opening(input_image, thr, n):
    """
    Filter out small scale noise on the image by applying a binary
    morphological opening, that is, erosion followed by dilation.

    .. _MaskedArray:\
        https://docs.scipy.org/doc/numpy/reference/maskedarray.baseclass.html#numpy.ma.MaskedArray

    .. _ndarray:\
    https://docs.scipy.org/doc/numpy/reference/generated/numpy.ndarray.html

    Parameters
    ----------
    input_image: ndarray_ or MaskedArray_
        Array of shape (m, n) containing the input image.
    thr: float
        The threshold used to convert the image into a binary image.
    n: int
        The structuring element size [pixels].

    Returns
    -------
    input_image: ndarray_ or MaskedArray_
        Array of shape (m,n) containing the filtered image.
    """
    if not CV2_IMPORTED:
        raise MissingOptionalDependency(
            "opencv package is required for the morphologyEx "
            "routine but it is not installed"
        )

    input_image = input_image.copy()

    # Check if a MaskedArray is used. If not, mask the ndarray
    to_ndarray = False
    if not isinstance(input_image, MaskedArray):
        to_ndarray = True
        input_image = np.ma.masked_invalid(input_image)

    np.ma.set_fill_value(input_image, input_image.min())

    # Convert to binary image
    field_bin = np.ndarray.astype(input_image.filled() > thr, "uint8")

    # Build a structuring element of size n
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (n, n))

    # Apply morphological opening (i.e. erosion then dilation)
    field_bin_out = cv2.morphologyEx(field_bin, cv2.MORPH_OPEN, kernel)

    # Build mask to be applied on the original image
    mask = (field_bin - field_bin_out) > 0

    # Filter out small isolated pixels based on mask
    input_image[mask] = np.nanmin(input_image)

    if to_ndarray:
        input_image = np.array(input_image)

    return input_image


class  LK(PostProcessingPlugin):

    def __init__(self, 
                transform_method:Optional[str]=None,
                transform_para:Optional[dict]=None,
                model_id_attr: Optional[str] = None,
                lk_kwargs: Optional[dict]=None,
                fd_method: Optional[str]="shitomasi",
                fd_kwargs: Optional[dict]=None,
                interp_method: Optional[str]="idwinterp2d",
                interp_kwargs: Optional[dict]=None,
                dense: Optional[bool]=True,
                nr_std_outlier: Optional[int]=3,
                k_outlier: Optional[int]=30,
                size_opening: Optional[int]=3,
                decl_scale: Optional[int]=20,
                verbose: Optional[bool]=False,
                ) -> None:
        """
        Initialise the class

        Args:
            model_id_attr:
                Name of the attribute used to identify the source model for
                blending.
            lk_kwargs: dict, optional
                Optional dictionary containing keyword arguments for the `Lucas-Kanade`_
                features tracking algorithm. See the documentation of
                :py:func:`pysteps.tracking.lucaskanade.track_features`.

            fd_method: {"shitomasi", "blob", "tstorm"}, optional
            Name of the feature detection routine. See feature detection methods in
            :py:mod:`pysteps.feature`.

            fd_kwargs: dict, optional
                Optional dictionary containing keyword arguments for the features
                detection algorithm.
                See the documentation of :py:mod:`pysteps.feature`.

            interp_method: {"idwinterp2d", "rbfinterp2d"}, optional
            Name of the interpolation method to use. See interpolation methods in
            :py:mod:`pysteps.utils.interpolate`.

            interp_kwargs: dict, optional
                Optional dictionary containing keyword arguments for the interpolation
                algorithm. See the documentation of :py:mod:`pysteps.utils.interpolate`.

            dense: bool, optional
                If True, return the three-dimensional array (2, m, n) containing
                the dense x- and y-components of the motion field.

                If False, return the sparse motion vectors as 2-D **xy** and **uv**
                arrays, where **xy** defines the vector positions, **uv** defines the
                x and y direction components of the vectors.

            nr_std_outlier: int, optional
                Maximum acceptable deviation from the mean in terms of number of
                standard deviations. Any sparse vector with a deviation larger than
                this threshold is flagged as outlier and excluded from the
                interpolation.
                See the documentation of
                :py:func:`pysteps.utils.cleansing.detect_outliers`.

            k_outlier: int or None, optional
                The number of nearest neighbors used to localize the outlier detection.
                If set to None, it employs all the data points (global detection).
                See the documentation of
                :py:func:`pysteps.utils.cleansing.detect_outliers`.

            size_opening: int, optional
                The size of the structuring element kernel in pixels. This is used to
                perform a binary morphological opening on the input fields in order to
                filter isolated echoes due to clutter. If set to zero, the filtering
                is not performed.
                See the documentation of
                :py:func:`pysteps.utils.images.morph_opening`.

            decl_scale: int, optional
                The scale declustering parameter in pixels used to reduce the number of
                redundant sparse vectors before the interpolation.
                Sparse vectors within this declustering scale are averaged together.
                If set to less than 2 pixels, the declustering is not performed.
                See the documentation of
                :py:func:`pysteps.utils.cleansing.decluster`.

            verbose: bool, optional
                If set to True, print some information about the program.

                    
        """
        self.model_id_attr=model_id_attr
        self.lk_kwargs=lk_kwargs
        self.fd_method=fd_method
        self.fd_kwargs=fd_kwargs
        self.interp_method=interp_method
        self.interp_kwargs=interp_kwargs
        self.dense=dense
        self.nr_std_outlier=nr_std_outlier
        self.k_outlier=k_outlier
        self.size_opening=size_opening
        self.decl_scale=decl_scale
        self.verbose=verbose
        self.transform_method=transform_method
        self.transform_para=transform_para

 
    def process(
        self,
        meb_griddata_list)->Tuple[xr.DataArray, datetime.timedelta]:
        """
        LK插件计算平流
        Args:
            meb_griddata_list: meb网格数据的列表，从前到后为之前到最近的实况场
        Returns:
            uv： 平流速度场
            delta： 外推间隔时间
        """

        #时间排序
        meb_griddata_list=sort_meb_griddata_list_along_time(meb_griddata_list)

        # 数据维度一致性检查
        for griddata in meb_griddata_list:
            if griddata.values.squeeze().ndim!=2:
                raise ValueError("uncorrect dimension, expect 2 dimensions data like [m,n]")
            else:
                continue

        # 时间间隔一致性检查
        if check_meb_griddata_time_interval(meb_griddata_list):
            pass
        else:
            raise ValueError('unequal time intervals in meb_griddata_list detected!')

        ## 数据提取
        np_array=[]
        for griddata in meb_griddata_list:
            np_array.append(griddata.values.squeeze())
        
        #构建三维输入

        np_array=np.array(np_array)
        

        #transform
        transform_mapping={'db':'dB_transform',
                           'box':'boxcox_transform',
                           'NQ':'NQ_transform',
                           'sqrt':'sqrt_transform'
                           }
        

        if self.transform_method is None:
            transform=None
        else:
            method=transform_mapping[self.transform_method]
            
            transform=getattr(dB_trans,method)

            np_array, metadata = transform(np_array,**self.transform_para)

            

        ## 维度提取
        grid_info=meb.get_grid_of_data(griddata)
        glon=[grid_info.slon,grid_info.elon,grid_info.dlon]
        glat=[grid_info.slat,grid_info.elat,grid_info.dlat]
        gtime=grid_info.gtime
        delta_t=pd.to_datetime(meb_griddata_list[-1].time).to_pydatetime()-pd.to_datetime(meb_griddata_list[-2].time).to_pydatetime()
        delta_t=delta_t[0]

        grid=meb.grid(glon,glat,gtime)
        grid.members=['u','v']

        result_np=forecast(np_array,
                            lk_kwargs=self.lk_kwargs,
                            fd_method=self.fd_method,
                            fd_kwargs=self.fd_kwargs,
                            interp_method=self.interp_method,
                            interp_kwargs=self.interp_kwargs,
                            dense=self.dense,
                            nr_std_outlier=self.nr_std_outlier,
                            k_outlier=self.k_outlier,
                            size_opening=self.size_opening,
                            decl_scale=self.decl_scale,
                            verbose=self.verbose)
        
        #重构meb.griddata
        nlat=result_np.shape[1]
        nlon=result_np.shape[2]
        result_np=result_np.reshape(2,1,1,1,nlat,nlon)
        result_griddata=meb.grid_data(grid,result_np)

        return result_griddata, delta_t
