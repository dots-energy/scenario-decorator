from dataclasses import dataclass, field
from dataclasses_json import dataclass_json

from esdl import InPort

@dataclass
class DhwProfileMetaData:
    ports : list[InPort] = field(default_factory=list)
    index_to_pick : int = 0

@dataclass_json
@dataclass
class PvSpecification:
    fraction_houses_pv : float
    power_range_values : list[int] = field(default_factory=[2500,2750, 3000, 3250, 3500])
    panel_angle_values : list[int] = field(default_factory=[15, 20, 25, 30])
    orientation_min : int = 90
    orientation_max : int = 270
    surface_area_min : int = 6
    surface_area_max : int = 16