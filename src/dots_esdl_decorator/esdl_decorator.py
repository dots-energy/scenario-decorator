from dataclasses import asdict
from modulefinder import test
from pathlib import Path
import uuid
import argparse
import json
import logging
import random

from esdl import Battery, Building, BuildingStructureInformation, ConnectableAsset, CostInformation, DateTimeProfile, EConnection, EVChargingStation, ElectricityDemand, ElectricityNetwork, EnergyAsset, EnergyMarket, EnergySystemInformation, EnvironmentalProfiles, HeatDemandTypeEnum, HeatPump, HeatingDemand, HybridHeatPump, InPort, Measure, Measures, MobilityDemand, MobilityFuelTypeEnum, MultiplierEnum, OutPort, PhysicalQuantityEnum, PVInstallation, Parties, Party, Point, ProfileElement, QuantityAndUnitType, Services, TimeSeriesProfile, UnitEnum, WaterBuffer
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from esdl.esdl_handler import EEnum, EnergySystemHandler

from dots_esdl_decorator.dataclasses import BaseLoadProfileSpecification, BatterySpecification, BuildingIsolationMetaData, BuildingIsolationSpecification, EConnectionSpecification, EvSpecification, EvProfileSpecification, HeatProfileSpecification, HeatingProfileMetaData, HybridHeatpumpSpecification, ProfileMetaData, PvSpecification, TouSpecification, WeatherDataSpecification

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')


def _parse_esdl_unit(unit: str, expected_physical_quantity: str | None = None) -> QuantityAndUnitType | None:
    unit_definitions = {
        "W": ("POWER", "WATT", None),
        "kW": ("POWER", "WATT", "KILO"),
        "MW": ("POWER", "WATT", "MEGA"),
        "Wh": ("ENERGY", "WATTHOUR", None),
        "kWh": ("ENERGY", "WATTHOUR", "KILO"),
        "MWh": ("ENERGY", "WATTHOUR", "MEGA"),
        "J": ("ENERGY", "JOULE", None),
        "kJ": ("ENERGY", "JOULE", "KILO"),
        "MJ": ("ENERGY", "JOULE", "MEGA"),
        "GJ": ("ENERGY", "JOULE", "GIGA"),
    }
    unit = unit.strip()
    if unit not in unit_definitions:
        logging.warning(f"Unsupported unit '{unit}' in esdl, setting unit in description")
        return None

    physical_quantity, unit_name, multiplier = unit_definitions[unit]
    if expected_physical_quantity is not None and physical_quantity != expected_physical_quantity:
        raise ValueError(
            f"Unit '{unit}' has physical quantity {physical_quantity}; "
            f"expected {expected_physical_quantity}"
        )

    return QuantityAndUnitType(
        physicalQuantity=PhysicalQuantityEnum.from_string(physical_quantity),
        unit=UnitEnum.from_string(unit_name),
        multiplier=MultiplierEnum.from_string(multiplier or "NONE"),
    )


