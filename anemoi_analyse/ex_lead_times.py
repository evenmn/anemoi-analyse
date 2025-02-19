from field_plotter import FieldPlotter

nc_file = "/pfs/lustrep3/scratch/project_465000454/anemoi/experiments/ni3_d_roll2_lr1e-6/inference/epoch_009/predictions/0/meps_240hfc_2023-08-15T00.nc"

fp = FieldPlotter(nc_file)
fp.plot(field='air_temperature_2m', lead_times=[0,12,24])
