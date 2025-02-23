from field_plotter import FieldPlotter

fp = FieldPlotter("field.nc", time='2023-08-15T00', model_label="NetCDF field")
fp.plot(field='air_temperature_2m', lead_times=[4,8,12])
