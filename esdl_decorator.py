import uuid
from typing import List
import json

from esdl import *
import pandas as pd
from pyecore.resources import ResourceSet, URI
from datetime import datetime, timedelta
import random
from esdl.esdl_handler import EnergySystemHandler
from base64 import b64encode


class EsdlDecorator:
    def __init__(self, esdl_name):
        rset_existing = ResourceSet()
        resource_existing = rset_existing.get_resource(URI(esdl_name))
        self.esdl_name = esdl_name
        self.energy_system = resource_existing.contents[0]
        self.area = self.energy_system.instance[0].area

    def add_dso(self):
        dso = Party(name='DSO', id=str(uuid.uuid4()))
        parties = Parties()
        parties.party.append(dso)
        self.energy_system.parties = parties

    def add_bandwidth_tariff(self, power_bandwidth: float, cost_bandwidth: float):
        # Add bandwidth tariff
        measures = Measures(id=str(uuid.uuid4()), name='measures')
        # add power
        bandwidth_tariff = Measure(id=str(uuid.uuid4()), name='dynamic bandwidth tariff', description=str(power_bandwidth))
        # add power
        # restriction = MinimumLabelRestriction(name='restriction', id=str(uuid.uuid4()), description=str(power_bandwidth))
        # bandwidth_tariff.restriction.append(restriction)
        # add costs
        cost_bw_value = SingleValue(id=str(uuid.uuid4()), name='bandwidth_price', value=cost_bandwidth)
        cost_information = CostInformation(name='cost_information', id=str(uuid.uuid4()),
                                           variableOperationalAndMaintenanceCosts=cost_bw_value)
        bandwidth_tariff.costInformation = cost_information
        measures.measure.append(bandwidth_tariff)
        self.energy_system.measures = measures

    def add_weather(self):
        energy_system_information = EnergySystemInformation(id=str(uuid.uuid4()))
        weather = EnvironmentalProfiles(name='weather', id=str(uuid.uuid4()))
        energy_system_information.environmentalProfiles = weather
        self.energy_system.energySystemInformation = energy_system_information

    def add_da_market(self, start_date_simulation: datetime, time_step_seconds: float):
        da_market = EnergyMarket(name='DA-market', id=str(uuid.uuid4()))
        services = Services(id=str(uuid.uuid4()))

        # get da-prices
        df = pd.read_csv("df_da_prices_2020.csv", index_col=0, parse_dates=True)
        end_date_initial_values = self.calculate_end_date_initial_da_values(start_date_simulation)
        df_slice = df[start_date_simulation: end_date_initial_values].iloc[:-1]
        duration = end_date_initial_values - start_date_simulation
        assert len(df_slice) == int(
            duration.total_seconds() / time_step_seconds), "simulation and data range do not overlap"
        dates = df_slice.index
        values = df_slice.values[:, 0]

        # add the prices to a profile
        da_price_datetime_profile = DateTimeProfile()
        for i in range(len(df_slice)):
            profile_element_da_price = ProfileElement(from_=dates[i],
                                                      to=dates[i] + timedelta(seconds=time_step_seconds),
                                                      value=values[i]/1000)  # euro/kWh
            da_price_datetime_profile.element.append(profile_element_da_price)

        # add the market to the energy system
        da_market.marketPrice = da_price_datetime_profile
        services.service.append(da_market)
        self.energy_system.services = services

    def add_pvs_and_batteries_to_houses(self, fraction_houses_pv, fraction_houses_pv_battery):
        houses = [esdl_element for esdl_element in self.energy_system.eAllContents() if isinstance(esdl_element, Building)]
        n_houses = len(houses)
        n_pv = round(fraction_houses_pv * n_houses)
        n_bat = round(fraction_houses_pv_battery * n_pv)

        # Generate random house indices
        random.seed(0)
        house_indices_pv = random.sample(range(0, n_houses), n_pv)
        house_indices_bat = random.sample(house_indices_pv, n_bat)

        # add pv to all phases for now
        for i in house_indices_pv:
            house = houses[i]
            surface_area = random.randint(6, 16)  # 1 panel 1mx1.60m, 4-10 panels
            power_range = [2500,2750, 3000, 3250, 3500]
            power = float(random.choice(power_range))
            panel_angles = [15, 20, 25, 30]
            panel_angle = random.choice(panel_angles)
            orientation = random.randint(90,270)
            pv_installation = PVInstallation(name='pv_' + house.name, id=str(uuid.uuid4()), power=power, angle=panel_angle,
                                             orientation=orientation, powerFactor=1.0) # ISIE
            # pv_installation = PVInstallation(name='pv_' + house.name, id=str(uuid.uuid4()), panelEfficiency=0.20,
            #                                  surfaceArea=surface_area, powerFactor=1.0)
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

    def add_heat_pump_to_houses(self, fraction_houses_hp):
        houses = [esdl_element for esdl_element in self.energy_system.eAllContents() if isinstance(esdl_element, Building)]
        n_houses = len(houses)
        n_hp = round(fraction_houses_hp * n_houses)
        # Generate random house indices
        house_indices_hp = random.sample(range(0, n_houses), n_hp)

        # open df_houses
        df = pd.read_csv("df_houses_town.csv", index_col=0)
        n_house_types = len(df)

        # add pv to all phases for now
        for count, i in enumerate(house_indices_hp):
            house = houses[i]
            phase_grids = [asset for asset in house.asset if isinstance(asset, ElectricityNetwork)]

            # Add thermal properties to the house as asset type
            house_properties = df.iloc[count % len(df)]
            asset_type_dict = {
                'C_s': house_properties['Cs'] * 3.6e6,
                'C_i': house_properties['Ci'] * 3.6e6,
                'C_m': house_properties['Cm'] * 3.6e6,
                'C_e': house_properties['Ce'] * 3.6e6,
                'R_is': house_properties['Ris']/1000,
                'R_im': house_properties['Rim']/1000,
                'R_ie': house_properties['Rie']/1000,
                'R_ea': house_properties['Rea']/1000,
                'A_w': house_properties['Aw']
            }
            house.assetType = json.dumps(asset_type_dict)

            # Calculate dimensions of heat pump
            HTC_house = df.iloc[0]['HTC']  # Heat Transfer Coefficient [kW/K]
            constant_power_needed = HTC_house * 25.0  # At about -5 C below zero [kW]
            possible_nominal_powers = [2.0, 2.5, 3.0]
            # calculate distances between needed and available nominal powers and select power with smallest distance
            distances = [abs(p_nom - constant_power_needed) for p_nom in possible_nominal_powers]
            nominal_power = possible_nominal_powers[distances.index(min(distances))] * 1000
            buffer_size = 20 * nominal_power / 1000  # rule of thumb [L]
            buffer_capacitance = buffer_size * 4183

            buffer_temp_set = 40.0
            buffer_temp_min = 25.0
            buffer_temp_max = 65.0
            buffer_temp_0 = buffer_temp_set + random.uniform(-10, 10)

            house_temp_set = random.choice([18.5, 19.0, 19.5, 20.0, 20.5, 21.0, 21.5])
            house_temp_min = house_temp_set - 0.8
            house_temp_max = house_temp_set + 0.8
            house_temp_0 = house_temp_set + random.uniform(-0.4, 0.4)

            description_dict = {'buffer_capacitance': buffer_capacitance,
                                'buffer_temp_set': buffer_temp_set,
                                'buffer_temp_min': buffer_temp_min,
                                'buffer_temp_max': buffer_temp_max,
                                'buffer_temp_0': buffer_temp_0,
                                'buffer_temp_hor': buffer_temp_set,
                                'house_temp_set': house_temp_set,
                                'house_temp_min': house_temp_min,
                                'house_temp_max': house_temp_max,
                                'house_temp_0': house_temp_0,
                                'house_temp_hor': house_temp_set}

            # add heat pump
            heat_pump = HeatPump(name='hp_' + house.name, id=str(uuid.uuid4()), power=nominal_power, powerFactor=0.98,
                                 assetType='air_water') # description=json.dumps(description_dict))

            # add to a random phase
            phase = random.randint(0, len(phase_grids) - 1)
            self.add_producing_asset_to_other_asset(heat_pump, phase_grids[phase], house)

    # Added for ISIE:
    def add_building_information(self, fraction_houses_dyn):
        houses = [esdl_element for esdl_element in self.energy_system.eAllContents() if
                  isinstance(esdl_element, Building)]
        n_houses = len(houses)
        random.seed(42)
        n_dyn = round(fraction_houses_dyn * n_houses)
        house_indices_dyn = random.sample(range(0, n_houses), n_dyn)

        asset_types = ['vrijst', '2_1kap', 'hoek', 'tussen', 'maisonette', 'galerij', 'portiek', 'overig']
        energy_labels = ['LABEL_A', 'LABEL_B', 'LABEL_C', 'LABEL_D', 'LABEL_E', 'LABEL_F']

        houses = [
            esdl_element for esdl_element in self.energy_system.eAllContents()
            if isinstance(esdl_element, Building)
        ]

        for house in houses:
            house.assetType = random.choice(asset_types)
            house.energyLabel = random.choice(energy_labels)

        econnections = [esdl_element for esdl_element in self.energy_system.eAllContents() if
                        isinstance(esdl_element, EConnection)]
        building_numbers_dynamic = random.sample(range(n_houses), n_dyn)
        counter_ems = 0
        for econnection in econnections:
            if counter_ems in house_indices_dyn:
                econnection.description = 'dynamic_contract'
                print('dynamic_contract')
            else:
                econnection.description = 'fixed_contract'
                print('fixed_contract')
            counter_ems += 1


    def add_ev_chargingstation(self, fraction_houses_ev):
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
            # max_charge_rate = item_dict['Home'][self.id].gmtypepower[loadcount] * 1e3
            # print(max_charge_rate)
            powerfactor = 0.95  # TODO: check whether realistic
            # powerfactor = item_dict['GM'][load].powerfactor
            charging_station = EVChargingStation(name='chargingstation_' + house.name, id=str(uuid.uuid4()),
                                                      power=power, fullLoadHours=int(annual_load/power),
                                                      powerFactor=powerfactor, assetType='privateEV')  # , description=sessions_car_json)
            # Add EV to 1 phase if the charge rate is 3.7kW and to three phases otherwise
            if power > 3700:
                # Add to all phases
                for connection_ph in phase_grids:
                    self.add_consuming_asset_to_other_asset(charging_station, connection_ph, house)
            else:
                # add to random phase
                # TODO: note that heat pump can be on the same phase as EV
                phase = random.randint(0, len(phase_grids) - 1)
                self.add_producing_asset_to_other_asset(charging_station, phase_grids[phase], house)



    def save_and_print_esdl(self):
        rset = ResourceSet()
        resource = rset.create_resource(URI('decorated_' + self.esdl_name))
        resource.append(self.energy_system)
        resource.save()

        esh = EnergySystemHandler(energy_system=self.energy_system)
        esh.resource = resource
        esdl_string = esh.to_string()

        esdl_string_utf = esdl_string.encode('utf-8')
        encoded_string = b64encode(esdl_string_utf)
        encoded_string_utf = encoded_string.decode('utf-8')
        print("Encoded esdl string:")
        print(encoded_string_utf)

    @staticmethod
    def calculate_end_date_initial_da_values(start_date: datetime) -> datetime:
        time_000 = datetime(start_date.year, start_date.month, start_date.day + 1, 0, 0)
        hour_start_date = start_date.hour
        if (0 <= hour_start_date) and (hour_start_date <= 12):
            return time_000
        else:
            return time_000 + timedelta(days=1.0)

    @staticmethod
    def add_consuming_asset_to_other_asset(asset, other_asset, background):
        # background refers to the non-energy asset to which the new asset is added (area, house, etc.)
        background.asset.append(asset)
        outport_other_asset = OutPort(id=str(uuid.uuid4()))
        other_asset.port.append(outport_other_asset)
        inport_asset = InPort(id=str(uuid.uuid4()), connectedTo=[outport_other_asset])
        asset.port.append(inport_asset)

    @staticmethod
    def add_producing_asset_to_other_asset(asset, other_asset, background):
        # background refers to the non-energy asset to which the new asset is added (area, house, etc.)
        background.asset.append(asset)
        inport_other_asset = InPort(id=str(uuid.uuid4()))
        other_asset.port.append(inport_other_asset)
        outport_asset = OutPort(id=str(uuid.uuid4()), connectedTo=[inport_other_asset])
        asset.port.append(outport_asset)