class EsdlBuilder:
    def __init__(self, esdl_name : str, harmonize_profiles_to_year : int, target_days: int, default_pv_lon, default_pv_lat):
        esh = EnergySystemHandler()
        self.esdl_name = esdl_name
        self.harmonize_profiles_to_year : int = harmonize_profiles_to_year
        self.target_days: int = target_days
        self.energy_system = esh.load_file(esdl_name)
        self.energy_system.measures = Measures()
        self.energy_system.services = Services(id=str(uuid.uuid4()))
        self.amount_of_connections = self.get_amount_number_of_type_in_esdl(EConnection)
        self.area = self.energy_system.instance[0].area
        self.heat_profiles_mapping :dict[str, HeatingProfileMetaData] = {} 
        self.base_load_profiles : ProfileMetaData = ProfileMetaData()
        self.rng = np.random.default_rng(42)
        self.weather_data_lon : float = default_pv_lon
        self.weather_data_lat : float = default_pv_lat
        self.isolation_params_data : BuildingIsolationMetaData = BuildingIsolationMetaData(data=pd.DataFrame(), spec=BuildingIsolationSpecification())

    def get_amount_number_of_type_in_esdl(self, esdl_type : type) -> int:
        return len([esdl_element for esdl_element in self.energy_system.eAllContents() if isinstance(esdl_element, esdl_type)])

    def add_dso(self):
        dso = Party(name='DSO', id=str(uuid.uuid4()))
        parties = Parties()
        parties.party.append(dso)
        self.energy_system.parties = parties

    def _equalize_timeseries_length(self, values:list[float], delta_t: int, target_days: int, name : str) -> list[float]:
        intervals_per_day = int(24* 3600 / delta_t)
        target_length = target_days * intervals_per_day
        current_length = len(values)

        if current_length == target_length:
            return values

        # Too many values -> truncate
        if current_length > target_length:
            logging.info(f"Truncating timeseries {name} from  "
                         f"{current_length} to {target_length} values")
            return values[:target_length]

        # Too few values -> repeat first values
        missing = target_length - current_length
        logging.info(f"Extending timeseries {name} from "
                     f"{current_length} to {target_length} values by repeating values")
        if missing < current_length:
            return values + values[:missing]
        else:
            ret_val = values
            for i in range(0, missing, current_length):
                if len(ret_val) + current_length < target_length:
                    ret_val = ret_val + values
                else:
                    ret_val = ret_val + values[:target_length - len(ret_val)]
            return ret_val


    def create_time_series_profile_from_df(self, df : pd.DataFrame, column_name : str, unit : QuantityAndUnitType | None = None, target_days: int | None = None) -> TimeSeriesProfile:
        if column_name in df.columns:
            delta_t = int((df.index[1] - df.index[0]).total_seconds())
            min_date = df.index[0].to_pydatetime()
            max_date = df.index[-1].to_pydatetime()
            values = self._get_values_for_timeseries(df, column_name, delta_t, min_date, max_date)

            if target_days is not None:
                values = self._equalize_timeseries_length(values, delta_t, target_days, column_name)

            timeseries_profile = self._build_time_series_profile(delta_t, min_date, values, unit)
            return timeseries_profile

        logging.warning(f"column {column_name} not found in provided input data")
        return TimeSeriesProfile()

    def _build_time_series_profile(self, delta_t : int, min_date : datetime, values, unit : QuantityAndUnitType | None):
        profile_start = min_date
        if self.harmonize_profiles_to_year is not None:
            target_start = min_date.replace(
                    year=self.harmonize_profiles_to_year
                )
            target_day_of_week = target_start.weekday()
            days_to_shift = (target_day_of_week - min_date.weekday()) % 7
            samples_per_day, remainder = divmod(24 * 60 * 60, delta_t)
            if remainder:
                logging.warning(
                        "Cannot harmonize profile dates for timestep %s seconds because it does not divide a day",
                        delta_t,
                    )
            else:
                samples_to_shift = days_to_shift * samples_per_day
                values = values[samples_to_shift:] + values[:samples_to_shift]
            profile_start = profile_start.replace(year=self.harmonize_profiles_to_year)

        timeseries_profile = TimeSeriesProfile(startDateTime=profile_start, timestep=delta_t)
        timeseries_profile.profileQuantityAndUnit = unit
        timeseries_profile.values.extend(values)
        return timeseries_profile

    def _get_values_for_timeseries(self, df, column_name, delta_t, min_date, max_date):
        data_date = min_date
        prev_value = 0
        data = df[column_name].reset_index().to_numpy()
        i = 0 
        values = []
        while data_date <= max_date:
            value = prev_value
            data_instance = data[i]
            pandas_timestampe  = data_instance[0]
            date = pandas_timestampe.to_pydatetime()
            if data_date == date:
                if np.isnan(data_instance[1]):
                    logging.warning(f"Data has a nan value for date {data_date}, using previous value {prev_value} for column {column_name}")
                else:
                    value = data_instance[1]
                    prev_value = value
                i += 1
            else:
                logging.warning(f"Data missing for date {data_date}, using previous value {prev_value} for column {column_name}")
            values.append(float(value))
            data_date += timedelta(seconds=delta_t)
        return values

    def add_weather(self, weather_specification: WeatherDataSpecification):
        energy_system_information = EnergySystemInformation(id=str(uuid.uuid4()))
        weather = EnvironmentalProfiles(name='weather', id=str(uuid.uuid4()))
        energy_system_information.environmentalProfiles = weather
        self.energy_system.energySystemInformation = energy_system_information
        df = pd.read_csv(weather_specification.path, index_col=0, parse_dates=True)
        if weather_specification.measure_data_location_lon is not None and weather_specification.measure_data_location_lat is not None:
            self.weather_data_lon = weather_specification.measure_data_location_lon
            self.weather_data_lat = weather_specification.measure_data_location_lat
        weather.soilTemperatureProfile = self.create_time_series_profile_from_df(
            df,
            weather_specification.soil_temperature_column,
            QuantityAndUnitType(physicalQuantity=PhysicalQuantityEnum.from_string('TEMPERATURE'), unit=UnitEnum.from_string('DEGREES_CELSIUS')), target_days=self.target_days
        )
        weather.solarIrradianceProfile = self.create_time_series_profile_from_df(
            df,
            weather_specification.solar_irradiance_column, target_days=self.target_days
        )
        weather.outsideTemperatureProfile = self.create_time_series_profile_from_df(
            df,
            weather_specification.outside_temperature_column,
            QuantityAndUnitType(physicalQuantity=PhysicalQuantityEnum.from_string('TEMPERATURE'), unit=UnitEnum.from_string('DEGREES_CELSIUS')), target_days=self.target_days)

    def add_market_data(self, day_ahead_prices_file: Path | None, price_column : str, price_unit : str, gass_price : float):
        file_exists = day_ahead_prices_file is not None and day_ahead_prices_file.exists()
        if file_exists or gass_price > 0:
            da_market = EnergyMarket(name=f'DA-market in {price_unit}', id=str(uuid.uuid4()))
            if file_exists:
                df = pd.read_csv(day_ahead_prices_file, index_col=0, parse_dates=True, date_format='ISO8601')
                df.sort_index(ascending=True)

                da_price_datetime_profile = self.create_time_series_profile_from_df(df, price_column,target_days=self.target_days)

                da_market.marketPrice = da_price_datetime_profile
            else:
                logging.warning(f"Skipped adding day ahead price data file {str(day_ahead_prices_file)} not found")

            if gass_price > 0:
                da_market.description = f"Gass price {gass_price} EUR/m3"

            self.energy_system.services.service.append(da_market)

    def add_heat_profiles(self, heat_profile_specification: HeatProfileSpecification, heating_demand_type: EEnum):
        heat_profile_file = Path(heat_profile_specification.profile_file)

        if heating_demand_type == HeatDemandTypeEnum.from_string('SPACE_HEATING'):
            heat_profiles = pd.read_csv(heat_profile_file)
            temps_np = list(heat_profiles.iloc[-1][1:])
            temps = [float(temp) for temp in temps_np]
            heat_profiles.drop(heat_profiles.index[-1], inplace=True)
            heat_profiles['timestamp'] = pd.to_datetime(heat_profiles["timestamp"], format='ISO8601')
            heat_profiles = heat_profiles.set_index('timestamp')
        else:
            heat_profiles = pd.read_csv(heat_profile_file, index_col=0, parse_dates=True, date_format='ISO8601')
            tap_water_setpoint = 55.0
            temps = [tap_water_setpoint for col in heat_profiles.columns]

        column_choices = list(range(len(heat_profiles.columns)))
        amount_of_profiles_to_chose = (
            heat_profile_specification.amount_of_profiles
            if heat_profile_specification.amount_of_profiles > 0
            else len(heat_profiles.columns)
        )
        cols = self.rng.choice(column_choices, size=amount_of_profiles_to_chose)
        for col, temp in zip(cols, temps):
            quantity_and_unit = _parse_esdl_unit(heat_profile_specification.unit)

            time_series_profile = self.create_time_series_profile_from_df(heat_profiles, heat_profiles.columns[col], quantity_and_unit, target_days=self.target_days)
            comfort_range = 4.0
            heating_demand = HeatingDemand(type=heating_demand_type, minTemperature=temp, maxTemperature=temp + comfort_range)
            heat_profile_name = heat_profile_specification.profile_name
            if heat_profile_name not in self.heat_profiles_mapping:
                self.heat_profiles_mapping[heat_profile_name] = HeatingProfileMetaData()
            esdl_heat_profile_name = f"{heat_profile_name}{len(self.heat_profiles_mapping[heat_profile_name].ports)}"

            heating_demand.name = esdl_heat_profile_name
            in_port = InPort(id=str(uuid.uuid4()), name="In")
            heating_demand.port.append(in_port)
            heating_demand.description = f"Unit: {heat_profile_specification.unit}"
            heating_demand.port.append(OutPort(id=str(uuid.uuid4()), name="Out"))
            heating_demand.port[1].profile.append(time_series_profile)
            self.heat_profiles_mapping[heat_profile_name].ports.append(in_port)
            self.heat_profiles_mapping[heat_profile_name].demands.append(heating_demand)
            self.heat_profiles_mapping[heat_profile_name].added_to_esdl.append(False)

    def add_base_load_profiles(self, base_load_profile_specification: BaseLoadProfileSpecification):
        base_load_profile_file = Path(base_load_profile_specification.profile_file)
        base_load_profiles = pd.read_csv(base_load_profile_file, index_col=0, parse_dates=True, date_format='ISO8601')
        delta_t = int((base_load_profiles.index[1] - base_load_profiles.index[0]).total_seconds())
        delta_t_hours = delta_t / 3600.0
        totals = base_load_profiles.sum(axis=0) * delta_t_hours
        if base_load_profile_specification.normalize:
            base_load_profiles = base_load_profiles.div(totals.to_numpy(), axis=1)

        column_choices = base_load_profiles.columns
        cols = column_choices if self.amount_of_connections >= len(column_choices) else self.rng.choice(column_choices, size=self.amount_of_connections, replace=False )

        for col_name in cols:
            quantity_and_unit = _parse_esdl_unit(base_load_profile_specification.unit, expected_physical_quantity="POWER")

            time_series_profile = self.create_time_series_profile_from_df(base_load_profiles, col_name, quantity_and_unit, target_days=self.target_days)
            electricity_demand = ElectricityDemand(id=str(uuid.uuid4()))
            esdl_base_load_profile_name = f"base_load_{col_name}"

            electricity_demand.description = f"{esdl_base_load_profile_name}, Unit: {base_load_profile_specification.unit}"
            electricity_demand.name = f"Total: {totals[col_name]} kwh"
            electricity_demand.powerFactor = 0.95
            in_port = InPort(id=str(uuid.uuid4()), name="In")
            electricity_demand.port.append(in_port)
            electricity_demand.port.append(OutPort(id=str(uuid.uuid4()), name="Out"))
            electricity_demand.port[1].profile.append(time_series_profile)
            self.base_load_profiles.ports.append(in_port)
            self.energy_system.instance[0].area.asset.append(electricity_demand)

    def add_ev_profile(self, entity : str, profile_data : pd.DataFrame, ev_specification : EvProfileSpecification) -> MobilityDemand:

        profile = DateTimeProfile()
        quantity_and_unit = _parse_esdl_unit(ev_specification.unit, expected_physical_quantity="ENERGY")
        profile.profileQuantityAndUnit = quantity_and_unit
        days_to_shift = 0
        min_date_data: datetime = profile_data[ev_specification.connection_start_date_time_column].min()
        target_year = min_date_data.year 
        source_date_start = datetime(target_year, 1, 1) 
        if self.harmonize_profiles_to_year is not None:
            target_year = self.harmonize_profiles_to_year
            target_start = datetime(year=self.harmonize_profiles_to_year, month=1, day=1)
            target_day_of_week = target_start.weekday()
            days_to_shift = (target_day_of_week - source_date_start.weekday()) % 7

        for index, profile_data_row in profile_data.iterrows():
            start_date_time_session : datetime = profile_data_row[ev_specification.connection_start_date_time_column]
            end_date_time_session : datetime = profile_data_row[ev_specification.connection_end_date_time_column]
            goes_to_next_year = start_date_time_session.year != end_date_time_session.year
            if start_date_time_session > source_date_start + timedelta(days=days_to_shift):
                start_date_time_session = start_date_time_session - timedelta(days=days_to_shift)
                end_date_time_session = end_date_time_session - timedelta(days=days_to_shift)
                start_date_time_session = start_date_time_session.replace(year=target_year)
                end_date_time_session = end_date_time_session.replace(year=target_year)
                if goes_to_next_year:
                    end_date_time_session = end_date_time_session.replace(year=target_year + 1)

                energy_consumed = profile_data_row[ev_specification.energy_demand_column]
                profile.element.append(ProfileElement(from_=start_date_time_session, to=end_date_time_session, value=energy_consumed))

        mobility_demand = MobilityDemand(fuelType=MobilityFuelTypeEnum.from_string('ELECTRICITY'))
        profile.physicalQuantityAndUnit = quantity_and_unit
        mobility_demand.name = f"ev_profile_{entity} in {ev_specification.unit}"
        in_port = InPort(id=str(uuid.uuid4()), name="In")
        mobility_demand.port.append(in_port)
        mobility_demand.port.append(OutPort(id=str(uuid.uuid4()), name="Out"))
        mobility_demand.port[1].profile.append(profile)
        self.energy_system.instance[0].area.asset.append(mobility_demand)
        return mobility_demand


    def add_pvs_and_batteries_to_houses(self, pv_specification : PvSpecification, battery_specification : BatterySpecification):
        houses = [esdl_element for esdl_element in self.energy_system.eAllContents() if isinstance(esdl_element, Building)]
        n_houses = len(houses)
        n_pv = round(pv_specification.fraction_houses_pv * n_houses)
        n_bat = round(battery_specification.fraction_houses_pv_battery * n_pv)

        house_indices_pv = self.rng.choice(range(0, n_houses), size=n_pv, replace=False)
        house_indices_bat = self.rng.choice(house_indices_pv, size=n_bat, replace=False)

        for i in house_indices_pv:
            house = houses[i]
            surface_area = self.rng.integers(low=pv_specification.surface_area_min, high=pv_specification.surface_area_max, endpoint=True)  # 1 panel 1mx1.60m, 4-10 panels
            orientation = self.rng.choice([45, 90, 135, 180, 225, 270, 315]) 
            orientation_angle_mapping = {
                45 : self.rng.integers(low=15, high=30, endpoint=True), # northeast
                90 : self.rng.integers(low=15, high=30, endpoint=True), # east
                135 : self.rng.integers(low=15, high=30, endpoint=True), # southeast
                180 : self.rng.integers(low=15, high=30, endpoint=True), # south
                225 : self.rng.integers(low=30, high=45, endpoint=True), # southwest
                270 : self.rng.integers(low=15, high=30, endpoint=True), # west
                315 : self.rng.integers(low=15, high=30, endpoint=True), # northwest
            }
            panel_efficiency = 0.2
            power_w = surface_area * 1000 * panel_efficiency
            pv_installation = PVInstallation(name='pv_' + house.name, id=str(uuid.uuid4()), power=float(power_w), angle=int(orientation_angle_mapping[orientation]),
                                             orientation=int(orientation), powerFactor=1.0, surfaceArea=int(surface_area), panelEfficiency=0.2) # ISIE
            if house.geometry is not None and isinstance(house, Point):
                pv_installation.geometry = Point(lon=house.geometry.lon, lat=house.geometry.lat)
            elif self.weather_data_lon is not None and self.weather_data_lat is not None:
                pv_installation.geometry = Point(lon=self.weather_data_lon, lat=self.weather_data_lat)

            phase_grids = [asset for asset in house.asset if isinstance(asset, ElectricityNetwork)]
            if i in house_indices_bat:
                capacity_kwh = self.rng.normal(battery_specification.capacity_kwh_mean, battery_specification.capacity_kwh_std)
                capacity_j = capacity_kwh * 3.6e6
                fill_level = self.rng.uniform(0.3, 0.7)  # fraction of total capacity
                charge_rate_w = capacity_kwh / battery_specification.power_kw_to_energy_kwh_ratio * 1000
                battery = Battery(name='battery_' + house.name, id=str(uuid.uuid4()),
                                  capacity=float(capacity_j),
                                  chargeEfficiency=battery_specification.efficiency, dischargeEfficiency=battery_specification.efficiency,
                                  fillLevel=float(fill_level),
                                  maxChargeRate=float(charge_rate_w), maxDischargeRate=float(charge_rate_w),
                                  powerFactor=1.0)
            for grid in phase_grids:
                self.add_producing_asset_to_other_asset(pv_installation, grid, house)
                if i in house_indices_bat:
                    self.add_consuming_asset_to_other_asset(battery, grid, house)


    def connect_heating_demand_heatpump_to_profile(self, asset_to_connect_to : ConnectableAsset, dhw_profile_name : str) -> HeatingDemand | None:
        heating_demand = None
        if len(self.heat_profiles_mapping) > 0 and dhw_profile_name in self.heat_profiles_mapping:
            meta_data = self.heat_profiles_mapping[dhw_profile_name]
            if not meta_data.added_to_esdl[meta_data.index_to_pick]:
                self.energy_system.instance[0].area.asset.append(meta_data.demands[meta_data.index_to_pick])
                meta_data.added_to_esdl[meta_data.index_to_pick] = True
                heating_demand = meta_data.demands[meta_data.index_to_pick]

            connected_to = meta_data.ports[meta_data.index_to_pick]
            out_port = OutPort(id=str(uuid.uuid4()), connectedTo=[connected_to])
            connected_to.connectedTo.append(out_port)
            asset_to_connect_to.port.append(out_port)
            amount_of_profiles = len(self.heat_profiles_mapping[dhw_profile_name].ports)
            self.heat_profiles_mapping[dhw_profile_name].index_to_pick = (self.heat_profiles_mapping[dhw_profile_name].index_to_pick + 1) % amount_of_profiles
        else:
            logging.warning(f"No heat profile found with name: {dhw_profile_name}")

        return heating_demand


    def connect_base_load_to_econnection(self, econnection : EConnection):
        if len(self.base_load_profiles.ports) > 0:
            port = self.base_load_profiles.ports[self.base_load_profiles.index_to_pick]
            self.base_load_profiles.index_to_pick = (self.base_load_profiles.index_to_pick + 1) % len(self.base_load_profiles.ports)
            phase_grids = [asset for asset in econnection.eContainer().asset if isinstance(asset, ElectricityNetwork)]
            for phase_grid in phase_grids:
                phase_port = next((port for port in phase_grid.port if isinstance(port, OutPort) and len(port.connectedTo) == 0), None)
                if phase_port is None:
                    new_phase_out_port = OutPort(id=str(uuid.uuid4()), name=f"Out")
                    phase_grid.port.append(new_phase_out_port)
                    phase_port = new_phase_out_port
                phase_port.connectedTo.append(port)
                port.connectedTo.append(phase_port)
        else:
            logging.warning("No heat profiles loaded so not connecting base load profiles to econnection")


    def connect_heatpump_and_buffer(self, heatpump : HeatPump, buffer : WaterBuffer):
        inport_buffer = InPort(id=str(uuid.uuid4()), name="In")
        outport_buffer = OutPort(id=str(uuid.uuid4()), name=f"Out_{buffer.name}")
        inport_buffer.connectedTo.append(outport_buffer)
        outport_buffer.connectedTo.append(inport_buffer)
        buffer.port.append(inport_buffer)
        heatpump.port.append(outport_buffer)


    def add_heat_pump_to_houses(self, fraction_houses_hp : float, hybrid_heatpump_specification : HybridHeatpumpSpecification, hw_profile_names : list[str]):
        fraction_houses_hhp = hybrid_heatpump_specification.fraction_houses_hhp
        if fraction_houses_hhp + fraction_houses_hp > 1.0:
            raise ValueError("Fraciton of houses for heatpump and hybrid heatpump should at most sum to 1.0")

        if fraction_houses_hhp + fraction_houses_hp > 0.0:
            houses = [esdl_element for esdl_element in self.energy_system.eAllContents() if isinstance(esdl_element, Building)]
            n_houses = len(houses)
            house_indices = list(range(n_houses))
            n_hp = round(fraction_houses_hp * n_houses)
            n_hhp = round(fraction_houses_hhp * n_houses)
            # Generate random house indices
            house_indices_hp = self.rng.choice(house_indices, size=n_hp, replace=False)
    
            dhw_names_options = hw_profile_names
    
            for i in house_indices_hp:
                house_indices.remove(i)
    
            houses_indices_hhp = self.rng.choice(house_indices, size=n_hhp, replace=False)
    
            for i in np.concatenate((house_indices_hp, houses_indices_hhp)):
                house = houses[i]
                phase_grids = [asset for asset in house.asset if isinstance(asset, ElectricityNetwork)]
                dhw_temp_set = 55.0
                dhw_temp_tap = 15.0 # 10.0 is only in the winter, 20.0 in the summer - >15.0 on average
                buffer_temp_min = 25.0
                buffer_temp_max = 65.0
    
                isolation_df = self.isolation_params_data.data
                isolation_params = None
                if not isolation_df.empty:
                    isolation_params = isolation_df[isolation_df[self.isolation_params_data.spec.asset_type_col].str.lower() == house.assetType.lower()]
                    if isolation_params.empty:
                        logging.warning(f"No isolation parameters found for house with assetType {house.assetType} in isolation parameters data")
                hw_buffer = None
                sh_buffer = None
                # add heat pump
                if i in house_indices_hp:
                    heat_pump = HeatPump(name='hp_' + house.name, id=str(uuid.uuid4()), power=10000.0, powerFactor=0.98, assetType='air_water')
                    if isolation_params is not None and not isolation_params.empty:
                        hw_buffer_size = float(isolation_params.iloc[0][self.isolation_params_data.spec.dhw_buffer_volume_hp_col])
                        sh_buffer_size = float(isolation_params.iloc[0][self.isolation_params_data.spec.sh_buffer_volume_hp_col])
                        hw_power = float(isolation_params.iloc[0][self.isolation_params_data.spec.heatPumpThermalPower_col])
                        hw_buffer = WaterBuffer(name='hw_buffer_' + house.assetType, id=str(uuid.uuid4()), selfDischargeRate=0.0, volume=hw_buffer_size, minStorageTemperature=dhw_temp_tap, maxStorageTemperature=dhw_temp_set, description="Hot water buffer temperatures in celsius")
                        sh_buffer = WaterBuffer(name='sh_buffer_' + house.assetType, id=str(uuid.uuid4()), selfDischargeRate=0.0, volume=sh_buffer_size, minStorageTemperature=buffer_temp_min, maxStorageTemperature=buffer_temp_max, description="Space heating buffer temperatures in celsius")
                        heat_pump.power = hw_power
                        self.connect_heatpump_and_buffer(heat_pump, hw_buffer)
                        self.connect_heatpump_and_buffer(heat_pump, sh_buffer)
                        house.asset.append(hw_buffer)
                        house.asset.append(sh_buffer)
    
                    heat_pump.COP = 3.5
    
                elif i in houses_indices_hhp:
    
                    heat_pump = HybridHeatPump(name='hhp_' + house.name, id=str(uuid.uuid4()), powerFactor=0.98,
                                               assetType='air_water', heatPumpThermalPower=10000.0,
                                               gasHeaterEfficiency=hybrid_heatpump_specification.gas_heater_efficiency,
                                               gasHeaterThermalPower=float(self.rng.normal(
                                                   hybrid_heatpump_specification.gass_thermal_power_mean,
                                                   hybrid_heatpump_specification.gass_thermal_power_std,
                                               )))
                    if isolation_params is not None and not isolation_params.empty:
                        w_power = float(isolation_params.iloc[0][self.isolation_params_data.spec.hybridheatPumpThermalPower_col])
                        sh_buffer_size = float(isolation_params.iloc[0][self.isolation_params_data.spec.hhp_sh_buffer_volume_col])
                        heat_pump.heatPumpThermalPower = w_power
                        sh_buffer = WaterBuffer(name='sh_buffer_' + house.assetType, id=str(uuid.uuid4()), volume=sh_buffer_size, minStorageTemperature=buffer_temp_min, selfDischargeRate=0.0, maxStorageTemperature=buffer_temp_max, description="Space heating buffer temperatures in celsius")
                        house.asset.append(sh_buffer)
                        self.connect_heatpump_and_buffer(heat_pump, sh_buffer)
    
                sh_profile_connecting_asset = heat_pump if sh_buffer is None else sh_buffer
                hw_profile_connecting_asset = heat_pump if hw_buffer is None else hw_buffer
                demand_sh = self.connect_heating_demand_heatpump_to_profile(sh_profile_connecting_asset, house.assetType.lower())
    
                dhw_names_options = hw_profile_names
                profile_name = self.rng.choice(dhw_names_options) if len(dhw_names_options) > 0 else "No Profile"
                demand_hw = self.connect_heating_demand_heatpump_to_profile(hw_profile_connecting_asset, profile_name)
    
                # add to a random phase
                phase = self.rng.integers(low=0, high=len(phase_grids) - 1, endpoint=True) 
                
                self.add_producing_asset_to_other_asset(heat_pump, phase_grids[phase], house)

    def _define_econnection_description_full(self, econnection_spec : EConnectionSpecification, counter_ems : int, house_indices_dyn : np.ndarray, house_indices_ems : np.ndarray) -> str:
        prop_dict = {}
        if counter_ems in house_indices_dyn:
            prop_dict['energy_contract'] = 'dynamic_contract'
            prop_dict['flat_price'] = econnection_spec.flat_rate_dyn
        else:
            prop_dict['energy_contract'] = 'fixed_contract'
            prop_dict['price'] = econnection_spec.static_price_contract
        if counter_ems in house_indices_ems:
            prop_dict['got_ems'] = True
        return json.dumps(prop_dict)

    def _define_econnection_description_min(self, counter_ems : int, house_indices_dyn : np.ndarray) -> str:
        ret_val = {}
        if counter_ems in house_indices_dyn:
            ret_val = 'dynamic_contract'
        else:
            ret_val = 'fixed_contract'
        return ret_val
        

    
    def add_econnection_information(self, econnection_spec : EConnectionSpecification):
        houses = [esdl_element for esdl_element in self.energy_system.eAllContents() if
                  isinstance(esdl_element, Building)]
        n_houses = len(houses)
        n_dyn = round(econnection_spec.fraction_houses_dyn * n_houses)
        n_ems = round(econnection_spec.fraction_houses_ems * n_houses)
        house_indices_dyn = self.rng.choice(range(0, n_houses), size=n_dyn, replace=False)
        house_indices_ems = self.rng.choice(range(0, n_houses), size=n_ems, replace=False)

        full_description = econnection_spec.static_price_contract > 0 and econnection_spec.flat_rate_dyn > 0 and econnection_spec.fraction_houses_ems > 0
    
        econnections : list[EConnection] = [esdl_element for esdl_element in self.energy_system.eAllContents() if
                        isinstance(esdl_element, EConnection)]
        counter_ems = 0
        for econnection in econnections:
            self.connect_base_load_to_econnection(econnection)
            if full_description:
                econnection.description = self._define_econnection_description_full(econnection_spec, counter_ems, house_indices_dyn, house_indices_ems)
            else:
                econnection.description = self._define_econnection_description_min(counter_ems, house_indices_dyn)
            counter_ems += 1


    def connect_ev_profile_to_chargingstation(self, chargingstation : EVChargingStation, mobility_demand : MobilityDemand):
        out_port = OutPort(id=str(uuid.uuid4()), name="Out")
        chargingstation.port.append(out_port)

        out_port.connectedTo.append(mobility_demand.port[0])
        mobility_demand.port[0].connectedTo.append(out_port)


    def add_ev_chargingstation(self, ev_specification : EvSpecification, ev_profile_params : EvProfileSpecification):
        if ev_specification.fraction_houses_ev > 0.0:
            houses = [esdl_element for esdl_element in self.energy_system.eAllContents() if isinstance(esdl_element, Building)]
            n_houses = len(houses)
            n_ev = round(ev_specification.fraction_houses_ev * n_houses)
            # Generate random house indices
            house_indices_ev = self.rng.choice(range(0, n_houses), size=n_ev, replace=False)
    
            ev_entities_in_data = []
            if ev_profile_params is not None and ev_profile_params.profile_file != '' and Path(ev_profile_params.profile_file).exists():
                data = pd.read_csv(ev_profile_params.profile_file)
                data[ev_profile_params.connection_start_date_time_column] = pd.to_datetime(data[ev_profile_params.connection_start_date_time_column], format='ISO8601')
                data[ev_profile_params.connection_end_date_time_column] = pd.to_datetime(data[ev_profile_params.connection_end_date_time_column], format='ISO8601')
                charging_stations = data[ev_profile_params.charging_station_identifier_column].unique()
                if len(charging_stations) > n_ev:
                    ev_entities_in_data = self.rng.choice(charging_stations, size=n_ev, replace=False)
                else:
                    ev_entities_in_data = self.rng.choice(charging_stations, size=n_ev)
    
            for i, house_index in enumerate(house_indices_ev):
                house = houses[house_index]
                phase_grids = [asset for asset in house.asset if isinstance(asset, ElectricityNetwork)]
    
                power_range = [3700, 11000]
                power_w = float(self.rng.choice(power_range))
                annual_load = self.rng.integers(low=1800000, high=4000000, endpoint=True)
                powerfactor = 0.95
    
                mobility_demand = None
                if len(ev_entities_in_data) > 0:
                    entity = ev_entities_in_data[i]
                    data_entity = data[data[ev_profile_params.charging_station_identifier_column] == entity]
                    mobility_demand = self.add_ev_profile(entity, data_entity, ev_profile_params)
                    power_w = data_entity[ev_profile_params.charging_power_column].mean() * 1000
                    annual_load = data_entity[ev_profile_params.energy_demand_column].sum()
    
                ev_specification_dict = asdict(ev_specification) 
                ev_specification_dict.pop('fraction_houses_ev', None)
                ev_specification_dict.pop('capacity_kwh_mean', None)
                ev_specification_dict.pop('capacity_kwh_std', None)
                ev_specification_dict['capacity_kwh'] = self.rng.normal(ev_specification.capacity_kwh_mean, ev_specification.capacity_kwh_std)
                charging_station = EVChargingStation(name='chargingstation_' + house.name, id=str(uuid.uuid4()),
                                                          power=power_w, fullLoadHours=int(annual_load/power_w),
                                                          powerFactor=powerfactor, assetType='privateEV', description=json.dumps(ev_specification_dict))
                cut_off_charge_rate_3_pahses_w = 3700
                if power_w > cut_off_charge_rate_3_pahses_w:
                    # Add to all phases
                    for connection_ph in phase_grids:
                        self.add_consuming_asset_to_other_asset(charging_station, connection_ph, house)
                else:
                    phase = self.rng.integers(low=0, high=len(phase_grids) - 1, endpoint=True)
                    self.add_producing_asset_to_other_asset(charging_station, phase_grids[phase], house)
    
                if mobility_demand is not None:
                    self.connect_ev_profile_to_chargingstation(charging_station, mobility_demand)


    def add_tou_measure(self, tou_spec : TouSpecification):
        tou_df = pd.read_csv(tou_spec.profile_file)
        tou_df[tou_spec.from_date_time_col] = pd.to_datetime(tou_df[tou_spec.from_date_time_col], format='ISO8601')
        tou_df[tou_spec.to_date_time_col] = pd.to_datetime(tou_df[tou_spec.to_date_time_col], format='ISO8601')

        tou_measure = Measure(name = "time of use", id=str(uuid.uuid4()))
        cost_information = CostInformation(id=str(uuid.uuid4()), name=f"time of use, fixed costs: €{tou_spec.fixed_tou_rate_eur}")
        tou_profile = DateTimeProfile()
        for index, profile_data_row in tou_df.iterrows():
            start_date_time_session : datetime = profile_data_row[tou_spec.from_date_time_col].to_pydatetime()
            end_date_time_session : datetime = profile_data_row[tou_spec.to_date_time_col].to_pydatetime()
            if self.harmonize_profiles_to_year is not None:
                start_date_time_session = start_date_time_session.replace(year=self.harmonize_profiles_to_year)
                end_date_time_session = end_date_time_session.replace(year=self.harmonize_profiles_to_year)
            tou_weight : float = profile_data_row[tou_spec.value_col]
            tou_profile.element.append(ProfileElement(from_=start_date_time_session, to=end_date_time_session, value=tou_weight))

        cost_information.variableOperationalCosts = tou_profile
        tou_measure.costInformation = cost_information
        self.energy_system.measures.measure.append(tou_measure)


    def add_building_isolation(self, isolation_specification: BuildingIsolationSpecification):
        isolation_data = pd.read_csv(isolation_specification.isolation_params_file)
        self.isolation_params_data = BuildingIsolationMetaData(data=isolation_data, spec=isolation_specification)
        buildings = [
            esdl_element
            for esdl_element in self.energy_system.eAllContents()
            if isinstance(esdl_element, Building)
        ]
        for building in buildings:
            isolation_data[isolation_specification.asset_type_col] = isolation_data[isolation_specification.asset_type_col].apply(lambda id: id.lower())
            matching_rows = isolation_data.loc[isolation_data[isolation_specification.asset_type_col] == building.assetType.lower()]
            if matching_rows.empty:
                logging.warning(f"No building isolation parameters found for asset type '{building.assetType}'")
            else:
                row = matching_rows.iloc[0]
                building_information = BuildingStructureInformation(
                    rcFloor=float(row[isolation_specification.rcFloor_col]),
                    rcRoof=float(row[isolation_specification.rcRoof_col]),
                    rcWall=float(row[isolation_specification.rcWall_col]),
                    uDoor=float(row[isolation_specification.uDoor_col]),
                    uWindow=float(row[isolation_specification.uWindow_col]),
                )
                building.buildinginformation.append(building_information)


    def add_congestion_measure(self, congestion_management_active : bool):
        congestion_measure = Measure(name="congestion_management_active", id=str(uuid.uuid4()))
        congestion_measure.description = str(congestion_management_active)
        self.energy_system.measures.measure.append(congestion_measure)


    def save_esdl(self, output_path: str | Path | None = None):
        esh = EnergySystemHandler(energy_system=self.energy_system)
        if output_path is None:
            input_path = Path(self.esdl_name)
            output_path = Path('decorated_' + input_path.name)
        esh.save(str(output_path))


    @staticmethod
    def add_consuming_asset_to_other_asset(asset : EnergyAsset, other_asset : EnergyAsset, background):
        # background refers to the non-energy asset to which the new asset is added (area, house, etc.)
        background.asset.append(asset)
        outport_other_asset = OutPort(id=str(uuid.uuid4()))
        other_asset.port.append(outport_other_asset)
        inport_asset = InPort(id=str(uuid.uuid4()), connectedTo=[outport_other_asset])
        asset.port.append(inport_asset)


    @staticmethod
    def add_producing_asset_to_other_asset(asset : EnergyAsset, other_asset : EnergyAsset, background):
        # background refers to the non-energy asset to which the new asset is added (area, house, etc.)
        background.asset.append(asset)
        inport_other_asset = InPort(id=str(uuid.uuid4()))
        other_asset.port.append(inport_other_asset)
        outport_asset = OutPort(id=str(uuid.uuid4()), connectedTo=[inport_other_asset])
        asset.port.append(outport_asset)


