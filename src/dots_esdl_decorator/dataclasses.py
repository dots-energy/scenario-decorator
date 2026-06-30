from dataclasses import dataclass, field

from esdl import InPort

@dataclass
class DhwProfileMetaData:
    ports : list[InPort] = field(default_factory=list)
    index_to_pick : int = 0