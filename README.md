# Scenario-Decorator
ESDL decorator to add scenario aspects (asset penetration, weather data, market data, etc) to infrastructure ESDL files. 

The tool takes an ESDL file containing an electricity network and connections connected to the electricity network. Usable networks in ESDL format can be found in the example repository. Using a json file specifying the parameters for decoration the tool outputs an ESDL file containing the original network plus weather and market data as well as assets connected to the connections.
Examples for input datasets can be found in test/inputfules.

## Parameters
```json
{
    "pv_specification" : {
        "fraction_houses_pv" : 0.28, // fraction of houses that have rooftop pv
        "surface_area_min" : 6, // the minimum surface area of the installed rooftop pv
        "surface_area_max" : 16 // the maximum surface area of the installed rooftop pv
    },
    "battery_specification" : {
        "fraction_houses_pv_battery" : 0.06, // fraction of houses with rooftop pv that have a battery
        "capacity_kwh_mean" : 17.68, // the mean capacity of the installed home batteries in kwh
        "capacity_kwh_std" : 1.32, // the standard deviation of the capacity the installed home batteries in kwh
        "efficiency" : 0.9, // efficiency of all the installed home batteries
        "power_kw_to_energy_kwh_ratio" : 4 // ratio between capacity and charge rate of the batteries
    },
    "harmonize_profiles_to_year" : 2060, // year to harmonize all the data to
    "fraction_houses_hp" : 0.23, // fraction of houses that have a heatpump
    "fraction_houses_hhp" : 0.77, // fraction of houses that have a hybridheatpump
    "fraction_houses_ev" : 0.3, // fraction of houses that have an electric vehicle charging station
    "gass_price_eur_m3" : 1.0, // the assumed global gass price per m3
    "defalut_lon" : 51.532534, // default longitude for the location of rooftop pv
    "defalut_lat" : 3.882267, // default latitude for the location of rooftop pv
    "weather_data" : {
        "path": "test/input_files/weather-data.csv", // path to the weather data dataset
        "soil_temperature_column": "soil_temperature_celcius", // column name of the soiltemperature
        "solar_irradiance_column": "solar_radiation_W/m2", // column name of the solar_irradiance_column
        "outside_temperature_column": "air_temperature_celcius", // column name of the air temperature
        "measure_data_location_lat" : 51.532534, // latitude of the location of the measured weather data
        "measure_data_location_lon" : 3.882267 // longitude of the location of the measured weather data
    },
    "da_market_data" : {
        "path": "test/input_files/df_da_prices_2023_fixed.csv", // path to the market data dataset
        "price_column" : "Day-ahead Price [EUR/MWh]", // column name of the day ahead price
        "price_unit" : "EUR/MWh" // Unit of the Day ahead price
    },
    "dhw_profiles" : [
        {
            "profile_name" : "test_name_hw", // name of the dhw profile
            "profile_file" : "test/input_files/dhw_profiles_example.csv", // path to the dhw profile
            "amount_of_profiles" : 5 // amount of profiles to use from the file
        }
    ],
    "space_heating_profiles" : [
        {
            "profile_name" : "test_name_sh", // name of the sh profile
            "profile_file" : "test/input_files/sh_profiles_example.csv", // path to the sh profile
            "amount_of_profiles" : 5  // amount of profiles to use from the file
        }
    ],
    "base_load_profiles" : [
        {
            "profile_file" : "test/input_files/base_load_profiles_example.csv", // path to the base load profiles
            "normalize" : false // boolean that states weather or not the profiles should be normalized
        }
    ],
    "ev_profiles" : {
        "profile_file" : "test/input_files/ev_profiles_example.csv", // path to the ev profiles dataset
        "connection_start_date_time_column" : "ConnectionStartDateTime", // column name of the arrival time of the ev
        "connection_end_date_time_column" : "ConnectionEndDateTime", // column name of the departure time of the ev
        "charging_station_identifier_column" : "household", // column name of the identifier of the profile
        "energy_demand_column" : "Energy", // column name of the energy demand of the ev
        "charging_power_column" : "Power" // column name of the power value the ev
    },
    "tou_specification" : {
      "profile_file" : "test/input_files/tou_tariff.csv", // path to tou profile dataset
      "from_date_time_col" : "from_tou_month_hour_val", // column name of from timestamp of the tou interval
      "to_date_time_col" : "to_tou_month_hour_val", // column name of to timestamp of the tou interval
      "value_col" : "tou_weight", // column name of the tou weight value
      "fixed_tou_rate_eur" : 0.60 // fixed rate in euro of time of use
    }
}
```
## Assumptions for data
format
base load power kw values
normalizes them in terms of the total

ev format from to energy and power and identifier
energy in kwh power in kw

date format ISO8601
filling missing values
todo:
document shifting values in case of harmonizing year

panel power rating based on efficiency and surface area see: https://www.heavengreenenergy.com/glossary/standard-test-conditions
panel orientation and angle based on: https://verdasol.nl/kennisbank/optimale-hoek-en-richting-voor-zonnepanelen/

document harmonizing length of profiles

## Installation
```
pip install dots-esdl-decorator
```
## Usage
Parameters must be configured using a json file an example can be found here. 
```
dots-esdl-decorator test/input_files/test.esdl example_params/params_example.json
```