if __name__ == "__main__":
    # standard parameters
    time_step_seconds = 900

    # simulation specific parameters
    simulation_start_date = datetime(2020, 9, 8, 0)
    power_bandwidth = 5.0e3  # W
    cost_bandwidth = 0.01  # euro/kWh
    fraction_houses_pv = 1  # fraction of houses having pv
    fraction_houses_pv_battery = 0.8 # fraction of houses with pv having a battery
    fraction_houses_hp = 0.8  # fraction of houses with hp
    fraction_houses_ev = 0.8
    fraction_houses_dyn = 1

    esdl_decorator = EsdlDecorator('network.esdl')
    # esdl_decorator.add_dso()
    # esdl_decorator.add_weather()
    # esdl_decorator.add_bandwidth_tariff(power_bandwidth, cost_bandwidth)
    # esdl_decorator.add_da_market(simulation_start_date, time_step_seconds)
    esdl_decorator.add_pvs_and_batteries_to_houses(fraction_houses_pv, fraction_houses_pv_battery)
    esdl_decorator.add_heat_pump_to_houses(fraction_houses_hp)
    esdl_decorator.add_ev_chargingstation(fraction_houses_ev)
    esdl_decorator.add_building_information(fraction_houses_dyn)

    esdl_decorator.save_and_print_esdl()







