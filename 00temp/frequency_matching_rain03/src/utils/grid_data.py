import math
import struct
import os
import warnings
import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import convolve
# 抑制 xarray 在 Windows 上加载 gini 引擎失败的无害警告
warnings.filterwarnings('ignore', message="Engine.*loading failed", module='xarray')

from utils.val_type import ValType
from utils.file_flag import FileFlag
from utils.io_meb import meb, resolve_existing_path


def _make_lon_arr(lon_start, d_lon, xn):
    """Create a float64 numpy array of longitudes using exact multiplication (same precision as list comprehension)."""
    return lon_start + np.arange(xn, dtype=np.float64) * d_lon


def _make_lat_arr(lat_start, d_lat, yn):
    """Create a float64 numpy array of latitudes."""
    return lat_start + np.arange(yn, dtype=np.float64) * d_lat


class GridData:
    """规则格点场（``val`` 形状 ``(yn, xn)``），读 Micaps4/NC/掩膜，供 FM / Cressman 使用。

    Micaps4 / NC 读写走 ``meteva_base``。
    """
    # val shape: (yn, xn) — y (lat) first, x (lon) second, matching C-order x-major disk layout
    def __init__(self, *args):
        if len(args) == 0:
            self.xn = 0
            self.yn = 0
            self.lon_start = 0.0
            self.lat_start = 0.0
            self.d_lon = 0.1
            self.d_lat = 0.1
            self._lon = np.array([], dtype=np.float64)
            self._lat = np.array([], dtype=np.float64)
            self.val = None
        elif len(args) == 6 and isinstance(args[0], int) and isinstance(args[1], int):
            local_xn, local_yn, local_lon_start, local_lat_start, local_lon_interval, local_lat_interval = args
            self.xn = local_xn
            self.yn = local_yn
            self.lon_start = local_lon_start
            self.lat_start = local_lat_start
            self.d_lon = local_lon_interval
            self.d_lat = local_lat_interval
            self._lon = _make_lon_arr(local_lon_start, local_lon_interval, local_xn)
            self._lat = _make_lat_arr(local_lat_start, local_lat_interval, local_yn)
            self.val = np.zeros((self.yn, self.xn), dtype=np.float64)
        elif len(args) == 6:
            local_lon_start, local_lon_end, local_lat_start, local_lat_end, local_lon_interval, local_lat_interval = args
            self.xn = int(round((local_lon_end + 1e-05 - local_lon_start) / local_lon_interval)) + 1
            self.yn = int(round((local_lat_end + 1e-05 - local_lat_start) / local_lat_interval)) + 1
            self.lon_start = local_lon_start
            self.lat_start = local_lat_start
            self.d_lon = local_lon_interval
            self.d_lat = local_lat_interval
            self._lon = _make_lon_arr(local_lon_start, local_lon_interval, self.xn)
            self._lat = _make_lat_arr(local_lat_start, local_lat_interval, self.yn)
            self.val = np.zeros((self.yn, self.xn), dtype=np.float64)
        elif len(args) == 1 or (len(args) == 2 and isinstance(args[1], FileFlag)):
            str_input_file_path = args[0]
            em_file_flag = args[1] if len(args) == 2 else FileFlag.m4
            resolved = resolve_existing_path(str_input_file_path, (".m4", ".nc"))
            if resolved:
                str_input_file_path = resolved
            if (len(args) == 1 or em_file_flag == FileFlag.m4) and str_input_file_path.lower().endswith('.nc'):
                em_file_flag = FileFlag.nc
            if em_file_flag == FileFlag.m4:
                self._read_val_from_micaps4(str_input_file_path)
            elif em_file_flag == FileFlag.cybin:
                self._read_val_from_cybin(str_input_file_path)
            elif em_file_flag == FileFlag.awx:
                self._read_val_from_awx(str_input_file_path)
            elif em_file_flag == FileFlag.latlon:
                self._read_val_from_micaps_radar(str_input_file_path)
            elif em_file_flag == FileFlag.argraster:
                self._read_val_from_arg_ascii_raster(str_input_file_path)
            elif em_file_flag == FileFlag.nc:
                self._read_val_from_nc(str_input_file_path)
            else:
                raise Exception("emfileflag is not right")

    @property
    def lon(self):
        return self._lon

    @lon.setter
    def lon(self, value):
        self._lon = np.asarray(value, dtype=np.float64)

    @property
    def lat(self):
        return self._lat

    @lat.setter
    def lat(self, value):
        self._lat = np.asarray(value, dtype=np.float64)

    @property
    def lon_end(self):
        if self._lon is None or len(self._lon) == 0:
            return 0.0
        return float(self._lon[-1])

    @property
    def lat_end(self):
        if self._lat is None or len(self._lat) == 0:
            return 0.0
        return float(self._lat[-1])

    @property
    def lon_interval(self):
        return self.d_lon

    @property
    def lat_interval(self):
        return self.d_lat

    def max_value(self):
        return float(np.max(self.val))

    def min_value(self):
        return float(np.min(self.val))

    def mean_value(self):
        return float(np.mean(self.val))

    def _fill_from_meb_grd(self, grd):
        """把 ``meb`` 格点填进本对象；``val`` 为 ``(yn, xn)``。"""
        lon = np.asarray(grd["lon"].values, dtype=np.float64)
        lat = np.asarray(grd["lat"].values, dtype=np.float64)
        vals = np.asarray(grd.values, dtype=np.float64).squeeze()
        if vals.ndim != 2:
            raise ValueError(f"grid_data 不是二维: shape={vals.shape}")
        self.lon_start = float(lon[0])
        self.lat_start = float(lat[0])
        self.d_lon = float(lon[1] - lon[0]) if lon.size > 1 else 0.1
        self.d_lat = float(lat[1] - lat[0]) if lat.size > 1 else 0.1
        self.xn = int(lon.size)
        self.yn = int(lat.size)
        self._lon = lon.copy()
        self._lat = lat.copy()
        if vals.shape == (self.yn, self.xn):
            self.val = vals.copy()
        elif vals.shape == (self.xn, self.yn):
            self.val = vals.T.copy()
        else:
            raise ValueError(f"格点形状 {vals.shape} 与网格 {self.yn}x{self.xn} 不一致")

    def _to_meb_grid(self, dt_input=None, i_valid=None):
        """由本对象组 ``grid_data``，经纬起止与间隔与读入时一致。"""
        kwargs = {}
        if dt_input is not None:
            kwargs["gtime"] = [dt_input]
        if i_valid is not None:
            kwargs["dtime_list"] = [int(i_valid)]
        grid = meb.grid(
            [self.lon_start, float(self._lon[-1]), self.d_lon],
            [self.lat_start, float(self._lat[-1]), self.d_lat],
            **kwargs)
        data = self.val.reshape(1, 1, 1, 1, self.yn, self.xn)
        return meb.grid_data(grid, data=data)

    def _read_val_from_micaps4(self, str_input_file_path):
        """meb 读入，再与原版南北约定对齐（业务场上 meb 可能相对原版颠倒）。"""
        from utils.io_meb import (
            align_meb_grid_to_original,
            parse_micaps4_like_original,
            read_griddata_from_micaps4,
        )
        grd = read_griddata_from_micaps4(str_input_file_path)
        if grd is not None:
            self._fill_from_meb_grd(grd)
            self.val = align_meb_grid_to_original(self.val, str_input_file_path)
            return
        parsed = parse_micaps4_like_original(str_input_file_path)
        if parsed is None:
            raise RuntimeError(f"meb.read_griddata_from_micaps4 失败: {str_input_file_path}")
        self.lon_start = float(parsed["lon0"])
        self.lat_start = float(parsed["lat0"])
        self.d_lon = float(parsed["dlon"])
        self.d_lat = float(parsed["dlat"])
        self.xn = int(parsed["xn"])
        self.yn = int(parsed["yn"])
        self._lon = self.lon_start + np.arange(self.xn, dtype=np.float64) * self.d_lon
        self._lat = self.lat_start + np.arange(self.yn, dtype=np.float64) * self.d_lat
        self.val = parsed["val"].copy()

    def read_float_val_from_bin(self, input_file_path):
        data = np.fromfile(input_file_path, dtype=np.float32)
        self.val = data.reshape((self.yn, self.xn)).astype(np.float64)

    def read_double_val_from_bin(self, input_file_path):
        data = np.fromfile(input_file_path, dtype=np.float64)
        self.val = data.reshape((self.yn, self.xn)).astype(np.float64)

    def _read_val_from_arg_ascii_raster(self, input_file_path):
        with open(input_file_path, 'r') as f:
            lines = f.readlines()
        idx = 0
        for _ in range(6):
            parts = lines[idx].split()
            idx += 1
            self.xn = int(parts[1])
            parts = lines[idx].split()
            idx += 1
            self.yn = int(parts[1])
            parts = lines[idx].split()
            idx += 1
            if parts[0].lower() == 'xllcorner':
                self.lon_start = float(parts[1])
                parts = lines[idx].split()
                idx += 1
                if parts[0].lower() == 'yllcorner':
                    self.lat_start = float(parts[1])
                    parts = lines[idx].split()
                    idx += 1
                    self.d_lon = float(parts[1])
                    self.d_lat = float(parts[1])
                    parts = lines[idx].split()
                    idx += 1
                    continue
                raise Exception("arg is not supported")
            raise Exception("arg is not supported")
        self._lon = _make_lon_arr(self.lon_start, self.d_lon, self.xn)
        self._lat = _make_lat_arr(self.lat_start, self.d_lat, self.yn)
        self.val = np.zeros((self.yn, self.xn), dtype=np.float64)
        for l in range(self.yn):
            parts = lines[idx].split()
            idx += 1
            for m in range(self.xn):
                self.val[l, m] = float(parts[m])

    def _read_val_from_cybin(self, str_file_path):
        with open(str_file_path, 'rb') as f:
            self.xn = struct.unpack('i', f.read(4))[0]
            self.yn = struct.unpack('i', f.read(4))[0]
            self.lon_start = struct.unpack('d', f.read(8))[0]
            self.lat_start = struct.unpack('d', f.read(8))[0]
            self.d_lon = struct.unpack('d', f.read(8))[0]
            self.d_lat = struct.unpack('d', f.read(8))[0]
            type_flag = struct.unpack('i', f.read(4))[0]
            self._lon = _make_lon_arr(self.lon_start, self.d_lon, self.xn)
            self._lat = _make_lat_arr(self.lat_start, self.d_lat, self.yn)
            if type_flag == 1:
                data = np.fromfile(f, dtype=np.float32, count=self.xn * self.yn)
                self.val = data.reshape((self.yn, self.xn)).astype(np.float64)
            elif type_flag == 2:
                data = np.fromfile(f, dtype=np.float64, count=self.xn * self.yn)
                self.val = data.reshape((self.yn, self.xn)).astype(np.float64)
            elif type_flag == 3:
                data = np.fromfile(f, dtype=np.int16, count=self.xn * self.yn)
                self.val = data.reshape((self.yn, self.xn)).astype(np.float64)
            else:
                raise Exception("type flag is not right")

    def _read_val_from_micaps_radar(self, str_input_file_path):
        with open(str_input_file_path, 'rb') as f:
            f.read(180)
            self.lat_start = struct.unpack('f', f.read(4))[0]
            self.lon_start = struct.unpack('f', f.read(4))[0]
            f.read(16)
            self.yn = struct.unpack('i', f.read(4))[0]
            self.xn = struct.unpack('i', f.read(4))[0]
            self.d_lat = struct.unpack('f', f.read(4))[0]
            self.d_lon = struct.unpack('f', f.read(4))[0]
            self.lat_start -= 0.5 * self.d_lat
            self.lon_start -= 0.5 * self.d_lon
            f.read(10)
            ratio = struct.unpack('h', f.read(2))[0]
            f.read(24)
            self._lon = _make_lon_arr(self.lon_start, self.d_lon, self.xn)
            self._lat = _make_lat_arr(self.lat_start, self.d_lat, self.yn)
            self.val = np.zeros((self.yn, self.xn), dtype=np.float64)
            while True:
                y_idx = struct.unpack('h', f.read(2))[0]
                x_idx = struct.unpack('h', f.read(2))[0]
                n = struct.unpack('h', f.read(2))[0]
                if y_idx == -1:
                    break
                for m in range(n):
                    v = struct.unpack('h', f.read(2))[0] / ratio
                    if v < 10.0:
                        v = 0.0
                    self.val[self.yn - 1 - y_idx, x_idx + m] = v

    def _read_val_from_awx(self, str_input_file_path):
        with open(str_input_file_path, 'rb') as f:
            f.read(14)
            struct.unpack('h', f.read(2))[0]
            struct.unpack('h', f.read(2))[0]
            count = struct.unpack('h', f.read(2))[0]
            f.read(40)
            struct.unpack('h', f.read(2))[0]
            self.xn = struct.unpack('h', f.read(2))[0]
            self.yn = struct.unpack('h', f.read(2))[0]
            f.read(6)
            top = struct.unpack('h', f.read(2))[0] / 100.0
            self.lat_start = struct.unpack('h', f.read(2))[0] / 100.0
            self.lon_start = struct.unpack('h', f.read(2))[0] / 100.0
            right = struct.unpack('h', f.read(2))[0] / 100.0
            self.d_lon = (right - self.lon_start) / (self.xn - 1)
            self.d_lat = (top - self.lat_start) / (self.yn - 1)
            f.read(16)
            struct.unpack('h', f.read(2))[0]
            struct.unpack('h', f.read(2))[0]
            struct.unpack('h', f.read(2))[0]
            f.read(2)
            color_table = [0.0] * 1024
            for i in range(1024):
                v = struct.unpack('h', f.read(2))[0]
                if v < 0:
                    v += 65536
                color_table[i] = v
            f.read(count)
            self._lon = _make_lon_arr(self.lon_start, self.d_lon, self.xn)
            self._lat = _make_lat_arr(self.lat_start, self.d_lat, self.yn)
            self.val = np.zeros((self.yn, self.xn), dtype=np.float64)
            for n in range(self.yn):
                for num4 in range(self.xn):
                    b = f.read(1)[0]
                    self.val[self.yn - 1 - n, num4] = color_table[4 * b] / 100.0

    def _read_val_from_nc(self, str_file_path):
        grd = meb.read_griddata_from_nc(str_file_path)
        if grd is None:
            raise RuntimeError(f"meb.read_griddata_from_nc 失败: {str_file_path}")
        self._fill_from_meb_grd(grd)

    def str_range_info(self):
        return (f"{self.lon_interval:.3f} {self.lat_interval:.3f} "
                f"{self._lon[0]:.2f} {self._lon[self.xn - 1]:.2f} "
                f"{self._lat[0]:.2f} {self._lat[self.yn - 1]:.2f} "
                f"{self.xn} {self.yn}")

    def write_val_to_micaps4(self, str_file_path, title=None, str_fortmat=None,
                            dt_input=None, i_valid=None):
        """写出 Micaps4：组 ``grid_data`` 交给 ``meb.write_griddata_to_micaps4``。

        网格范围与时效来自 ``grd``；``title`` 仅作说明文字（可选），
        不要传原版整行 ``diamond 4 …`` 文件头。
        """
        del str_fortmat
        grd = self._to_meb_grid(dt_input, i_valid)
        kwargs = {'creat_dir': True, 'effectiveNum': 2, 'inte': 5, 'vmin': 0, 'vmax': 200}
        if title:
            kwargs['title'] = str(title).strip()
        meb.write_griddata_to_micaps4(grd, str_file_path, **kwargs)

    def write_val_to_micaps4_with_simple_header(self, str_file_path, str_simple_header='simple_header'):
        self.write_val_to_micaps4(str_file_path, title=str_simple_header)

    def write_val_to_nc(self, str_file_path, dt_input=None, i_valid=0):
        grd = self._to_meb_grid(dt_input, i_valid)
        meb.write_griddata_to_nc(grd, save_path=str_file_path, creat_dir=True)

    def write_float_val_to_bin(self, str_file_path):
        os.makedirs(os.path.dirname(str_file_path), exist_ok=True)
        self.val.astype(np.float32).tofile(str_file_path)

    def write_double_val_to_bin(self, str_file_path):
        os.makedirs(os.path.dirname(str_file_path), exist_ok=True)
        self.val.tofile(str_file_path)

    def write_val_to_cybin(self, str_file_path, val_type=ValType.float32):
        os.makedirs(os.path.dirname(str_file_path), exist_ok=True)
        with open(str_file_path, 'wb') as f:
            f.write(struct.pack('i', self.xn))
            f.write(struct.pack('i', self.yn))
            f.write(struct.pack('d', self.lon_start))
            f.write(struct.pack('d', self.lat_start))
            f.write(struct.pack('d', self.d_lon))
            f.write(struct.pack('d', self.d_lat))
            if val_type == ValType.float32:
                f.write(struct.pack('i', 1))
                self.val.astype(np.float32).tofile(f)
            elif val_type == ValType.double64:
                f.write(struct.pack('i', 2))
                self.val.tofile(f)
            elif val_type == ValType.int16:
                f.write(struct.pack('i', 3))
                self.val.astype(np.int16).tofile(f)
            else:
                f.write(struct.pack('i', 1))
                self.val.astype(np.float32).tofile(f)

    def write_float_val_to_jilin_bin(self, str_file_path, header="simple header"):
        os.makedirs(os.path.dirname(str_file_path), exist_ok=True)
        text = (f"GRIDDATA    XXXXXXXXProductTitle={header},"
                f"Top={self.lat_end:.2f},Bottom={self.lat_start:.2f},"
                f"Left={self.lon_start:.2f},Right={self.lon_end:.2f},"
                f"Height={self.yn},Width={self.xn},"
                f"Resolution_x={self.lon_interval},Resolution_y={self.lat_interval},"
                f"Offset=0,Ratio=1,Invalid=-9999,DataType=6,Levels=1,Dimension=1,LevelValue=NAN")
        new_value = str(len(text)).rjust(8)
        text = text.replace("XXXXXXXX", new_value)
        with open(str_file_path, 'w') as f:
            f.write(text)
        with open(str_file_path, 'ab') as f:
            for num in range(self.yn - 1, -1, -1):
                self.val[num, :].astype(np.float32).tofile(f)

    def mesh_val(self, local_lon_start, local_lon_end, local_lat_start, local_lat_end,
                 local_lon_interval, local_lat_interval, db_undef=None):
        fill_val = db_undef if db_undef is not None else 0.0
        num_x = int(round((local_lon_end + 1e-05 - local_lon_start) / local_lon_interval)) + 1
        num_y = int(round((local_lat_end + 1e-05 - local_lat_start) / local_lat_interval)) + 1

        # Fast path: same grid — just copy the data (no interpolation needed)
        if (abs(local_lon_start - self.lon_start) < 1e-10 and
            abs(local_lon_interval - self.d_lon) < 1e-10 and
            abs(local_lat_start - self.lat_start) < 1e-10 and
            abs(local_lat_interval - self.d_lat) < 1e-10 and
            num_x == self.xn and num_y == self.yn):
            grid_data = GridData(num_x, num_y, local_lon_start, local_lat_start,
                                 local_lon_interval, local_lat_interval)
            grid_data.val = self.val.copy()
            return grid_data

        # _lon / _lat are already numpy float64 arrays (no conversion needed)
        src_lon_arr = self._lon
        src_lat_arr = self._lat

        # Build target coordinates with exact multiplication (NOT np.arange with float step,
        # which is unreliable due to floating-point accumulation → produces wrong count)
        target_lon = local_lon_start + np.arange(num_x, dtype=np.float64) * local_lon_interval
        target_lat = local_lat_start + np.arange(num_y, dtype=np.float64) * local_lat_interval

        # val is (yn, xn); interp expects (len(lon), len(lat)) so pass val.T
        interp = RegularGridInterpolator(
            (src_lon_arr, src_lat_arr), self.val.T,
            method='linear', bounds_error=False, fill_value=float(fill_val)
        )
        t_lon_grid, t_lat_grid = np.meshgrid(target_lon, target_lat, indexing='ij')
        result_vals = interp((t_lon_grid, t_lat_grid))  # shape (num_x, num_y)

        grid_data = GridData(num_x, num_y, local_lon_start, local_lat_start,
                             local_lon_interval, local_lat_interval)
        # result_vals.T shape: (num_y, num_x) — guaranteed exact match
        grid_data.val = result_vals.T.astype(np.float64)
        return grid_data

    def copy_grid_data(self):
        grid_data = GridData.__new__(GridData)
        grid_data.xn = self.xn
        grid_data.yn = self.yn
        grid_data.lon_start = self.lon_start
        grid_data.lat_start = self.lat_start
        grid_data.d_lon = self.d_lon
        grid_data.d_lat = self.d_lat
        grid_data._lon = self._lon  # share reference (immutable in practice, same values)
        grid_data._lat = self._lat
        grid_data.val = self.val.copy()
        return grid_data

    def is_same_grid(self, inp):
        return self.xn == inp.xn and self.yn == inp.yn

    def mask_val(self, mask, mask_value):
        if self.is_same_grid(mask):
            self.val[mask.val <= 0.0] = mask_value
        else:
            raise Exception("grid net is not the same!")

    def add_val(self, inp):
        if isinstance(inp, GridData):
            if self.is_same_grid(inp):
                self.val += inp.val
            else:
                raise Exception("grid net is not the same!")
        else:
            self.val += inp

    def add_val_form_new_grid_data(self, inp):
        gd = self.copy_grid_data()
        gd.add_val(inp)
        return gd

    def sub_val(self, inp):
        if isinstance(inp, GridData):
            if self.is_same_grid(inp):
                self.val -= inp.val
            else:
                raise Exception("grid net is not the same!")
        else:
            self.val -= inp

    def sub_val_form_new_grid_data(self, inp):
        gd = self.copy_grid_data()
        gd.sub_val(inp)
        return gd

    def multi_val(self, inp):
        if isinstance(inp, GridData):
            if self.is_same_grid(inp):
                self.val *= inp.val
            else:
                raise Exception("grid net is not the same!")
        else:
            self.val *= inp

    def multi_val_form_new_grid_data(self, inp):
        gd = self.copy_grid_data()
        gd.multi_val(inp)
        return gd

    def div_val(self, inp):
        if isinstance(inp, GridData):
            if self.is_same_grid(inp):
                self.val /= inp.val
            else:
                raise Exception("grid net is not the same!")
        else:
            self.val /= inp

    def div_val_form_new_grid_data(self, inp):
        gd = self.copy_grid_data()
        gd.div_val(inp)
        return gd

    def reverse_y(self):
        self.val = np.flipud(self.val)

    def reverse_x(self):
        self.val = np.fliplr(self.val)

    def clear_to_num(self, number):
        self.val.fill(number)

    def clear_to_num_greater_than(self, number, number_limit):
        self.val[self.val >= number_limit + 1e-05] = number

    def clear_to_num_less_than(self, number, number_limit):
        self.val[self.val < number_limit - 1e-05] = number

    def abs_vals(self):
        np.abs(self.val, out=self.val)

    def remove_mean(self):
        self.val -= self.mean_value()

    def standardize_by_max_min(self, min_val=None, max_val=None):
        if min_val is None and max_val is None:
            mn = self.min_value()
            mx = self.max_value()
            self.val = (self.val - mn) / (mx - mn)
        else:
            mask_high = self.val >= max_val
            mask_low = self.val < min_val
            mask_mid = ~mask_high & ~mask_low
            self.val[mask_high] = 1.0
            self.val[mask_low] = 0.0
            self.val[mask_mid] = (self.val[mask_mid] - min_val) / (max_val - min_val)

    def paste_grid_data(self, gd_paste_data):
        grid_data = gd_paste_data.mesh_val(self._lon[0], self._lon[self.xn - 1],
                                           self._lat[0], self._lat[self.yn - 1],
                                           self.d_lon, self.d_lat, 99999.0)
        mask = grid_data.val == 99999.0
        grid_data.val[mask] = self.val[mask]
        return grid_data

    def to_scatter_data(self):
        from utils.point_data import PointData
        from utils.scatter_data import ScatterData
        total = self.xn * self.yn
        # Pre-allocate list with known size
        arr = [None] * total
        idx = 0
        for i in range(self.yn):
            lat_i = self._lat[i]
            base_id = i * self.xn
            row = self.val[i, :]
            for j in range(self.xn):
                arr[idx] = PointData(str(j + base_id), float(self._lon[j]), float(lat_i), float(row[j]))
                idx += 1
        return ScatterData(arr)

    def count_num_greater_than(self, db_limit_num):
        return int(np.sum(self.val >= db_limit_num))

    def count_num_less_than(self, db_limit_num):
        return int(np.sum(self.val < db_limit_num))

    def count_num_between(self, db_limit_num1, db_limit_num2):
        return int(np.sum((self.val >= db_limit_num1) & (self.val < db_limit_num2)))

    def to_scatter_data_greater_than(self, db_limit):
        from utils.point_data import PointData
        from utils.scatter_data import ScatterData
        mask = self.val >= db_limit
        idx_y, idx_x = np.where(mask)
        n = len(idx_y)
        lst = [None] * n
        for k in range(n):
            y, x = int(idx_y[k]), int(idx_x[k])
            lst[k] = PointData(str(x + y * self.xn), float(self._lon[x]),
                               float(self._lat[y]), float(self.val[y, x]))
        return ScatterData(lst)

    def to_scatter_data_less_than(self, db_limit):
        from utils.point_data import PointData
        from utils.scatter_data import ScatterData
        mask = self.val < db_limit
        idx_y, idx_x = np.where(mask)
        n = len(idx_y)
        lst = [None] * n
        for k in range(n):
            y, x = int(idx_y[k]), int(idx_x[k])
            lst[k] = PointData(str(x + y * self.xn), float(self._lon[x]),
                               float(self._lat[y]), float(self.val[y, x]))
        return ScatterData(lst)

    def smooth9(self, ct_num):
        kernel = np.array([[0.0625, 0.125, 0.0625],
                           [0.125,  0.25,  0.125],
                           [0.0625, 0.125, 0.0625]], dtype=np.float64)
        # Pre-allocate buffer to avoid allocation per iteration
        buf = np.empty_like(self.val)
        for _ in range(ct_num):
            convolve(self.val, kernel, output=buf, mode='constant', cval=0.0)
            # x edges (axis 1): left/right — vectorized
            buf[1:-1, 0] = buf[1:-1, 1] + (buf[1:-1, 1] - buf[1:-1, 2])
            buf[1:-1, -1] = buf[1:-1, -2] + (buf[1:-1, -2] - buf[1:-1, -3])
            # y edges (axis 0): bottom/top — vectorized
            buf[0, :] = buf[1, :] + (buf[1, :] - buf[2, :])
            buf[-1, :] = buf[-2, :] + (buf[-2, :] - buf[-3, :])
            np.maximum(buf, 0.0, out=buf)
            # Swap buffers
            self.val, buf = buf, self.val

    def get_point_data(self, pd_input):
        pd = pd_input.copy_point_data()
        num = int(math.floor((pd_input.lon - self.lon_start + 1e-05) / self.d_lon))   # x-index
        num2 = int(math.floor((pd_input.lat - self.lat_start + 1e-05) / self.d_lat))  # y-index
        if 0 <= num < self.xn - 1 and 0 <= num2 < self.yn - 1:
            num3 = (float(self.val[num2, num]) * (self._lon[num + 1] - pd_input.lon) +
                    float(self.val[num2, num + 1]) * (pd_input.lon - self._lon[num])) / self.d_lon
            num4 = (float(self.val[num2 + 1, num]) * (self._lon[num + 1] - pd_input.lon) +
                    float(self.val[num2 + 1, num + 1]) * (pd_input.lon - self._lon[num])) / self.d_lon
            num5 = (num3 * (self._lat[num2 + 1] - pd_input.lat) +
                    num4 * (pd_input.lat - self._lat[num2])) / self.d_lat
            pd.val = num5
        elif num == self.xn - 1 and 0 <= num2 < self.yn - 1:
            pd.val = (float(self.val[num2, num]) * (self._lat[num2 + 1] - pd_input.lat) +
                      float(self.val[num2 + 1, num]) * (pd_input.lat - self._lat[num2])) / self.d_lat
        elif 0 <= num < self.xn - 1 and num2 == self.yn - 1:
            pd.val = (float(self.val[num2, num]) * (self._lon[num + 1] - pd_input.lon) +
                      float(self.val[num2, num + 1]) * (pd_input.lon - self._lon[num])) / self.d_lon
        elif num == self.xn - 1 and num2 == self.yn - 1:
            pd.val = float(self.val[num2, num])
        return pd

    @staticmethod
    def linear_interp(x1, x2, t1, t2, t):
        grid_data = x1.copy_grid_data()
        grid_data.val = ((t2 - t) * x1.val + (t - t1) * x2.val) / (t2 - t1)
        return grid_data

    def to_string(self, db_lon, db_lat):
        num = int((db_lon + 1e-05 - self.lon_start) / self.lon_interval)   # x-index
        num2 = int((db_lat + 1e-05 - self.lat_start) / self.lat_interval)  # y-index
        return f"lon: {db_lon}  lat{db_lat}  value: {self.val[num2, num]}"

if __name__ == '__main__':
    # 测试读取 nc 文件
    gd = GridData(r"C:\Users\admin\Desktop\rain01\rain01_qpf\C#84\temp\ecmwf\2025100100.001_out.nc")
    gd.write_val_to_nc(r"C:\Users\admin\Desktop\rain01\rain01_qpf\C#84\temp\ecmwf\2025100100.001_out_test.nc")