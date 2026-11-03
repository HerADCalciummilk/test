class ConfigureData:
    """计算区经纬范围、分辨率与外扩；可由 ``config.json`` 覆盖。"""
    def __init__(self, str_file_path=None, file_flag=None):
        self.center_lon_left = 70.0
        self.center_lon_right = 140.0
        self.center_lat_bottom = 0.0
        self.center_lat_top = 60.0
        self.lonlat_ext = 0.0
        self.dlon = 0.1
        self.dlat = 0.1
        self.cimissip = "NMC_YBS_schen"
        self.cimissport = "1885"
        self.cimissid = "NMC_YBS_schen"
        self.cimisspassword = "nmc0450"
        self.m4ip = "10.172.10.30"
        self.m4port = "8080"
        self.m4id = "test"
        self.m4password = "test"

        if str_file_path is not None:
            self._read_from_configure_ini(str_file_path)

    @property
    def large_lon_left(self):
        return self.center_lon_left - self.lonlat_ext

    @property
    def large_lon_right(self):
        return self.center_lon_right + self.lonlat_ext

    @property
    def large_lat_bottom(self):
        return self.center_lat_bottom - self.lonlat_ext

    @property
    def large_lat_top(self):
        return self.center_lat_top + self.lonlat_ext

    def _read_from_configure_ini(self, str_file_path):
        try:
            with open(str_file_path, 'r', encoding='gb2312') as f:
                lines = f.readlines()
            for line in lines:
                line = line.strip()
                if '=' not in line:
                    continue
                parts = line.split('=', 1)
                key = parts[0].strip().lower()
                value = parts[1].strip()
                if key == 'cimissip':
                    self.cimissip = value
                elif key == 'cimissport':
                    self.cimissport = value
                elif key == 'cimissid':
                    self.cimissid = value
                elif key == 'cimisspassword':
                    self.cimisspassword = value
                elif key == 'm4ip':
                    self.m4ip = value
                elif key == 'm4port':
                    self.m4port = value
                elif key == 'm4id':
                    self.m4id = value
                elif key == 'm4password':
                    self.m4password = value
                elif key == 'lonstart':
                    self.center_lon_left = float(value)
                elif key == 'lonend':
                    self.center_lon_right = float(value)
                elif key == 'latstart':
                    self.center_lat_bottom = float(value)
                elif key == 'latend':
                    self.center_lat_top = float(value)
                elif key == 'dlon':
                    self.dlon = float(value)
                elif key == 'dlat':
                    self.dlat = float(value)
                elif key == 'extent1':
                    self.lonlat_ext = float(value)
        except Exception:
            raise Exception("read para ini wrong!")
