################################################################
Python自适应集成降水算法24h说明
创建者：郝书剑
编辑时间： 2023/09/04
################################################################


项目描述：
    本项目为从107服务器实时运行的反编译的Mait24小时的Python版本，输出结果应与服务器版本几乎一致。


项目文件结构:
    - mait_24_cli.py(主程序)
    - mait_24_plugin_new.py
        - [数据类相关]
    - mait_24_plugin_util.py
        - [数据函数相关]

    - src/
        - util_new.py
            - [数据处理相关]
    - para/
        - para_24.ini
            - [mait24数据路径配置文件]

如何运行:
    1. 从服务器拷贝相关文件夹和文件至项目根目录：
        - info/
            - mask010.dat
            - station_info.txt  (站点信息)
        - para/
            - para_24.ini    (mait24模式及权重数据读取和存储位置)
        - beta_24h/ (mait24历史权重信息，程序可不依托历史权重运行)
            - YYYYMMDDHH
                -*_VVV.info （历史权重，VVV为预报时效）
        
        注：历史权重最多会读取

    2. 修改para/para_*.ini中所有数据读写路径，其中*Model为模式数据路径，fact为站点实况路径，staoutputPath为本项目结果输出路径，YYYYMMDDHH.VVV为目标路径名格式，YYYY为四位年，MMDDHH为两位月日时，VVV为三位预报时效（可根据目标文件名格式更改）
    
    3. 运行主程序


示例用法:
    
1. 导入nimm库以及程序处理类，如mait_24_cli

        import sys
        sys.path.insert(0,'.../nimm')
        from nimm.mait import mait_24_cli
   
2. 运行Process：

       1. 过往时刻抓取：程序会抓取输入时刻作为运行时刻
       mait_24_cli.process(time_input='202401010800')

       2. 分区域做评分与权重计算融合（示例：2*2=4个区域）
       mait_24_cli.process(split_lat=2, split_lon=2)

       3. para文件路径配置，若无则选取对应时间的/para/para_x.ini
       mait_24_cli.process(time_input='202401010800',para_path='xxx/xxxx/para.ini')

       4. beta输出目录配置，生成对应YYYYMMDDHH/x.info文件，若无则输出至mait根目录下
       mait_24_cli.process(time_input='202401010800',beta_path='xxx/xxxx/')

       5. 实况数据世界时和北京时可选项,is_obs_bjt(默认False)
       mait_24_cli.process(time_input='202401010800',is_obs_bjt=True)

       6. 生成的格点数据是否插值的可选性,is_interp(默认False)
       mait_24_cli.process(time_input='202401010800',is_interp=True)

       7. 生成的数据裁剪的范围和分辨率的可选性,clip_coords(默认不裁切)
       mait_24_cli.process(time_input='202401010800',clip_coords=[70.0, 140.0, 0.0, 60.0, 0.1, 0.1])

       8. 程序分几个进程来运行,pro_count(默认为3个进程)
       mait_24_cli.process(time_input='202401010800',pro_count=3)

3. 调用实例
        
    ~~~python
    # -*- coding: UTF-8 -*-
    import pandas as pd
    import mait_24h_cli

    time_start_str, time_end_str = '20250715000000','20250901000000'
    date_str_list = pd.date_range(time_start_str, time_end_str, freq='D').strftime('%Y%m%d').to_list()
    dtimes = [36, 60, 84, 108, 132, 156, 180, 204, 228, 252]  # 时效列表
    para_path = r'./para/para_24.ini'  # 输入输出路径配置
    beta_path = r'./beta_24_split_2x2/YYYYMMDDHH'  # 转中保存目录
    is_obs_bjt = True  # 实况是世界时
    clip_coords = [70.0, 140.0, 0.0, 60.0, 0.1, 0.1]  # 精度与范围
    pro_count = 6  # 子进程数
    split_lat = 2  # 划分区域个数 竖向
    split_lon = 2  # 划分区域个数 横向
    for date_str in date_str_list:
        for hour_minute in ['0800','2000']:
            time_input = date_str + hour_minute # 传的时间为世界时
            keyword = {
                "time_input" : time_input,  # 计算时次
                "dtimes" : dtimes,  # 融合目标时效列表
                "para_path" : para_path,  # 配置文件路径
                "beta_path" : beta_path,  # 权重记录路径
                "is_obs_bjt" : is_obs_bjt,  # 实况是否北京时间
                "clip_coords" : clip_coords,  # 精度范围
                "pro_count" : pro_count,  # 多进程个数
                "split_lat" : split_lat,  # 分区个数
                "split_lon" : split_lon   # 分区个数
            }
            mait_24h_cli.process(**keyword)
    ~~~

贡献者:
- 郝书剑
- 赵如奇
- 杨宸源
    

