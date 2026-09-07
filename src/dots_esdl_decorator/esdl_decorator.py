from modulefinder import test
from pathlib import Path
import uuid
import argparse
import json
import logging

from esdl import Battery, Building, DateTimeProfile, EConnection, EVChargingStation, ElectricityDemand, ElectricityNetwork, EnergyAsset, EnergyMarket, EnergySystemInformation, EnvironmentalProfiles, HeatDemandTypeEnum, HeatPump, HeatingDemand, InPort, MobilityDemand, MobilityFuelTypeEnum, OutPort, PVInstallation, Parties, Party, Point, ProfileElement, Services, TimeSeriesProfile
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random
from esdl.esdl_handler import EEnum, EnergySystemHandler

from dots_esdl_decorator.dataclasses import BatterySpecification, EvSpecification, ProfileMetaData, PvSpecification

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

class EsdlBuilder:
    def __init__(self, esdl_name : str, harmonize_profile_dates : datetime | None = None):
        esh = EnergySystemHandler()
        self.esdl_name = esdl_name
        self.harmonize_profile_dates = harmonize_profile_dates
        self.energy_system = esh.load_file(esdl_name)
        self.amount_of_connections = self.get_amount_number_of_type_in_esdl(EConnection)
        self.area = self.energy_system.instance[0].area
        self.heat_profiles_mapping :dict[str, ProfileMetaData] = {} 
        self.base_load_profiles : ProfileMetaData = ProfileMetaData()

    def get_amount_number_of_type_in_esdl(self, esdl_type : type) -> int:
        return len([esdl_element for esdl_element in self.energy_system.eAllContents() if isinstance(esdl_element, esdl_type)])

    def add_dso(self):
        dso = Party(name='DSO', id=str(uuid.uuid4()))
        parties = Parties()
        parties.party.append(dso)
        self.energy_system.parties = parties

    def create_time_series_profile_from_df(self, df : pd.DataFrame, column_name : str) -> TimeSeriesProfile:
        if column_name in df.columns:
            delta_t = int((df.index[1] - df.index[0]).total_seconds())
            min_date = df.index[0].to_pydatetime()
            max_date = df.index[-1].to_pydatetime()
            values = self._get_values_for_timeseries(df, column_name, delta_t, min_date, max_date)

            timeseries_profile = self._build_time_series_profile(delta_t, min_date, values)
            return timeseries_profile

        logging.warning(f"column {column_name} not found in provided input data")
        return TimeSeriesProfile()

    def _build_time_series_profile(self, delta_t, min_date, values):
        profile_start = min_date
        if self.harmonize_profile_dates is not None:
            target_start = min_date.replace(
                    year=self.harmonize_profile_dates.year,
                    month=self.harmonize_profile_dates.month,
                    day=self.harmonize_profile_dates.day,
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
            profile_start = target_start

        timeseries_profile = TimeSeriesProfile(startDateTime=profile_start, timestep=delta_t)
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

    def add_weather(self, data_file : Path, column_mapping: dict[str, str] | None = None):
        energy_system_information = EnergySystemInformation(id=str(uuid.uuid4()))
        weather = EnvironmentalProfiles(name='weather', id=str(uuid.uuid4()))
        energy_system_information.environmentalProfiles = weather
        self.energy_system.energySystemInformation = energy_system_information
        df = pd.read_csv(data_file, index_col=0, parse_dates=True)

        weather.soilTemperatureProfile = self.create_time_series_profile_from_df(
            df,
            column_mapping['soil_temperature'],
        )
        weather.solarIrradianceProfile = self.create_time_series_profile_from_df(
            df,
            column_mapping['solar_irradiance'],
        )
        weather.outsideTemperatureProfile = self.create_time_series_profile_from_df(
            df,
            column_mapping['outside_temperature'],
        )

    def add_da_market_timeseries_profile(self, day_ahead_prices_file: Path, price_column : str, price_unit : str):
        da_market = EnergyMarket(name=f'DA-market in {price_unit}', id=str(uuid.uuid4()))
        services = Services(id=str(uuid.uuid4()))
        df = pd.read_csv(day_ahead_prices_file, index_col=0, parse_dates=True, date_format='ISO8601')
        df.sort_index(ascending=True)

        da_price_datetime_profile = self.create_time_series_profile_from_df(df, price_column)

        da_market.marketPrice = da_price_datetime_profile
        services.service.append(da_market)
        self.energy_system.services = services

    def add_heat_profiles(self, heat_profile_file : Path, amount_of_profiles : int, heat_profile_name : str, heating_demand_type : EEnum):

        heat_profiles = pd.read_csv(heat_profile_file, index_col=0, parse_dates=True, date_format='ISO8601')
        column_choices = list(range(len(heat_profiles.columns)))
        amount_of_profiles_to_chose = amount_of_profiles if amount_of_profiles > 0 else len(heat_profiles.columns)
        cols = np.random.choice(column_choices, size=amount_of_profiles_to_chose)
        for col in cols:
            
            time_series_profile = self.create_time_series_profile_from_df(heat_profiles, heat_profiles.columns[col])

            heating_demand = HeatingDemand(type=heating_demand_type)
            if heat_profile_name not in self.heat_profiles_mapping:
                self.heat_profiles_mapping[heat_profile_name] = ProfileMetaData()
            esdl_heat_profile_name = f"{heat_profile_name}{len(self.heat_profiles_mapping[heat_profile_name].ports)}"

            heating_demand.name = esdl_heat_profile_name
            in_port = InPort(id=str(uuid.uuid4()), name="In")
            heating_demand.port.append(in_port)
            heating_demand.port.append(OutPort(id=str(uuid.uuid4()), name="Out"))
            heating_demand.port[1].profile.append(time_series_profile)
            self.heat_profiles_mapping[heat_profile_name].ports.append(in_port)
            self.energy_system.instance[0].area.asset.append(heating_demand)


    def add_base_load_profiles(self, base_load_profile_file : Path, normalize : bool):
        base_load_profiles = pd.read_csv(base_load_profile_file, index_col=0, parse_dates=True, date_format='ISO8601')
        delta_t = int((base_load_profiles.index[1] - base_load_profiles.index[0]).total_seconds())
        delta_t_hours = delta_t / 3600.0
        totals = base_load_profiles.sum(axis=0) * delta_t_hours
        if normalize:
            base_load_profiles = base_load_profiles.div(totals.to_numpy(), axis=1)

        column_choices = base_load_profiles.columns
        cols = column_choices if self.amount_of_connections >= len(column_choices) else np.random.choice(column_choices, size=self.amount_of_connections, replace=False )
        for col_name in cols:
            time_series_profile = self.create_time_series_profile_from_df(base_load_profiles, col_name)

            electricity_demand = ElectricityDemand()
            esdl_base_load_profile_name = f"base_load_{col_name}"

            electricity_demand.description = esdl_base_load_profile_name
            electricity_demand.name = f"Total: {totals[col_name]} kwh"
            in_port = InPort(id=str(uuid.uuid4()), name="In")
            electricity_demand.port.append(in_port)
            electricity_demand.port.append(OutPort(id=str(uuid.uuid4()), name="Out"))
            electricity_demand.port[1].profile.append(time_series_profile)
            self.base_load_profiles.ports.append(in_port)
            self.energy_system.instance[0].area.asset.append(electricity_demand)

    def add_ev_profile(self, entity : str, profile_data : pd.DataFrame, ev_specification : EvSpecification) -> MobilityDemand:

        profile = DateTimeProfile()
        for index, profile_data_row in profile_data.iterrows():
            start_date_time_session_str = profile_data_row[ev_specification.connection_start_date_time_column]
            end_date_time_session_str = profile_data_row[ev_specification.connection_end_date_time_column]
            start_date_time_session = datetime.strptime(start_date_time_session_str, '%Y-%m-%dT%H:%M:%S')
            end_date_time_session = datetime.strptime(end_date_time_session_str, '%Y-%m-%dT%H:%M:%S')
            energy_consumed = profile_data_row[ev_specification.energy_demand_column]
            profile.element.append(ProfileElement(from_=start_date_time_session, to=end_date_time_session, value=energy_consumed))

        mobility_demand = MobilityDemand(fuelType=MobilityFuelTypeEnum.from_string('ELECTRICITY'))

        mobility_demand.name = f"ev_profile_{entity} in kWh"
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

        house_indices_pv = random.sample(range(0, n_houses), n_pv)
        house_indices_bat = random.sample(house_indices_pv, n_bat)

        for i in house_indices_pv:
            house = houses[i]
            surface_area = random.randint(6, 16)  # 1 panel 1mx1.60m, 4-10 panels
            power_range = pv_specification.power_range_values
            power = float(random.choice(power_range))
            panel_angles = pv_specification.panel_angle_values
            panel_angle = random.choice(panel_angles)
            orientation = random.randint(pv_specification.orientation_min, pv_specification.orientation_max)
            pv_installation = PVInstallation(name='pv_' + house.name, id=str(uuid.uuid4()), power=power, angle=panel_angle,
                                             orientation=orientation, powerFactor=1.0, surfaceArea=surface_area) # ISIE

            pv_installation.geometry = Point(CRS="Simple", lon=236.0, lat=415.0)
            phase_grids = [asset for asset in house.asset if isinstance(asset, ElectricityNetwork)]
            if i in house_indices_bat:
                capacity = random.uniform(battery_specification.min_capacity_kwh, battery_specification.max_capacity_kwh) * 3.6e6
                fill_level = random.uniform(0.3, 0.7)  # fraction of total capacity
                charge_rate = random.uniform(battery_specification.min_charge_rate_kw, battery_specification.max_charge_rate_kw) * 1.0e3
                battery = Battery(name='battery_' + house.name, id=str(uuid.uuid4()),
                                  capacity=capacity,
                                  chargeEfficiency=0.95, dischargeEfficiency=0.95,
                                  fillLevel=fill_level,
                                  maxChargeRate=charge_rate, maxDischargeRate=charge_rate,
                                  powerFactor=1.0)
            for grid in phase_grids:
                self.add_producing_asset_to_other_asset(pv_installation, grid, house)
                if i in house_indices_bat:
                    self.add_consuming_asset_to_other_asset(battery, grid, house)


    def connect_heating_demand_heatpump_to_profile(self, heatpump : HeatPump, dhw_profile_name : str):
        if len(self.heat_profiles_mapping) > 0:
            meta_data = self.heat_profiles_mapping[dhw_profile_name]
            connected_to = meta_data.ports[meta_data.index_to_pick]
            out_port = OutPort(id=str(uuid.uuid4()), connectedTo=[connected_to])
            connected_to.connectedTo.append(out_port)
            heatpump.port.append(out_port)
            amount_of_profiles = len(self.heat_profiles_mapping[dhw_profile_name].ports)
            self.heat_profiles_mapping[dhw_profile_name].index_to_pick = (self.heat_profiles_mapping[dhw_profile_name].index_to_pick + 1) % amount_of_profiles
        else:
            logging.warning("No heat profiles loaded so not connecting hot water profiles")


    def connect_base_load_to_econnection(self, econnection : EConnection):
        if len(self.base_load_profiles.ports) > 0:
            port = self.base_load_profiles.ports[self.base_load_profiles.index_to_pick]
            self.base_load_profiles.index_to_pick = (self.base_load_profiles.index_to_pick + 1) % len(self.base_load_profiles.ports)
            phase_grids = [asset for asset in econnection.eContainer().asset if isinstance(asset, ElectricityNetwork)]
            phase_port = random.choice(phase_grids).port[1]
            phase_port.connectedTo.append(port)
            port.connectedTo.append(phase_port)
        else:
            logging.warning("No heat profiles loaded so not connecting base load profiles to econnection")


    def add_heat_pump_to_houses(self, fraction_houses_hp : float):
        houses = [esdl_element for esdl_element in self.energy_system.eAllContents() if isinstance(esdl_element, Building)]
        n_houses = len(houses)
        n_hp = round(fraction_houses_hp * n_houses)
        # Generate random house indices
        house_indices_hp = random.sample(range(0, n_houses), n_hp)

        # add pv to all phases for now
        for i in house_indices_hp:
            house = houses[i]
            phase_grids = [asset for asset in house.asset if isinstance(asset, ElectricityNetwork)]

            possible_nominal_powers = [2.0, 2.5, 3.0]

            nominal_power = random.choice(possible_nominal_powers) * 1000

            # add heat pump
            heat_pump = HeatPump(name='hp_' + house.name, id=str(uuid.uuid4()), power=nominal_power, powerFactor=0.98,
                                 assetType='air_water')

            self.connect_heating_demand_heatpump_to_profile(heat_pump, "test_name_hw")
            self.connect_heating_demand_heatpump_to_profile(heat_pump, "test_name_sh")

            # add to a random phase
            phase = random.randint(0, len(phase_grids) - 1)
            self.add_producing_asset_to_other_asset(heat_pump, phase_grids[phase], house)


    def add_econnection_information(self, fraction_houses_dyn : float):
        houses = [esdl_element for esdl_element in self.energy_system.eAllContents() if
                  isinstance(esdl_element, Building)]
        n_houses = len(houses)
        n_dyn = round(fraction_houses_dyn * n_houses)
        house_indices_dyn = random.sample(range(0, n_houses), n_dyn)

        econnections = [esdl_element for esdl_element in self.energy_system.eAllContents() if
                        isinstance(esdl_element, EConnection)]
        counter_ems = 0
        for econnection in econnections:
            self.connect_base_load_to_econnection(econnection)
            if counter_ems in house_indices_dyn:
                econnection.description = 'dynamic_contract'
            else:
                econnection.description = 'fixed_contract'
            counter_ems += 1


    def connect_ev_profile_to_chargingstation(self, chargingstation : EVChargingStation, mobility_demand : MobilityDemand):
        out_port = OutPort(id=str(uuid.uuid4()), name="Out")
        chargingstation.port.append(out_port)

        out_port.connectedTo.append(mobility_demand.port[0])
        mobility_demand.port[0].connectedTo.append(out_port)


    def add_ev_chargingstation(self, fraction_houses_ev : float, ev_specification : EvSpecification):
        houses = [esdl_element for esdl_element in self.energy_system.eAllContents() if isinstance(esdl_element, Building)]
        n_houses = len(houses)
        n_ev = round(fraction_houses_ev * n_houses)
        # Generate random house indices
        house_indices_ev = random.sample(range(0, n_houses), n_ev)

        ev_entities_in_data = []
        if ev_specification.profile_file is not None and ev_specification.profile_file != '' and Path(ev_specification.profile_file).exists():
            data = pd.read_csv(ev_specification.profile_file)
            charging_stations = data[ev_specification.charging_station_identifier_column].unique()
            ev_entities_in_data = np.random.choice(charging_stations, size=n_ev)

        for i, house_index in enumerate(house_indices_ev):
            house = houses[house_index]
            phase_grids = [asset for asset in house.asset if isinstance(asset, ElectricityNetwork)]

            power_range = [3700, 11000]
            power = float(random.choice(power_range))
            annual_load = random.randint(1800000,4000000)
            powerfactor = 0.95  

            mobility_demand = None
            if len(ev_entities_in_data) > 0:
                entity = ev_entities_in_data[i]
                data_entity = data[data[ev_specification.charging_station_identifier_column] == entity] 
                mobility_demand = self.add_ev_profile(entity, data_entity, ev_specification)
                power = data_entity[ev_specification.charging_power_column].mean()
                annual_load = data_entity[ev_specification.energy_demand_column].sum()

            charging_station = EVChargingStation(name='chargingstation_' + house.name, id=str(uuid.uuid4()),
                                                      power=power, fullLoadHours=int(annual_load/power),
                                                      powerFactor=powerfactor, assetType='privateEV')  # , description=sessions_car_json)
            cut_off_charge_rate_3_pahses_kw = 3700
            if power > cut_off_charge_rate_3_pahses_kw:
                # Add to all phases
                for connection_ph in phase_grids:
                    self.add_consuming_asset_to_other_asset(charging_station, connection_ph, house)
            else:
                phase = random.randint(0, len(phase_grids) - 1)
                self.add_producing_asset_to_other_asset(charging_station, phase_grids[phase], house)

            if mobility_demand is not None:
                self.connect_ev_profile_to_chargingstation(charging_station, mobility_demand)



    def save_esdl(self):
        esh = EnergySystemHandler(energy_system=self.energy_system)
        input_path = Path(self.esdl_name)
        out_name = 'decorated_' + input_path.name
        esh.save(out_name)


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
    dhw_profiles = params.get(params_key, [])
    for profile in dhw_profiles:
        path = Path(profile["profile_file"])
        if path.exists():
            profile_name = profile.get("profile_name", default_profile_name)
            amount_of_profiles = profile.get("amount_of_profiles", -1)
            esdl_decorator.add_heat_profiles(path, amount_of_profiles, profile_name, profile_enum_type)
        else:
            logging.info(f"Skip adding {default_profile_name} profile because file {str(path)} does not exist")


def parse_base_load_profile(params : dict, esdl_decorator : EsdlBuilder):
    base_load_profiles = params.get('base_load_profiles', [])
    for profile in base_load_profiles:
        path = Path(profile["profile_file"])
        if path.exists():
            esdl_decorator.add_base_load_profiles(path, profile.get("normalize", False))
        else:
            logging.info(f"Skip adding base load profile because file {str(path)} does not exist")


def parse_market_data(params : dict, esdl_decorator : EsdlBuilder):
    da_market_data = params.get('da_market_data', 'df_da_prices_2023_fixed.csv')
    if isinstance(da_market_data, dict):
        path_market_data_file = Path(da_market_data.get('path', 'weather-data.csv'))
        if path_market_data_file.exists():
            price_column = da_market_data.get('price_column', 'Day-ahead Price [EUR/MWh]')
            price_unit = da_market_data.get('price_unit', 'EUR/MWh')
            esdl_decorator.add_da_market_timeseries_profile(path_market_data_file, price_column, price_unit)
        else:
            logging.info("Skip adding market data as the file was not found")


def parse_weather_data(params : dict, esdl_decorator : EsdlBuilder):
    weather_data = params.get('weather_data', '')
    if isinstance(weather_data, dict):
        weather_path = weather_data.get('path', 'weather-data.csv')
        weather_columns = {
            'soil_temperature': weather_data.get('soil_temperature_column', 'soil_temperature_celcius'),
            'solar_irradiance': weather_data.get('solar_irradiance_column', 'solar_radiation_W/m2'),
            'outside_temperature': weather_data.get('outside_temperature_column', 'air_temperature_celcius')
        }
        path_weather_file = Path(weather_path)
        if path_weather_file.exists():
            esdl_decorator.add_weather(path_weather_file, weather_columns)
        else:
            logging.info("Skip adding weather data as the file was not found")


def main() -> int:
    parser = argparse.ArgumentParser(description="Decorate an ESDL file using JSON parameters")
    parser.add_argument('esdl', help='Path to the input ESDL file')
    parser.add_argument('params', help='Path to a JSON file with parameters')
    args = parser.parse_args()

    try:
        with open(args.params, 'r', encoding='utf-8') as fh:
            params = json.load(fh)
    except Exception as e:
        logging.exception(f"Failed to load params file {args.params}: {e}")
        return 2

    pv_specification = PvSpecification.from_dict(params.get('pv_specification'))
    battery_specification = BatterySpecification.from_dict(params.get('battery_specification'))

    esdl_path = Path(args.esdl)
    if esdl_path.exists():
        esdl_decorator = EsdlBuilder(
            str(esdl_path),
            params.get('harmonize_profile_dates'),
        )
    else:
        logging.error(f"ESDL file {str(esdl_path)} does not exist")
        return 2

    parse_weather_data(params, esdl_decorator)

    parse_market_data(params, esdl_decorator)

    parse_heating_profile(params, 'dhw_profiles', 'other_domestic_hot_water', HeatDemandTypeEnum.from_string('HOT_TAPWATER'), esdl_decorator)

    parse_heating_profile(params, 'space_heating_profiles', 'other_space_heating', HeatDemandTypeEnum.from_string('SPACE_HEATING'), esdl_decorator)

    parse_base_load_profile(params, esdl_decorator)

    fraction_houses_hp = params.get('fraction_houses_hp', 0.0)
    fraction_houses_ev = params.get('fraction_houses_ev', 0.0)
    fraction_houses_dyn = params.get('fraction_houses_dyn', 0.0)
    esdl_decorator.add_pvs_and_batteries_to_houses(pv_specification, battery_specification)
    esdl_decorator.add_heat_pump_to_houses(fraction_houses_hp)
    ev_profile_params : EvSpecification =  EvSpecification.from_dict(params.get('ev_profiles'))
    esdl_decorator.add_ev_chargingstation(fraction_houses_ev, ev_profile_params)
    esdl_decorator.add_econnection_information(fraction_houses_dyn)
    esdl_decorator.save_esdl()

    return 0


if __name__ == "__main__":
    exit(main())
