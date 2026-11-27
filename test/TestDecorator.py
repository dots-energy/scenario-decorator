from datetime import datetime
from pathlib import Path
import pandas as pd
import unittest
from unittest.mock import patch

from esdl import Battery, Building, BuildingStructureInformation, EVChargingStation, ElectricityDemand, HeatDemandTypeEnum, HeatPump, HybridHeatPump, Measure, PVInstallation, TimeSeriesProfile

from dots_esdl_decorator.dataclasses import BaseLoadProfileSpecification, BatterySpecification, BuildingIsolationSpecification, EvProfileSpecification, EvSpecification, HeatProfileSpecification, HybridHeatpumpSpecification, PvSpecification, TouSpecification, WeatherDataSpecification
from dots_esdl_decorator.esdl_decorator import EsdlBuilder, parse_isolation_parameters

class Test(unittest.TestCase):

    def setUp(self):
        self.esdl_test_file_path = str(Path(__file__).parent / "input_files" / "test.esdl")
        self.da_prices_file = Path(__file__).parent / "input_files" / "da_prices_example.csv"
        self.weather_data_file = Path(__file__).parent / "input_files" / "weather-data.csv"
        self.esdl_decorator = EsdlBuilder(self.esdl_test_file_path, None, None, None, None)
        buildings = [e for e in self.esdl_decorator.energy_system.instance[0].area.asset if isinstance(e, Building)]
        self.n_buildings = len(buildings)
        self.default_weather_col_mapping = {
            'soil_temperature_column': 'soil_temperature_celcius',
            'solar_irradiance_column': 'solar_radiation_W/m2',
            'outside_temperature_column': 'air_temperature_celcius'
        }

    def get_amount_of_assets_with_type_in_building(self, asset_type):
        ret_val = 0
        for e in self.esdl_decorator.energy_system.instance[0].area.asset:
            if isinstance(e, Building):
                if any(isinstance(a, asset_type) for a in e.asset):
                    ret_val += 1
        return ret_val

    def test_save_esdl_uses_provided_output_path(self):
        output_path = Path("output") / "decorated.esdl"
        with patch("dots_esdl_decorator.esdl_decorator.EnergySystemHandler") as handler_class:
            self.esdl_decorator.save_esdl(output_path)

        handler_class.return_value.save.assert_called_once_with(str(output_path))

    def test_save_esdl_keeps_default_output_path(self):
        with patch("dots_esdl_decorator.esdl_decorator.EnergySystemHandler") as handler_class:
            self.esdl_decorator.save_esdl()

        handler_class.return_value.save.assert_called_once_with("decorated_test.esdl")

    def test_add_pvs_and_batteries_counts_houses(self):

        pv_specification = PvSpecification(0.5)
        battery_specification = BatterySpecification(0.1)

        self.esdl_decorator.add_pvs_and_batteries_to_houses(pv_specification, battery_specification)

        houses_with_pv = self.get_amount_of_assets_with_type_in_building(PVInstallation)
        houses_with_battery = self.get_amount_of_assets_with_type_in_building(Battery)

        expected_pv = round(pv_specification.fraction_houses_pv * self.n_buildings)
        expected_batt = round(battery_specification.fraction_houses_pv_battery * expected_pv)
        self.assertEqual(houses_with_pv, expected_pv)
        self.assertEqual(houses_with_battery, expected_batt)

    def test_add_hp_counts_houses(self):

        fraction_houses_hp = 0.5
        hybrid_heatpump_specification = HybridHeatpumpSpecification(
            fraction_houses_hhp=0.5,
            gas_heater_efficiency=0.91,
            gass_thermal_power_mean=16000.0,
            gass_thermal_power_std=0.0,
        )

        self.esdl_decorator.add_heat_pump_to_houses(fraction_houses_hp, hybrid_heatpump_specification, ['profile1', 'profile2'])

        houses_with_heatpump = self.get_amount_of_assets_with_type_in_building(HeatPump)
        houses_with_heatpump_hhp = self.get_amount_of_assets_with_type_in_building(HybridHeatPump)

        expected_hp = round(fraction_houses_hp * self.n_buildings)
        expected_hpp = round(hybrid_heatpump_specification.fraction_houses_hhp * self.n_buildings)
        self.assertEqual(houses_with_heatpump, expected_hp)
        self.assertEqual(houses_with_heatpump_hhp, expected_hpp)
        hybrid_heatpumps = [
            asset
            for building in self.esdl_decorator.energy_system.eAllContents()
            if isinstance(building, Building)
            for asset in building.asset
            if isinstance(asset, HybridHeatPump)
        ]
        self.assertTrue(all(asset.gasHeaterEfficiency == 0.91 for asset in hybrid_heatpumps))
        self.assertTrue(all(asset.gasHeaterThermalPower == 16000.0 for asset in hybrid_heatpumps))

    def test_add_ev_counts_houses(self):

        fraction_houses_ev = 0.5

        self.esdl_decorator.add_ev_chargingstation(EvSpecification(fraction_houses_ev), None)

        houses_with_ev = self.get_amount_of_assets_with_type_in_building(EVChargingStation)

        expected_ev = round(fraction_houses_ev * self.n_buildings)
        self.assertEqual(houses_with_ev, expected_ev)

    def test_add_weather_data(self):

        spec = WeatherDataSpecification(self.weather_data_file, **self.default_weather_col_mapping)
        self.esdl_decorator.add_weather(spec)

        expected_irradiance_values = [2, 1, 1, 1, 1, 2, 2, 2, 2, 2, 1, 1, 2, 1, 1, 1, 2, 2, 2, 1, 2, 1, 1, 2]
        expected_soil_temperature_values = [9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7, 9.7]
        expected_air_temperature_values = [15.5, 15.5, 15.4, 15.3, 15.2, 15.3, 15.2, 15.3, 15.3, 15.3, 15.1, 15.1, 14.9, 14.9, 14.8, 14.7, 14.8, 14.7, 14.7, 14.7, 14.9, 14.7, 14.8, 14.8]

        irradiance_profile : TimeSeriesProfile = self.esdl_decorator.energy_system.energySystemInformation.environmentalProfiles.solarIrradianceProfile
        soil_temperature_profile : TimeSeriesProfile = self.esdl_decorator.energy_system.energySystemInformation.environmentalProfiles.soilTemperatureProfile
        air_temperature_profile : TimeSeriesProfile = self.esdl_decorator.energy_system.energySystemInformation.environmentalProfiles.outsideTemperatureProfile

        self.assertListEqual(irradiance_profile.values, expected_irradiance_values)
        self.assertEqual(irradiance_profile.startDateTime, datetime.strptime('2022-12-31T23:50:00Z', '%Y-%m-%dT%H:%M:%S%z'))
        self.assertEqual(irradiance_profile.timestep, 600)
        self.assertListEqual(soil_temperature_profile.values, expected_soil_temperature_values)
        self.assertEqual(soil_temperature_profile.startDateTime, datetime.strptime('2022-12-31T23:50:00Z', '%Y-%m-%dT%H:%M:%S%z'))
        self.assertEqual(soil_temperature_profile.timestep, 600)
        self.assertListEqual(air_temperature_profile.values, expected_air_temperature_values)
        self.assertEqual(air_temperature_profile.startDateTime, datetime.strptime('2022-12-31T23:50:00Z', '%Y-%m-%dT%H:%M:%S%z'))
        self.assertEqual(air_temperature_profile.timestep, 600)

    def test_add_building_isolation(self):
        isolation_file = Path(__file__).parent / "input_files" / "building_isolation_params.csv"
        specification = BuildingIsolationSpecification(
            str(isolation_file),
            "ID",
            "rcFloor",
            "rcRoof",
            "rcWall",
            "uDoor",
            "uWindow",
            "heatPumpThermalPower",
            "sh_buffer_volume",
            "dhw_buffer_volume",
            "hybridheatPumpThermalPower",
            "hhp_sh_buffer_volume"
        )
        buildings = [asset for asset in self.esdl_decorator.energy_system.eAllContents() if isinstance(asset, Building)]
        for building in buildings:
            building.assetType = "vrijstaande woning_before_1964"

        self.esdl_decorator.add_building_isolation(specification)

        self.assertEqual(len(buildings), self.n_buildings)
        self.assertTrue(all(len(building.buildinginformation) == 2 for building in buildings))
        building_information : BuildingStructureInformation = buildings[0].buildinginformation[1]
        self.assertIsInstance(building_information, BuildingStructureInformation)
        self.assertAlmostEqual(building_information.rcFloor, 3.5)
        self.assertAlmostEqual(building_information.rcRoof, 3.5)
        self.assertAlmostEqual(building_information.rcWall, 1.7)
        self.assertAlmostEqual(building_information.uDoor, 1.4)
        self.assertAlmostEqual(building_information.uWindow, 1.4)

    def test_add_market_data(self):

        self.esdl_decorator.add_market_data(self.da_prices_file, 'Day-ahead Price [EUR/MWh]', "EUR/MWh", 0.0)

        expected_market_values = [-3.61, -3.61, -3.61, -3.61, -1.46, -1.46, -1.46, -1.46, -1.52, -1.52, -1.52, -1.52, -5.0, -5.0, -5.0, -5.0, -4.6, -4.6, -4.6, -4.6, -4.05, -4.05, -4.05, -4.05]

        market_profile : TimeSeriesProfile = self.esdl_decorator.energy_system.services.service[0].marketPrice

        self.assertListEqual(market_profile.values, expected_market_values)
        self.assertEqual(market_profile.startDateTime, datetime.strptime('2023-01-01 00:00:00', '%Y-%m-%d %H:%M:%S'))
        self.assertEqual(market_profile.timestep, 900)

    def test_add_dhw_profiles(self):
        test_profiles_file = Path(__file__).parent / "input_files" / "dhw_profiles_example.csv"
        heat_profile_specification = HeatProfileSpecification(test_profiles_file, "hw", 2, "kW")
        self.esdl_decorator.add_heat_profiles(heat_profile_specification, HeatDemandTypeEnum.from_string("HOT_TAPWATER"))
        heating_demands = self.esdl_decorator.heat_profiles_mapping['hw'].demands

        self.assertEqual(len(heating_demands), 2)
        self.assertTrue(all(demand.type == HeatDemandTypeEnum.from_string("HOT_TAPWATER") for demand in heating_demands))

    def test_add_sh_profiles(self):
        test_profiles_file = Path(__file__).parent / "input_files" / "sh_profiles_example.csv"
        sh_spec = HeatProfileSpecification(test_profiles_file, "sh", 2, "kW")
        self.esdl_decorator.add_heat_profiles(sh_spec, HeatDemandTypeEnum.from_string("SPACE_HEATING"))
        heating_demands = self.esdl_decorator.heat_profiles_mapping['sh'].demands
        heating_demands_18_degrees = [demand for demand in heating_demands if demand.minTemperature == 18 and demand.maxTemperature == 22]
        heating_demands_21_degrees = [demand for demand in heating_demands if demand.minTemperature == 21 and demand.maxTemperature == 25]
        self.assertEqual(len(heating_demands), 2)
        self.assertEqual(len(heating_demands_18_degrees), 1)
        self.assertEqual(len(heating_demands_21_degrees), 1)
        self.assertTrue(all(demand.type == HeatDemandTypeEnum.from_string("SPACE_HEATING") for demand in heating_demands))
        

    def test_add_ev_profiles(self):
        test_params = [
            # harmonize year,  household,       amount-of_sessions
            (None,            'Household0001', 134),
            (2055,            'Household0001', 131)
        ]
        for i in range(len(test_params)):
            test_param = test_params[i]
            with self.subTest(i=i, params = test_params[i]):
                esdl_decorator = EsdlBuilder(self.esdl_test_file_path, test_param[0], None, None, None)
                test_profiles_file = Path(__file__).parent / "input_files" / "ev_profiles_example.csv"
                df = pd.read_csv(test_profiles_file)
                ev_specification = EvProfileSpecification(test_profiles_file, "ConnectionStartDateTime", "ConnectionEndDateTime", "household", "Energy", "Power")
                df[ev_specification.connection_start_date_time_column] = pd.to_datetime(df[ev_specification.connection_start_date_time_column], format='ISO8601')
                df[ev_specification.connection_end_date_time_column] = pd.to_datetime(df[ev_specification.connection_end_date_time_column], format='ISO8601')
                df_household = df[df['household'] == test_param[1]]
                demand = esdl_decorator.add_ev_profile(test_param[1], df_household, ev_specification)
                date_time_profile = demand.port[1].profile[0]

                self.assertEqual(len(date_time_profile.element), test_param[2])


    def test_target_days_profiles(self):
        test_params = [
            50,
            2,
            200
        ]
        for i in range(len(test_params)):
            target_days = test_params[i]
            with self.subTest(i=i, params = test_params[i]):
                 esdl_decorator = EsdlBuilder(self.esdl_test_file_path, None, target_days, None, None)
                 test_profiles_file = Path(__file__).parent / "input_files" / "da_prices_example_lengthen_timeseries.csv"
                 esdl_decorator.add_market_data(test_profiles_file, "Day-ahead Price [EUR/MWh]", "EUR/MWh", 0.0)
                 market_profile : TimeSeriesProfile = esdl_decorator.energy_system.services.service[0].marketPrice
                 self.assertEqual(len(market_profile.values), target_days*24*4)


    def test_add_tou(self):
        test_tou_file = Path(__file__).parent / "input_files" / "tou_dataset.csv"
        self.esdl_decorator.add_tou_measure(TouSpecification(test_tou_file, 0.60, "from_tou_month_hour_val", "to_tou_month_hour_val", "tou_weight"))
        measures = [obj for obj in self.esdl_decorator.energy_system.eAllContents() if isinstance(obj, Measure)]
        self.assertEqual(len(measures), 1)
        self.assertEqual(len(measures[0].costInformation.variableOperationalCosts.element), 66)

    def test_add_base_load_profiles(self):
        test_profiles_file = Path(__file__).parent / "input_files" / "base_load_profiles_example.csv"
        profiles_df = pd.read_csv(test_profiles_file, index_col=0, parse_dates=True)
        baseload_profile_spec = BaseLoadProfileSpecification(test_profiles_file, True, "kW")
        self.esdl_decorator.add_base_load_profiles(baseload_profile_spec)

        e_demands = [obj for obj in self.esdl_decorator.energy_system.eAllContents() if isinstance(obj, ElectricityDemand)]

        self.assertEqual(len(e_demands), 2)

        for e_demand in e_demands:
            time_series_profile = e_demand.port[1].profile[0]
            total_value = float(e_demand.name.split(" ")[1])
            col_name = e_demand.description.split("_")[-1].split(",")[0]
            for value, expected in zip(time_series_profile.values, profiles_df[col_name]):
                self.assertAlmostEqual(value * total_value, expected, places=2)

    def test_harmonize_profile_dates(self):
        harmonize_year = 2050
        esdl_decorator = EsdlBuilder(self.esdl_test_file_path, harmonize_year, None, None, None)
        test_profiles_file = Path(__file__).parent / "input_files" / "da_prices_harmonize_test_example.csv"
        esdl_decorator.add_market_data(test_profiles_file, "Day-ahead Price [EUR/MWh]", "EUR/MWh", 0.0)

        market_profile : TimeSeriesProfile = esdl_decorator.energy_system.services.service[0].marketPrice

        self.assertEqual(market_profile.startDateTime, datetime(harmonize_year, 3, 1, 0, 0))
        self.assertEqual(market_profile.values[0], 130.01)
        self.assertEqual(market_profile.values[-1], 124.22)

if __name__ == '__main__':
    unittest.main()
