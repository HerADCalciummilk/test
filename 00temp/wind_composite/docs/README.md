# 风速风向合成（wind_composite）

由风的 u、v 分量计算合成风速与气象风向，输入输出均为 meb 标准网格数据。

## 算法说明

- **风速**：`speed = sqrt(u² + v²)`，低于静风阈值 0.3 m/s 的格点置 0，单位 m/s。
- **风向**：`dd = (270 - atan2(v, u) × 180/π) mod 360`，为风的来向，正北 0 度、顺时针增加，单位 degree。

输出网格沿用输入坐标，`member` 改写为 `wind_speed` / `wind_direction`，并补齐
`units`、`model_var`、`dtime_units`、`level_type`、`time_type`、`time_bounds` 六项属性。

## 调用示例

作为插件调用：

```python
from wind_composite import ComputeWindSpeed

speed = ComputeWindSpeed().process(u_grid, v_grid)
```

命令行处理测试数据：

```bash
python cli/run_wind_composite.py --u resource/sample_u.nc --v resource/sample_v.nc --out output
```

## 数据要求

u、v 分量需为同一时刻、同一层次、同一网格范围的 meb 六维网格
（`member`、`level`、`time`、`dtime`、`lat`、`lon`）。
