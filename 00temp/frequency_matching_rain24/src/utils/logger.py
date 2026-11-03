# -- coding: utf-8 --
import logging
import os
import datetime

log_colors_config = {
    "DEBUG": "cyan",
    "INFO": "white",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "red",
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

console_Bool = True

if console_Bool:
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] [%(funcName)s] - %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

# 本文件位于 src/utils/，项目根为其上两级
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
log_path = os.path.join(_repo_root, "log")

if not os.path.exists(log_path):
    os.makedirs(log_path)

time_str = datetime.datetime.now().strftime("%Y-%m-%d")
log_name = "{time}.log".format(time=time_str)

log_file_path = os.path.join(log_path, log_name)
log_handler = logging.FileHandler(log_file_path, encoding="utf-8")

file_formatter = "[%(asctime)s] [%(processName)s] [%(process)d] [%(levelname)s] [%(filename)s:%(lineno)d] [%(funcName)s] - %(message)s"

log_handler.setFormatter(logging.Formatter(file_formatter))
logger.addHandler(log_handler)
