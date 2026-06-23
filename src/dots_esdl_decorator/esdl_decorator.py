from pathlib import Path
import uuid
import argparse
import json
import logging

from esdl import Battery, Building, DateTimeProfile, EConnection, EVChargingStation, ElectricityNetwork, EnergyAsset, EnergyMarket, EnergySystemInformation, EnvironmentalProfiles, HeatPump, InPort, OutPort, PVInstallation, Parties, Party, Point, ProfileElement, Services, TimeSeriesProfile
import numpy as np
import pandas as pd
from datetime import timedelta
import random
from esdl.esdl_handler import EnergySystemHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

class EsdlDecorator:
    def __init__(self, esdl_name : str):
        esh = EnergySystemHandler()
        self.esdl_name = esdl_name
        self.energy_system = esh.load_file(esdl_name)
        self.area = self.energy_system.instance[0].area

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

    def add_weather(self, data_file : Path):
        energy_system_information = EnergySystemInformation(id=str(uuid.uuid4()))
        weather = EnvironmentalProfiles(name='weather', id=str(uuid.uuid4()))
        energy_system_information.environmentalProfiles = weather
        self.energy_system.energySystemInformation = energy_system_information
        df = pd.read_csv(data_file, index_col=0, parse_dates=True)
        weather.soilTemperatureProfile = self.create_time_series_profile_from_df(df, 'soil_temperature_celcius')
        weather.solarIrradianceProfile = self.create_time_series_profile_from_df(df, 'solar_radiation_W/m2')
        weather.outsideTemperatureProfile = self.create_time_series_profile_from_df(df, 'air_temperature_celcius')

    def add_da_market_timeseries_profile(self, day_ahead_prices_file: Path):
        da_market = EnergyMarket(name='DA-market', id=str(uuid.uuid4()))
        services = Services(id=str(uuid.uuid4()))
        # 01-01-2009 00:00
        df = pd.read_csv(day_ahead_prices_file, index_col=0, parse_dates=True, date_format='%Y-%m-%d %H:%M:%S')
        print(df.index.dtype)
        df.sort_index(ascending=True)

        da_price_datetime_profile = self.create_time_series_profile_from_df(df, 'Day-ahead Price [EUR/MWh]')

        da_market.marketPrice = da_price_datetime_profile
        services.service.append(da_market)
        self.energy_system.services = services


    def add_pvs_and_batteries_to_houses(self, fraction_houses_pv : float, fraction_houses_pv_battery : float):
        houses = [esdl_element for esdl_element in self.energy_system.eAllContents() if isinstance(esdl_element, Building)]
        n_houses = len(houses)
        n_pv = round(fraction_houses_pv * n_houses)
        n_bat = round(fraction_houses_pv_battery * n_pv)

        random.seed(0)
        house_indices_pv = random.sample(range(0, n_houses), n_pv)
        house_indices_bat = random.sample(house_indices_pv, n_bat)

        for i in house_indices_pv:
            house = houses[i]
            surface_area = random.randint(6, 16)  # 1 panel 1mx1.60m, 4-10 panels
            power_range = [2500,2750, 3000, 3250, 3500]
            power = float(random.choice(power_range))
            panel_angles = [15, 20, 25, 30]
            panel_angle = random.choice(panel_angles)
            orientation = random.randint(90,270)
            pv_installation = PVInstallation(name='pv_' + house.name, id=str(uuid.uuid4()), power=power, angle=panel_angle,
                                             orientation=orientation, powerFactor=1.0, surfaceArea=surface_area) # ISIE

            pv_installation.geometry = Point(CRS="Simple", lon=236.0, lat=415.0)
            phase_grids = [asset for asset in house.asset if isinstance(asset, ElectricityNetwork)]
            if i in house_indices_bat:
                capacity = random.uniform(10.0, 16.0) * 3.6e6
                fill_level = random.uniform(0.3, 0.7)  # fraction of total capacity
                charge_rate = random.uniform(5.0, 7.5) * 1.0e3
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
        try:
            input_path = Path(self.esdl_name)
            out_name = 'decorated_' + input_path.name
        except Exception:
            out_name = 'decorated_' + str(self.esdl_name)
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

def main():
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

    fraction_houses_pv = params.get('fraction_houses_pv', 0.0)
    fraction_houses_pv_battery = params.get('fraction_houses_pv_battery', 0.0)
    fraction_houses_hp = params.get('fraction_houses_hp', 0.0)
    fraction_houses_ev = params.get('fraction_houses_ev', 0.0)
    fraction_houses_dyn = params.get('fraction_houses_dyn', 0.0)

    weather_file = params.get('weather_file', 'weather-data.csv')
    da_market_file = params.get('da_market_file', 'df_da_prices_2023_fixed.csv')

    esdl_path = Path(args.esdl)
    if esdl_path.exists():
        esdl_decorator = EsdlDecorator(str(esdl_path))
    else:
        logging.error(f"ESDL file {str(esdl_path)} does not exist")
        return 2

    path_weather_file = Path(weather_file)
    if path_weather_file.exists():
        esdl_decorator.add_weather(path_weather_file)
    else:
        logging.info("Skip adding weather data as the file was not found")

    path_market_data_file = Path(da_market_file)
    if path_weather_file.exists():
        esdl_decorator.add_da_market_timeseries_profile(path_market_data_file)
    else:
        logging.info("Skip adding market data as the file was not found")

    esdl_decorator.add_pvs_and_batteries_to_houses(fraction_houses_pv, fraction_houses_pv_battery)
    esdl_decorator.add_heat_pump_to_houses(fraction_houses_hp)
    esdl_decorator.add_ev_chargingstation(fraction_houses_ev)
    esdl_decorator.add_econnection_information(fraction_houses_dyn)

    esdl_decorator.save_esdl()

    return 0

if __name__ == "__main__":
    exit(main())
