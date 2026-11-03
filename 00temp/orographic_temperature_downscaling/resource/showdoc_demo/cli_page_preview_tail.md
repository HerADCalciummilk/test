# 批量调度示例

在 `data/ec_t2m/` 下有待处理的 EC 气温数据；另备源地形、海陆掩码、目标 1 km 地形。下面用 `get_path_list_in_dir` 列出全部 nc，逐文件估 Γ → 插到 1 km → Apply。

```python
from pathlib import Path
import numpy as np
import meteva_base a