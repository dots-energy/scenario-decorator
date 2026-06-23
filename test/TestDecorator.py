from datetime import datetime
from pathlib import Path
import unittest
from pathlib import Path

from esdl import Battery, Building, EVChargingStation, HeatPump, PVInstallation, TimeSeriesProfile

from dots_esdl_decorator.esdl_decorator import EsdlDecorator

class Test(unittest.TestCase):

    def setUp(self):
        esdl_test_file_path = Path(__file__).parent / "input_files" / "test.esdl"
        self.da_prices_file = Path(__file__).parent / "input_files" / "df_da_prices_2023_fixed.csv"
        self.weather_data_file = Path(__file__).parent / "input_files" / "weather-data.csv"
        self.esdl_decorator = EsdlDecorator(str(esdl_test_file_path))
        buildings = [e for e in self.esdl_decorator.energy_system.instance[0].area.asset if isinstance(e, Building)]
        self.n_buildings = len(buildings)

    def get_amount_of_assets_with_type_in_building(self, asset_type):
        ret_val = 0
        for e in self.esdl_decorator.energy_system.instance[0].area.asset:
            if isinstance(e, Building):
                if any(isinstance(a, asset_type) for a in e.asset):
                    ret_val += 1
        return ret_val

    def tearDown(self):
        return super().tearDown()

    def test_add_pvs_and_batteries_counts_houses(self):

        fraction_houses_pv = 0.5
        fraction_houses_pv_battery = 0.1

        self.esdl_decorator.add_pvs_and_batteries_to_houses(fraction_houses_pv, fraction_houses_pv_battery)

        houses_with_pv = self.get_amount_of_assets_with_type_in_building(PVInstallation)
        houses_with_battery = self.get_amount_of_assets_with_type_in_building(Battery)

        expected_pv = round(fraction_houses_pv * self.n_buildings)
        expected_batt = round(fraction_houses_pv_battery * expected_pv)
        self.assertEqual(houses_with_pv, expected_pv)
        self.assertEqual(houses_with_battery, expected_batt)

    def test_add_hp_counts_houses(self):

        fraction_houses_hp = 0.5

        self.esdl_decorator.add_heat_pump_to_houses(fraction_houses_hp)

        houses_with_heatpump = self.get_amount_of_assets_with_type_in_building(HeatPump)

        expected_hp = round(fraction_houses_hp * self.n_buildings)
        self.assertEqual(houses_with_heatpump, expected_hp)

    def test_add_ev_counts_houses(self):

        fraction_houses_ev = 0.5

        self.esdl_decorator.add_ev_chargingstation(fraction_houses_ev)

        houses_with_ev = self.get_amount_of_assets_with_type_in_building(EVChargingStation)

        expected_hp = round(fraction_houses_ev * self.n_buildings)
        self.assertEqual(houses_with_ev, expected_hp)

    def test_add_weather_data(self):

        self.esdl_decorator.add_weather(self.weather_data_file)

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

    def test_add_market_data(self):

        self.esdl_decorator.add_da_market_timeseries_profile(self.da_prices_file)

        expected_market_values = [-3.61, -3.61, -3.61, -3.61, -1.46, -1.46, -1.46, -1.46, -1.52, -1.52, -1.52, -1.52, -5.0, -5.0, -5.0, -5.0, -4.6, -4.6, -4.6, -4.6, -4.05, -4.05, -4.05, -4.05]

        market_profile : TimeSeriesProfile = self.esdl_decorator.energy_system.services.service[0].marketPrice

        self.assertListEqual(market_profile.values, expected_market_values)
        self.assertEqual(market_profile.startDateTime, datetime.strptime('2023-01-01 00:00:00', '%Y-%m-%d %H:%M:%S'))
        self.assertEqual(market_profile.timestep, 900)


if __name__ == '__main__':
    unittest.main()

