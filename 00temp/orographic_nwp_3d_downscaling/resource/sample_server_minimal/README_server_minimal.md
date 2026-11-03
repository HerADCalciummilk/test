# Server minimal test layout

Copy these files on the server:

```bash
mkdir -p /home/nimm/test_g_interp_root/Parameter/EC
mkdir -p /home/nimm/test_g_interp_root/lib/terrain/EC_12P5KM
mkdir -p /home/nimm/test_g_interp_work/EC_12P5KM

cp sample_server_minimal/Fast_refine_interp_site.ini /home/nimm/test_g_interp_work/EC_12P5KM/
cp sample_server_minimal/Parameter/*.ini /home/nimm/test_g_interp_root/Parameter/
cp sample_server_minimal/Parameter/Station1 /home/nimm/test_g_interp_root/Parameter/
cp sample_server_minimal/Parameter/EC/EC_12P5KM_Info.ini /home/nimm/test_g_interp_root/Parameter/EC/
```

You still need terrain files:

```text
/home/nimm/test_g_interp_root/lib/terrain/EC_12P5KM/Terrain_12P5km.tif
/home/nimm/test_g_interp_root/lib/terrain/EC_12P5KM/Zoning_12P5km.tif  optional
```

Run from code directory:

```bash
cd /home/nimm/cli_code/g_interp
python runner/fast_refine_interp_runner.py
```
