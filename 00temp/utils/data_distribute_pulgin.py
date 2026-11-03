import meteva_base as meb
import numpy as np
import datetime
import shutil
import copy
import os


from utils.multipro_plugin import SimpleParallelTool

para_list_example = [
    {
        "input":r"O:\data\grid\GRAPES_GFS\APCP\YYYYMMDD\YYMMDDHH.TTT.nc",
        "output":r"L:\luoqi\GRAPES_GFS\APCP\YYYYMMDD\YYMMDDHH.TTT.nc",
        "start":datetime.datetime(2020,3,1,8,0),
        "end":datetime.datetime(2020,6,1,8,0),
        "hour_range":[8,21,12],
        "dh_range":[3,241,3],
        "recover":False
    },

    {
        "input": r"O:\data\grid\ECMWF_HR\APCP\YYYYMMDD\YYMMDDHH.TTT.nc",
        "output": r"L:\luoqi\ECMWF_HR\APCP\YYYYMMDD\YYMMDDHH.TTT.nc",
        "start": datetime.datetime(2020, 3, 1, 8, 0),
        "end": datetime.datetime(2020, 6, 1, 8, 0),
        "hour_range": [8, 21, 12],
        "dh_range": [3, 241, 3],
        "recover": False
    },

    {
        "input": r"O:\data\grid\NCEP_GFS_HR\APCP\YYYYMMDD\YYMMDDHH.TTT.nc",
        "output": r"L:\luoqi\NCEP_GFS_HR\APCP\YYYYMMDD\YYMMDDHH.TTT.nc",
        "start": datetime.datetime(2020, 3, 1, 8, 0),
        "end": datetime.datetime(2020, 6, 1, 8, 0),
        "hour_range": [8, 21, 12],
        "dh_range": [3, 241, 3],
        "recover": False
    },

    {
        "input": r"O:\data\grid\SHANGHAI_HR\APCP\YYYYMMDD\YYMMDDHH.TTT.nc",
        "output": r"L:\luoqi\SHANGHAI_HR\APCP\YYYYMMDD\YYMMDDHH.TTT.nc",
        "start": datetime.datetime(2020, 3, 1, 8, 0),
        "end": datetime.datetime(2020, 6, 1, 8, 0),
        "hour_range": [0, 24, 1],
        "dh_range": [0, 25, 1],
        "recover": False
    },

    {
        "input": r"O:\data\grid\GRAPES_MESO_HR\APCP\YYYYMMDD\YYMMDDHH.TTT.nc",
        "output": r"L:\luoqi\GRAPES_MESO_HR\APCP\YYYYMMDD\YYMMDDHH.TTT.nc",
        "start": datetime.datetime(2020, 3, 1, 8, 0),
        "end": datetime.datetime(2020, 6, 1, 8, 0),
        "hour_range": [2, 24, 3],
        "dh_range": [0, 85, 1],
        "recover": False
    },

    {
        "input": r"O:\data\grid\GRAPES_3KM\APCP\YYYYMMDD\YYMMDDHH.TTT.nc",
        "output": r"L:\luoqi\GRAPES_3KM\APCP\YYYYMMDD\YYMMDDHH.TTT.nc",
        "start": datetime.datetime(2020, 3, 1, 8, 0),
        "end": datetime.datetime(2020, 6, 1, 8, 0),
        "hour_range": [2, 24, 3],
        "dh_range": [0, 37, 1],
        "recover": False
    },

]


