from fy4_batch_latlon_channel_plugin import FY4BatchLatLonChannelPlugin


plugin = FY4BatchLatLonChannelPlugin(
    input_root="/mnt/data_229/SatelliteData/fy4b_l1",
    output_root="/mnt/data_229/SatelliteData/fy4b_channel_latlon",
    start_time="2023010406",
    end_time="2023010423",
    resolution=0.04,
    lat_min=-60,
    lat_max=60,
    lon_half_width=75,
    channels="1-15",
    resampling="bilinear",
    centers=("1050E", "1330E"),
    overwrite=False,
    recursive=False,
)

plugin.process()
