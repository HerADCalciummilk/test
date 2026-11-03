# -*- coding: utf-8 -*-
from utils.util_env import (
    get_resolved_paths,
    get_default_predict_valid_list,
    get_default_pro_count,
    get_default_is_multi,
    get_repo_root,
)
from pathlib import Path


def test_paths_under_repo():
    root = Path(get_repo_root())
    paths = get_resolved_paths()
    assert paths["para_ini"].startswith(str(root))
    para = paths["para_ini"].replace("\\", "/")
    bg = paths["background_ini"].replace("\\", "/")
    assert para.endswith("resource/para_3.ini")
    assert bg.endswith("resource/para_3_background.ini")
    assert paths["mask_dat"].endswith("mask010.dat") or "mask010" in paths["mask_dat"]


def test_default_valids_step3():
    vals = get_default_predict_valid_list()
    assert vals[0] == 3
    assert vals[-1] == 252
    assert all(v % 3 == 0 for v in vals)


def test_default_pro_count():
    assert get_default_pro_count() == 3


def test_default_is_multi():
    assert get_default_is_multi() is False
