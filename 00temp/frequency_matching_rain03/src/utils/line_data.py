class LineData:
    def __init__(self, *args):
        if len(args) == 2:
            if isinstance(args[0], list) and isinstance(args[1], list):
                db_lon, db_lat = args
                if len(db_lon) != len(db_lat):
                    raise Exception("lon and lat is not the same!")
                self.point_num = len(db_lon)
                self.point_lon = list(db_lon)
                self.point_lat = list(db_lat)
                self.line_value = 0.0
            elif hasattr(args[0], '__len__') and hasattr(args[0][0], 'lon'):
                pd_data, db_line_value = args
                self.point_num = len(pd_data)
                self.point_lon = [pd.lon for pd in pd_data]
                self.point_lat = [pd.lat for pd in pd_data]
                self.line_value = db_line_value
            else:
                raise Exception("LineData: invalid arguments")
        elif len(args) == 1:
            if isinstance(args[0], int):
                pd_num = args[0]
                self.point_num = pd_num
                self.point_lon = [0.0 + 1.0 * i for i in range(pd_num)]
                self.point_lat = [0.0 + 1.0 * i for i in range(pd_num)]
                self.line_value = 0.0
            elif hasattr(args[0], '__len__') and hasattr(args[0][0], 'lon'):
                pd_data = args[0]
                self.point_num = len(pd_data)
                self.point_lon = [pd.lon for pd in pd_data]
                self.point_lat = [pd.lat for pd in pd_data]
                self.line_value = 0.0
        elif len(args) == 3:
            db_lon, db_lat, db_line_value = args
            if len(db_lon) != len(db_lat):
                raise Exception("lon and lat is not the same!")
            self.point_num = len(db_lon)
            self.point_lon = list(db_lon)
            self.point_lat = list(db_lat)
            self.line_value = db_line_value
        else:
            raise Exception("LineData: invalid arguments")

    def to_scatter_data(self):
        from utils.point_data import PointData
        from utils.scatter_data import ScatterData
        arr = [PointData(self.point_lon[i], self.point_lat[i], self.line_value)
               for i in range(self.point_num)]
        return ScatterData(arr)

    def to_point_data_array(self):
        from utils.point_data import PointData
        return [PointData(self.point_lon[i], self.point_lat[i], self.line_value)
                for i in range(self.point_num)]

    def copy_line_data(self):
        return LineData(list(self.point_lon), list(self.point_lat), self.line_value)

    def __str__(self):
        return f"lineNum:{self.point_num}, lineValue:{self.line_value:8.2f}"

    def repr_with_index(self, pt_index):
        if 0 <= pt_index < self.point_num:
            return f"lon:{self.point_lon[pt_index]:8.2f},lat:{self.point_lat[pt_index]:8.2f},lineValue:{self.line_value:8.2f}"
        raise Exception("index is not in the range proper")