def parse_heating_profile(params : dict, params_key : str, default_profile_name : str, profile_enum_type : EEnum, esdl_decorator : EsdlBuilder):
    heat_profiles = params.get(params_key, [])
    for profile in heat_profiles:
        heat_profile_specification = HeatProfileSpecification.from_dict(
            {**profile, "profile_name": profile.get("profile_name", default_profile_name)}
        )
        path = Path(heat_profile_specification.profile_file)
        if path.exists():
            esdl_decorator.add_heat_profiles(heat_profile_specification, profile_enum_type)
        else:
            logging.info(f"Skip adding {default_profile_name} profile because file {str(path)} does not exist")


def parse_base_load_profile(params : dict, esdl_decorator : EsdlBuilder):
    base_load_profiles = params.get('base_load_profiles', [])
    for profile in base_load_profiles:
        base_load_profile_specification = BaseLoadProfileSpecification.from_dict(profile)
        path = Path(base_load_profile_specification.profile_file)
        if path.exists():
            esdl_decorator.add_base_load_profiles(base_load_profile_specification)
        else:
            logging.info(f"Skip adding base load profile because file {str(path)} does not exist")


def parse_market_data(params : dict, esdl_decorator : EsdlBuilder):
    da_market_data = params.get('da_market_data', 'df_da_prices_2023_fixed.csv')
    path_market_data_file = None
    price_column = ''
    price_unit = ''
    if isinstance(da_market_data, dict):
        path_market_data_file = Path(da_market_data.get('path', 'weather-data.csv'))
        price_column = da_market_data.get('price_column', 'Day-ahead Price [EUR/MWh]')
        price_unit = da_market_data.get('price_unit', 'EUR/MWh')

    gass_price = params.get('gass_price_eur_m3', 0.0)
    esdl_decorator.add_market_data(path_market_data_file, price_column, price_unit, gass_price)