def copy_data_file(para_list):
    """
    复制指定时间范围内的数据文件，考虑特定的小时和dh值。
    此函数遍历指定时间范围内的每一天，然后对每个小时范围内的小时和每个dh范围内的dh值，
    将文件从输入路径复制到输出路径。
    参数
    ----------
    para_list : list of dict
        参数字典列表，每个字典包含：
        - start : datetime.datetime
            数据复制范围的开始时间
        - end : datetime.datetime
            数据复制范围的结束时间
        - hour_range : list of int
            小时范围，格式为 [开始小时, 结束小时, 步长]
        - dh_range : list of int
            DH范围，格式为 [开始dh, 结束dh, 步长]
        - recover : bool
            如果为True，覆盖现有文件；如果为False，仅在输出不存在时复制
        - input : str
            用于meb.get_path()的输入路径模式
        - output : str
            用于meb.get_path()的输出路径模式
    返回值
    -------
    None
    """
    # 遍历每个参数字典
    for para in para_list:
        # 获取开始时间
        time0 = para["start"]
        # 将时间调整到当天的0点0分
        time1 = datetime.datetime(time0.year, time0.month, time0.day, 0, 0)
        # 生成小时列表
        hour_list = np.arange(para["hour_range"][0], para["hour_range"][1], para["hour_range"][2]).tolist()
        # 生成dh值列表
        dh_list = np.arange(para["dh_range"][0], para["dh_range"][1], para["dh_range"][2]).tolist()
        # 获取是否覆盖现有文件的标志
        recover = para["recover"]

        # 遍历时间范围内的每一天
        while time1 <= para["end"]:
            # 遍历每个小时
            for hour in hour_list:
                # 计算当前处理时间
                time2 = time1 + datetime.timedelta(hours=hour)
                # 遍历每个dh值
                for dh in dh_list:
                    # 构建输出路径
                    path_out = meb.get_path(para["output"], time2, dh)
                    # 如果需要覆盖或输出文件不存在
                    if recover or not os.path.exists(path_out):
                        # 构建输入路径
                        path_in = meb.get_path(para["input"], time2, dh)
                        # 如果输入文件存在
                        if os.path.exists(path_in):
                            # 创建输出目录
                            meb.creat_path(path_out)
                            # 复制文件
                            shutil.copyfile(path_in, path_out)
            # 移动到下一天
            time1 = time1 + datetime.timedelta(hours=24)


def copy_file(**param):
    path_in = param["path"][0]
    path_out = param["path"][1]

    # 如果输入文件存在
    if os.path.exists(path_in):
        # 创建输出目录
        meb.creat_path(path_out)
        # 复制文件
        shutil.copyfile(path_in, path_out)

    return


def copy_data_file_multi(para_list, num_process=4):
    """
        复制指定时间范围内的数据文件，考虑特定的小时和dh值。
        此函数遍历指定时间范围内的每一天，然后对每个小时范围内的小时和每个dh范围内的dh值，
        将文件从输入路径复制到输出路径。
        参数
        ----------
        para_list : list of dict
            参数字典列表，每个字典包含：
            - start : datetime.datetime
                数据复制范围的开始时间
            - end : datetime.datetime
                数据复制范围的结束时间
            - hour_range : list of int
                小时范围，格式为 [开始小时, 结束小时, 步长]
            - dh_range : list of int
                DH范围，格式为 [开始dh, 结束dh, 步长]
            - recover : bool
                如果为True，覆盖现有文件；如果为False，仅在输出不存在时复制
            - input : str
                用于meb.get_path()的输入路径模式
            - output : str
                用于meb.get_path()的输出路径模式
        返回值
        -------
        None
        """

    t_files = []

    # 遍历每个参数字典
    for para in para_list:
        # 获取开始时间
        time0 = para["start"]
        # 将时间调整到当天的0点0分
        time1 = datetime.datetime(time0.year, time0.month, time0.day, 0, 0)
        # 生成小时列表
        hour_list = np.arange(para["hour_range"][0], para["hour_range"][1], para["hour_range"][2]).tolist()
        # 生成dh值列表
        dh_list = np.arange(para["dh_range"][0], para["dh_range"][1], para["dh_range"][2]).tolist()
        # 获取是否覆盖现有文件的标志
        recover = para["recover"]

        # 遍历时间范围内的每一天
        while time1 <= para["end"]:
            # 遍历每个小时
            for hour in hour_list:
                # 计算当前处理时间
                time2 = time1 + datetime.timedelta(hours=hour)
                # 遍历每个dh值
                for dh in dh_list:
                    # 构建输出路径
                    path_out = meb.get_path(para["output"], time2, dh)
                    # 如果需要覆盖或输出文件不存在
                    if recover or not os.path.exists(path_out):
                        # 构建输入路径
                        path_in = meb.get_path(para["input"], time2, dh)
                        # 拷贝
                        t_files.append([path_in, path_out])
            # 移动到下一天
            time1 = time1 + datetime.timedelta(hours=24)

    parallel_tool = SimpleParallelTool(
        target_func=copy_file,
        parallel_mode="sync",
        with_return=False,
        num_process=num_process,
    )
    times = {"path": [path for path in t_files]}
    results = parallel_tool.process(times)
    return results


