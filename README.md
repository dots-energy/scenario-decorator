# Scenario-Decorator
ESDL decorator to add scenario aspects (asset penetration, weather data, market data, etc) to infrastructure ESDL files. 

The tool takes an ESDL file containing an electricity network and connections connected to the electricity network. Usable networks in ESDL format can be found in the example repository. Using a json file specifying the parameters for decoration the tool outputs an ESDL file containing the original network plus weather and market data as well as assets connected to the connections.
Examples for input datasets can be found in `test/input_files`.

## Parameters
Below an overview of all paramters and their description can be found. Some general parameters will be described after the overview.
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
    "target_days": 365, // the amount of days all the datasets should contain
    "fraction_houses_hp" : 0.23, // fraction of houses that have a heatpump
    "hybrid_heatpump_specification" : {
        "fraction_houses_hhp" : 0.77, // fraction of houses that have a hybridheatpump
        "gas_heater_efficiency" : 0.96, // efficiency of the hybrid heat pump gas heater
        "gass_thermal_power_mean" : 18000.0, // mean gas heater thermal power
        "gass_thermal_power_std" : 0.0 // standard deviation of gas heater thermal power
    },
    "econnection_specification" : {
        "fraction_houses_dyn" : 0.5, // fraction of houses with a dynamic energy contract
        "flat_rate_dyn" : 0.35, // flat rate for a dynamic contract typically the energy tax per kwh
        "static_price_contract" :  0.08, // the static price when having a fixed energy contract
        "fraction_houses_ems" : 0.5 // fraction of houses with an energy management system (ems)
    },
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
            "amount_of_profiles" : 5, // amount of profiles to use from the file
            "unit" : "kW" // unit of the profile values
        }
    ],
    "base_load_profiles" : [
        {
            "profile_file" : "test/input_files/base_load_profiles_example.csv", // path to the base load profiles
            "normalize" : false, // boolean that states weather or not the profiles should be normalized
            "unit" : "kW" // unit of the profile values
        }
    ],
    "ev_specification" : {
        "fraction_houses_ev" : 0.3, // fraction of houses that have an electric vehicle charging station
        "min_charge_rate_kw" : 4.2, // the minimal charge rate of the ev in KW
        "min_soc_percentage" : 0.3, // the minimal soc percentage an must always when implementing v2g behaviour
        "max_soc_kwh" : 75, // the maximum soc in kwh of the ev
        "efficiency" : 0.95 // the (dis)charge efficiency of the evs
    },
    "ev_profiles" : {
        "profile_file" : "test/input_files/ev_profiles_example.csv", // path to the ev profiles dataset
        "connection_start_date_time_column" : "ConnectionStartDateTime", // column name of the arrival time of the ev
        "connection_end_date_time_column" : "ConnectionEndDateTime", // column name of the departure time of the ev
        "charging_station_identifier_column" : "household", // column name of the identifier of the profile
        "energy_demand_column" : "Energy", // column name of the energy demand of the ev
        "unit" : "kWh", // unit of the energy_demand_column values
        "charging_power_column" : "Power" // column name of the power value the ev specified in kw
    },
    "tou_specification" : {
      "profile_file" : "test/input_files/tou_dataset.csv", // path to tou profile dataset
      "from_date_time_col" : "from_tou_month_hour_val", // column name of from timestamp of the tou interval
      "to_date_time_col" : "to_tou_month_hour_val", // column name of to timestamp of the tou interval
      "value_col" : "tou_weight", // column name of the tou weight value
      "fixed_tou_rate_eur" : 0.60 // fixed rate in euro of time of use
    },
    "building_isolation" : {
        "isolation_params_file" : "test/input_files/building_isolation_params.csv", // path to file containing isolation parameters
        "asset_type_col" : "ID", // column containing the assettype it needs to match
        "rcFloor_col" : "rcFloor", // Thermal insulation value of the floor in m²K/W.
        "rcRoof_col" : "rcRoof", // Thermal insulation value of the roof in m²K/W.
        "rcWall_col" : "rcWall", // Thermal insulation value of the walls in m²K/W.
        "uDoor_col" : "uDoor", // Heat transfer coefficient of the doors in W/m²K.
        "uWindow_col" : "uWindow", // Heat transfer coefficient of the windows in W/m²K.
        "heatPumpThermalPower_col" : "heatPumpThermalPower", // column name describing the power value of the heatpump in watts
        "sh_buffer_volume_col" : "sh_buffer_volume", // column name describing the volume of the space heating buffer in m3
        "dhw_buffer_volume_col" : "dhw_buffer_volume" // column name describing the volume of the hot water buffer in m3
    }
}
```
### Parameter `building_isolation`
This optional parameter adds building year and structure information to each building. The CSV must include an `ID` column whose value exactly matches each building's `assetType`. The configured `building_year_col` supplies `buildingYear`; the other configured columns supply `rcFloor`, `rcRoof`, `rcWall`, `uDoor`, and `uWindow` in the building's `BuildingStructureInformation`. If an asset type has multiple matching rows, the first row in the CSV is used. An example of the data format for building information can be found below:

| ID | type | buildingYear | rcFloor | rcRoof | rcWall | uDoor | uWindow | heatPumpThermalPower | sh_buffer_volume | dhw_buffer_volume |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| vrijstaande woning_before_1964 | vrijstaande woning | 1964 | 3.5 | 3.5 | 1.7 | 1.4 | 1.4 | 14000 | 280 | 200 |
| vrijstaande woning_1965_1974 | vrijstaande woning | 1970 | 3.5 | 3.5 | 1.7 | 1.4 | 1.4 | 14000 | 280 | 200 |
| vrijstaande woning_1975_1991 | vrijstaande woning | 1983 | 3.5 | 3.5 | 1.7 | 1.4 | 1.4 | 14000 | 280 | 200 |
| vrijstaande woning_1992_2005 | vrijstaande woning | 1998 | 3.5 | 3.5 | 2.5 | 1.4 | 1.4 | 14000 | 280 | 200 |

### Parameter `harmonize_profiles_to_year`
This parameter specifies the year all datasets should be harmonized to. Meaning that the year of the timestamp in the datasets will be transformed to the year specified by the parameter. Day of the week will be preserved meaning that values that are associated with a certain day of the week are still associated with the same day of the week after the transformation. Values that are skipped at the beginning will be appended at the end of the dataset. If no year is specified the datasets will be put in the esdl's as specified in the files.

For example, consider the below dataset and `harmonize_profiles_to_year` is set to `2050`. 
| time | day of week | value | 
| --- | ---: | ---: | 
| 2024-01-01T00:00:00Z | Monday | 1 |
| 2024-02-01T00:00:00Z | Tuesday | 2 |
| 2024-03-01T00:00:00Z | Wednesday | 3 |
| 2024-04-01T00:00:00Z | Thursday | 4 |
| 2024-05-01T00:00:00Z | Friday | 5 |
| 2024-06-01T00:00:00Z | Saturday | 6 |
| 2024-07-01T00:00:00Z | Sunday | 7 |

The dataset will be converted to the dataset depicted below. Because in 2024 1st of january is on a monday and in 2025 1st of january is on a wednesday, the data will now start at value 3. The skipped values at the beginning are now added the end of the dataset. See the example below:

| time | day of week | value | 
| --- | ---: | ---: | 
| 2025-01-01T00:00:00Z | Wednesday | 3 |
| 2025-02-01T00:00:00Z | Thursday | 4 |
| 2025-03-01T00:00:00Z | Friday | 5 |
| 2025-04-01T00:00:00Z | Saturday | 6 |
| 2025-05-01T00:00:00Z | Sunday | 7 |
| 2025-06-01T00:00:00Z | Monday | 1 |
| 2025-07-01T00:00:00Z | Tuesday | 2 |

### Parameters `target_days`
This parameter specifies the amount of days all the datasets should have. If a dataset does not have the required amount of days it will either be prolonged by repeating values or cut short to match the amount of days. 

For example consider the dataset below and `target_days` is set to 5.
| time | day of week | value | 
| --- | ---: | ---: | 
| 2024-01-01T00:00:00Z | Monday | 1 |
| 2024-02-01T00:00:00Z | Tuesday | 2 |
| 2024-03-01T00:00:00Z | Wednesday | 3 |
| 2024-04-01T00:00:00Z | Thursday | 4 |
| 2024-05-01T00:00:00Z | Friday | 5 |
| 2024-06-01T00:00:00Z | Saturday | 6 |
| 2024-07-01T00:00:00Z | Sunday | 7 |

The dataset will be truncated to 5 days and result in the dataset below.

| time | day of week | value | 
| --- | ---: | ---: | 
| 2024-01-01T00:00:00Z | Monday | 1 |
| 2024-02-01T00:00:00Z | Tuesday | 2 |
| 2024-03-01T00:00:00Z | Wednesday | 3 |
| 2024-04-01T00:00:00Z | Thursday | 4 |
| 2024-05-01T00:00:00Z | Friday | 5 |

Next, consider the same dataset and `target_days` is set to 14.

| time | day of week | value | 
| --- | ---: | ---: | 
| 2024-01-01T00:00:00Z | Monday | 1 |
| 2024-02-01T00:00:00Z | Tuesday | 2 |
| 2024-03-01T00:00:00Z | Wednesday | 3 |
| 2024-04-01T00:00:00Z | Thursday | 4 |
| 2024-05-01T00:00:00Z | Friday | 5 |
| 2024-06-01T00:00:00Z | Saturday | 6 |
| 2024-07-01T00:00:00Z | Sunday | 7 |
| 2024-08-01T00:00:00Z | Monday | 1 |
| 2024-09-01T00:00:00Z | Tuesday | 2 |
| 2024-10-01T00:00:00Z | Wednesday | 3 |
| 2024-11-01T00:00:00Z | Thursday | 4 |
| 2024-12-01T00:00:00Z | Friday | 5 |
| 2024-13-01T00:00:00Z | Saturday | 6 |
| 2024-14-01T00:00:00Z | Sunday | 7 |

The dataset will be enlarged by repeating the required amount of values. Resulting in the dataset shown above.
## Input dataset formats

The examples below are excerpts from the CSV files in `test/input_files`. Include a header row, and use the column names configured in the parameter JSON. The `unit` property on each base-load and space-heating profile, and on `ev_profiles` for the `energy_demand_column`, specifies the units of the input values. Supported values are `W`, `kW`, `MW`, `Wh`, `kWh`, `MWh`, `J`, `kJ`, `MJ`, and `GJ`. Values are not converted; the specified quantity and unit are written to ESDL. The defaults are `kW` for base-load and space-heating profiles and `kWh` for EV energy demand. Set `normalize` to true to normalize base-load profiles against their integrated total.

### Weather data

The first column is the timestamp index. The remaining columns contain the measurements; configure their names with `soil_temperature_column`, `solar_irradiance_column`, and `outside_temperature_column`.

| time | solar_radiation_W/m2 | soil_temperature_celcius | air_temperature_celcius |
| --- | ---: | ---: | ---: |
| 2022-12-31T23:50:00Z | 2 | 9.7 | 15.5 |
| 2023-01-01T00:00:00Z | 1 | 9.7 | 15.5 |

### Day-ahead market data

The first column is the timestamp index. The configured `price_column` contains the values; `price_unit` in the parameters describes their unit.

| time | Day-ahead Price [EUR/MWh] |
| --- | ---: |
| 2023-01-01T00:00:00 | -3.61 |
| 2023-01-01T00:15:00 | -3.61 |

### Domestic hot-water profiles

The first column is the timestamp index. Each other column is a separate profile. The profile values in the example are in L/s.

| timestamp | load_hp | load_hp.1 |
| --- | ---: | ---: |
| 2020-01-01T00:00:00 | 1 | 1 |
| 2020-01-01T00:15:00 | 2 | 2 |

### Space-heating profiles

The first column contains timestamps and each other column is a separate profile. The final CSV row is reserved for the corresponding profile temperatures in degrees celcius; do not include it as a timestamped value. The `unit` parameter describes the profile values.

| timestamp | profile_1 | profile_2 |
| --- | ---: | ---: |
| 2020-01-01T00:00:00 | 1 | 1 |
| 2020-01-01T00:15:00 | 2 | 2 |
| ... | ... | ... |
| Temp | 18 | 21 |

### Base-load profiles

The first column is the timestamp index. Each other column is a separate load profile. The `unit` parameter describes the profile values; when `normalize` is true, profiles are normalized against their integrated total.

| time | Klant 1 | Klant 2 |
| --- | ---: | ---: |
| 2013-01-01T00:00:00 | 1 | 21 |
| 2013-01-01T00:15:00 | 2 | 23 |

### EV charging sessions

Each row describes one charging session. The parameter JSON maps the start and end timestamps, station identifier, energy demand, and power columns. Other columns may be present.

| household | ConnectionStartDateTime | ConnectionEndDateTime | Power | Energy |
| --- | --- | --- | ---: | ---: |
| Household0001 | 2050-01-01T21:45:00 | 2050-01-02T10:13:00 | 11 | 24.09 |
| Household0001 | 2050-01-04T18:15:00 | 2050-01-05T08:39:00 | 11 | 18.7 |

The EV `unit` parameter specifies the unit of `energy_demand_column`; it does not convert the values. The example energy values are in kWh and power values are in kW.

### Time-of-use tariff

Each row describes a tariff interval and its weight. The current parser expects recurring year/month/day and time values in `YYYY-MM-DDTHH:MM` form, as shown here.

| from_tou_month_hour_val | to_tou_month_hour_val | tou_weight |
| --- | --- | ---: |
| 2000-01-01T00:00 | 01-01T01:00 | 0.7 |
| 2000-01-01T01:00 | 01-01T07:00 | 0.5 |

### Datetime format

All full datetime values in the weather, day-ahead market, domestic hot-water, space-heating, base-load, and EV datasets must use the `ISO8601` format, for example `2020-01-01T00:15:00` or `2022-12-31T23:50:00Z`. The recurring time-of-use interval fields are the exception: they use the yearless `MM-DDTHH:MM` format shown above.

## Assumptions for assets
Asset parameters are in the parameter json as well. Per asset certain assumptions hold these will be listed in the sections below:

### PV
The PV installations are generated with a surface area, efficiency, angle, orientation and power values. 
The surface area is sampled from a uniform distribution in range specified by `surface_area_min` and `surface_area_max`. 
The orientation value is an angle value in degrees sampled from a discrete uniform distribution with possible values being: `[45, 90, 135, 180, 225, 270, 315]`.
The angle values depend on the orientation value and are also sampled from a discrete uniform distribution. The angles are chosen based on the maximum efficiency associated with the orientation. The angle ranges per orientation are coming from [this source](https://www.milieucentraal.nl/energie-besparen/zonnepanelen/zonnepanelen-hoe-geschikt-is-je-dak/), which gives efficiency values given an orientation and an angle for solar panels in the Netherlands. The power rating is calculated according to the stardard test conditions for PV panels as described [here](https://www.heavengreenenergy.com/glossary/standard-test-conditions).

### Battery
The capacity of the battery is drawn from a normal distribution. The mean can be specified using the `capacity_kwh_mean` parameter and the standard deviation can be specified by the `capacity_kwh_std` parameter. The charge rate value of the batteries is calculated  using the `power_kw_to_energy_kwh_ratio` using the following formula: `charge_rate_kw = capacity_kwh / battery_specification.power_kw_to_energy_kwh_ratio`. 

### Heatpump and HybridHeatpump demands
The input esdls specify a buildingtype per connection. This building type can be associated with a heating demand. Heating demands are specified in a dataset and express the amount of energy demanded by a specific building to maintain a certain setpoint temperature inside the building. 

Hybrid heat-pump gas-heater thermal power is sampled from a normal distribution using `gass_thermal_power_mean` and `gass_thermal_power_std`; each generated hybrid heat pump also receives `gas_heater_efficiency`.

For example consider the following building in the esdl file: 
```xml
<asset xsi:type="esdl:Building" id="acbf09b0-0c31-4e88-a15d-86b6f53757e8" name="Home90_1" originalIdInSource="901" assetType="test_name_sh" energyLabel="LABEL_E">
```
The asset type of the building specifies the set of possible heating demands it can get connected to. The tool will search the added heating demands names for a demand matching the asset type. In the example above, the building will only be assigned a heating demand if the input parameters specify a heating demand dataset named `test_name_sh`. This only holds for the space heating demands. For hot tap water demands the tool will assign one randomly.

### Phases connections 
New assets are connected to a random phase of a connection. Baseloads are assumed to be uniformly distributed amoung the different phases. Hence, these are connected to all three phases. Each connection is connected to one of the supplied base load profiles.

## Installation
```
pip install dots-esdl-decorator
```
## Usage
Parameters must be configured using a json file an example can be found here. 
```
dots-esdl-decorator test/input_files/test.esdl example_params/params_example.json
```
By default, the decorated file is saved as `decorated_<input filename>` in the current directory. Use `--output` or `--o` to specify a destination:
```
dots-esdl-decorator test/input_files/test.esdl example_params/params_example.json --o output/decorated.esdl
```