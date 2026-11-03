import json
import os
import struct

import numpy as np
import geopandas as gpd
import meteva_base as meb
from shapely.geometry import Point, shape
from shapely.ops import unary_union



def get_area_pre_max(arr, lats, lons):

    max_coords = []
    max_val = arr.max()
    all_max_coords = np.argwhere(arr == max_val)

    for coord in all_max_coords:
        max_coords.append((lats[coord[0]], lons[coord[1]]))

    print("所有最大值坐标: ", max_val, max_coords)

    return max_val, max_coords


def get_county(lonP, latP):

    # 空间查询
    def locate_city(point, gdf):
        # 检查哪个多边形包含该点
        mask = gdf.contains(point)
        if mask.any():
            city_info = gdf[mask].iloc[0]
            # print(city_info)
            return city_info["city"], city_info["province"], city_info["county"]
        return None

    # 加载GeoJSON数据
    gdf = gpd.read_file("nx_county.json")

    # 定义目标坐标（注意顺序：经度, 纬度）
    target_point = Point(lonP, latP)  # 北京坐标

    # 执行查询
    result = locate_city(target_point, gdf)
    print(result)
    return result


def load_geojson_union(path):
    """读取 GeoJSON 并合并几何，不依赖 Fiona（避免 geopandas/fiona 版本冲突）。"""
    with open(path, encoding="utf-8") as f:
        gj = json.load(f)
    typ = gj.get("type")
    geoms = []
    if typ == "FeatureCollection":
        for feat in gj.get("features", []):
            geom = feat.get("geometry")
            if geom is None:
                continue
            geoms.append(shape(geom))
    elif typ == "Feature":
        geom = gj.get("geometry")
        if geom is not None:
            geoms.append(shape(geom))
    else:
        geoms.append(shape(gj))
    if not geoms:
        raise ValueError(f"GeoJSON 中无有效几何: {path}")
    return unary_union(geoms)


def write_mask_dat(dat_path, mask_north_up, lon_array, lat_array):
    """
    写入与 util_new.read_float_val_from_bin / read_grid_mask 一致的 float32 栅格二进制。
    mask_north_up: (nlat, nlon)，行 0 为北侧（与 get_mask 里 flipud 后的 mask 一致）。
    """
    lon_arr = np.asarray(lon_array, dtype=np.float64)
    lat_arr = np.asarray(lat_array, dtype=np.float64)
    dlon = float(lon_arr[1] - lon_arr[0])
    dlat = float(lat_arr[1] - lat_arr[0])
    lon_start, lon_end = float(lon_arr[0]), float(lon_arr[-1])
    lat_start, lat_end = float(lat_arr[0]), float(lat_arr[-1])
    xn = int(round((lon_end + 0.00001 - lon_start) / dlon)) + 1
    yn = int(round((lat_end + 0.00001 - lat_start) / dlat)) + 1
    if mask_north_up.shape != (yn, xn):
        raise ValueError(f"mask shape {mask_north_up.shape} != ({yn}, {xn}) from lon/lat")

    val = np.ascontiguousarray(mask_north_up[::-1, :].T, dtype=np.float32)
    dat_dir = os.path.dirname(os.path.abspath(dat_path))
    if dat_dir:
        os.makedirs(dat_dir, exist_ok=True)
    with open(dat_path, "wb") as f:
        for j in range(yn):
            for i in range(xn):
                f.write(struct.pack("f", float(val[i, j])))


def write_mask_png(png_path, mask_north_up):
    """简单预览：区内浅红，区外黑色。"""
    from PIL import Image

    h, w = mask_north_up.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    inside = mask_north_up > 0
    rgb[inside] = [255, 90, 90]
    png_dir = os.path.dirname(os.path.abspath(png_path))
    if png_dir:
        os.makedirs(png_dir, exist_ok=True)
    Image.fromarray(rgb, "RGB").save(png_path)


