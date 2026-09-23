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
    power_mean_kw : float = 7
    power_std_kw : float = 1
    orientation_min : int = 90
    orientation_max : int = 270
    surface_area_min : int = 6
    surface_area_max : int = 16
    panel_angle_values : list[int] = field(default_factory=lambda: [15, 20, 25, 30])

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

@dataclass
class BufferTemperatures:
    buffer_temp_set : float
    buffer_temp_min : float
    buffer_temp_max : float
    buffer_temp_0 : float

@dataclass
class BufferCapacitances:
    buffer_capacitance : float
    hw_buffer_capacitance : float