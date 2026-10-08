from dataclasses import dataclass, field
from dataclasses_json import dataclass_json

from esdl import HeatingDemand, InPort

@dataclass
class ProfileMetaData:
    ports : list[InPort] = field(default_factory=list)
    index_to_pick : int = 0


@dataclass
class HeatingProfileMetaData(ProfileMetaData):
    demands : list[HeatingDemand] = field(default_factory=list)
    added_to_esdl : list[bool] = field(default_factory=list)

@dataclass_json
@dataclass
class PvSpecification:
    fraction_houses_pv : float
    surface_area_min : int = 6
    surface_area_max : int = 16

@dataclass_json
@dataclass
class BatterySpecification:
    fraction_houses_pv_battery : float
    capacity_kwh_mean : float = 10.0
    capacity_kwh_std : float = 16.0
    efficiency : float = 5.0
    power_kw_to_energy_kwh_ratio : float = 7.5

@dataclass_json
@dataclass
class EvSpecification:
    profile_file : str
    connection_start_date_time_column : str
    connection_end_date_time_column : str
    charging_station_identifier_column : str
    energy_demand_column : str
    charging_power_column : str

@dataclass_json
@dataclass
class TouSpecification:
    profile_file : str
    fixed_tou_rate_eur : float
    from_date_time_col : str
    to_date_time_col : str
    value_col : str

@dataclass
class GenericHeatpumpTemperatures:
    buffer_temp_set : float
    buffer_temp_min : float
    buffer_temp_max : float
    buffer_temp_0 : float
    dhw_temp_set : float
    dhw_temp_tap : float

@dataclass
class HpParams:
    buffer_capacitance : float
    hw_buffer_capacitance : float
    nominal_heat : float

@dataclass
class HhpParams:
    buffer_capacitance : float
    nominal_heat : float