def parse_tou_data(params : dict, esdl_decorator : EsdlBuilder):
    tou_spec = params.get('tou_specification', {})
    if tou_spec != {}:
        tou_spec = TouSpecification.from_dict(tou_spec)
        path_tou_data_file = Path(tou_spec.profile_file)
        if path_tou_data_file.exists():
            esdl_decorator.add_tou_measure(tou_spec)
        else:
            logging.info("Skip adding market data as the file was not found")

def parse_weather_data(params : dict, esdl_decorator : EsdlBuilder):
    weather_data = params.get('weather_data', '')
    if isinstance(weather_data, dict):
        weather_spec : WeatherDataSpecification = WeatherDataSpecification.from_dict(params.get('weather_data'))
        path_weather_file = Path(weather_spec.path)
        if path_weather_file.exists():
            esdl_decorator.add_weather(weather_spec)
        else:
            logging.info("Skip adding weather data as the file was not found")


def parse_isolation_parameters(params : dict, esdl_decorator : EsdlBuilder):
    isolation_params = params.get('building_isolation', None)
    if isinstance(isolation_params, dict):
        isolation_specification = BuildingIsolationSpecification.from_dict(isolation_params)
        path_isolation_file = Path(isolation_specification.isolation_params_file)
        if path_isolation_file.exists():
            esdl_decorator.add_building_isolation(isolation_specification)
        else:
            logging.info("Skip adding building isolation because the file was not found")


