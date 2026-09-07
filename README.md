# Scenario-Decorator
ESDL decorator to add scenario aspects (asset penetration, weather data, market data, etc) to infrastructure ESDL files. 

The tool takes an ESDL file containing an electricity network and connections connected to the electricity network. Usable networks in ESDL format can be found in the example repository. Using a json file specifying the parameters for decoration the tool outputs an ESDL file containing the original network plus weather and market data as well as assets connected to the connections.
Input formats for the weather and market data can be found here.

## Assumptions for data
format
base load power kw values
normalizes them in terms of the total

ev format from to energy and power and identifier

date format ISO8601

## Installation
```
pip install dots-esdl-decorator
```
## Usage
Parameters must be configured using a json file an example can be found here. 
```
dots-esdl-decorator test/input_files/test.esdl example_params/params_example.json
```