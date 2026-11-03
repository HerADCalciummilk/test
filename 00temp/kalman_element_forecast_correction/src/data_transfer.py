"""Copy ECMWF soil fields into the Kalman process-data layout."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class TransferConfig:
    """Data copy configuration."""

    source_bases: dict[str, str]
    target_base: str
    level_mapping: dict[str, str]


DEFAULT_TRANSFER_CONFIG = TransferConfig(
    source_bases={
        "SWVL": "/data/mnt/model_RT/globalECMWF_D1D/SWVL",
        "STL": "/data/mnt/model_RT/globalECMWF_D1D/STL",
    },
    target_base="/data234/GUO_data/Kalman_data/process_data",
    level_mapping={
        "0-7": "5",
        "7-28": "10",
        "28-100": "40",
        "100-MISSING": "100",
    },
)


def copy_process_data(
    run_date: datetime | None = None,
    *,
    config: TransferConfig = DEFAULT_TRANSFER_CONFIG,
) -> int:
    """Copy one day of SWVL/STL nc files into the process-data directory."""
    today = datetime.now()
    if run_date is None:
        run_date = today - timedelta(days=1)

    date_str = run_date.strftime("%Y%m%d")
    year_str = run_date.strftime("%Y")
    print(f"当前系统时间：{today:%Y-%m-%d %H:%M:%S}")
    print(f"复制日期：{date_str}")
    print(f"目标根目录：{config.target_base}\n")

    total_copied = 0
    for var_name, source_base in config.source_bases.items():
        print(f"开始处理变量：{var_name}")
        var_target_base = Path(config.target_base) / var_name

        for old_level, new_level in config.level_mapping.items():
            source_dir = Path(source_base) / old_level / year_str / date_str
            print(f"  处理层级：{old_level} -> {new_level}")

            if not source_dir.exists():
                print(f"    源目录不存在：{source_dir}\n")
                continue

            target_dir = var_target_base / new_level / year_str / date_str
            target_dir.mkdir(parents=True, exist_ok=True)

            copied_count = 0
            for source_file in source_dir.iterdir():
                if source_file.suffix != ".nc":
                    continue
                target_file = target_dir / source_file.name
                try:
                    shutil.copy2(source_file, target_file)
                    print(f"    已复制 {source_file.name}")
                    copied_count += 1
                    total_copied += 1
                except Exception as err:
                    print(f"    复制失败 {source_file.name}: {err}")

            print(f"    本层级复制文件数：{copied_count}\n")

        print(f"变量处理完成：{var_name}\n")

    print(f"全部完成，共复制 {total_copied} 个文件")
    print(f"处理日期：{date_str}")
    return total_copied
