import cartopy.crs as ccrs
import datetime
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from tqdm import trange
import xarray as xr
import anemoi.datasets

from data import get_data, get_era5_data, read_era5
from utils import mesh, panel_config_auto, interpolate, plot
from map_keys import map_keys

plt.rcParams["font.family"] = "serif"


def panel_daemon(
        num_models: int, 
        num_lead_times: int, 
        ens_size: int, 
        plot_ens_mean: bool, 
        include_ref: bool, 
        swap_axes: bool = False,
    ) -> (tuple[int], tuple[int], tuple[int], tuple[int], tuple[int]):
    """Panel daemon that controls panel configuration.
    Striving for a square-horizontal layout, but a square-vertical
    layout can be invokes by setting swap_axes=True.

    Policy:
    - Can only plot two dimensions at the same time, meaning that
      either num_models, num_lead_times or num_members + plot_ens_mean
      has to be one.
    - If two of them are one, the dimensions is rearranged into 2d
      as close to square as possible, with a horizontal preference.
      Note that panels can be left empty if perfect rearrangement
      if not possible (e.g. in case of a prime number of panels)
    - If two dimensions, the shortest dimension will always be in
      vertical direction (usually in order model - lead time - ens).
    - Reference will never be appended to lead times direction,
      and then appended to the longest dimension of model and ens

    Args:
    - num_models: int
        number of models/paths
    - num_lead_times: int
        number of lead times to plot
    - num_members: int
        number of ensemble members to include
    - plot_ens_mean: bool
        plot ens mean true/false
    - include ref: bool
        include reference true/false
    - swap_axes: bool
        swap x- and y axis, making plot vertical

    Returns:
    - panel_shape: tuple[int]
        number of panels in x (horizontal) and y (vertical) directions
    - var_idx_xy: tuple[int]
        variable indices in x- and y-directions, 1d if only one variable
        0: model, 1: lead time, 2: ens
    - var_len_xy: tuple[int]
        variable lengths in x- and y-directions, 1d if only one variable
        in practice only used when only one variable and empty panel
    - ens_mean: tuple(int)
        Indicates which dimension or dimensions to put ens_mean
        (all ens_mean, x, y)
    - ref_dim: tuple(int)
        dimension to append reference along, (x, y)
    """
    if ens_size is None:
        # num_members can not be set (None) for two reasons:
        # 1. deterministic forecast, set num_members to 1
        # 2. plotting ensemble mean only, set num_members to 0
        if plot_ens_mean:
            ens_size = 0
        else:
            ens_size = 1

    # always append ens mean panel in ensemble dim
    num_members = ens_size + plot_ens_mean

    # assert correct dimensionalities
    var_len = np.array([num_models, num_lead_times, num_members])
    assert not 0 in var_len, "Cannot deal with zero dimension"
    assert 1 in var_len, "At least one dimension needs length 1"

    # check dimensionality
    active_var = var_len > 1  # which dimension has more than 1 element?
    num_vars = active_var.sum()  # number of dimensions longer than 1
    var_idx = np.argsort(var_len) # putting longest dimension last

    var_idx_xy = var_idx[-2:]  # dimension indices longer than 1 element
    var_len_xy = var_len[var_idx_xy]  # number of panels in each direction
    panel_shape = var_len_xy

    # ensemble mean position [only ens mean, x, y]
    ens_mean = [None, None, None]
    if plot_ens_mean:
        if var_idx_xy[0] == 2:
            ens_mean[1] = num_members-1
        elif var_idx_xy[1] == 2:
            ens_mean[2] = num_members-1
        else:
            ens_mean[0] = 0

    # reference position [x, y]
    ref = [None, None]
    if include_ref:
        # add ref along longest dim, but not lead times
        #ref_dim =  int(dim_len[1] > 1)  
        if var_idx_xy[0] != 1:
            ref_dim = 0
        else:
            ref_dim = 1
        ref[ref_dim] = panel_shape[ref_dim]
        panel_shape[ref_dim] += 1

    # rearrange to 2d if 1d
    if min(panel_shape) < 2:
        conf_map = [None,
                    (1,1), (1,2), (2,2), (2,2),
                    (2,3), (2,3), (2,4), (2,4),
                    (3,3), (3,4), (3,4), (3,4),
                    (4,4), (4,4), (4,4), (4,4),
                   ]
        panel_limit = len(conf_map) - 1

        if panel_shape[1] > panel_limit:
            raise ValueError(f"Panel limit reached!")
        
        if plot_ens_mean:
            ens_mean = conf_map[ens_mean[-1]]  # this is not correct, swap only the last two dims
        if include_ref:
            ref = conf_map[ref[-1]]
        var_idx_xy = var_idx_xy[1:]
        var_len_xy = panel_shape[1:]
        panel_shape = conf_map[panel_shape[-1]]

    if swap_axes:
        var_idx_xy = reversed(var_idx_xy)
        var_len_xy = reversed(var_len_xy)
        panel_shape = reversed(panel_shape)
        ref = reversed(ref)
        ens_mean = reversed(ens_mean) # this is not correct, swap only the last two dims
    
    return tuple(panel_shape), tuple(var_idx_xy), tuple(var_len_xy), tuple(ens_mean), tuple(ref)


