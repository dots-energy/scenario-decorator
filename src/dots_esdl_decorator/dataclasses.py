from dataclasses import dataclass, field
import pandas as pd
from dataclasses_json import dataclass_json

from esdl import HeatingDemand, InPort

@dataclass
class ProfileMetaData:
    ports : list[InPort] = field(default_factory=list)
    index_to_pick : int = 0

@dataclass
class BuildingIsolationMetaData:
    data : pd.DataFrame
    spec : BuildingIsolationSpecification


@dataclass
class HeatingProfileMetaData(ProfileMetaData):
    demands : list[HeatingDemand] = field(default_factory=list)
    added_to_esdl : list[bool] = field(default_factory=list)

@dataclass_json
@dataclass
class PvSpecification:
    fraction_houses_pv : float = 0.0
    surface_area_min : int = 6
    surface_area_max : int = 16

@dataclass_json
@dataclass
class BatterySpecification:
    fraction_houses_pv_battery : float = 0.0
    capacity_kwh_mean : float = 10.0
    capacity_kwh_std : float = 16.0
    efficiency : float = 5.0
    power_kw_to_energy_kwh_ratio : float = 7.5

@dataclass_json
@dataclass
class EvSpecification:
    fraction_houses_ev : float = 0.0
    min_charge_rate_kwh : float = 4.2
    min_soc_percentage_v2g : float = 0.3
    capacity_kwh_mean : float = 75
    capacity_kwh_std : float = 0.0
    efficiency : float = 0.95

@dataclass_json
@dataclass
class EvProfileSpecification:
    profile_file : str = ''
    connection_start_date_time_column : str = ''
    connection_end_date_time_column : str = ''
    charging_station_identifier_column : str = ''
    energy_demand_column : str = ''
    charging_power_column : str = ''
    unit : str = "kWh"

@dataclass_json
@dataclass
class HeatProfileSpecification:
    profile_file : str
    profile_name : str = ""
    amount_of_profiles : int = -1
    unit : str = "kW"

@dataclass_json
@dataclass
class BaseLoadProfileSpecification:
    profile_file : str
    normalize : bool = False
    unit : str = "kW"

@dataclass_json
@dataclass
class TouSpecification:
    profile_file : str
    fixed_tou_rate_eur : float
    from_date_time_col : str
    to_date_time_col : str
    value_col : str

@dataclass_json
@dataclass
class WeatherDataSpecification:
    path: str = ''
    soil_temperature_column: str = ''
    solar_irradiance_column: str = ''
    outside_temperature_column: str = ''
    measure_data_location_lat : float | None = None
    measure_data_location_lon : float | None = None

@dataclass_json
@dataclass
class BuildingIsolationSpecification:
    isolation_params_file: str = ""
    asset_type_col : str = ""
    rcFloor_col: str = ""
    rcRoof_col: str = ""
    rcWall_col: str = ""
    uDoor_col: str = ""
    uWindow_col: str = ""
    heatPumpThermalPower_col : str = ""
    sh_buffer_volume_hp_col : str = ""
    dhw_buffer_volume_hp_col : str = ""
    hybridheatPumpThermalPower_col : str = ""
    hhp_sh_buffer_volume_col : str = ""


