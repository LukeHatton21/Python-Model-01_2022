import pyomo.environ as pm
import p_constraints as cons
import matplotlib.pyplot as plt
import time
import gurobipy
import pandas as pd
import os


class optimiser:
    """Class designed for optimising an ammonia plant given a renewable energy profile"""

    def __init__(self, Target_Production, Sensitivity_dictionary):
        """Store the location data in the class and create the model and its solver"""

        self.model = pm.AbstractModel()
        self.opt = pm.SolverFactory('gurobi')
        self.opt.options["Method"] = 3
        self.opt.options["NodeMethod"] = 2
        self.path = os.getcwd() +r'/Model_for_Luke-main/'
        self.NoRelHeurWork = 5
        self.NodefileStart = 0.5
        self.target_production = Target_Production
        self.scaling_factor = Target_Production/1000
        self.model_set_up(Sensitivity_dictionary)
        self.start_time = time.time()

    def model_set_up(self, Sensitivity_dictionary):
        """Calls the functions which create the model"""
        self.model_sets()
        self.general_model_features(Sensitivity_dictionary)
        self.model_parameters()
        self.model_variables()
        
    def read_data(self, element, sensitivity):
        """Imports equipment cost data based on the nominated sensitivity"""
        #df = pd.read_csv(self.path + r'Equipment Data/' + element + r'.csv').set_index('Components')[sensitivity]
        df = pd.read_csv(self.path + r'Equipment Data/' + element + r'.csv').set_index('Components')[sensitivity]
        if len(df) == 1:
            return {None: df.iloc[0]}
        else:
            return df.to_dict() #All in milion USD/installed MW

    def general_model_features(self, Sensitivity_dictionary):
        """Sets up the model features that are common to all locations
        Input data to the model also stored here."""
        #Unpack the sensitivities:
        Finance_sensitivity = Sensitivity_dictionary['Finance']
        Production_sensitivity = Sensitivity_dictionary['Production']
        Storage_sensitivity = Sensitivity_dictionary['Storage']        
        
        # Key sets (non-location specific)      
        self._renewables = ['Solar', 'Wind']
        self._components = ['Elec', 'HB+ASU', 'Battery']
        self._storage_components = ['Battery', 'Hydrogen']
        self._flows = ['pi', 'beta', 'gamma', 'H2', 'NH3']
        # pi = electricity from renewables, beta = electricity from batteries, gamma =
        # electricity from H2 fuel cell.

        # Constants not used in the optimisation model but required for pre- or post-processing of results
            
        self.G_operating_years = 30
        self.G_discount_rate_general = self.read_data('Finance', Finance_sensitivity)[None]
        self.AUD_to_USD = 0.7  # AUD/USD
        self.TUOS_DUOS = self.read_data('TUOS', Production_sensitivity)[None]  # in AUD/MWh
        self.distance_factor = 1.1
        
        # Parameters depending on sets
        self._CF = {('pi', 'H2'): 1 / 50, ('pi', 'NH3'): 1 / (0.532 + 0.11 * 14 / 17),
                    ('H2', 'NH3'): 17 / 3, ('pi', 'beta'): 0.98, ('H2',
                                                                  'gamma'): 0.6 * 141 / 3.6 / 1}  # Materials
        # in t, powers in MW, ammonia energy demand and fuel cell efficiency from Nayak-Luke 2020
        self._Cost_components = self.read_data('Components', Production_sensitivity) #Data in USD/MW
        # Just added in to adjust for scale:
        if self.target_production/0.8 < 1E6:
            self._Cost_components['HB+ASU'] = self._Cost_components['HB+ASU']*(self.target_production/0.8/8E4)**0.7/(self.target_production/0.8/8E4)
        else:
            self._Cost_components['HB+ASU'] = self._Cost_components['HB+ASU']#*(1E6/8E4)**0.7/(1E6/8E4)
        self._Cost_storage = self.read_data('Storage Components', Storage_sensitivity) # Data in USD/MWh or USD/t
        self._Cost_FC = self.read_data('FC', Storage_sensitivity) #Data in USD/MW
        self._Cost_renewables = self.read_data('Renewables', Production_sensitivity) #in Million USD/MW See # https://irena.org/-/media/Files/IRENA/Agency/Publication/2020/Jun/IRENA_Power_Generation_Costs_2019.pdf 
        #for base costs (p 65 for solar for Australia, p53 for wind, general to Oceania)
        
        #For grid data references see x_transmission comparison
        #All costs in AUD
        self._Cost_grid_fixed = {'LV': 23, 'HV': 55} #in AUD
        self._Cost_grid_variable =  {'LV':0.4, 'HV':2.1} #in AUD/km
        self._grid_efficiency = {'LV':0.7, 'HV':0.99696} #Loss per 100 km
        self._transformer_efficiency = {'LV': 0.99, 'HV':0.96}
        # million USD for connection; scaled because it is an integer variable

        # Constants (not included in parameters function betcause the value needs to be set here)
        self.model.G_production = pm.Param(
            initialize=self.target_production / self.scaling_factor)  # t/year, target production same for all cases
        
        self.model.G_annual_hours = pm.Param(initialize=8760 - 2 * 168)  # Assumes 2 weeks off per year for maintenance
        self._storage_component_units = {'Battery': 'MWh', 'Hydrogen': 't'}
        
        # LCOA input parameters
        self.model.O_and_M = pm.Param(initialize=0.02)  # For all components
        self.model.ramp_up = pm.Param(initialize=0.02)  # For all components
        self.model.ramp_down = pm.Param(initialize=0.2)  # For all components
        self.model.water_cost = pm.Param(initialize=2E-6)  # millions of USD/t
        self.model.water_consumption = pm.Param(initialize=9)
        G_crf = self.G_discount_rate_general * (1 + self.G_discount_rate_general) ** self.G_operating_years / (
                (1 + self.G_discount_rate_general) ** self.G_operating_years - 1)
        self.model.G_crf = pm.Param(initialize=G_crf)

    def specific_model_features(self, location, grid_sale):
        """Sets up the model to be location specific (i.e. gets data for the list of hours)"""
        # Set up the timer
        
        #Luke - this should all be obselete to you except for self.interpret_profile()
        self.location = location
        self.transmission_type = 'HV'
        self.transmission_efficiency = 1

        if self.location.grid_on:
            self._grid_max_use = 175/self.scaling_factor
            if grid_sale:
                self._grid_max_sale = 175/self.scaling_factor
            else:
                self._grid_max_sale = 0
        else:
            self._grid_max_use = 0
            self._grid_max_sale = 0

        self.interpret_profile()  # Sets up power profiles

    def interpret_profile(self):
        """Takes the location data and creates a power profile that matches to each t."""
        self._powers = {}
        self._grid_power_cost = {}
        self._grid_power_cost_no_TUOS = {}
        self._t_weights = {}
        # Interpret profile as a dictionary
        self._times = pm.RangeSet(len(self.location.hourly_data))
        for time in self._times:
            self._t_weights[time] =  self.location.concat['Weights'].iloc[time-1]
            for renewable in self.location.renewables:
                self._powers[(renewable, time)] = self.location.concat[renewable].iloc[time-1]
            if self.location.grid_on:
                self._grid_power_cost[time] = (self.location.concat['Grid'].iloc[time-1]\
                     + self.TUOS_DUOS)/self.transmission_efficiency * self.AUD_to_USD * 1E-6
                self._grid_power_cost_no_TUOS[time] = self.location.concat['Grid'].iloc[time-1]*self.transmission_efficiency * self.AUD_to_USD * 1E-6
            else:
                self._grid_power_cost[time] = 1
                self._grid_power_cost_no_TUOS[time] =1

    def model_sets(self):
        """Creates the sets used by the model"""
        # General sets
        
        self.model.Renewables = pm.Set()
        self.model.Components = pm.Set()
        self.model.StorageComponents = pm.Set()
        self.model.Flows = pm.Set()

        # Location specific sets
        self.model.t = pm.Set()

    def model_parameters(self):
        """Creates the parameters used by the model"""
        self.model.power_supply = pm.Param(self.model.Renewables * self.model.t,
                                           within=pm.NonNegativeReals, mutable=True)
        self.model.CF = pm.Param(self.model.Flows * self.model.Flows,
                                 within=pm.NonNegativeReals)  # CF[flow1, flow2] is the amount of flow 1 required to make 1 unit of flow 2, masses in t, powers in MWh
        self.model.t_weights = pm.Param(self.model.t, within=pm.NonNegativeIntegers,
                                              mutable=True)  # weighting of each time step based on aggregation
        self.model.total_days = pm.Param(within=pm.NonNegativeIntegers,
                                         mutable=True)  # Refers to the total number of days in the dataset
        self.model.battery_self_discharge = pm.Param(within=pm.NonNegativeReals, mutable=False)
        self.model.grid_power_cost = pm.Param(self.model.t, mutable=True)
        self.model.grid_power_cost_no_TUOS = pm.Param(self.model.t, mutable=True)
        self.model.grid_max_use = pm.Param(mutable=True, within=pm.NonNegativeReals)
        self.model.grid_max_sale = pm.Param(mutable=True, within=pm.NonNegativeReals)
        self.model.ramp_down_rate = pm.Param(mutable = False, initialize=0.2)
        self.model.ramp_up_rate = pm.Param(mutable = False, initialize=0.02)

    def model_variables(self):
        """Creates the variables used by the model"""
        self.model.pi = pm.Var(self.model.Components, self.model.t, bounds=(0, 5))
        self.model.beta = pm.Var(self.model.Components, self.model.t, bounds=(0, 5))
        self.model.gamma = pm.Var(self.model.Components, self.model.t, bounds=(0, 5))
        self.model.eta_in = pm.Var(self.model.t, bounds=(0,0.175))
        self.model.eta_out = pm.Var(self.model.t, bounds=(0,0.175))
        self.model.curtailed = pm.Var(self.model.t, bounds = (0,5))
        self.model.storage_volume = pm.Var(self.model.StorageComponents, self.model.t, bounds=(0, 1E4))

    def model_constraints(self):
        """Creates the constraints used in the model. Constraint functions are listed in p_constraints.py"""
        self.model.PowerBalance = pm.Constraint(self.model.t, rule=cons._PowerBalance)
        self.model.CurtailedLimit = pm.Constraint(self.model.t, rule=cons._CurtailedLimit)
        self.model.ComponentCap = pm.Constraint(self.model.Components, self.model.t,
                                                rule=cons._ComponentCap)
        self.model.DischargeCap = pm.Constraint(self.model.t, rule=cons._DischargeCap)
        self.model.StorageCap = pm.Constraint(self.model.StorageComponents, self.model.t,
                                              rule=cons._StorageCap)
        self.model.HBCap_min = pm.Constraint(self.model.t, rule=cons._HBCap_min)
        self.model.FC_Cap = pm.Constraint(self.model.t, rule=cons._FC_Cap)
        self.model.FC_limit = pm.Constraint(self.model.t, rule=cons._FC_limit)
        self.model.Battery_limit = pm.Constraint(self.model.t, rule=cons._Battery_limit)
        self.model.grid_power_limit_in = pm.Constraint(self.model.t, rule=cons._grid_power_limit_in)
        self.model.grid_power_limit_out = pm.Constraint(self.model.t, rule=cons._grid_power_limit_out)

    def create_data(self):
        """Creates a data dictionary which can be loaded into an instance"""
        self.data = {None: {'t': {None: self._times}, 'Renewables': {None: self._renewables},
                            'Components': {None: self._components},
                            'StorageComponents': {None: self._storage_components}, 'Flows': {None: self._flows},
                            'CF': self._CF,'total_days': {None: self.location.total_days},
                            'power_supply': self._powers, 'grid_power_cost': self._grid_power_cost,
                            't_weights': self._t_weights, 'grid_max_use': {None: self._grid_max_use},
                            'grid_max_sale': {None: self._grid_max_sale}, 'grid_max_use': {None: self._grid_max_use},
                            'grid_power_cost_no_TUOS': self._grid_power_cost_no_TUOS}}
    def create_instance(self):
        """Creates an instance of the model"""
        instance = self.model.create_instance(self.data)

        max_weight = max(self._t_weights)
        instance.pi.setub(5*max_weight)
        instance.beta.setub(5*max_weight)
        instance.gamma.setub(5*max_weight)
        instance.eta_in.setub(0.175*max_weight)
        instance.eta_out.setub(0.175*max_weight)
        instance.curtailed.setub(5*max_weight)

        instance.HydrogenBalance = pm.Constraint(instance.t, rule=cons._HydrogenBalance)
        instance.BatteryBalance = pm.Constraint(instance.t, rule=cons._BatteryBalance)
        instance.NH3_ramp_down = pm.Constraint(instance.t, rule=cons._NH3_ramp_down)
        instance.NH3_ramp_up = pm.Constraint(instance.t, rule=cons._NH3_ramp_up)

        return instance

    def update_instance(self, instance):
        """Updates the instance with new data specific to the location"""

        instance.power_supply.clear()
        instance.power_supply._constructed = False
        instance.power_supply.construct(self._powers)

        instance.grid_power_cost.clear()
        instance.grid_power_cost._constructed = False
        instance.grid_power_cost.construct(self._grid_power_cost)
        
        instance.grid_power_cost_no_TUOS.clear()
        instance.grid_power_cost_no_TUOS._constructed = False
        instance.grid_power_cost_no_TUOS.construct(self._grid_power_cost_no_TUOS)
        
        instance.t_weights.clear()
        instance.t_weights._constructed = False
        instance.t_weights.construct(self._t_weights)

        delete_list = ['PowerBalance', 'PowerBalance_index','HydrogenBalance', 'HydrogenBalance_index', 'BatteryBalance', 'BatteryBalance_index',
                       'NH3_ramp_down', 'NH3_ramp_down_index', 'NH3_ramp_up', 'NH3_ramp_up_index']
        for element in delete_list:
            instance.del_component(element)
        instance.PowerBalance = pm.Constraint(instance.t, rule=cons._PowerBalance)
        instance.HydrogenBalance = pm.Constraint(instance.t, rule=cons._HydrogenBalance)
        instance.BatteryBalance = pm.Constraint(instance.t, rule=cons._BatteryBalance)

    def solve_model(self, instance):
        """Solves the model, and checks that it reached an optimal solution"""
        sol = self.opt.solve(instance, tee=False, warmstart=False)
        #instance.display("Results.csv") #Only used if you want to check the results
        if sol.solver.termination_condition != pm.TerminationCondition.optimal:
            print('\nThe instance did not converge properly')
            self.converged = False
        else:
            self.converged = True

    def store_results(self, instance):
        """Stores the results from the model into a dictionary"""
        self.results['Converged'] = True

        # Store some location specific information
        self.results['Latitude'] = self.location.latitude
        self.results['Longitude'] = self.location.longitude
        self.results['Aggregation_variable'] = self.location.aggregation_variable
        self.results['Aggregation_mode'] = self.location.aggregation_mode
        self.results['Production'] = self.target_production
        self.results['Max weight'] = max(pm.value(instance.t_weights[t]) for t in instance.t.data())
        self.results['Total time'] = sum(pm.value(instance.t_weights[t]) for t in instance.t.data())

        # Store Wind and Solar
        for Renewable in instance.Renewables:
            self.results[Renewable] = round(pm.value(instance.C_power[Renewable] * self.scaling_factor), 2)

        # Store electrolyser, Battery and HB capacities (Also calculate and store load factors)
        for Component in instance.Components:
            Capacity = pm.value(instance.C_components[Component])
            LF = 0
            for t in instance.t.data():
                LF += pm.value(
                    (instance.pi[Component, t] + instance.beta[Component, t] + instance.gamma[
                        Component, t]))
            if LF > 0 and Capacity > 0:
                LF /= (self.results['Total time']*Capacity/100)
                LF = round(LF, 2)
            else:
                LF = 'N/A'
            self.results[str(Component) + ' LF'] = LF
            self.results[Component] = round(Capacity * self.scaling_factor, 2)
            
        # Store Storage component capacities
        for StorageComponent in instance.StorageComponents:
            self.results[str(StorageComponent) + ' storage capacity'] = round(
                pm.value(instance.C_storage[StorageComponent]) * self.scaling_factor, 2)

        # Store HB Fuel Cell data
        Capacity = pm.value(instance.C_FC)
        if Capacity > 0:
            LF = 0
            for t in instance.t.data():
                LF += sum(pm.value(instance.gamma[Component, t]) for Component in instance.Components)
            LF /= (self.results['Total time'] * Capacity / 100)
            self.results['FC LF'] = round(LF, 2)
        else:
            self.results['FC LF'] = 0
        self.results['FC Capacity'] = round(Capacity * self.scaling_factor, 2)

        # Store grid connection data
        self.results['Grid Active'] = pm.value(instance.grid_active)
        if self.results['Grid Active']:
            self.results['Grid Fraction'] = round(sum(pm.value(instance.eta_in[t])
                                            for t in instance.t)*100/sum(pm.value(instance.pi[Component, t])
                                            for Component in instance.Components for t in instance.t),2)
                                            
        #Estimate Curtailment
        if sum(pm.value(instance.power_supply[Renewable, t])*
                                         pm.value(instance.C_power[Renewable]) for Renewable in instance.Renewables
                                         for t in instance.t) > 0:
            self.results['Curtailed'] = sum(pm.value(instance.curtailed[t])
                                        for t in instance.t)/\
                                    sum(pm.value(instance.power_supply[Renewable, t])*
                                         pm.value(instance.C_power[Renewable]) for Renewable in instance.Renewables
                                         for t in instance.t)
        else:
            self.results['Curtailed'] = 0
        
        # Report Storage volume
        H2_storage = []
        Battery_storage = []
        Ammonia_production = []
        eta_in = []
        eta_out = []
        total_carbon = 0
        carbon_avoided = 0
        for t in instance.t.data():
            eta_in.append(pm.value(instance.eta_in[t] * self.scaling_factor))
            eta_out.append(pm.value(instance.eta_out[t] * self.scaling_factor))
            H2_storage.append(
                round(pm.value(instance.storage_volume[('Hydrogen', t)]) * self.scaling_factor, 2))
            Battery_storage.append(
                round(pm.value(instance.storage_volume[('Battery', t)]) * self.scaling_factor, 2))
            Ammonia_production.append(round((pm.value(instance.pi[('HB+ASU', t)]) + pm.value(
                instance.beta[('HB+ASU', t)]) + pm.value(
                instance.gamma[('HB+ASU',  t)])) / pm.value(instance.C_components['HB+ASU']), 3))
        self.results['Hydrogen Storage'] = H2_storage
        self.results['Battery Storage'] = Battery_storage
        self.results['Ammonia Production'] = Ammonia_production
        
        #Estimate power cost and revenue
        power_cost = 0
        power_revenue = 0
        for t in instance.t:
            if pm.value(instance.grid_power_cost[t]) < 0:
                power_revenue -= pm.value(instance.grid_power_cost[t]/instance.t_weights[t]) * pm.value(instance.eta_in[t])
            else:
                power_cost += pm.value(instance.grid_power_cost[t]/instance.t_weights[t]) * pm.value(instance.eta_in[t])
                power_revenue += pm.value(instance.grid_power_cost_no_TUOS[t]/instance.t_weights[t]) * pm.value(instance.eta_out[t])
        self.results['Power cost'] = power_cost*self.scaling_factor
        self.results['Power revenue'] = power_revenue*self.scaling_factor
        if power_revenue != 0 or power_cost != 0:
            self.results['LCOE'] = (power_cost)*1E6/(sum(pm.value(instance.eta_in[t])
                                                            for t in instance.t))

        self.results['Solve time'] = round(time.time() - self.start_time, 2)
        self.start_time = time.time()
        #fig, ax1 = plt.subplots()
        #ax1.plot([t for t in instance.t.data()], [i/max(Ammonia_production) for i in Ammonia_production])
        #ax1.set_ylim([0,1.2])
        #plt.show()
        print('The time taken to run this case was ' + str(self.results['Solve time']) + ' s')
        print('The total days were {a}'.format(a = pm.value(instance.total_days)))

    def store_non_converged_results(self):
            """Store some data for a case that didn't converge"""
            self.results = {}
            self.results['Converged'] = False
            self.results['Latitude'] = self.location.latitude
            self.results['Longitude'] = self.location.longitude
            self.results['Production'] = self.target_production
            self.results['LCOA'] = 'Did not converge'
            return self.results