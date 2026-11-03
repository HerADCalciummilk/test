# -*- coding: utf-8 -*-
"""
性能测试脚本：测试优化后的全流程各阶段耗时
对比优化前基线：load=70.2s, identify=0.9s, select=36.8s, judge=19.8s, encode=8.8s, total=136.5s
"""
import time
import sys
import os
import logging

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)

from src.utils.data_loader import load_segment
from src.identifier import identify
from src.selector import select
from src.logic_judger import judge
from src.encoder import encode

init_time = "2026030100"
seg_idx = 1

print(f"{'=' * 60}")
print(f"全流程性能测试（int8索引优化后）")
print(f"起报时次: {init_time}, 时段: seg={seg_idx}")
print(f"{'=' * 60}")

# Step 1: load_segment
t0 = time.perf_counter()
data_dict, shape, lat_arr, lon_arr = load_segment(init_time, seg_idx)
t1 = time.perf_counter()
t_load = t1 - t0
print(f"\n[1] load_segment : {t_load:.3f}s")

if shape is None:
    print("数据缺失，无法继续测试")
    sys.exit(1)

# Step 2: identify
t0 = time.perf_counter()
occur = identify(data_dict)
t1 = time.perf_counter()
t_identify = t1 - t0
print(f"[2] identify     : {t_identify:.3f}s")

# Step 3: select
t0 = time.perf_counter()
idx_A, idx_B = select(occur)
t1 = time.perf_counter()
t_select = t1 - t0
print(f"[3] select       : {t_select:.3f}s")

# Step 4: judge
t0 = time.perf_counter()
logic, idx_final_A, idx_final_B = judge(idx_A, idx_B, occur)
t1 = time.perf_counter()
t_judge = t1 - t0
print(f"[4] judge        : {t_judge:.3f}s")

# Step 5: encode
t0 = time.perf_counter()
result = encode(idx_final_A, idx_final_B, logic)
t1 = time.perf_counter()
t_encode = t1 - t0
print(f"[5] encode       : {t_encode:.3f}s")

# 汇总
total = t_load + t_identify + t_select + t_judge + t_encode
print(f"\n{'=' * 60}")
print(f"{'阶段':<14} {'耗时(s)':<10} {'占比':<8} {'优化前(s)':<12} {'加速比'}")
print(f"{'-' * 60}")

baseline = {"load": 70.227, "identify": 0.944, "select": 36.778, "judge": 19.780, "encode": 8.783}
stages = [
    ("load_segment", t_load, baseline["load"]),
    ("identify", t_identify, baseline["identify"]),
    ("select", t_select, baseline["select"]),
    ("judge", t_judge, baseline["judge"]),
    ("encode", t_encode, baseline["encode"]),
]
for name, t, old in stages:
    pct = t / total * 100
    speedup = old / t if t > 0.001 else float('inf')
    print(f"  {name:<12} {t:<10.3f} {pct:>5.1f}%    {old:<12.3f} {speedup:.1f}x")

total_old = sum(baseline.values())
print(f"{'-' * 60}")
print(f"  {'总计':<12} {total:<10.3f} {'100%':<8} {total_old:<12.3f} {total_old/total:.1f}x")
print(f"{'=' * 60}")
