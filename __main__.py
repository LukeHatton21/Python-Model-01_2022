import xarray
import p_location_class as location_class
import p_data_store as d_store
import p_driver as driver
import pandas as pd
import xarray as xr
import netCDF4 as nc
from netCDF4 import Dataset
import p_optimisation_designer as optimisation_designer
import time
from pathos.multiprocessing import ProcessPool
import os




def main():

    #Read netcdf file
    weather_input = input("Weather Data Filename: ")
    weather_file = "~/Desktop/4YP/Model_for_Luke-main/Equipment Data/" + weather_input
    weather_data = [xr.open_dataset(weather_file)]



    #Read .csv file
    #weather_data = ['52.99_0.68_renewable_energy data2021.csv']


    #Class for storing data
    stored_data = d_store.Data_store()
    
    #Modify this for scale adjustments
    Target_Productions = [1E6]
    if len(Target_Productions) ==1:
        Target_Production = Target_Productions[0]
    
    #Modify this to adjust the parallelism (i.e. how many cores in your computer are used)
    Processes = 3 #Higher number means more cores - but you will run into RAM limits so don't make it too high
    pool = ProcessPool(nodes=Processes)
    
    #Modify this to adjust any data aggregation you'd like to do
    aggregation_mode = 'aggregate'
    aggregation_variable = 1 #This aggregates the data on your behalf into smaller timesteps; Luke - I would leave set to 1

    #This builds sets of years over which the analysis will be done - #Luke - only modify this if you want to design using >1 year of data; I wouldn't to start.
    year_cases = []
    period = 1 #Number of years of analysis
    for year in range(2019, 2020, period):
        lst = [year+i for i in range(0,period)]
        year_cases.append(lst)
    if len(year_cases) ==1:
        design_years = year_cases[0]
    
    #Now, iterate over the relevant cases to do the optimisation
    for Target_Production in Target_Productions: #Here the model iterates over target productions, but you can change this to iterate over something else (e.g. A model input parameter)
        start_time = time.time()
        
        #Set up case
        optimal_design = optimisation_designer.location_optimise_design(Target_Production)
        stored_data.get_active_components(optimal_design)

        #Run case - goes through the driver to implement parallelism
        TASKS = [(driver.driver, (datum, optimal_design, design_years, aggregation_variable, aggregation_mode))\
                                            for datum in weather_data]
        imap_it = pool.imap(driver.calculatestar, TASKS)

        #Calculate and store results
        for result in imap_it:
            if not isinstance(result, str):
                stored_data.add_location(result, design_years, scale = Target_Production)

        # Uncomment the lines below if you'd like each run to be stored in a separate file (And comment the section outside the loop)
        # df = pd.DataFrame.from_dict(stored_data.collated_results, orient="index")
        # output_file_name = 'Target_Production_{a}_.csv'.format(a = Target_Production)
        # df.to_csv(output_file_name)
        # stored_data = d_store.Data_store() #If this line is uncommented, be sure to output the csv for every run, because the results will be deleted

    # Comment the lines below if you don't want all the data to be stored in a single file
    df = pd.DataFrame.from_dict(stored_data.collated_results, orient="index")
    output_file_name = 'Basic_run_2061_2063.csv'.format(a = design_years[0])
    df.to_csv(output_file_name)

    pool.close()    
    pool.join()

if __name__ == '__main__':
    # Set up the class in which data will be stored
    main()