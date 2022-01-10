"""File to reduce long periods of renewable data down to its midoids, and then design an ammonia plant off it"""
# import p_renewable_auxiliary as aux
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
#import glob
import xarray as xr
#import pvlib
#import bisect
#from kneed import KneeLocator
#from shapely.geometry import Point




class renewable_data:
    # Data stored for a specific renewable location, including cluster information


    def __init__(self, weather_data, renewables, latitude =3.5 , longitude =53.5, years_of_interest = None, aggregation_variable = 1, aggregation_mode = None):
        """Initialises the data class by importing the relevant file, loading the data, and finding the location.
        Reshapes the data.
        Note that df refers to just the data for the specific location as an xarray; not the data for all locations."""

        #self.longitude = weather_data[weather_data.find('_')+1:weather_data.find('_', weather_data.find('_')+1)]
        #self.latitude = weather_data[0:weather_data.find('_')]

        self.latitude = latitude
        self.longitude = longitude
        self.aggregation_variable = aggregation_variable
        self.aggregation_mode = aggregation_mode
        #self.concat = pd.read_csv(weather_data)
        self.get_data_from_nc(weather_data)
        print('The plant is at latitude {latitude} and longitude {longitude}'.format(
            latitude = self.latitude, longitude = self.longitude))
        self.total_days = len(self.hourly_data)//24
        self.grid_on = False #Luke - you won't be using grid data so keep this as false
        # Extract the relevant profile
        self.renewables = renewables
        self.set_years()

    def to_csv(self):
        """Sends output weather data to a csv file - not typically called"""
        output_file_name = '{a}_{b}_renewable_energy data.csv'.format(a = self.latitude, b = self.longitude)
        self.concat.to_csv(output_file_name)
            
    def set_years(self, years_of_interest = None, aggregation_mode = None):
        """Initialises or re-initialises the data, then selects only the years you want, and trims them if apropriate - Luke you shouldn't need this if you import the data straight from a csv"""
        self.get_data_as_list()
        self.trim_years(years_of_interest)
        
        if aggregation_mode == 'optimal_cluster':
            self.consecutive_temporal_cluster(self.aggregation_variable)
        else:
            self.aggregate(self.aggregation_variable)


        
    def get_data_from_nc(self,weather_data):
        """Imports only the weather data for years in which grid data is available - Luke this should not be used in your model"""
        self.data={}
        self.data['Solar'] = weather_data.Wind.loc[:, self.latitude, self.longitude].values*0
        self.data['Wind'] = weather_data.Wind.loc[:, self.latitude, self.longitude].values
        self.hourly_data = pd.to_datetime(weather_data.time.values)

    def get_longitude(self, longitude):
            self.longitude = input("Longitude of Site: ")

    def get_latitude(self, latitude):
            self.latitude = input("Latitude of Site: ")

        
    def correct_start_time(self, source, start_time):
        """Corrects the start time of the data so that the grid and renewable start times match each other - Luke you shouldn't need to use this function"""       
        direct_output = self.data[source]
        # Move the last few values to the front so that we start at midnight
        if start_time > 0:
            edited_output = np.append(direct_output[-start_time:],
                                      direct_output[:np.shape(direct_output)[0] - start_time], axis=0)
        else:
            edited_output = np.array(direct_output)
        return edited_output
        
    def get_data_as_list(self):
        """Extracts the data required and stores it in lists by hour - Luke you shouldn't need this if you're importing data straight from a csv"""
        df = pd.DataFrame()
        for source in self.renewables:
            edited_output = self.correct_start_time(source, 10) #Be careful here
            df[source] = edited_output    
        if self.grid_on:
            grid_data = pd.read_csv(self.path + "//Grid_data//" + self.wire_state + '.csv')
            grid_data = grid_data['RRP'][0:len(self.data['Solar'])].to_numpy()
            df['Grid'] = grid_data
            df['Normalised Grid'] = 1-grid_data/max(grid_data)

        self.concat = df
        self.years_list()
        
    def trim_years(self, years_of_interest):
        """Trims the concatenated dataset to only include data from the years listed; fixes the years and dates data
        to match. Must be used BEFORE PCA or other analysis - Luke you shouldn't need this unless you're feeding the model several years of data but only want to do analysis on one of them"""
        if years_of_interest is not None:
            year_data = []
            years2 = []
            for year_of_interest in years_of_interest:
                start_row = bisect.bisect_left(self.years, year_of_interest)#+1992
                finish_row = bisect.bisect_right(self.years, year_of_interest)#-(8760-2500)
                year_data.append(self.concat.iloc[start_row:finish_row])
                years2 += self.years[start_row:finish_row]
            self.concat = year_data[0]
            headings = self.concat.columns
            self.years = years2

            for count, year_datum in enumerate(year_data):
                if count > 0:
                    self.concat = pd.DataFrame(np.append(self.concat, year_datum, axis=0))

            index = pd.Series(range(0, self.concat.shape[0]))
            self.concat = self.concat.set_index(index)
            self.concat.columns = headings
        self.total_days = len(self.concat)//24
        
    def aggregate(self, aggregation_count):
        """Aggregates self.concat into blocks of fixed numbers of size aggregation_count. aggregation_count must be an integer which is a factor of 24 (i.e. 1, 2, 3, 4, 6, 12, 24)"""
        """To be corrected to work without days/clusters - Luke you shouldn't need to use this unless you decide to further aggregate your weather data"""
        if self.concat.shape[0]%aggregation_count != 0:
            raise TypeError("Aggregation counter must divide evenly into the total number of data points")
        
        self.concat['Weights'] = np.ones(self.concat.shape[0]).tolist()
        for i in range(0, self.concat.shape[0]//aggregation_count): 
            keep_index = i*aggregation_count
            for j in range(1, aggregation_count):
                drop_index = keep_index+j
                self.concat.loc[keep_index] += self.concat.loc[drop_index]
                self.concat.drop(drop_index, inplace = True) 
        if self.grid_on:
            self.concat.drop(columns = ['Normalised Grid'], inplace = True)
            
    def consecutive_temporal_cluster(self, data_reduction_factor):
        """Reduces the data size by clustering adjacent hours until it has reduced in size by data_reduction_factor - Luke you shouldn't need to use this unless you decide to further aggregate your weather data"""
        
        if data_reduction_factor<1:
            raise TypeError("Data reduction factor must be greater than 1")
        
        self.concat['Weights'] = np.ones(self.concat.shape[0]).tolist()
        columns_to_sum = ['Solar', 'Wind']
        if self.grid_on:
            columns_to_sum.append('Normalised Grid')
            
        proximity = []
        for row in range(self.concat.shape[0]):
            if row < self.concat.shape[0]-1:
                differences = sum(abs(self.concat[element].iloc[row] - self.concat[element].iloc[row+1]) for element in columns_to_sum)
                proximity.append(2*differences*self.concat['Weights'].iloc[row]*self.concat['Weights'].iloc[row+1]\
                /(self.concat['Weights'].iloc[row] + self.concat['Weights'].iloc[row+1]))
        proximity.append(1E6)            
        self.concat['Proximity'] = proximity
        
        target_size = self.concat.shape[0]//data_reduction_factor
        while self.concat.shape[0] > target_size:
            keep_index = self.concat['Proximity'].idxmin()
            i_keep_index = self.concat.index.get_indexer([keep_index])[0]
            drop_index = self.concat.index.values[i_keep_index+1]
            self.concat.loc[keep_index] += self.concat.loc[drop_index]
            self.concat.drop(drop_index, inplace = True)
            if i_keep_index+1 < len(self.concat):
                differences = sum(abs(self.concat[element].iloc[i_keep_index]/self.concat['Weights'].iloc[i_keep_index]\
                                            - self.concat[element].iloc[i_keep_index+1]/self.concat['Weights'].iloc[i_keep_index+1])\
                                            for element in columns_to_sum)
                self.concat['Proximity'].iloc[i_keep_index] = 2*differences*self.concat['Weights'].iloc[i_keep_index]\
                                                                *self.concat['Weights'].iloc[i_keep_index+1]\
                                                /(self.concat['Weights'].iloc[i_keep_index] + self.concat['Weights'].iloc[i_keep_index+1])
        if self.grid_on:
            self.concat.drop(columns = ['Proximity', 'Normalised Grid'], inplace = True)
        else:
            self.concat.drop(columns = ['Proximity'], inplace = True)
        
    def years_list(self):
        """Creates a list of cells matching the date, that contains only their year"""
        self.years = []
        for row in range(self.concat.shape[0]):
            self.years.append(self.hourly_data[row].year)