def _plot_panel(
        ax: matplotlib.axes.Axes,
        data: np.array, 
        lat_grid: np.ndarray,
        lon_grid: np.ndarray,
        data_contour: np.ndarray = None,
        lat: np.ndarray = None,
        lon: np.ndarray = None,
        xlim: tuple[float] = None,
        ylim: tuple[float] = None,
        titlex: str = None,
        titley: str = None,
        resolution: float = None,
        **kwargs
    ) -> matplotlib.collections.QuadMesh:
    """Plot a single panel. Interpolate if necessary."""
    if data.ndim == 1:
        data = interpolate(data, lat, lon, resolution)

    if data_contour is not None:
        if data_contour.ndim == 1:
            data_contour = interpolate(data_contour, lat, lon, resolution)

    im = plot(ax, data, lon_grid, lat_grid, contour=data_contour, **kwargs)
    ax.set_title(titlex)
    ax.annotate(titley, (-0.2, 0.5), xycoords='axes fraction', rotation=90, va='center', fontsize=12)
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    return im


def _process_fig(
        fig: matplotlib.figure,
        axs: np.ndarray[matplotlib.axes.Axes],
        im: matplotlib.collections.QuadMesh,
        field: str,
        time: datetime.datetime,
        units: str, 
        path_out: str = None,
        show: bool = True,
    ) -> matplotlib.figure:
    """Add super title to figure, colorbar, potentially save and show figure.

    Return fig such that it can be used outside class
    """
    fig.suptitle(time.strftime('%Y-%m-%dT%H'))
    plt.tight_layout()
    cbax = fig.colorbar(im, ax=axs.ravel().tolist())
    cbax.set_label(f"{field} ({units})")
    if path_out is not None:
        plt.savefig(path_out)
    if show:
        plt.show()
    return fig

