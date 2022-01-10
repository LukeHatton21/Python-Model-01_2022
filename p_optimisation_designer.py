import pyomo.environ as pm
import p_constraints as cons
from p_optimisation_parent import optimiser
import matplotlib.pyplot as plt
import time 

class location_optimise_design(optimiser):
    """Class designed for optimising an ammonia plant given a profile formed in clusters"""

    def __init__(self, Target_Production, Sensitivity_dictionary = {'Production': 'Base', 'Storage': 'Base', 'Finance': 'Base', 'Year': 'Base'}, HB_min = 0.2):
        """Store the location data in the class and create the model and its solver"""
        super().__init__(Target_Production, Sensitivity_dictionary = Sensitivity_dictionary)
        self.design_requirements(HB_min = HB_min)

    def design_requirements(self, HB_min = 0.2):
        
        #Parameters
        self.model.Cost_power = pm.Param(self.model.Renewables, within = pm.NonNegativeReals, initialize = self._Cost_renewables) #million USD/installed MW
        self.model.Cost_components = pm.Param(self.model.Components, within = pm.NonNegativeReals, initialize = self._Cost_components) #million USD/installed MW
        self.model.Cost_storage = pm.Param(self.model.StorageComponents, within = pm.NonNegativeReals, initialize = self._Cost_storage) #million USD/installed MW
        self.model.Cost_FC = pm.Param(within = pm.NonNegativeReals, initialize = self._Cost_FC) #million USD/installed MW
        self.model.Cost_grid = pm.Param(within=pm.NonNegativeReals, mutable = True)
        
        self.model.G_HB_min = pm.Param(initialize=HB_min, mutable=True)  # TBC

        #Variables
        self.model.C_power = pm.Var(self.model.Renewables, bounds = (0, 20), initialize = 10)
        self.model.C_components = pm.Var(self.model.Components, bounds = (0, 20), initialize = 100)
        self.model.C_storage = pm.Var(self.model.StorageComponents, bounds = (0, 20), initialize = 100)
        self.model.C_FC = pm.Var(bounds = (0,20), initialize = 0)
        self.model.grid_active = pm.Var(within=pm.Binary)

        #Constraints
        super().model_constraints()
        self.model.grid_active_constraint_in = pm.Constraint(rule=cons._grid_active_constraint_in)
        self.model.grid_active_constraint_out = pm.Constraint(rule=cons._grid_active_constraint_out)
        self.model.AmmoniaBalance = pm.Constraint(rule = cons._AmmoniaBalance)
        
        #Objective  
        self.model.obj = pm.Objective(rule = cons._LCOA)

    def create_data(self):
        """Creates a data dictionary which can be loaded into an instance"""
        super().create_data()
        self.data[None]['Cost_grid'] = {None:(self._Cost_grid_fixed[self.transmission_type])
                                             *self.AUD_to_USD/self.scaling_factor}
           
    def update_instance(self, instance):
        """Updates the instance with new data specific to the location"""
        super().update_instance(instance)

        delete_list = ['obj']
        for element in delete_list:
            instance.del_component(element)
        
        instance.obj = pm.Objective(rule = cons._LCOA) #Objective needs to be reconstructed for each location because equipment CAPEX changes
        if not self.location.grid_on:
            instance.grid_active.fix(0)        
        
    def print_results(self, instance):
        """Prints results from model"""
        try:
            print('The value of the objective function is: ' + str(self.results['LCOA']) + ' USD/t\n')
        except:
            self.store_results(instance)
            
        for Renewable in instance.Renewables:
            print('The ' + str(Renewable) + ' installed capacity is ' + str(self.results[Renewable]) + ' MW.') 
        for Component in instance.Components:
            print('The ' + str(Component) + ' installed capacity is ' + str(self.results[Component]) +
                  ' MW; its load factor is ' + str(self.results[str(Component) + ' LF']) + '%.')
        for StorageComponent in instance.StorageComponents:
            print('The ' + str(StorageComponent) + ' storage capacity is ' +
                  str(self.results[str(StorageComponent) + ' storage capacity']) + ' ' +
                  self._storage_component_units[StorageComponent])
        print('The Hydrogen fuel cell capacity is ' + str(self.results['FC Capacity']) + ' MW. Its load factor is ' +
              str(self.results['FC LF']) + '%.')
        if self.results['Grid Active']:
            print('There is an active grid connection which provides ' + str(self.results['Grid Fraction']) +
                  '% of the total plant electricity.')
            print('The cost of power is {Costs:.2f} million USD/annum'.format(
                Costs=self.results['Power cost']))
            print('The revenue made from buying negatively priced power and selling power is {Revenue:.2f} million USD/annum'.format(
                Revenue=self.results['Power revenue']))
            print('The LCOE of purchased grid electricity is {LCOE:.2f} USD/MWh'.format(LCOE=self.results['LCOE']))
        else:
            print('There is no grid connection.')
        print('{Curtailed:.2f}% of renewable electricity was curtailed\n'.format(Curtailed = self.results['Curtailed']*100))

        ## Plot storage volume
        #plt.plot(self.hours,self.results['eta_check'])
        #plt.plot(self.hours,self.results['eta_out'])
        # ## plt.plot(self.hours, self.cluster_list)
        #plt.grid()
        #plt.title('Grid electricity use')
        #plt.xlabel('Hour through year')
        #plt.ylabel('Grid electricity use in MWh')
        #plt.grid()
        # if pm.value(instance.ramp_up_rate) < 1:
        #     ramp_off = 0
        # else:
        #     ramp_off = 1
        #plt.savefig('Test')
        # plt.clf()
        
    def store_results(self, instance):
        """Stores the results from the model into a dictionary"""
        self.results = {}
        
        self.results['Solar Capex'] = pm.value(instance.Cost_power['Solar'])
        self.results['Wind Capex'] = pm.value(instance.Cost_power['Wind'])
        
        #Store some high level results relating to the solution
        self.results['LCOA'] = round(pm.value(instance.obj()), 2)

        self.results['Transfer Efficiency'] = round(self.transmission_efficiency, 2)
        
        super().store_results(instance)
        
        return self.results
        
    def get_capacities(self, instance):
        """Stores the capacities from the designed solution in a useful dictionary for the operating optimiser"""
        
        capacities = {'Renewables' : {}, 'Components': {}, 'StorageComponents': {}, 'FC': pm.value(instance.C_FC), 'Production_LCOA':pm.value(instance.obj())}
        for Renewable in instance.Renewables:
            capacities['Renewables'][Renewable] = pm.value(instance.C_power[Renewable])
        for Component in instance.Components:
            capacities['Components'][Component] = pm.value(instance.C_components[Component])
        for StorageComponent in instance.StorageComponents:
            capacities['StorageComponents'][StorageComponent] = pm.value(instance.C_storage[StorageComponent])
        capacities['Grid Active'] = pm.value(instance.grid_active)
        return capacities