import numpy as np
import p_location_class as location_class
import p_data_store as d_store
from multiprocessing import current_process
import pandas as pd

def calculate(func, args):
    result = func(*args)
    return result
        
def calculatestar(args):
    return calculate(*args)

def driver(weather_data, design_class, design_years, aggregation_variable, aggregation_mode, operating_class = None):
    """N Salmon 25/05/2021: Solves design problem and uses it as input to operating problem"""

    # Import the weather data for the given location:
    location = location_class.renewable_data(weather_data, design_class._renewables, years_of_interest = design_years, aggregation_variable = aggregation_variable, aggregation_mode = aggregation_mode)
    
    # Import the data and set up the optimisation:
    design_class.specific_model_features(location, False)
    design_class.create_data()
    design_instance = design_class.create_instance()            
               
    # Solve the design optimisation
    design_class.solve_model(design_instance)
    
    if design_class.converged:
    # Store the results
        results = design_class.store_results(design_instance)
        design_class.print_results(design_instance)
        
        ## Uncomment the below if you're nterested in operating the designed plant:
        # operating_years = [[design_years[0] - i] for i in range(1,4)]
        # for operating_year in operating_years:
            # location.set_years(years_of_interest = operating_year, aggregation_mode = aggregation_mode)
            # operating_class.specific_model_features(location, grid_sale)
            # equipment_capacities = design_class.get_capacities(design_instance)    
            # operating_class.create_data(equipment_capacities)
            # operating_instance = operating_class.create_instance()
            # operating_class.solve_model(operating_instance)
            
            # if operating_class.converged:
                # operating_results = operating_class.store_results(operating_instance)
                # operating_class.print_results(operating_instance)
                # results['Production in {year}'.format(year = operating_year)] = operating_results['Annual Production']
            # else:
                # results['Production in {year}'.format(year = operating_year)] = 'Non-converged'
    
    else:
        results = design_class.store_non_converged_results()
    return results