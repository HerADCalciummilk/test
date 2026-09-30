# 风速合成结果快视（notebook 说明）

```python
import matplotlib.pyplot as plt
import meteva_base as meb

from wind_composite import ComputeWindSpeed

u = meb.read_griddata_from_nc("../resource/sample_u.nc", member_list=["ec"])
v = meb.read_griddata_from_nc("../resource/sample_v.nc", member_list=["ec"])
speed = ComputeWindSpeed().process(u, v)

speed.isel(member=0, level=0, time=0, dtime=0).plot(cmap="YlGnBu")
plt.title("10m 合成风速 (m/s)")
plt.show()
```
