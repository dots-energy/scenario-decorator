from pathlib import Path
import uuid
import argparse
import json
import logging

from esdl import Battery, Building, EConnection, EVChargingStation, ElectricityNetwork, EnergyAsset, EnergyMarket, EnergySystemInformation, EnvironmentalProfiles, HeatPump, HeatingDemand, InPort, OutPort, PVInstallation, Parties, Party, Point, Services, TimeSeriesProfile, HeatDemandTypeEnum
import numpy as np
import pandas as pd
from datetime import timedelta
import random
from esdl.esdl_handler import EnergySystemHandler

from dots_esdl_decorator.dataclasses import BatterySpecification, DhwProfileMetaData, PvSpecification

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

class EsdlDecorator:
    def __init__(self, esdl_name : str):
        esh = EnergySystemHandler()
        self.esdl_name = esdl_name
        self.energy_system = esh.load_file(esdl_name)
        self.area = self.energy_system.instance[0].area
        self.dhw_profiles_mapping :dict[str, DhwProfileMetaData] = {} 

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
            timeseries_profile = TimeSeriesProfile(startDateTime=min_date, timestep=delta_t)
            data_date = min_date
            prev_value = 0
            data = df[column_name].reset_index().to_numpy()
            i = 0 
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
                timeseries_profile.values.append(float(value))
                data_date += timedelta(seconds=delta_t)
            return timeseries_profile

        logging.warning(f"column {column_name} not found in provided input data")
        return TimeSeriesProfile()

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

    def add_da_market_timeseries_profile(self, day_ahead_prices_file: Path, price_column : str):
        da_market = EnergyMarket(name='DA-market', id=str(uuid.uuid4()))
        services = Services(id=str(uuid.uuid4()))
        df = pd.read_csv(day_ahead_prices_file, index_col=0, parse_dates=True, date_format='%Y-%m-%d %H:%M:%S')
        df.sort_index(ascending=True)

        da_price_datetime_profile = self.create_time_series_profile_from_df(df, price_column)

        da_market.marketPrice = da_price_datetime_profile
        services.service.append(da_market)
        self.energy_system.services = services

    def add_dhw_profiles(self, dhw_profile_file : Path, amount_of_profiles : int, dhw_profile_name : str):

        dhw_profiles = pd.read_csv(dhw_profile_file, index_col=0, parse_dates=True, date_format='%Y-%m-%d %H:%M:%S')
        column_choices = list(range(len(dhw_profiles.columns)))

        for i in range(amount_of_profiles):
            col_nr = random.choice(column_choices)
            column_choices.remove(col_nr)

            time_series_profile = self.create_time_series_profile_from_df(dhw_profiles, dhw_profiles.columns[col_nr])

            heating_demand = HeatingDemand(type=HeatDemandTypeEnum.from_string('HOT_TAPWATER'))
            if dhw_profile_name not in self.dhw_profiles_mapping:
                self.dhw_profiles_mapping[dhw_profile_name] = DhwProfileMetaData()
            esdl_dhw_profile_name = f"{dhw_profile_name}{len(self.dhw_profiles_mapping[dhw_profile_name].ports)}"

            heating_demand.name = esdl_dhw_profile_name
            in_port = InPort(id=str(uuid.uuid4()), name="In")
            heating_demand.port.append(in_port)
            heating_demand.port.append(OutPort(id=str(uuid.uuid4()), name="Out"))
            heating_demand.port[1].profile.append(time_series_profile)
            self.dhw_profiles_mapping[dhw_profile_name].ports.append(in_port)
            self.energy_system.instance[0].area.asset.append(heating_demand)


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

    def connect_dhw_heatpump_to_profile(self, heatpump : HeatPump, dhw_profile_name : str):
        if len(self.dhw_profiles_mapping) > 0:
            meta_data = self.dhw_profiles_mapping[dhw_profile_name]
            connected_to = meta_data.ports[meta_data.index_to_pick]
            out_port = OutPort(id=str(uuid.uuid4()), connectedTo=[connected_to])
            connected_to.connectedTo.append(out_port)
            heatpump.port.append(out_port)
            amount_of_profiles = len(self.dhw_profiles_mapping[dhw_profile_name].ports)
            self.dhw_profiles_mapping[dhw_profile_name].index_to_pick = (self.dhw_profiles_mapping[dhw_profile_name].index_to_pick + 1) % amount_of_profiles
        else:
            logging.warning("No domestic hot water profiles loaded so not connecting hot water profiles")

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
            
            self.connect_dhw_heatpump_to_profile(heat_pump, "test_name")

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
            if counter_ems in house_indices_dyn:
                econnection.description = 'dynamic_contract'
            else:
                econnection.description = 'fixed_contract'
            counter_ems += 1

    def add_ev_chargingstation(self, fraction_houses_ev : float):
        houses = [esdl_element for esdl_element in self.energy_system.eAllContents() if isinstance(esdl_element, Building)]
        n_houses = len(houses)
        n_ev = round(fraction_houses_ev * n_houses)
        # Generate random house indices
        house_indices_ev = random.sample(range(0, n_houses), n_ev)

        for count, i in enumerate(house_indices_ev):
            house = houses[i]
            phase_grids = [asset for asset in house.asset if isinstance(asset, ElectricityNetwork)]

            power_range = [3700, 11000]
            power = float(random.choice(power_range))
            annual_load = random.randint(1800000,4000000)
            powerfactor = 0.95  
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
    fraction_houses_hp = params.get('fraction_houses_hp', 0.0)
    fraction_houses_ev = params.get('fraction_houses_ev', 0.0)
    fraction_houses_dyn = params.get('fraction_houses_dyn', 0.0)

    esdl_path = Path(args.esdl)
    if esdl_path.exists():
        esdl_decorator = EsdlDecorator(str(esdl_path))
    else:
        logging.error(f"ESDL file {str(esdl_path)} does not exist")
        return 2

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

    da_market_data = params.get('da_market_data', 'df_da_prices_2023_fixed.csv')
    if isinstance(da_market_data, dict):
        path_market_data_file = Path(da_market_data.get('path', 'weather-data.csv'))
        if path_weather_file.exists():
            price_column = da_market_data.get('price_column', 'Day-ahead Price [EUR/MWh]')
            esdl_decorator.add_da_market_timeseries_profile(path_market_data_file, price_column)
        else:
            logging.info("Skip adding market data as the file was not found")

    dhw_profiles = params.get('dhw_profiles', [])
    for profile in dhw_profiles:
        path = Path(profile["profile_file"])
        if path.exists():
            profile_name = profile["profile_name"]
            amount_of_profiles = profile["amount_of_profiles"]
            esdl_decorator.add_dhw_profiles(path, amount_of_profiles, profile_name)
        else:
            logging.info(f"Skip adding domestic hot water profile because file {str(path)} does not exist")

    esdl_decorator.add_pvs_and_batteries_to_houses(pv_specification, battery_specification)
    esdl_decorator.add_heat_pump_to_houses(fraction_houses_hp)
    esdl_decorator.add_ev_chargingstation(fraction_houses_ev)
    esdl_decorator.add_econnection_information(fraction_houses_dyn)

    esdl_decorator.save_esdl()

    return 0

if __name__ == "__main__":
    exit(main())
