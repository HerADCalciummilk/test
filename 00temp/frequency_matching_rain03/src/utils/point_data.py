import math


class PointData:
    def __init__(self, *args):
        if len(args) == 4:
            str_id, db_lon, db_lat, db_value = args
            self.id = str_id.strip()
            self.lon = db_lon if db_lon >= 0.0 else 360.0 + db_lon
            self.lat = db_lat
            self.val = db_value
        elif len(args) == 3:
            db_lon, db_lat, db_value = args
            self.id = str(int(db_lon * 100.0 + db_lat * 10000000.0)).zfill(11).strip()
            self.lon = db_lon if db_lon >= 0.0 else 360.0 + db_lon
            self.lat = db_lat
            self.val = db_value
        elif len(args) == 2:
            db_lon, db_lat = args
            self.id = str(int(db_lon * 100.0 + db_lat * 10000000.0)).zfill(11).strip()
            self.lon = db_lon if db_lon >= 0.0 else 360.0 + db_lon
            self.lat = db_lat
            self.val = 0.0
        else:
            raise ValueError("PointData: invalid arguments")

    def copy_point_data(self):
        return PointData(self.id, self.lon, self.lat, self.val)

    def add_val(self, db_input):
        self.val += db_input

    def sub_val(self, db_input):
        self.val -= db_input

    def multi_val(self, db_input):
        self.val *= db_input

    def div_val(self, db_input):
        if db_input != 0.0:
            self.val /= db_input
        else:
            raise Exception("div val is zero")

    def add_val_form_new_pd(self, db_input):
        pd = PointData(self.id, self.lon, self.lat, self.val)
        pd.add_val(db_input)
        return pd

    def sub_val_form_new_pd(self, db_input):
        pd = PointData(self.id, self.lon, self.lat, self.val)
        pd.sub_val(db_input)
        return pd

    def multi_val_form_new_pd(self, db_input):
        pd = PointData(self.id, self.lon, self.lat, self.val)
        pd.multi_val(db_input)
        return pd

    def div_val_form_new_pd(self, db_input):
        pd = PointData(self.id, self.lon, self.lat, self.val)
        pd.div_val(db_input)
        return pd

    def is_same_point(self, pd_input):
        num = 0
        if abs(pd_input.lon - self.lon) >= 0.0001:
            num += 1
        if abs(pd_input.lat - self.lat) >= 0.0001:
            num += 1
        if num > 0:
            return False
        return True

    def interplot_from_grid_data(self, gd_input, db_undef=0.0):
        num = int((self.lon + 1e-05 - gd_input.lon_start) / gd_input.lon_interval)
        num2 = int((self.lat + 1e-05 - gd_input.lat_start) / gd_input.lat_interval)
        if 0 <= num < gd_input.xn - 1 and 0 <= num2 < gd_input.yn - 1:
            num3 = (float(gd_input.val[num2, num]) * (gd_input.lon[num + 1] - self.lon) +
                    float(gd_input.val[num2, num + 1]) * (self.lon - gd_input.lon[num])) / gd_input.lon_interval
            num4 = (float(gd_input.val[num2 + 1, num]) * (gd_input.lon[num + 1] - self.lon) +
                    float(gd_input.val[num2 + 1, num + 1]) * (self.lon - gd_input.lon[num])) / gd_input.lon_interval
            num5 = (num3 * (gd_input.lat[num2 + 1] - self.lat) +
                    num4 * (self.lat - gd_input.lat[num2])) / gd_input.lat_interval
            self.val = num5
        else:
            self.val = db_undef

    def nearest_from_grid_data(self, gd_input, db_undef=0.0):
        num = int(round((self.lon + 1e-05 - gd_input.lon_start) / gd_input.lon_interval))
        num2 = int(round((self.lat + 1e-05 - gd_input.lat_start) / gd_input.lat_interval))
        if 0 <= num < gd_input.xn - 1 and 0 <= num2 < gd_input.yn - 1:
            self.val = float(gd_input.val[num2, num])
        else:
            self.val = db_undef

    def select_from_scatter_data(self, sd_input, db_undef=0.0):
        num = 0
        for pd in sd_input.sta_data:
            if pd.id == self.id:
                self.val = pd.val
                num = 1
                break
        if num == 0:
            self.val = db_undef

    def get_line_distance_in_angle(self, pd_input):
        num = pd_input.lon - self.lon
        num2 = pd_input.lat - self.lat
        return math.sqrt(num * num + num2 * num2)

    def get_line_distance_in_meter(self, pd_input):
        num = 6371.3 * math.cos(math.pi * self.lat / 180.0) * math.cos(math.pi * self.lon / 180.0)
        num2 = 6371.3 * math.cos(math.pi * self.lat / 180.0) * math.sin(math.pi * self.lon / 180.0)
        num3 = 6371.3 * math.sin(math.pi * self.lat / 180.0)
        num4 = 6371.3 * math.cos(math.pi * pd_input.lat / 180.0) * math.cos(math.pi * pd_input.lon / 180.0)
        num5 = 6371.3 * math.cos(math.pi * pd_input.lat / 180.0) * math.sin(math.pi * pd_input.lon / 180.0)
        num6 = 6371.3 * math.sin(math.pi * pd_input.lat / 180.0)
        return math.sqrt((num - num4) ** 2 + (num2 - num5) ** 2 + (num3 - num6) ** 2)

    def get_rad_distance_in_meter(self, pd_input):
        R = 6371.4
        x1 = R * math.cos(math.pi * self.lat / 180.0) * math.cos(math.pi * self.lon / 180.0)
        y1 = R * math.cos(math.pi * self.lat / 180.0) * math.sin(math.pi * self.lon / 180.0)
        z1 = R * math.sin(math.pi * self.lat / 180.0)
        x2 = R * math.cos(math.pi * pd_input.lat / 180.0) * math.cos(math.pi * pd_input.lon / 180.0)
        y2 = R * math.cos(math.pi * pd_input.lat / 180.0) * math.sin(math.pi * pd_input.lon / 180.0)
        z2 = R * math.sin(math.pi * pd_input.lat / 180.0)
        d = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2)
        d /= 2.0
        return 2.0 * math.asin(d / R) * R

    def get_rad_distance_in_angle(self, pd_input):
        R = 6371.4
        x1 = R * math.cos(math.pi * self.lat / 180.0) * math.cos(math.pi * self.lon / 180.0)
        y1 = R * math.cos(math.pi * self.lat / 180.0) * math.sin(math.pi * self.lon / 180.0)
        z1 = R * math.sin(math.pi * self.lat / 180.0)
        x2 = R * math.cos(math.pi * pd_input.lat / 180.0) * math.cos(math.pi * pd_input.lon / 180.0)
        y2 = R * math.cos(math.pi * pd_input.lat / 180.0) * math.sin(math.pi * pd_input.lon / 180.0)
        z2 = R * math.sin(math.pi * pd_input.lat / 180.0)
        d = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2)
        d /= 2.0
        return 2.0 * math.asin(d / R) * 180.0 / math.pi

    def is_in_line(self, ld_data):
        num = ld_data.point_num - 1
        flag = False
        for i in range(ld_data.point_num):
            if (((ld_data.point_lat[i] < self.lat and ld_data.point_lat[num] >= self.lat) or
                 (ld_data.point_lat[num] < self.lat and ld_data.point_lat[i] >= self.lat)) and
                (ld_data.point_lon[i] <= self.lon or ld_data.point_lon[num] <= self.lon) and
                ld_data.point_lon[i] + (self.lat - ld_data.point_lat[i]) /
                (ld_data.point_lat[num] - ld_data.point_lat[i]) *
                (ld_data.point_lon[num] - ld_data.point_lon[i]) < self.lon):
                flag = not flag
            num = i
        return flag

    def is_in_line_v2(self, ld_data):
        num = 0
        num2 = 0
        num3 = ld_data.point_num - 1
        while num2 < ld_data.point_num:
            if (ld_data.point_lat[num2] > self.lat) != (ld_data.point_lat[num3] > self.lat) and \
               self.lon < (ld_data.point_lon[num3] - ld_data.point_lon[num2]) * \
               (self.lat - ld_data.point_lat[num2]) / \
               (ld_data.point_lat[num3] - ld_data.point_lat[num2]) + ld_data.point_lon[num2]:
                num = 1 + num
            num3 = num2
            num2 += 1
        if num % 2 == 0:
            return False
        return True

    def __str__(self):
        return f"id:{self.id}, lon:{self.lon:8.3f}, lat:{self.lat:8.3f}, value:{self.val:8.3f}"

    def __repr__(self):
        return self.__str__()
