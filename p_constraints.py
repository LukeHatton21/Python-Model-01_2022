import pyomo.environ as pm

def _PowerBalance(model, t):
    """Checks that the renewables are producing more energy than is consumed"""
    return sum(model.power_supply[Renewable, t] * model.C_power[Renewable] for Renewable in model.Renewables) + \
           model.eta_in[t] - model.curtailed[t] == sum(model.pi[Component, t] for Component in model.Components)+model.eta_out[t]

def _CurtailedLimit(model, t):
    """Stops the model curtailing more energy than the current production of renewable energy"""
    return model.curtailed[t] <= sum(model.power_supply[Renewable, t] * model.C_power[Renewable] for Renewable in model.Renewables)

def _HydrogenBalance(model, t):
    """Size hydrogen storage, ensuring there is always enough to meet ammonia demand"""
    if t == 1:
        old_storage = model.storage_volume[('Hydrogen', len(model.t))]
    else:
        old_storage = model.storage_volume[('Hydrogen', t-1)]
    return old_storage + model.CF[('pi', 'H2')] * (model.pi[('Elec', t)] + model.beta[('Elec',t)]) \
           - model.CF[('pi', 'NH3')] / (model.CF[('H2', 'NH3')]) * (
                   model.pi[('HB+ASU', t)] + model.beta[('HB+ASU', t)] + model.gamma[
               ('HB+ASU', t)]) \
           - model.CF[('H2', 'gamma')] * sum(model.gamma[(Component,t)] for Component in model.Components) \
           == model.storage_volume[('Hydrogen', t)]

def _AmmoniaBalance(model):
    """Forces the model to produce a target amount of ammonia in a year"""
    return sum(
        (model.pi[('HB+ASU',t)] + model.beta[('HB+ASU', t)] + model.gamma[('HB+ASU', t)]) for t in model.t) * \
           (model.G_annual_hours / 24) / model.total_days * \
           model.CF[('pi', 'NH3')] \
           == model.G_production

def _BatteryBalance(model, t):
    """Forces the model to increase the size of the battery when it is used for storage"""
    if t == 1:
        old_storage = model.storage_volume[('Battery', len(model.t))]
    else:
        old_storage = model.storage_volume[('Battery', t - 1)]

    return 0.999943 * old_storage + model.CF[('pi', 'beta')] * model.pi[('Battery', t)] - sum(
        model.beta[(Component, t)] for Component in model.Components) == model.storage_volume[
               ('Battery', t)]

def _NH3_ramp_down(model,t):
    """Places a cap on how quickly the ammonia plant can ramp down"""
    if t == 1:
        old_weight = model.t_weights[len(model.t)]
        old_rate = (model.pi[('HB+ASU', len(model.t))] + model.beta[('HB+ASU', len(model.t))] + \
                   model.gamma[('HB+ASU', len(model.t))])/old_weight
    else:
        old_weight = model.t_weights[t-1]
        old_rate = (model.pi[('HB+ASU', t - 1)] + model.beta[('HB+ASU', t - 1)] + model.gamma[
            ('HB+ASU', t - 1)])/old_weight
            
    modifier = (2 * old_weight * model.t_weights[t])/(old_weight + model.t_weights[t])

    return old_rate - (model.pi[('HB+ASU', t)] + model.beta[('HB+ASU', t)] + model.gamma[
        ('HB+ASU', t)])/model.t_weights[t] <= model.C_components['HB+ASU'] * model.ramp_down * modifier

def _NH3_ramp_up(model, t):
    """Places a cap on how quickly the ammonia plant can ramp down"""
    if t == 1:
        old_weight = model.t_weights[len(model.t)]
        old_rate = (model.pi[('HB+ASU', len(model.t))] + model.beta[('HB+ASU', len(model.t))] + \
                   model.gamma[('HB+ASU', len(model.t))])/old_weight
    else:
        old_weight = model.t_weights[t-1]
        old_rate = (model.pi[('HB+ASU', t - 1)] + model.beta[('HB+ASU', t - 1)] + model.gamma[
            ('HB+ASU', t - 1)])/old_weight
            
    modifier = (2 * old_weight * model.t_weights[t])/(old_weight + model.t_weights[t])

    return (model.pi[('HB+ASU', t)] + model.beta[('HB+ASU', t)] + model.gamma[
        ('HB+ASU', t)])/model.t_weights[t] - old_rate <= model.C_components['HB+ASU'] * model.ramp_up * modifier

