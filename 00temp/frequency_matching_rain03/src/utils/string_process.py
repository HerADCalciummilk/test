from datetime import datetime


class StringProcess:
    """标题模板：把 ``YYYYMMDDHH`` / ``VVV`` 换成起报与时效。

    业务文件路径用 ``utils.io_meb.expand_data_path``（``meb.get_path``）。
    """
    @staticmethod
    def date_replace(input_data, dt_input=None, i_valid=0,
                     i_year=None, i_month=None, i_day=None, i_hour=None,
                     i_minute=None, i_second=None):
        """替换日期与时效占位符（``YYYY``/``MM``/``DD``/``HH``/``VVV`` 等）。"""
        if dt_input is not None and isinstance(dt_input, datetime):
            result = input_data
            result = result.replace("YYYY", f"{dt_input.year:04d}")
            result = result.replace("YY", f"{dt_input.year:04d}"[2:])
            result = result.replace("MM", f"{dt_input.month:02d}")
            result = result.replace("DD", f"{dt_input.day:02d}")
            result = result.replace("HH", f"{dt_input.hour:02d}")
            result = result.replace("NN", f"{dt_input.minute:02d}")
            result = result.replace("SS", f"{dt_input.second:02d}")
            result = result.replace("VVV", f"{i_valid:03d}")
            result = result.replace("VV", f"{i_valid:02d}")
            return result
        elif i_year is not None:
            result = input_data
            result = result.replace("YYYY", f"{i_year:04d}")
            result = result.replace("YY", f"{i_year:04d}"[2:])
            result = result.replace("MM", f"{i_month:02d}")
            result = result.replace("DD", f"{i_day:02d}")
            result = result.replace("HH", f"{i_hour:02d}")
            result = result.replace("VVV", f"{i_valid:03d}")
            result = result.replace("VV", f"{i_valid:02d}")
            if i_minute is not None:
                result = result.replace("NN", f"{i_minute:02d}")
            if i_second is not None:
                result = result.replace("SS", f"{i_second:02d}")
            return result
        raise ValueError("StringProcess.date_replace: invalid arguments")

    @staticmethod
    def write_str_to_txt(str_file_path, str_context):
        import os
        os.makedirs(os.path.dirname(str_file_path), exist_ok=True)
        with open(str_file_path, 'w', encoding='gb2312') as f:
            f.write(str_context)