def copy_during_data_file(root_in, root_out, start=None, end=None, recover=False):
    """
    复制指定时间范围内的文件。
    此函数从输入根目录中获取指定时间范围内的文件路径列表，
    然后将这些文件复制到输出根目录，保持相对路径结构不变。
    参数
    ----------
    root_in : str
        输入根目录路径
    root_out : str
        输出根目录路径
    start : datetime.datetime, optional
        开始时间，默认为 None
    end : datetime.datetime, optional
        结束时间，默认为 None
    recover : bool, optional
        如果为 True，覆盖现有文件；如果为 False，仅在输出文件不存在时复制，默认为 False
    返回值
    -------
    None
    """
    # 获取指定时间范围内的文件路径列表
    path_list = meb.path_tools.get_during_path_list_in_dir(root_in, None, start, end)

    # 遍历每个文件路径
    for path in path_list:
        # 构建输出路径（将输入路径中的 root_in 替换为 root_out）
        path_copy = path.replace(root_in, root_out)

        # 如果需要覆盖或输出文件不存在
        if not os.path.exists(path_copy) or recover:
            # 创建输出目录（如果不存在）
            meb.path_tools.creat_path(path_copy)
            # 复制文件
            shutil.copy(path, path_copy)


def copy_during_file(param):
    path = param["path"]
    root_in = param["root_in"]
    root_out = param["root_out"]
    recover = param["recover"]

    # 构建输出路径（将输入路径中的 root_in 替换为 root_out）
    path_copy = path.replace(root_in, root_out)

    # 如果需要覆盖或输出文件不存在
    if not os.path.exists(path_copy) or recover:
        # 创建输出目录（如果不存在）
        meb.path_tools.creat_path(path_copy)
        # 复制文件
        shutil.copy(path, path_copy)

    return


def copy_during_data_file_multi(root_in, root_out, start=None, end=None, recover=False, num_process=4):
    # 获取指定时间范围内的文件路径列表
    path_list = meb.path_tools.get_during_path_list_in_dir(root_in, None, start, end)

    parallel_tool = SimpleParallelTool(
        target_func=copy_during_file,
        parallel_mode="sync",
        with_return=False,
        num_process=num_process,
        fixed_params={"root_in": root_in, "root_out": root_out, "recover": recover}
    )
    times = {"path": [path for path in path_list]}
    results = parallel_tool.process(times)
    return results



if __name__ == '__main__':
    _para_list_example = [
        {
            "input": r"/mnt/245sm_qpf/test/ecModel/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "output": r"/data/python_code/mait_24h/plugin/coopy_files/ecModel/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "start": datetime.datetime(2025, 8, 1, 0, 0, 0),
            "end": datetime.datetime(2025, 8, 3, 0, 0, 0),
            "hour_range": [0, 12, 12],
            "dh_range": [36, 252, 24],
            "recover": False
        },

        {
            "input": r"/mnt/245sm_qpf/test/ncepModel/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "output": r"/data/python_code/mait_24h/plugin/coopy_files/ncepModel/YYYYMMDD/YYYYMMDDHH.TTT.m3",
            "start": datetime.datetime(2025, 8, 1, 0, 0, 0),
            "end": datetime.datetime(2025, 8, 3, 0, 0, 0),
            "hour_range": [0, 12, 12],
            "dh_range": [36, 252, 24],
            "recover": False
        },
    ]
    # copy_data_file(_para_list_example)
    copy_data_file_multi(_para_list_example)