def _ComponentCap(model, Component, t):
    """Forces the component capacity to be greater than or equal to the power supply to that component"""
    return model.pi[(Component, t)] + model.beta[(Component, t)] + model.gamma[
        (Component, t)] <= model.C_components[Component] * model.t_weights[t]

def _DischargeCap(model, t):
    """Checks that the battery doesn't discharge at a greater rate than its capacity"""
    return sum(model.beta[(Component, t)] for Component in model.Components) <= model.C_components['Battery'] * model.t_weights[t]

def _StorageCap(model, StorageComponent, t):
    """Forces the storage capacity to be >= the most full that the storage gets at any time"""
    return model.storage_volume[(StorageComponent, t)] <= model.C_storage[StorageComponent]

def _HBCap_min(model, t):
    """ Checks that the ammonia plant is within acceptable operating limits"""
    return model.G_HB_min * model.C_components['HB+ASU']  <= (model.pi[('HB+ASU', t)] + model.beta[
        ('HB+ASU', t)] + model.gamma[('HB+ASU', t)])/model.t_weights[t]

def _FC_Cap(model, t):
    """Sets the capacity of the fuel cell"""
    return sum(model.gamma[(Component, t)] for Component in model.Components) <= model.C_FC * model.t_weights[t]

def _grid_power_limit_in(model, t):
    """Limits the total amount of power that can be used from the electricity grid"""
    return model.eta_in[t] <= model.grid_max_use * model.t_weights[t]
    
def _grid_power_limit_out(model, t):
    """Limits the total amount of power that can be sold to the electricity grid"""
    return model.eta_out[t] <= model.grid_max_sale * model.t_weights[t]

def _grid_active_constraint_in(model):
    """Determines whether or not there is a need to pay for a grid connection, including transformer"""
    return sum(model.eta_in[t] for t in model.t)/(model.total_days*24*20) <= \
           model.grid_active #20 us the UB of the value of eta_in at a single time. 
           
def _grid_active_constraint_out(model):
    """Determines whether or not there is a need to pay for a grid connection based on the choice to sell power"""
    return sum(model.eta_out[t] for t in model.t)/(model.total_days*24*20) <= \
           model.grid_active #20 us the UB of the value of eta_in at a single time. 

def _FC_limit(model, t):
    """Sets the flow from the fuel cell to the electrolyser and from the fuel cell to the battery to 0"""
    return model.gamma[('Elec', t)] + model.gamma[('Battery', t)] == 0

def _Battery_limit(model, t):
    """Sets the flow from the battery to itself to be 0"""
    return model.beta[('Battery', t)] == 0

def _LCOA(model):
    """Estimates the LCOA of the plant - used as the objective function for the design case"""
    CAPEX = (sum(model.Cost_power[Renewable] * model.C_power[Renewable] for Renewable in model.Renewables) + \
            sum(model.Cost_components[Component] * model.C_components[Component] for Component in model.Components)) + \
            sum(model.Cost_storage[StorageComponent] * model.C_storage[StorageComponent] for StorageComponent in
                model.StorageComponents) + (model.Cost_FC * model.C_FC) + (model.Cost_grid * model.grid_active)

    OPEX = sum((model.eta_in[t] * model.grid_power_cost[t] - 
                model.eta_out[t] * model.grid_power_cost_no_TUOS[t])/model.t_weights[t] for t in model.t) * model.G_annual_hours / 24 / model.total_days +\
           model.water_cost * model.water_consumption / model.CF[('H2', 'NH3')] * model.G_production +\
           model.O_and_M * CAPEX

    return 1E6 * (model.G_crf * CAPEX + OPEX) / model.G_production

def _AmmoniaProduction(model):
    """Calculates ammonia production given plant performance - alternative objective function for the operation case."""
    ammonia_in = sum((model.pi[('HB+ASU', t)] + model.beta[('HB+ASU', t)] + model.gamma[
                ('HB+ASU', t)]) for t in model.t) * model.CF[('pi', 'NH3')]
                
    ammonia_out = sum((model.eta_in[t] * model.grid_power_cost[t] - model.eta_out[(t)] * model.grid_power_cost_no_TUOS[t])*
                1E6 for t in model.t)/model.G_production_LCOA
    
    return model.G_annual_hours / 24 / model.total_days * (ammonia_in-ammonia_out)