def main() -> int:
    parser = argparse.ArgumentParser(description="Decorate an ESDL file using JSON parameters")
    parser.add_argument('esdl', help='Path to the input ESDL file')
    parser.add_argument('params', help='Path to a JSON file with parameters')
    parser.add_argument('--output', '--o', dest='output', help='Path where the output ESDL file will be stored')
    args = parser.parse_args()

    try:
        with open(args.params, 'r', encoding='utf-8') as fh:
            params = json.load(fh)
    except Exception as e:
        logging.exception(f"Failed to load params file {args.params}: {e}")
        return 2

    pv_specification = PvSpecification.from_dict(params.get('pv_specification', {}))
    battery_specification = BatterySpecification.from_dict(params.get('battery_specification', {}))
    ev_specification = EvSpecification.from_dict(params.get('ev_specification', {}))

    esdl_path = Path(args.esdl)
    if esdl_path.exists():
        harmonize_profile_dates_to = params.get('harmonize_profiles_to_year', None)
        harmonize_profile_dates_to_year = None
        no_target_days = params.get('target_days', 365)
        default_lon = params.get('default_lon', 51.532534)
        default_lat = params.get('default_lat', 3.882267)
        harmonize_profile_dates_to_year = harmonize_profile_dates_to
        esdl_decorator = EsdlBuilder(str(esdl_path), harmonize_profile_dates_to_year, no_target_days, default_lon, default_lat)
    else:
        logging.error(f"ESDL file {str(esdl_path)} does not exist")
        return 2

    parse_weather_data(params, esdl_decorator)

    parse_market_data(params, esdl_decorator)

    parse_heating_profile(params, 'dhw_profiles', 'other_domestic_hot_water', HeatDemandTypeEnum.from_string('HOT_TAPWATER'), esdl_decorator)

    parse_heating_profile(params, 'space_heating_profiles', 'other_space_heating', HeatDemandTypeEnum.from_string('SPACE_HEATING'), esdl_decorator)

    parse_base_load_profile(params, esdl_decorator)

    parse_tou_data(params, esdl_decorator)

    parse_isolation_parameters(params, esdl_decorator)

    fraction_houses_hp = params.get('fraction_houses_hp', 0.0)
    hybrid_heatpump_specification = HybridHeatpumpSpecification.from_dict(params.get('hybrid_heatpump_specification',{} ))

    congestion_management_active = params.get('congestion_management_active', False)
    esdl_decorator.add_congestion_measure(congestion_management_active)

    dhw_profile_names = []
    if "dhw_profiles" in params:
        dhw_profile_names = [
            profile["profile_name"]
            for profile in params["dhw_profiles"]
        ]

    esdl_decorator.add_pvs_and_batteries_to_houses(pv_specification, battery_specification)
    esdl_decorator.add_heat_pump_to_houses(fraction_houses_hp, hybrid_heatpump_specification, dhw_profile_names)
    ev_profile_params : EvProfileSpecification =  EvProfileSpecification.from_dict(params.get('ev_profiles', {}))
    esdl_decorator.add_ev_chargingstation(ev_specification, ev_profile_params)
    econnection_spec = EConnectionSpecification.from_dict(params.get('econnection_specification',{}))
    esdl_decorator.add_econnection_information(econnection_spec)
    esdl_decorator.save_esdl(args.output)

    return 0


if __name__ == "__main__":
    exit(main())
