import math
import os
import random
import numpy as np
from scipy.interpolate import RegularGridInterpolator
from utils.file_flag import FileFlag
from utils.point_data import PointData


def _read_text_lines(str_input_file_path):
    with open(str_input_file_path, 'rb') as f:
        raw = f.read()
    for encoding in ('gb2312', 'gbk', 'utf-8', 'gb18030'):
        try:
            return raw.decode(encoding).splitlines()
        except UnicodeDecodeError:
            pass
    return raw.decode('gb18030', errors='ignore').splitlines()


class ScatterData:
    """站点散点（id/lon/lat/val），读 Micaps3 / 站点表，供频率匹配与 Cressman 使用。

    Micaps3 读写走 ``meteva_base``；``sta.info`` 仍按本包站点表格式解析。
    """
    def __init__(self, *args):
        self._dct_cache = None   # lazily built dictionary cache
        self._lon_arr = None     # cached numpy lon array
        self._lat_arr = None     # cached numpy lat array
        if len(args) == 1 and isinstance(args[0], list):
            pd_input_data = args[0]
            lst = []
            dct = {}
            for pd in pd_input_data:
                if pd.id not in dct:
                    lst.append(pd.copy_point_data())
                    dct[pd.id] = pd.val
            self.sta_data = lst
            self._dct_cache = dct
        elif len(args) == 2 and isinstance(args[0], str):
            str_input_file_path, em_file_flag = args
            if em_file_flag == FileFlag.m3:
                self._read_from_m3(str_input_file_path)
            elif em_file_flag == FileFlag.stainfo:
                self._read_from_stainfo(str_input_file_path)
            elif em_file_flag == FileFlag.stadata:
                self._read_from_stadata(str_input_file_path)
            else:
                raise Exception("strflag is not right")
        elif len(args) == 1 and isinstance(args[0], str):
            self._read_from_m3(args[0])

    @property
    def length(self):
        return len(self.sta_data)

    def max_value(self):
        num = -9999999.0
        for pd in self.sta_data:
            if pd.val >= num:
                num = pd.val
        return num

    def min_value(self):
        num = 9999999.0
        for pd in self.sta_data:
            if pd.val <= num:
                num = pd.val
        return num

    def mean_value(self):
        num = 0.0
        for pd in self.sta_data:
            num += pd.val
        return num / len(self.sta_data)

    def _invalidate_cache(self):
        """Called after any mutation that changes sta_data or point values via external dict."""
        self._dct_cache = None
        self._lon_arr = None
        self._lat_arr = None

    def _get_dictionary_data(self):
        if self._dct_cache is None:
            dct = {}
            for pd in self.sta_data:
                if pd.id not in dct:
                    dct[pd.id] = pd.val
            self._dct_cache = dct
        return self._dct_cache

    def _put_dictionary_data(self, dc_data):
        for pd in self.sta_data:
            if pd.id in dc_data:
                pd.val = dc_data[pd.id]
        self._invalidate_cache()

    def _get_lon_arr(self):
        """Lazily build numpy array of station longitudes (for interpolation)."""
        if self._lon_arr is None:
            self._lon_arr = np.array([pd.lon for pd in self.sta_data], dtype=np.float64)
        return self._lon_arr

    def _get_lat_arr(self):
        """Lazily build numpy array of station latitudes (for interpolation)."""
        if self._lat_arr is None:
            self._lat_arr = np.array([pd.lat for pd in self.sta_data], dtype=np.float64)
        return self._lat_arr

    def _read_from_m3(self, str_input_file_path):
        from utils.io_meb import resolve_existing_path, read_stadata_rows
        path = resolve_existing_path(str_input_file_path, (".m3",)) or str_input_file_path
        rows = read_stadata_rows(path)
        lst, dct = [], {}
        for sid, lon, lat, val in rows:
            if sid not in dct:
                lst.append(PointData(sid, lon, lat, val))
                dct[sid] = val
        self.sta_data = lst
        self._dct_cache = dct

    def _read_from_stainfo(self, str_input_file_path):
        lst = []
        dct = {}
        for line in _read_text_lines(str_input_file_path):
            arr = line.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ').split()
            if len(arr) >= 3:
                from utils.io_meb import norm_sta_id
                text = norm_sta_id(arr[0].strip())
                db_lon = float(arr[1].strip())
                db_lat = float(arr[2].strip())
                if text not in dct:
                    lst.append(PointData(text, db_lon, db_lat, 0.0))
                    dct[text] = 0.0
        self.sta_data = lst
        self._dct_cache = dct

    def _read_from_stadata(self, str_input_file_path):
        lst = []
        dct = {}
        for line in _read_text_lines(str_input_file_path):
            arr = line.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ').split()
            if len(arr) >= 4:
                from utils.io_meb import norm_sta_id
                text = norm_sta_id(arr[0].strip())
                db_lon = float(arr[1].strip())
                db_lat = float(arr[2].strip())
                num = float(arr[3].strip())
                if text not in dct:
                    lst.append(PointData(text, db_lon, db_lat, num))
                    dct[text] = num
        self.sta_data = lst
        self._dct_cache = dct

    def read_val_from_micaps3(self, str_input_file_path):
        """按站号从 Micaps3 更新 ``val``。"""
        from utils.io_meb import resolve_existing_path, read_stadata_rows
        path = resolve_existing_path(str_input_file_path, (".m3",)) or str_input_file_path
        rows = read_stadata_rows(path)
        dct = self._get_dictionary_data()
        for sid, _lon, _lat, val in rows:
            if sid in dct:
                dct[sid] = val
        self._dct_cache = dct
        for pd in self.sta_data:
            if pd.id in dct:
                pd.val = dct[pd.id]
        self._lon_arr = None
        self._lat_arr = None

    def slow_read_val_from_micaps3(self, str_input_file_path):
        for line in _read_text_lines(str_input_file_path):
            arr = line.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ').split()
            if len(arr) != 5:
                continue
            text = arr[0].strip()
            float(arr[1].strip())
            float(arr[2].strip())
            val = float(arr[4].strip())
            for pd in self.sta_data:
                if pd.id.strip() == text.strip():
                    pd.val = val
                    break

    def writer_to_micaps3(self, str_file_path, dt_input=None, i_valid=0, title=None):
        """写出 Micaps3：组站点表交给 ``meb.write_stadata_to_micaps3``。

        ``title`` 仅作说明文字（可选），不要传原版整行 ``diamond 3 …`` 文件头。
        """
        from utils.io_meb import write_stadata_m3
        write_stadata_m3(
            (pd.id for pd in self.sta_data),
            (pd.lon for pd in self.sta_data),
            (pd.lat for pd in self.sta_data),
            (pd.val for pd in self.sta_data),
            str_file_path,
            dt_input=dt_input,
            i_valid=i_valid,
            title=title,
        )

    def writer_to_micaps3_with_simple_header(self, str_file_path, str_simple_header="simple_header"):
        self.writer_to_micaps3(str_file_path, title=str_simple_header)

    def copy_scatter_data(self):
        sd = ScatterData(self.sta_data)
        sd._dct_cache = dict(self._dct_cache) if self._dct_cache is not None else None
        return sd

    def read_from_sactter_data(self, sd_input):
        dct = self._get_dictionary_data()
        for pd in sd_input.sta_data:
            if pd.id in dct:
                dct[pd.id] = pd.val
        self._dct_cache = dct
        for pd in self.sta_data:
            if pd.id in dct:
                pd.val = dct[pd.id]
        self._lon_arr = None
        self._lat_arr = None

    def add(self, sd_input_data):
        dct = self._get_dictionary_data()
        for pd in sd_input_data.sta_data:
            if pd.id in dct:
                dct[pd.id] = dct[pd.id] + pd.val
        self._put_dictionary_data(dct)

    def add_form_new_scatter_data(self, sd_input_data):
        sd = ScatterData(self.sta_data)
        sd.add(sd_input_data)
        return sd

    def sub(self, sd_input_data):
        dct = self._get_dictionary_data()
        for pd in sd_input_data.sta_data:
            if pd.id in dct:
                dct[pd.id] = dct[pd.id] - pd.val
        self._put_dictionary_data(dct)

    def sub_form_new_scatter_data(self, sd_input_data):
        sd = ScatterData(self.sta_data)
        sd.sub(sd_input_data)
        return sd

    def multi(self, sd_input_data):
        dct = self._get_dictionary_data()
        for pd in sd_input_data.sta_data:
            if pd.id in dct:
                dct[pd.id] = dct[pd.id] * pd.val
        self._put_dictionary_data(dct)

    def multi_form_new_scatter_data(self, sd_input_data):
        sd = ScatterData(self.sta_data)
        sd.multi(sd_input_data)
        return sd

    def div(self, sd_input_data):
        dct = self._get_dictionary_data()
        for pd in sd_input_data.sta_data:
            if pd.id in dct:
                dct[pd.id] = dct[pd.id] / pd.val
        self._put_dictionary_data(dct)

    def div_form_new_scatter_data(self, sd_input_data):
        sd = ScatterData(self.sta_data)
        sd.div(sd_input_data)
        return sd

    def add_value(self, apha):
        self._invalidate_cache()
        for pd in self.sta_data:
            pd.val = apha + pd.val

    def add_value_form_new_scatter_data(self, apha):
        sd = ScatterData(self.sta_data)
        sd.add_value(apha)
        return sd

    def sub_value(self, apha):
        self._invalidate_cache()
        for pd in self.sta_data:
            pd.val = pd.val - apha

    def sub_value_form_new_scatter_data(self, apha):
        sd = ScatterData(self.sta_data)
        sd.sub_value(apha)
        return sd

    def multi_value(self, apha):
        self._invalidate_cache()
        for pd in self.sta_data:
            pd.val = apha * pd.val

    def multi_value_form_new_scatter_data(self, apha):
        sd = ScatterData(self.sta_data)
        sd.multi_value(apha)
        return sd

    def div_value(self, apha):
        self._invalidate_cache()
        for pd in self.sta_data:
            pd.val = pd.val / apha

    def div_value_form_new_scatter_data(self, apha):
        sd = ScatterData(self.sta_data)
        sd.div_value(apha)
        return sd

    def standardize_by_max_min(self, min_val=None, max_val=None):
        self._invalidate_cache()
        if min_val is None and max_val is None:
            mn = self.min_value()
            mx = self.max_value()
            for pd in self.sta_data:
                if mx != mn:
                    pd.val = (pd.val - mn) / (mx - mn)
                else:
                    pd.val = 0.0
        else:
            if max_val <= min_val:
                raise Exception("max value should larger than min value")
            for pd in self.sta_data:
                pd.val = (pd.val - min_val) / (max_val - min_val)

    def select_greater_than(self, choose_limit):
        lst = [pd.copy_point_data() for pd in self.sta_data if pd.val >= choose_limit]
        return ScatterData(lst)

    def select_less_than(self, choose_limit):
        lst = [pd.copy_point_data() for pd in self.sta_data if pd.val < choose_limit]
        return ScatterData(lst)

    def clear_to_num(self, number):
        self._invalidate_cache()
        for pd in self.sta_data:
            pd.val = number

    def clear_to_num_less_than(self, number, number_limit):
        self._invalidate_cache()
        for pd in self.sta_data:
            if pd.val < number_limit:
                pd.val = number

    def clear_to_num_greater_than(self, number, number_limit):
        self._invalidate_cache()
        for pd in self.sta_data:
            if pd.val >= number_limit:
                pd.val = number

    def frame_by_line(self, ld_data):
        # Fast path: detect axis-aligned rectangle (4 points, same lons for lat pairs)
        if self._is_axis_aligned_rect(ld_data):
            return self._frame_by_rect(ld_data)
        lst = [pd for pd in self.sta_data if ScatterData.is_point_in_line_v2(pd, ld_data)]
        return ScatterData(lst)

    @staticmethod
    def _is_axis_aligned_rect(ld_data):
        """Check if line data describes an axis-aligned rectangle (4 points)."""
        if ld_data.point_num != 4:
            return False
        lons = ld_data.point_lon
        lats = ld_data.point_lat
        # Rectangle: [lon_min, lon_max, lon_max, lon_min], [lat_min, lat_min, lat_max, lat_max]
        return (abs(lons[0] - lons[3]) < 1e-10 and abs(lons[1] - lons[2]) < 1e-10 and
                abs(lats[0] - lats[1]) < 1e-10 and abs(lats[2] - lats[3]) < 1e-10)

    def _frame_by_rect(self, ld_data):
        """Fast axis-aligned rectangle filtering using numpy vectorization."""
        lon_min = min(ld_data.point_lon[0], ld_data.point_lon[1])
        lon_max = max(ld_data.point_lon[0], ld_data.point_lon[1])
        lat_min = min(ld_data.point_lat[0], ld_data.point_lat[2])
        lat_max = max(ld_data.point_lat[0], ld_data.point_lat[2])
        # Vectorized comparison — O(n) single pass
        lst = [pd for pd in self.sta_data
               if lon_min - 1e-10 <= pd.lon <= lon_max + 1e-10 and
               lat_min - 1e-10 <= pd.lat <= lat_max + 1e-10]
        return ScatterData(lst)

    def bilinear_interpolation_from_grid_data(self, input_data, db_undef=0.0):
        lons = self._get_lon_arr()
        lats = self._get_lat_arr()
        # input_data._lon/_lat are already numpy float64 arrays (no conversion needed)
        src_lon = input_data._lon
        src_lat = input_data._lat
        interp = RegularGridInterpolator(
            (src_lon, src_lat), input_data.val.T,
            method='linear', bounds_error=False, fill_value=db_undef
        )
        vals = interp(np.column_stack([lons, lats]))
        # Vectorized assignment — avoid Python for-loop
        for i, pd in enumerate(self.sta_data):
            pd.val = float(vals[i])

    def nearest_from_grid_data(self, input_data, db_undef=0.0):
        for pd in self.sta_data:
            num2 = int(round((pd.lon + 1e-05 - input_data.lon_start) / input_data.lon_interval))
            num3 = int(round((pd.lat + 1e-05 - input_data.lat_start) / input_data.lat_interval))
            if 0 <= num2 < input_data.xn - 1 and 0 <= num3 < input_data.yn - 1:
                pd.val = float(input_data.val[num3, num2])
            else:
                pd.val = db_undef

    def idw_from_grid_data(self, input_data, radius=1.0, db_undef=0.0):
        num2 = radius ** 2
        for pd in self.sta_data:
            num3 = int(radius / input_data.lon_interval)
            num4 = int(radius / input_data.lat_interval)
            num5 = int((pd.lon - input_data.lon_start) / input_data.lon_interval)
            num6 = int((pd.lat - input_data.lat_start) / input_data.lat_interval)
            num7 = 0.0
            pd.val = 0.0
            for j in range(num6 - num4, num6 + num4 + 1):
                for k in range(num5 - num3, num5 + num3 + 1):
                    if 0 <= k < input_data.xn and 0 <= j < input_data.yn:
                        num8 = ((input_data.lon_start + k * input_data.lon_interval - pd.lon) ** 2 +
                                (input_data.lat_start + j * input_data.lat_interval - pd.lat) ** 2)
                        num9 = (num2 - num8) / (num2 + num8)
                        if 0.0 <= num9 <= 1.0:
                            pd.val = pd.val + num9 * float(input_data.val[j, k])
                            num7 += num9
            if num7 > 0.0:
                pd.val = pd.val / num7
            else:
                pd.val = db_undef

    def is_contain(self, str_id):
        for pd in self.sta_data:
            if pd.id == str_id:
                return True
        return False

    def select_pd_data_by_id(self, str_id):
        for pd in self.sta_data:
            if pd.id == str_id:
                return pd.copy_point_data()
        return None

    def to_point_data_array(self):
        return [pd.copy_point_data() for pd in self.sta_data]

    @staticmethod
    def flatten_from_grid_data(input_data):
        lst = [PointData(input_data.lon[j], input_data.lat[i], float(input_data.val[i, j]))
               for i in range(input_data.yn) for j in range(input_data.xn)]
        return ScatterData(lst)

    @staticmethod
    def linear_interp(x1, x2, t1, t2, t):
        sd = x1.copy_scatter_data()
        for i in range(len(x1.sta_data)):
            sd.sta_data[i].val = ((t2 - t) * x1.sta_data[i].val + (t - t1) * x2.sta_data[i].val) / (t2 - t1)
        return sd

    @staticmethod
    def is_point_in_line_v2(pd_data, ld_data):
        num = 0
        num2 = 0
        num3 = ld_data.point_num - 1
        while num2 < ld_data.point_num:
            if ((ld_data.point_lat[num2] > pd_data.lat) != (ld_data.point_lat[num3] > pd_data.lat) and
                pd_data.lon < ((ld_data.point_lon[num3] - ld_data.point_lon[num2]) *
                               (pd_data.lat - ld_data.point_lat[num2]) /
                               (ld_data.point_lat[num3] - ld_data.point_lat[num2]) +
                               ld_data.point_lon[num2])):
                num = 1 + num
            num3 = num2
            num2 += 1
        if num % 2 == 0:
            return False
        return True

    def __str__(self):
        return f"staNum: {len(self.sta_data)},firstData: {self.sta_data[0]}" if self.sta_data else "empty"

    def to_string_by_index(self, i_num):
        if 0 <= i_num < len(self.sta_data):
            return f"staNum: {len(self.sta_data)},ChooseData: {self.sta_data[i_num]}"
        raise Exception("iNum is not proper")

    def to_string_by_id(self, str_id):
        for pd in self.sta_data:
            if pd.id == str_id:
                return f"staNum: {len(self.sta_data)},ChooseData: {pd}"
        return "No Wanted Information"