def get_mask(pro_name, lon_array, lat_array, json_file):
    nx_polygon = load_geojson_union(json_file)

    # 生成网格点掩码
    def create_mask(lon_array, lat_array, polygon):
        mask = np.zeros((len(lat_array), len(lon_array)))

        for i, lat in enumerate(lat_array):
            for j, lon in enumerate(lon_array):
                point = Point(lon, lat)
                mask[i, j] = polygon.contains(point)

        return mask

    # 应用掩码筛选数据
    mask = create_mask(lon_array, lat_array, nx_polygon)
    mask = np.flipud(mask)

    # np.set_printoptions(threshold=np.inf, linewidth=np.inf)
    # print(mask)
    lon_arr = np.asarray(lon_array, dtype=np.float64)
    lat_arr = np.asarray(lat_array, dtype=np.float64)
    dlon = float(lon_arr[1] - lon_arr[0])
    dlat = float(lat_arr[1] - lat_arr[0])
    grid_base = meb.grid(
        [float(lon_arr[0]), float(lon_arr[-1]), dlon],
        [float(lat_arr[0]), float(lat_arr[-1]), dlat],
    )
    grd = meb.grid_data(grid_base, mask.astype(np.float32).T)
    meb.write_griddata_to_nc(grd, f"{pro_name}_mask.nc", creat_dir=True, effectiveNum=0)
    write_mask_dat(f"{pro_name}_mask.dat", mask, lon_array, lat_array)
    write_mask_png(f"{pro_name}_mask.png", mask)

    return


def get_mask_no_region(pro_name, glon, glat, json_file=None):
    """
    无区域裁剪：整幅网格掩码恒为 1，写出 nc / dat（与 get_mask 同一套读写约定）。
    glon: [slon, elon, dlon]，glat: [slat, elat, dlat]，同 meb.grid。
    json_file 仅与其它接口对齐时可传入，本函数不使用。
    """
    _ = json_file
    grb = meb.grid(glon, glat)
    lon_array = (grb.slon + np.arange(grb.nlon, dtype=np.float64) * grb.dlon).tolist()
    lat_array = (grb.slat + np.arange(grb.nlat, dtype=np.float64) * grb.dlat).tolist()

    mask = np.ones((grb.nlat, grb.nlon), dtype=np.float32)
    mask = np.flipud(mask)

    grd = meb.grid_data(grb, mask.astype(np.float32).T)
    meb.write_griddata_to_nc(grd, f"{pro_name}_mask.nc", creat_dir=True, effectiveNum=0)
    write_mask_dat(f"{pro_name}_mask.dat", mask, lon_array, lat_array)


if __name__ == "__main__":
    # 有行政边界约束的掩码
    json_file = r"D:\Work\mait_24h\resource\cangzhou.geojson"
    # 37-39N，115.5-118E，分辨率0.05
    lon_array = np.round(np.arange(115.50, 118.0001, 0.05), decimals=2).tolist()
    lat_array = np.round(np.arange(37.00, 39.0001, 0.05), decimals=2).tolist()
    # print(len(lon_array), len(lat_array))
    # print(lon_array)
    # print(lat_array)
    get_mask("cangzhou_mask_1", lon_array, lat_array, json_file)

    # 35-42N，112-120E，分辨率0.05
    lon_array = np.round(np.arange(112.00, 120.0001, 0.05), decimals=2).tolist()
    lat_array = np.round(np.arange(35.00, 42.0001, 0.05), decimals=2).tolist()
    print(len(lon_array), len(lat_array))
    print(lon_array)
    print(lat_array)
    get_mask("cangzhou_mask_2", lon_array, lat_array, json_file)

    # 无行政边界约束的掩码（全1）
    get_mask_no_region("mask_2", [112.00, 120.00, 0.05], [35.00, 42.00, 0.05], json_file=None)
    get_mask_no_region("mask_3", [115.50, 118.00, 0.05], [37.00, 39.00, 0.05], json_file=None)
