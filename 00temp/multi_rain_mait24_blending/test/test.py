import os

import meteva
import pandas as pd
import numpy as np
import meteva_base as meb
import meteva.product as mpd

import meteva.method as mem
import meteva.product as mpd

import datetime

import meteva_base as meb
import numpy as np
import matplotlib.pyplot as plt


map_extend = [113, 119.99, 36, 42.99]
axs = meb.creat_axs(3, map_extend, ncol=2, add_index=["观测", "EC", "MAIT"], wspace=1, add_minmap="right")
print(axs)