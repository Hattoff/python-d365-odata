from __future__ import annotations
from dataclasses import dataclass
from typing import Dict

# ------- Metadata -------- #

@dataclass(frozen=True)
class EntityType:
    name: str
    properties: Dict[str, str] 
    """properties: edm type e.g. "Edm.String", "Edm.Int32"""


@dataclass(frozen=True)
class ServiceMetadata:
    entity_sets: Dict[str, str]          # entity_set -> entity_type_name
    entity_types: Dict[str, EntityType]  # entity_type_name -> EntityType

    def entity_type_for_set(self, entity_set: str) -> EntityType:
        if entity_set not in self.entity_sets:
            raise KeyError(f"Unknown entity set: {entity_set}")
        et_name = self.entity_sets[entity_set]
        if et_name not in self.entity_types:
            raise KeyError(f"Entity type not found for set '{entity_set}': {et_name}")
        return self.entity_types[et_name]