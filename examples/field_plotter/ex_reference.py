from field_plotter import FieldPlotter

file_ref="/pfs/lustrep3/scratch/project_465000454/anemoi/datasets/MEPS/aifs-meps-2.5km-2020-2024-6h-v6.zarr", 

fp = FieldPlotter("field.nc", time='2023-08-15T00', model_label="NetCDF field")
fp.plot(field='air_temperature_2m', lead_times=4, file_ref=file_ref, ref_label="MEPS")
