"""Creates a class in which the optimisation driver stores results"""
import numpy as np

def is_leap(year):
    """Returns true if the input year is a leap year. Returns false otherwise"""
    if year%100 == 0:
        if year%400 ==0:
            return True
        else:
            return False
    elif year %4 == 0:
        return True
    else:
        return False

class Data_store:
    """Class designed to store data from each instance of the optimisation driver case"""
    def __init__(self):
        """Creates an empty dictionary in which data will be stored"""
        self.collated_results = {}
        self.hydrogen_storage = {}
        self.battery_storage = {}
        self.grid_usage = {}
        self.ammonia_production = {}
        self.renewables = None
                
    def get_active_components(self, model_class):
        """Just sets up the equipment used in the program"""
        self.Renewables = model_class._renewables
        self.Components = model_class._components
        self.StorageComponents = model_class._storage_components
        self._storage_component_units = model_class._storage_component_units
    
    def add_location(self, location_results, years, scale = None):
        """Adds a location to the collated results"""
        if scale is None:
            self.key = str(location_results['Latitude']) + '_' + str(location_results['Longitude']) \
                    + '_' + str(years[0])
        else:
            self.key = str(location_results['Latitude']) + '_' + str(location_results['Longitude']) \
                    + '_' + str(scale)
        if location_results['Converged']:
            #self.hydrogen_storage[self.key] = location_results.pop('Hydrogen Storage')
            location_results.pop('Hydrogen Storage')
            #self.battery_storage[self.key] = location_results.pop('Battery Storage')
            location_results.pop('Battery Storage')
            #self.grid_usage[self.key] = location_results.pop('eta_in')
            #location_results.pop('eta_in')
            #location_results.pop('eta_out')

            ammonia_production = location_results.pop('Ammonia Production')
            
        self.collated_results[self.key] = location_results  
            
    def add_operating_year(self, production, operating_year):
        """Adds the operating year to the dictionary - used for most recent case only"""
        self.collated_results[self.key][operating_year] = production
        
    def print_results(self, location_name):
        """Prints results from model"""
        try:
            dict_ = self.collated_results[location_name]
        except:
            print(str(location_name) + ' has not been stored.')
            pass
            
        print('\nThe value of the objective function is: ' + str(dict_['Objective']) + ' billion USD')    
        print('The LCOA is: ' + str(dict_['LCOA']) + ' USD/t\n')
        for Renewable in self.Renewables:
            print('The ' + str(Renewable) + ' installed capacity is ' + str(dict_[Renewable]) + ' MW.') 
        for Component in self.Components:
            print('The ' + str(Component) + ' installed capacity is ' + str(dict_[Component]) + ' MW; its load factor is ' + str(dict_[str(Component) + ' LF']) + '%') 
        for StorageComponent in self.StorageComponents:
            print('The ' + str(StorageComponent) + ' storage capacity is ' + str(dict_[str(StorageComponent) + ' storage']) + ' ' + self._storage_component_units[StorageComponent]) 
        print(str(dict_['Curtailed']) + ' % of electricity was curtailed')
    