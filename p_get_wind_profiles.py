#import p_country_map as pcm
import pandas as pd
import numpy as np
import xarray as xr
import pvlib
import netCDF4 as nc
import matplotlib.pyplot as plt
import glob


class all_locations:
    # List of files and relevant information
    def __init__(self, path):
        self.variables = { '100m_u_component_of_wind': 'u100',
                          '100m_v_component_of_wind': 'v100', 'surface_solar_radiation_downwards': 'ssrd'} #'2m_temperature': 't2m', ,
                          #'model_bathymetry': 'wmb'
        self.path = path
        if path is None:
            self.file_list = glob.glob(
                r'/Users/lukehatton/Desktop/4YP/Model_for_Luke-main/Wales')
        else:
            self.file_list = glob.glob(path + r'/Model_for_Luke-main/*')
        #self.file_list = ['Test.nc']#Needs changing to required file
        print(self.file_list)
        for count, file in enumerate(self.file_list):
            if count == 0:
                self.ds = xr.open_dataset(file)
            elif file[-9:] == 'ential.nc':
                self.altitude = xr.open_dataset(file)
            else:
                self.ds = xr.merge([self.ds, xr.open_dataset(file)])


class get_renewables:
    def __init__(self, data):
        """Sets up the solar model"""
        __temperature_model_parameters = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS['sapm']['open_rack_glass_glass']
        self.__pvwatts_system = pvlib.pvsystem.PVSystem(module_parameters={'pdc0': 240, 'gamma_pdc': -0.004},
                                                        inverter_parameters={'pdc0': 240},
                                                        temperature_model_parameters=__temperature_model_parameters)

        self.data = data.ds
        #self.altitudes = data.altitude
        self.hourly_data = pd.to_datetime(self.data.time.values)

    def get_data(self, latitude, longitude):
        """Imports the data from the nc files and interprets them into wind and solar profiles"""
        ds = self.data
        self.latitude = latitude
        self.longitude = longitude
        #altitude = self.altitudes.z.loc[:, self.latitude, self.longitude].values[0] / 9.80665
        v100 = ds.v100.loc[:, self.latitude, self.longitude].values
        u100 = ds.u100.loc[:, self.latitude, self.longitude].values
        #t2m = ds.t2m.loc[:, self.latitude, self.longitude].values
        #ssrd = ds.ssrd.loc[:, self.latitude, self.longitude].values
        v10 = ds.v10.loc[:, self.latitude, self.longitude].values
        u10 = ds.u10.loc[:, self.latitude, self.longitude].values
        s10 = [(u ** 2 + v ** 2) ** 0.5 for u, v in zip(u10, v10)]
        v1 = np.array([s * np.log(1 / 0.03) / np.log(10 / 0.03) for s in s10])

        return [self.get_wind_power(v100, u100)] #self.get_solar_power(ssrd, t2m, v1, altitude),

    def get_wind_power(self, u100, v100):
        """Given u100 and v100 estimates wind power for a Vestas 3.0MW with a rotor diameter of 90m and a nacelle height of 80m
        Vestas is the most common wind turbine type on Australian wind farms"""
        measured_height = 100
        hub_height = 120
        rated = 3000  # installed capacity in kW
        cut_in = 3
        cut_out = 25
        power = []
        for u, v in zip(u100, v100):
            speed_measured = (u ** 2 + v ** 2) ** 0.5
            speed_hub = speed_measured * np.log(hub_height / 0.03) / np.log(measured_height / 0.03)
            if speed_hub < cut_in or speed_hub > cut_out:
                power.append(0)
            elif speed_hub < 7.5:
                power.append(2.785299 * speed_hub ** 3.161124 / rated)
            elif speed_hub < 11.5:
                power.append((-103.447526 * speed_hub ** 2 + 2319.060494 * speed_hub - 10004.69559) / rated)
            else:
                power.append(1)
        return np.array(power)

    def get_solar_power(self, ssrd, t2m, v1, altitude):
        """Uses PV_Lib to estimate solar power based on provided weather data"""
        """Note t2m to the function in Kelvin - function converts to degrees C!"""
        # Manipulate input data
        times = self.hourly_data.tz_localize('ETC/GMT')
        ssrd = pd.DataFrame(ssrd / 3600, index=times, columns=['ghi'])
        #t2m = pd.DataFrame(t2m - 273.15, index=times, columns=['temp_air'])
        v1 = pd.DataFrame(v1, index=times, columns=['wind_speed'])

        # Set up solar farm design
        mc_location = pvlib.location.Location(latitude=self.latitude, longitude=self.longitude, altitude=altitude,
                                              name='NA')
        solpos = pvlib.solarposition.pyephem(times, latitude=self.latitude, longitude=self.longitude, altitude=altitude,
                                             pressure=101325, temperature=t2m.mean(), horizon='+0:00')
        mc = pvlib.modelchain.ModelChain(self.__pvwatts_system, mc_location, aoi_model='physical',
                                         spectral_model='no_loss')

        # Get the diffuse normal irradiance (dni) and diffuse horizontal irradiance (dhi) from the data; hence create a weather dataframe
        df_res = pd.concat([ssrd, t2m, v1, solpos['zenith']], axis=1)
        df_res['dni'] = pd.Series([pvlib.irradiance.disc(ghi, zen, i)['dni'] for ghi, zen, i in
                                   zip(df_res['ghi'], df_res['zenith'], df_res.index)], index=times).astype(float)
        df_res['dhi'] = df_res['ghi'] - df_res['dni'] * np.cos(np.radians(df_res['zenith']))
        weather = df_res.drop('zenith', axis=1)
        dc_power = mc.run_model(weather).dc / 240
        return np.array(dc_power)


data = all_locations(None)
get_renewables_class = get_renewables(data)
#Adjust for long/latitude for the data
lon_range = np.arange(3.5,4.5)
lat_range = np.arange(53.5,54.5)

#Solar = np.zeros((len(get_renewables_class.hourly_data), len(lat_range), len(lon_range)))
Wind = np.zeros((len(get_renewables_class.hourly_data), len(lat_range), len(lon_range)))

for count_lat, lat in enumerate(lat_range):
    #print(lat)
    for count_lon, lon in enumerate(lon_range):
        #print(lon)
        location_data = get_renewables_class.get_data(lat, lon)
        #Solar[:, count_lat, count_lon] = location_data[0]
        Wind[:, count_lat, count_lon] = location_data[0] #[1]

#ds = xr.Dataset(data_vars={'Solar': (['time', 'latitude', 'longitude'], Solar)}, coords=dict(
    #latitude=(['latitude'], lat_range.tolist()), longitude=(['longitude'], lon_range.tolist()),
    #time=(['time'], get_renewables_class.hourly_data)), )

#ds.to_netcdf('Solar2.nc', mode='w')

ds2 = xr.Dataset(data_vars={'Wind': (['time', 'latitude', 'longitude'], Wind)}, coords=dict(
    latitude=(['latitude'], lat_range.tolist()), longitude=(['longitude'], lon_range.tolist()),
    time=(['time'], get_renewables_class.hourly_data)), )

ds2.to_netcdf('WindWales.nc', mode='w')
print(ds2)