class FieldPlotter:
    """Plot ensemble field and potentially compare to ERA5."""
    def __init__(
            self,
            time: str or pd.Timestamp,
            path: str or list[str],
            members: int or list[int] = None,
            resolution: float = None,
            freq: str = '6h',
            file_prefix: str = "",
            model_labels: list[str] = None,
            xlim: tuple[float] = None,
            ylim: tuple[float] = None,
            latlon_units: str = 'deg',
        ) -> None:
        """
        Args:
            time: str or pd.Timestamp
                Specify a time stamps to be plotted
            path: str or list[str]
                Path to directory where files to be analysed are found.
                If several paths are provided, comparison mode is invoked
                (maybe add information about NetCDF format and folder structure?)
            ens_size: int
                Number of ensemble members to include, leave as None for deterministic models.
                (switch to member list to be able to choose members, in case some are corrupt)
            resolution: float
                Resolution in degrees used in interpolation. Using 1 for o96 and 0.25 for n320 by default.
            freq: str
                Frequency of lead times. Supports pandas offset alias: 
                https://pandas.pydata.org/docs/user_guide/timeseries.html#timeseries-offset-aliases
            file_prefix: str
                filenames prefix, to use if there are multiple files at same date
            model_labels: list[str]
                Labels associated with paths to be plotted as panel titles
            xlim: tuple[float]
                limit x-range of data. No limit by default
            ylim: tuple[float]
                limit y-range of data. No limit by default
        """
        self.members = np.atleast_1d(members)
        self.ens_size = len(self.members)
        self.resolution = resolution

        self.paths = np.atleast_1d(path)
        self.model_labels = model_labels
        if self.model_labels is not None:
            self.model_labels = np.atleast_1d(self.model_labels)
            assert len(self.model_labels) == len(self.paths), "Number of model labels must be equal to number of models" 

        if isinstance(time, str):
            time = pd.Timestamp(time)
        self.time = time
        self.freq = freq
        self.file_prefix = file_prefix

        self.xlim = xlim
        self.ylim = ylim

        if latlon_units == 'rad':
            rad = True
        elif latlon_units == 'deg':
            rad = False
        else:
            raise NotImplementedError(f"Unknown latlon_units '{latlon_units}'!")

        self.path_features = self._get_path_features(resolution, rad)

    def _get_path_features(
            self, 
            resolution: float,
            rad: bool = False,
        ) -> dict:
        """extract path-specific features.
        Returns a list with a dictionary for each path.

        TODO: more variables can be made path specific,
        for instance resolution could be given as a tuple.
        """
        path_features = []
        for path in self.paths:
            features = {}
            # get (ensemble) data
            ds = get_data(path, self.time, self.ens_size, self.file_prefix)
            features['ds'] = ds

            if resolution is None:
                resolution = 0.25 #if ds[field].shape[-1] == 542080 else 1
            features['resolution'] = resolution

            regular = False
            if ds.latitude.ndim==1:
                if self.xlim is not None and self.ylim is not None:
                    ds = ds.where(
                        (ds.latitude >= xlim[0]) &
                        (ds.latitude <= xlim[1]) &
                        (ds.longitude >= ylim[0]) &
                        (ds.longitude <= ylim[1]),
                        drop=True
                    )
                lon = np.array(ds.latitude)
                lat = np.array(ds.longitude)
                if rad:
                    lon = np.rad2deg(lon)
                    lat = np.rad2deg(lat)
                lat_grid, lon_grid = mesh(lat, lon, resolution) 
                features['lon'] = lon
                features['lat'] = lat
            elif ds.latitude.ndim==2:
                regular = True
                lat_grid, lon_grid = ds.y, ds.x #ds.latitude, ds.longitude
                lat_center = float(ds.latitude.max()+ds.latitude.min()) / 2.
                lon_center = float(ds.longitude.max()+ds.longitude.min()) / 2.
                features['lon_center'] = lon_center
                features['lat_center'] = lat_center
                features['lon'] = None
                features['lat'] = None
            else:
                raise ValueError
            features['regular'] = regular
            features['lat_grid'] = lat_grid
            features['lon_grid'] = lon_grid
            path_features.append(features)
        return path_features

    def _get_ref_features(
            self, 
            file_ref: str,
            pressure_contour: bool,
            ds: xr.open_dataset,
            regular: bool,
            resolution: float,
            rad: bool,
        ) -> (anemoi.datasets.open_dataset, xr.open_dataset, np.ndarray, np.ndarray):
        """Reference features."""
        fields = [self.field]
        if pressure_contour:
            fields.append('air_pressure_at_sea_level')
        max_lead_time = max(self.lead_times)+1
        ds_ref = read_era5(fields, file_ref, [self.time], max_lead_time, freq=self.freq)
        data_ref = get_era5_data(ds_ref, 0, fields, max_lead_time)
        if regular:
            y, x = ds.latitude.shape
            for key, value in data_ref.items():
                data_ref[key] = value.reshape(-1, y, x)
            lat_grid_ref = ds.y
            lon_grid_ref = ds.x
        else:
            lat_grid_ref, lon_grid_ref = mesh(ds_ref.latitudes, ds_ref.longitudes, resolution)

        if rad:
            lat_grid_ref = np.rad2deg(lat_grid_ref)
            lon_grid_ref = np.rad2deg(lon_grid_ref)
        return data_ref, ds_ref, lat_grid_ref, lon_grid_ref

    def plot(
            self,
            field: str, 
            lead_times: list[int] or int = 0,
            file_ref: str = None, 
            plot_ens_mean: bool = False,
            norm: bool = False,
            xlim: tuple[float] = None,
            ylim: tuple[float] = None,
            path_out: str = None,
            pressure_contour: bool = False,
            show: bool = True, 
            swap_axes: bool = False,
            ref_label: str = 'ref',
            ref_units: str = 'deg',
            **kwargs,
        ) -> (matplotlib.figure, np.ndarray[matplotlib.axes.Axes]):
        """
        Args:
            field: str
                Specify a field to be verified. Currently supports
                air_temperature_2m, wind_speed_10m, precipitation_amount_acc6, air_sea_level_pressure
            lead_times: list[int] or int
                One or multiple lead times to be plotted
            file_ref: str
                Reference file to be compared to. Not included by default.
            plot_ens_mean: bool
                Whether or not to plot ensemble mean.
            norm: bool
                Whether or not to normalize plots. In particular used with precipitation.
            xlim: tuple[float]
                xlim used in panels. No limit by default
            ylim: tuple[float]
                ylim used in panels. No limit by default
            path_out: str
                Path to where to save the image(s). If not given, images will not be saved
            pressure_contour: bool
                Whether or not to add pressure contour lines to field. Not added by default
            show: bool
                Whether or not to show plots
            swap_axes: bool
                Swap x- and y-axes to make plot vertical instead of horizontal
            ref_label: str
                Reference label to be printed as panel title
        """
        lead_times = np.atleast_1d(lead_times)
        self.field = field
        self.lead_times = lead_times

        units = map_keys[field]['units']

        if ref_units == 'rad':
            rad_ref = True
        elif ref_units == 'deg':
            rad_ref = False
        else:
            raise NotImplementedError(f"Unknown latlon_units '{latlon_units}'!")

        include_ref = False if file_ref is None else True
        if include_ref:
            data_ref, ds_ref, lat_grid_ref, lon_grid_ref = self._get_ref_features(file_ref, pressure_contour, self.path_features[0]['ds'], self.path_features[0]['regular'], self.resolution, rad_ref)

        # find vmin and vmax and add values to kwargs
        vmin = +np.inf
        vmax = -np.inf
        if include_ref:
            vmin = min(vmin, data_ref[field][lead_times].min())
            vmax = max(vmax, data_ref[field][lead_times].max())
        for path_idx, features in enumerate(self.path_features):
            ds = features['ds']
            vmin = min(vmin, float(ds[field][:,lead_times].min()))
            vmax = min(vmax, float(ds[field][:,lead_times].max()))
            cen = (vmax-vmin)/10.
            vmin += cen
            vmax -= cen
        if norm:
            boundaries = np.logspace(0.001, np.log10(vmax), cmap.N-1)
            boundaries = [0.0, 0.5, 1, 2, 4, 8, 16, 32]
            norm = matplotlib.colors.BoundaryNorm(boundaries, cmap.N, extend='both')
            kwargs['norm'] = norm
        else:
            kwargs['vmin'] = vmin
            kwargs['vmax'] = vmax
        kwargs['shading'] = 'auto'

        # define fig and axes
        regular = self.path_features[0]['regular'] # assume all panels have the same projection for now
        if regular:
            lon_center = self.path_features[0]['lon_center']
            lat_center = self.path_features[0]['lat_center']
            projection = ccrs.LambertConformal(lon_center, lat_center, standard_parallels=(lat_center, lat_center))
        else:
            projection = ccrs.PlateCarree()
        panel_shape, var_idx_xy, var_len_xy, ens_mean, ref_dim = panel_daemon(len(self.paths), len(self.lead_times), self.ens_size, plot_ens_mean, include_ref, swap_axes)
        fig, axs = plt.subplots(*panel_shape, figsize=(8,6), squeeze=False, subplot_kw={'projection': projection})
            
        def model_label(i):
            if self.model_labels is None:
                return f'model {i}'
            if i >= len(self.model_labels):
                return ""
            return self.model_labels[i]

        def lt_label(i):
            lead_time = 6 * lead_times[i]
            return f'+{lead_time}h'

        def member_label(i):
            member_id = self.members[i]
            return f'member {member_id}'
        labels = [model_label, lt_label, member_label]

        # mapping panel to correct data
        idx = [0,0,0] # model_idx, lt_idx, ens_idx

        # actual plotting
        for i in trange(panel_shape[0]):
            for j in range(panel_shape[1]):
                k = panel_shape[1] * i + j
                if len(var_idx_xy) == 1:
                    idx[var_idx_xy[0]] = k
                    if k >= var_len_xy[0]:
                        fig.delaxes(axs[i,j])
                        continue
                else:
                    idx[var_idx_xy[0]] = i
                    idx[var_idx_xy[1]] = j
                model_idx, lt_idx, ens_idx = idx
                if plot_ens_mean:
                    i_em, j_em = ens_mean
                    if (i_em is None or i==i_em) and (j_em is None or j==j_em):
                        data = ds[field][:, lt_idx].mean(axis=0)
                        data_pressure = ds['air_pressure_at_sea_level'][:, lt_idx].mean(axis=0) if pressure_contour else None
                        label_x = "ensemble mean" if i==0 else None
                        im = _plot_panel(axs[i,j], data, lat_grid, lon_grid, data_pressure, lat, lon, xlim, ylim, titlex=label_x, titley=label_y, resolution=resolution, **kwargs)
                        continue
                    
                if include_ref:
                    i_ref, j_ref = ref_dim
                    if (i_ref is None or i==i_ref) and (j_ref is None or j==j_ref):
                        data = data_ref[field][lt_idx]
                        data_pressure = data_ref['air_pressure_at_sea_level'][lt_idx] if pressure_contour else None
                        label_x = ref_label if i == 0 else None
                        label_y = ref_label if j == 0 else None
                        im = _plot_panel(axs[i,j], data, lat_grid_ref, lon_grid_ref, data_pressure, ds_ref.latitudes, ds_ref.longitudes, xlim, ylim, titlex=label_x, titley=label_y, resolution=resolution, **kwargs)
                        continue
                if len(var_idx_xy) == 1:
                    label_x = labels[var_idx_xy[0]](k)
                    label_y = None
                else:
                    label_x = labels[var_idx_xy[1]](j) if i == 0 else None
                    label_y = labels[var_idx_xy[0]](i) if j == 0 else None
                features = self.path_features[model_idx]
                ds = features['ds']
                resolution = features['resolution']
                regular = features['regular']
                lon = features['lon']
                lat = features['lat']
                lon_grid = features['lon_grid']
                lat_grid = features['lat_grid']

                data = ds[field][ens_idx, lt_idx]
                data_pressure = ds['air_pressure_at_sea_level'][ens_idx, lt_idx] if pressure_contour else None
                im = _plot_panel(axs[i,j], data, lat_grid, lon_grid, data_pressure, lat, lon, xlim, ylim, titlex=label_x, titley=label_y, resolution=resolution, **kwargs)
        fig = _process_fig(fig, axs, im, field, self.time, units, path_out, show)
        return fig, axs


