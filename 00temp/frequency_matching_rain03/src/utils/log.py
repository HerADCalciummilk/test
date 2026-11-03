import os
from datetime import datetime


class Log:
    def __init__(self, file_path):
        self.log_file_path = file_path
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'a', encoding='gb2312') as f:
                f.write(' \n')
                f.write(f"========={datetime.now().strftime('%Y%m%d%H%M%S')}=================\n")
        except Exception:
            pass

    def write_info(self, str_log_information, flag=0):
        try:
            with open(self.log_file_path, 'a', encoding='gb2312') as f:
                if flag == 0:
                    f.write("Log Info-----------------------------\n")
                    f.write(str_log_information + '\n')
                    f.write("-------------------------------------\n")
                else:
                    f.write("Log Info-----------------------------\n")
                    print(str_log_information)
                    f.write(str_log_information + '\n')
                    f.write("-------------------------------------\n")
        except Exception:
            pass

    def write_warn(self, str_log_warning, flag=0):
        try:
            with open(self.log_file_path, 'a', encoding='gb2312') as f:
                if flag == 0:
                    f.write("Log Warn-----------------------------\n")
                    f.write(str_log_warning + '\n')
                    f.write("-------------------------------------\n")
                else:
                    f.write("Log Warn-----------------------------\n")
                    print(str_log_warning)
                    f.write(str_log_warning + '\n')
                    f.write("-------------------------------------\n")
        except Exception:
            pass

    def write_error(self, str_log_error, flag=0):
        try:
            with open(self.log_file_path, 'a', encoding='gb2312') as f:
                if flag == 0:
                    f.write("Log Error----------------------------\n")
                    f.write(str_log_error + '\n')
                    f.write("-------------------------------------\n")
                else:
                    f.write("Log Error----------------------------\n")
                    print(str_log_error)
                    f.write(str_log_error + '\n')
                    f.write("-------------------------------------\n")
        except Exception:
            pass
