from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
from collections import defaultdict
import re

# ------- Metadata Classes -------- #

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
    
# ------- Parse Metadata -------- #

class EdmxMetadata:
    def __init__(self):
        # EDMX Namespaces
        self.EDMX_NS = "http://docs.oasis-open.org/odata/ns/edmx"
        self.EDM_NS = "http://docs.oasis-open.org/odata/ns/edm"
        self.NS = {"edmx": self.EDMX_NS, "edm": self.EDM_NS}
        self._GUID_NAME_RE = re.compile(r"^_(.+?)_value$")
        """Property cleanup regex for GUIDs"""
        self._COLLECTION_RE = re.compile(r"^\s*Collection\s*\(\s*(?P<inner>.+?)\s*\)\s*$")
        """Identify and parse regex for Collection types"""

    def parse_edmx_file(self, root):
        metadata = []
        # Get all schemas
        schemas = root.findall("edmx:DataServices/edm:Schema", self.NS)
        # Get the attributes for all EntityType elements
        for schema in schemas:
            schema_namespace = schema.get("Namespace")
            schema_alias = schema.get("Alias")
            result = {
                "namespace": schema_namespace,
                "alias": schema_alias,
                "entities": {},
                "enums": {},
                "entity_set_bindings": {},
                "complex_types": {},
                "functions": {}
            }

            # ------- Entities with Attributes and Navigation Properties -------- #
            for et in schema.findall("edm:EntityType", self.NS):
                entity_name = et.get("Name")
                entity_edm = schema.find(f"edm:EntityType[@Name='{entity_name}']", self.NS)
                entity_keys = []
                entity_attributes = {}
                navigation_properties = {}

                if entity_edm:
                    entity_keys = self.get_entity_keys(entity_edm, entity_name)
                    entity_attributes = self.get_properties(entity_edm, schema_namespace, schema_alias)   
                    navigation_properties = self.get_navigation_properties(entity_edm, entity_name, schema_alias)     

                entity = {
                    "name": entity_name,
                    "primary_key": entity_keys[0] if entity_keys else None,
                    "base_type": et.get("BaseType"),
                    "abstract": et.get("Abstract"),
                    "open_type": et.get("OpenType"),
                    "entity_sets": [],
                    "attributes": entity_attributes,
                    "navigation_properties": navigation_properties,
                }

                result["entities"][entity_name] = entity

            # ------- Enums -------- #
            for em in schema.findall("edm:EnumType", self.NS):
                # When IsFlags is True, a combined value is equivalent to the bitwise OR (often denoted "|" ) of the discrete values.
                # It encodes hierarchies of options.
                # What this usually means is that most enumerated values will be (2^n) or (2^n) - 1.
                # When a flag is one less than a power of two, it can be thought of as a combination of all powers of 2 less than it.
                # In general:
                    # p|q = q iif p = (2^n) and q < 2*p
                    # r|s = r iif r = (2^n)-1 and s < 2*r
                    # t|t = t for all positive t
                    # w|x|y|...|z = (2^n)-1 iif w,x,y,...,z are all successive powers of 2 less than 2^n
                # For example: If an enum had values 0, 1, 2, 4, 7, 8, 15...
                        # Having a combined value of 3 is the same as having options 0, 1, and 2 since 0|1|2 => 3
                        # Having a combined value of 7 is the same as having options 0, 1, 2, and 4 since 0|1|2|4 => 7
                            # And so on...
                        # Having a combined value of 10, a combination of 2 and 8, is an unlabled combination in this enum
                enum_name = em.get("Name")
                enum_is_flags = em.get("IsFlags", False)
                members = {}
                for m in em.findall("edm:Member", self.NS):
                    member_name = m.get("Name")
                    member_value = m.get("Value")
                    if member_name and member_value:
                        members[member_name] = member_value

                result["enums"][enum_name] = {
                    "enum_is_flags": enum_is_flags,
                    "members": members
                }

            # ------- Complex Types -------- #
            for ct in schema.findall("edm:ComplexType", self.NS):
                complex_type_name = ct.get("Name")
                result["complex_types"][complex_type_name] = self.get_properties(ct, schema_namespace, schema_alias)   

            # ------- Functions -------- #
            for fn in schema.findall("edm:Function", self.NS):
                function_name = fn.get("Name")
                parameters = {}
                for p in fn.findall("edm:Parameter", self.NS):
                    param_name = p.get("Name")
                    param_type = p.get("Type")
                    if param_name and param_type:
                        is_optional = False
                        for annotation in p.findall("edm:Annotation", self.NS):
                            if "OptionalParameter" in (annotation.get("Term","") or ""):
                                is_optional = True
                                break
                        
                        parameters[param_name] = {
                            "type": param_type,
                            "is_complex": (param_name in result["complex_types"]),
                            "optional": is_optional,
                        }

                returns = False
                return_type = None
                if return_types := fn.findall("edm:ReturnType", self.NS):
                    returns = True
                    full_return_type = return_types[0].get("Type",None)
                    return_type = self.cleanup_name(name=full_return_type, namespace=schema_namespace, alias=schema_alias)

                func = {
                    "is_api_function": False,
                    "api_name": None,
                    "parameters": parameters,
                    "returns": returns,
                    "return_type": return_type
                }

                result["functions"][function_name] = func

            
            if entity_containers := schema.findall("edm:EntityContainer", self.NS):
                # ------- Entity Sets -------- #
                entity_container = entity_containers[0]
                for es in entity_container.findall("edm:EntitySet", self.NS):
                    entity_set_name = es.get("Name")
                    full_entity_set_type = es.get("EntityType")
                    entity_set_type = self.cleanup_name(name=full_entity_set_type, namespace=schema_namespace, alias=schema_alias)

                    if result["entities"].get(entity_set_type):
                        if entity_set_name not in result["entities"][entity_set_type]["entity_sets"]:
                            result["entities"][entity_set_type]["entity_sets"].append(entity_set_name)

                    navigation_property_bindings = {}
                    for n in es.findall("edm:NavigationPropertyBinding", self.NS):
                        set_path = n.get("Path")
                        set_target = n.get("Target")
                        if set_path and set_target:
                            navigation_property_bindings[set_path] = set_target

                    result["entity_set_bindings"][entity_set_name] = navigation_property_bindings

                # ------- API Functions -------- #
                for af in entity_container.findall("edm:FunctionImport", self.NS):
                    function_api_name = af.get("Name")
                    full_function_type = af.get("Function")
                    function_type = self.cleanup_name(name=full_function_type, namespace=schema_namespace, alias=schema_alias)

                    if result["functions"].get(function_type):
                        result["functions"][function_type]["is_api_function"] = True
                        result["functions"][function_type]["api_name"] = function_api_name

            metadata.append(result)
        return metadata
    
    # Remove preceeding namespace or alias values from element names
    def cleanup_name(self, name: str, namespace: str, alias: str) -> str:
        if f"{namespace}." in name:
            clean_name = name.removeprefix(f"{namespace}.")
        elif f"{alias}." in name:
            clean_name = name.removeprefix(f"{alias}.")
        else:
            clean_name = name
        return clean_name
    
    # Get key elements
    def get_entity_keys(self, entity_type_elem, entity_name):
        key = entity_type_elem.find("edm:Key", self.NS)
        if key is None:
            return []
        
        keys = [pr.get("Name") for pr in key.findall("edm:PropertyRef", self.NS)]
        if len(keys) > 1:
            print(f"Found more than one key for entity {entity_name} ")
        return keys
    
    # If the property type is a Guid, the logical name may be of the form _[attribute name]_value; which needs to be removed.
    def normalize_property_name(self, name: str, edm_type: str = None, force: bool = False) -> str:
        if edm_type != "Edm.Guid" and not force:
            return name
        match = self._GUID_NAME_RE.match(name)
        return match.group(1) if match else name
    
    def check_collection_type(self, type_str):
        m = self._COLLECTION_RE.match(type_str)
        if m:
            return True, m.group("inner")
        return False, type_str.strip()
    
    # Get the properties of a given element
    def get_properties(self, element, schema_namespace, schema_alias):
        all_props = {}
        for p in element.findall("edm:Property", self.NS):
            property_name = p.get("Name")
            property_type = p.get("Type")
            is_collection, full_collection_type = self.check_collection_type(property_type)
            collection_type = self.cleanup_name(name=full_collection_type, namespace=schema_namespace, alias=schema_alias)
            normalized_name = self.normalize_property_name(property_name, property_type)
            property = {
                "logical_name": self.normalize_property_name(property_name, property_type),
                "api_name":property_name,
                "type": property_type,
                "is_collection": is_collection,
                "collection_type": collection_type if collection_type and is_collection else None
            }
            all_props[normalized_name] = property
        return all_props
    
    # Get EntityType Navigation Properties. These are used in $expand odata queries.
    def get_navigation_properties(self, element, entity_name, schema_alias):
        navs = {}
        for np in element.findall("edm:NavigationProperty", self.NS):
            navigation_property_name = np.get("Partner")
            if navigation_property_name is None:
                continue

            nav_name = np.get("Name")
            constraints = []
            for rc in np.findall("edm:ReferentialConstraint", self.NS):
                from_property_name = rc.get("Property")
                to_property_name = rc.get("ReferencedProperty")
                constraints.append({
                    "from_name": self.normalize_property_name(from_property_name, force=True),
                    "to_name": self.normalize_property_name(to_property_name, force=True),
                    "from_api_name": from_property_name,
                    "to_api_name": to_property_name,
                })

            if len(constraints) > 1:
                print(f"Found more than one constraint for {entity_name} on property {nav_name}")
            
            nav_type = np.get("Type")
            if schema_alias is not None and schema_alias != "":
                _alias_re = re.compile(r"^" + schema_alias + r"\.([^\.]+?)$")
                match = _alias_re.match(nav_type)
                to_entity_name = match.group(1) if match else nav_type
            else:
                to_entity_name = nav_type
            
            from_property = constraints[0]['from_name'] if constraints else None
            to_property = constraints[0]['to_name'] if constraints else None

            navs[navigation_property_name] = {
                "navigation_property_name": navigation_property_name,
                "from_property": from_property,
                "to_property": to_property,
                "to_entity_name": to_entity_name,
                "to_entity_base_type": nav_type,
                "nullable": np.get("Nullable"),
            }
        return navs