if __name__ == "__main__":

    import matplotlib

    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("my_cmap", ["white", "white", "#3c78d8", "#00ffff", "#008800", "#ffff00", "red"])

    fp = FieldPlotter(
        #time="2022-06-29T00", 
        time="2023-08-15T00", 
        path=[
            #"/pfs/lustrep3/scratch/project_465000454/anemoi/experiments/ni3_c/inference/epoch_077_10mem_1year/predictions/", 
            #"/pfs/lustrep3/scratch/project_465000454/anemoi/experiments/ni3_c_kl/inference/epoch_076/predictions/", 
            #"/pfs/lustrep3/scratch/project_465000454/anemoi/experiments/ni3_c_kl_w1e-2/inference/epoch_076/predictions/", 
            #"/pfs/lustrep3/scratch/project_465000454/anemoi/experiments/ni3_c_kl_w1/inference/epoch_076/predictions/", 
            #"/pfs/lustrep3/scratch/project_465000454/anemoi/experiments/ni3_c_safcrps_k5_s1/inference/epoch_076/predictions/", 
            #"/pfs/lustrep3/scratch/project_465000454/anemoi/experiments/ni3_b_s0.1_mp/inference/epoch_030/predictions/",
            "/pfs/lustrep3/scratch/project_465000454/anemoi/experiments/ni3_d_roll2_lr5e-7/inference/epoch_009/predictions/",
            "/pfs/lustrep3/scratch/project_465000454/anemoi/experiments/ni3_d_roll2_lr1e-6/inference/epoch_009/predictions/",
        ],
        #model_labels = ['CRPS+KL\n'+r'$\lambda=10^{-4}$', 'CRPS+KL\n'+r'$\lambda=10^{-2}$', 'CRPS+KL\n'+r'$\lambda=1$'],
        #model_labels = ['CRPS', 'CRPS+CRPS(filter)'],
        #model_labels = ['5e-7', '1e-6'],
        members=0,
        #file_prefix="240hfc",
        #latlon_units='rad',
        #resolution=0.25,
    )

    fp.plot(
        field='precipitation_amount_acc6h', 
        lead_times=[0,4,8,12], #,16,20,24,28,32,36,40], 
        #pressure_contour=True,
        cmap=cmap, 
        norm=True,
        file_ref="/pfs/lustrep3/scratch/project_465000454/anemoi/datasets/MEPS/aifs-meps-2.5km-2020-2024-6h-v6.zarr", 
        #file_ref="/pfs/lustrep3/scratch/project_465000454/anemoi/datasets/ERA5/aifs-ea-an-oper-0001-mars-n320-1979-2022-6h-v6.zarr", 
        #xlim=(-4e5,0),
        #ylim=(-6e5,0),
        #xlim=(100,180),
        #ylim=(-11, 40),
        swap_axes=False,
        ref_label='MEPS',
    )
