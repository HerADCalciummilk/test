from __future__ import annotations

from pathlib import Path
from datetime import datetime


class Log:
    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("a", encoding="gb2312", errors="ignore") as f:
            f.write(" \n")
            f.write(f"========={datetime.now():%Y%m%d%H%M%S}=================\n")

    def _write(self, level: str, message: str, echo: bool = False) -> None:
        with self.file_path.open("a", encoding="gb2312", errors="ignore") as f:
            f.write(f"{level}-----------------------------\n")
            f.write(message + "\n")
            f.write("-------------------------------------\n")
        if echo:
            print(message)

    def write_info(self, message: str, flag: int = 0) -> None:
        self._write("Log Info", message, flag != 0)

    def write_warn(self, message: str, flag: int = 0) -> None:
        self._write("Log Warn", message, flag != 0)

    def write_error(self, message: str, flag: int = 0) -> None:
        self._write("Log Error", message, flag != 0)
