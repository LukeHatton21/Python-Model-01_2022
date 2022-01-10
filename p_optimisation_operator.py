import pyomo.environ as pm
import p_constraints as cons
from p_optimisation_parent import optimiser
import matplotlib.pyplot as plt
import time

class location_optimise_operation(optimiser):
    """Class designed for optimising an ammonia plant given a profile formed in clusters"""

    def __init__(self, Target_Production, Sensitivity_dictionary ={'Production': 'Base', 'Storage': 'Base', 'Finance': 'Base', 'Year': 'Base'}):
        """Store the location data in the class and create the model and its solver"""
        super().__init__(Target_Production, Sensitivity_dictionary)
        self.operating_requirements() #Doesn't need finance information to work...

    def operating_requirements(self):
        """Includes parameters and variables that are specifically required by the operating case. Defines the
        constraints and the objective. """
        # Parameters
        self.model.G_HB_min = pm.Param(initialize=0.2, mutable=True)  # TBC
        self.model.C_power = pm.Param(self.model.Renewables, within=pm.NonNegativeReals, mutable=True)
        self.model.C_components = pm.Param(self.model.Components, within=pm.NonNegativeReals, mutable=True)
        self.model.C_storage = pm.Param(self.model.StorageComponents, within=pm.NonNegativeReals, mutable=True)
        self.model.C_FC = pm.Param(within=pm.NonNegativeReals, mutable=True)
        self.model.G_production_LCOA = pm.Param(within=pm.NonNegativeReals, mutable=True)
        self.model.grid_active = pm.Param(within=pm.Binary, mutable=True)

        # Constraints
        super().model_constraints()

        # Objective

    def create_data(self, Equipment_capacities):
        """Creates a data dictionary which can be loaded into an instance"""
        super().create_data()
        self.data[None]['C_power'] = Equipment_capacities['Renewables']
        self.data[None]['C_components'] = Equipment_capacities['Components']
        self.data[None]['C_storage'] = Equipment_capacities['StorageComponents']
        self.data[None]['C_FC'] = {None: Equipment_capacities['FC']}
        self.data[None]['G_production_LCOA'] = {None: Equipment_capacities['Production_LCOA']}
        self.data[None]['grid_active'] = {None: Equipment_capacities['Grid Active']}

        self.model.obj = pm.Objective(rule=cons._AmmoniaProduction, sense=pm.maximize)
    def update_instance(self, instance):
        """Updates the instance with new data specific to the location"""

        super().update_instance(instance)

        # if len(instance.cluster_weights) < 365 or self.location.grid_on:
            # instance.del_component('obj')
            # instance.obj = pm.Objective(rule=cons._AmmoniaProduction,
                                        # sense=pm.maximize)  # Objective needs to be reconstructed for each location
            # if cluster weights change, or for new grid power system.

    def print_results(self, instance):
        """Prints results from model"""
        try:
            print('The value of the objective function is: ' + str(self.results['Annual Production']) + ' MMTPA\n')

        #     total_production = sum((
        #         pm.value(instance.pi[('HB+ASU', Cluster, t)]) + pm.value(instance.beta[('HB+ASU', Cluster, t)])
        #         + pm.value(instance.gamma[('HB+ASU', Cluster, t)])) * pm.value(instance.cluster_weights[Cluster])
        #         for Cluster in instance.Clusters for t in instance.t) * pm.value(instance.CF[('pi', 'NH3')])
        #     discounted_Production = sum(
        #         pm.value(instance.eta[Cluster, t]) * pm.value(instance.grid_power_cost[Cluster, t]) * 1E6
        #         for Cluster in instance.Clusters for t in
        #         instance.t) / pm.value(instance.G_production_LCOA)
        #     print('The total production is ' + str(total_production))
        #     print('The discounted ammonia production is ' + str(discounted_Production))
        except NameError:
            self.store_results(instance)

        # for Component in instance.Components:
            # print('The ' + str(Component) + ' installed capacity is ' +
                  # str(self.results[Component]) + 'MW; its load factor is ' +
                  # str(self.results[str(Component) + ' LF']) + '%.')
        # for StorageComponent in instance.StorageComponents: print('The ' + str(StorageComponent) + ' storage
        # capacity is ' + str(self.results[str(StorageComponent) + ' storage capacity']) + ' ' +
        # self._storage_component_units[StorageComponent]) print('The Hydrogen fuel cell capacity is ' + str(
        # self.results['FC Capacity']) + ' MW. Its load factor is ' + str(self.results['FC LF']) + '%.')

        # print(str(self.results['Curtailed']) + ' % of electricity was curtailed\n')

        # ## Plot storage volume
        # plt.plot(self.hours,self.results['Ammonia Production'])
        # plt.plot(self.hours, self.cluster_list)
        # plt.grid()
        # plt.title('Ammonia production at ' + self.results['Location'])
        # plt.xlabel('Hour through year')
        # plt.ylabel('Hydrogen in storage, t')
        # plt.show()
        # if pm.value(instance.ramp_up_rate) < 1:
        # ramp_off = 0
        # else:
        # ramp_off = 1
        # plt.savefig(self.results['Location'] + '_' + str(len(self.results['Midoids'])) + '_' + str(ramp_off))
        # plt.clf()

    def store_results(self, instance):
        """Stores the results from the model into a dictionary"""
        self.results = {}

        if self.converged:
            self.results['Annual Production'] = round(pm.value(instance.obj()) * self.scaling_factor * 1E-6,
                                                      3)  # Production in Mtpa
            super().store_results(instance)

            
        else:
            self.results['Annual Production'] = 'NaN'
        
        return self.results