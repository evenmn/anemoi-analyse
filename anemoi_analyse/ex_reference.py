from field_plotter import FieldPlotter

nc_file = "/pfs/lustrep3/scratch/project_465000454/anemoi/experiments/ni3_d_roll2_lr1e-6/inference/epoch_009/predictions/0/meps_240hfc_2023-08-15T00.nc"
file_ref="/pfs/lustrep3/scratch/project_465000454/anemoi/datasets/MEPS/aifs-meps-2.5km-2020-2024-6h-v6.zarr", 

fp = FieldPlotter(nc_file, time='2023-08-15T00')
fp.plot(field='air_temperature_2m', file_ref=file_ref)
