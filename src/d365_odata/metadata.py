from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple
from collections.abc import Iterable as IterableABC
import re
from pathlib import Path
import xml.etree.ElementTree as ET
import json
from .utilities import _find_case_insensitive

import logging
logger = logging.getLogger(__name__)

# ------- Metadata Classes -------- #
@dataclass(frozen=True)
class EntityType:
    name: str
    properties: Dict[str, str] 
    """properties: edm type e.g. "Edm.String", "Edm.Int32"""

@dataclass(frozen=True)
class ServiceMetadata:
    schema_namespace: str
    schema_alias: str
    entity_sets: Dict[str, str]
    """maps entity sets to entities"""
    entity_types: Dict[str, EntityType]
    """maps entities to EntityType objects"""
    entities: Dict[str, Any]
    enums: Dict[str, Any]
    complex_types: Dict[str, Any]

    def entity_type_for_set(self, entity_set: str) -> EntityType:
        if entity_set not in self.entity_sets:
            raise KeyError(f"Unknown entity set: {entity_set}")
        et_name = self.entity_sets[entity_set]
        if et_name not in self.entity_types:
            raise KeyError(f"Entity type not found for set '{entity_set}': {et_name}")
        return self.entity_types[et_name]
    

    def get_attribute(self, attribute_name: str, *, entity: Optional[Dict[str, Any]] = None, entity_name: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        return self._get_entity_prop("attributes", attribute_name, entity=entity, entity_name=entity_name)

    def get_navigation_property(self, navigation_property_name: str, *, entity: Optional[Dict[str, Any]] = None, entity_name: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        return self._get_entity_prop("navigation_properties", navigation_property_name, entity=entity, entity_name=entity_name)
    
    def _get_entity_prop(
            self,
            prop_type: str,
            prop_name: str,
            *,
            entity: Optional[Dict[str, Any]] = None,
            entity_name: Optional[str] = None
        ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Generalized to fetch values from iterable objects on the Entity.
        
        :param prop_type: Name of the iterable object found on the entity. If the object is not iterable then this will return nothing.
        :type prop_type: str
        :param prop_name: Name of the item in within the iterable object.
        :type prop_name: str
        :param entity: Entity object to search.
        :type entity: Optional[Dict[str, Any]]
        :param entity_name: Name of the entity. Will use get_entity to resolve.
        :type entity_name: Optional[str]
        :return: Return the item by the name provided and the actual name of that item, if they exist. Otherwise return None, None.
        :rtype: Tuple[Dict[str, Any] | None, str | None]
        """
        options = [entity, entity_name]
        selected_options = list(filter(lambda o: o is not None, options))
        if len(selected_options) != 1:
            raise ValueError(f"Expected only one of the following [entity, entity_name] but got {len(selected_options)}.")
        
        if not isinstance(prop_name, str):
            try:
                prop_name = str(prop_name)
            except:
                raise ValueError(f"Expected the name to be a string. Got {type(prop_name)} whcih cannot be converted to a string.")

        if entity_name is not None:
            entity, _ = self.get_entity(entity_name)
        
        if entity is None:
            return None, None

        if props:= entity.get(prop_type):
            if isinstance(props, IterableABC) and (not isinstance(props, str)):
                if prop_name in props:
                    return props[prop_name], prop_name

                prop, actual_prop_name = _find_case_insensitive(prop_name, props)
                if prop:
                    return prop, actual_prop_name
        return None, None
        
    def get_entity(self, name: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Search for an entity by name and return it.
        
        :param name: Check if name is an entity name, if not it will check entity_set names; will also check case-insensitive variants.
        :type name: str
        :return: Entity info and list of properties
        :rtype: Dict[str, Any]
        """
        if entity := self.entities.get(name):
            # direct name match
            return entity, name
        
        if entity_name := self.entity_sets.get(name):
            if entity := self.entities.get(entity_name):
                # entity_set name match
                return entity, entity_name
            
        entity_name, _ = _find_case_insensitive(name, self.entity_sets)
        if entity_name:
            if entity := self.entities.get(entity_name):
                # case-insensitive entity_set name match
                return entity, entity_name
            
        entity, entity_name = _find_case_insensitive(name, self.entities)
        if entity:
            # case-insensitive entity name match
            return entity, entity_name
        
        return None, None
    
    def ensure_entity_set_name(self, name: str) -> Optional[str]:
        """
        Ensure the name used is the proper entity set name.
        
        :param name: Check if name is already an entity_set name, if not it will check for entity name; will also check case-insensitive variants.
        :type name: str
        :return: Correct variant of the entity set name.
        :rtype: Dict[str, Any]
        """

        entity_name, actual_entity_set_name = _find_case_insensitive(name, self.entity_sets)
        if entity_name:
            return actual_entity_set_name
        
        entity, entity_name = _find_case_insensitive(name, self.entities)
        if entity:
            return entity.get("entity_set_name", None)
        
        return None
    
    def get_complex_type(self, name: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if complex_type := self.complex_types.get(name):
            # direct name match
            return complex_type, name
        
        complex_type, complex_type_name = _find_case_insensitive(name, self.complex_types)
        if complex_type:
            # case-insensitive name match
            return complex_type, complex_type_name
        return None, None

    def get_enum(self, name: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if enum := self.enums.get(name):
            # direct name match
            return enum, name
        
        enum, enum_name = _find_case_insensitive(name, self.enums)
        if enum:
            # case-insensitive name match
            return enum, enum_name
        return None, None
    
    def get_enum_info(
            self,
            enum_name: str,
            *,
            enum_variable: Optional[str] = None,
            enum_member: Optional[str] = None,
            enum_value: Optional[str] = None
        ) -> Optional[Dict[str, str]]:
        """
        Lookup an enum by name and value, return a complete set of information for that member.
        
        :param enum_name: Enumerator name. Will search case-insensitive if needed.
        :type enum_name: str
        :param enum_variable: Use if you are unsure if you have the member name or value. Will search member names first, then values.
        :type enum_variable: Optional[str]
        :param enum_member: Search member names. Will search case-insensitive if needed.
        :type enum_member: Optional[str]
        :param enum_value: Search enum values for the member name. Will cast value to string if needed.
        :type enum_value: Optional[str]
        :return: Enumerator information -> Enum Path: [Schema Namespace].[Enum Name], Enum Member, Enum Value, Enum Is Flags (enum values combine using bitwise-or)
        :rtype: Dict[str, str] | None
        """
        options = [enum_variable, enum_member, enum_value]
        selected_options = list(filter(lambda o: o is not None, options))
        if len(selected_options) != 1:
            raise ValueError(f"Expected only one of the following [enum_variable, enum_member, enum_value] but got {len(selected_options)}.")

        enum, actual_enum_name = self.get_enum(enum_name)
        enum_member_name = None
        if enum is not None:
            members = (enum.get("members",{}) or {})
            target_member = enum_variable if enum_variable is not None else enum_member
            if target_member is not None:
                if target_member in members:
                    enum_member_name = target_member
                else:
                    member, actual_target_member = _find_case_insensitive(str(target_member), members)
                    if member:
                        enum_member_name = actual_target_member

            if enum_member_name is None:
                target_value = enum_variable if enum_variable is not None else enum_value
                if target_value is not None:
                    try:
                        enum_member_name = list(members.keys())[list(members.values()).index(target_value)]
                    except:
                        try:
                            enum_member_name = list(members.keys())[list(members.values()).index(str(target_value))]
                        except:
                            pass

            if enum_val := members.get(enum_member_name):
                return {
                    "enum_path": f"{self.schema_namespace}.{actual_enum_name}",
                    "enum_member": enum_member_name,
                    "enum_value": enum_val,
                    "enum_is_flags": enum.get("enum_is_flags")
                }
        
        return None
            


def service_metadata_from_parsed_edmx(parsed: list[dict]) -> ServiceMetadata:
    # for now just go with the default schema
    schema = parsed[0]

    entity_sets = {}
    entity_types = {}

    # entity_sets: from entities[*].entity_set_name
    for ename, e in schema["entities"].items():
        if e.get("entity_set_name"):
            entity_sets[e["entity_set_name"]] = ename

        props = {pname: pinfo["type"] for pname, pinfo in e["attributes"].items()}
        entity_types[ename] = EntityType(name=ename, properties=props)

    return ServiceMetadata(
        schema_namespace=schema["namespace"],
        schema_alias=schema["alias"],
        entity_sets=entity_sets,
        entity_types=entity_types,
        entities=schema["entities"],
        enums=schema["enums"],
        complex_types=schema["complex_types"]
    )

    
# ------- Parse Metadata -------- #

class EdmxSourceError(ValueError):
    """Raised when the EDMX source cannot be loaded or validated."""

class EdmxMetadata:
    # Caches of entity, entity-sets, complex types, and enums per schema.
    _entity_names: Dict[str, List[str]] = {}
    _enum_names: Dict[str, List[str]] = {}
    _entity_set_names: Dict[str, List[str]] = {}
    _complex_type_names: Dict[str, List[str]] = {}
   
    _GUID_NAME_RE = re.compile(r"^_(.+?)_value$")
    """Property cleanup regex for GUIDs"""
    _COLLECTION_RE = re.compile(r"^\s*Collection\s*\(\s*(?P<inner>.+?)\s*\)\s*$")
    """Identify and parse regex for Collection types"""
    # EDMX Namespaces
    _EDMX_NS = "http://docs.oasis-open.org/odata/ns/edmx"
    _EDM_NS = "http://docs.oasis-open.org/odata/ns/edm"
    NS = {"edmx": _EDMX_NS, "edm": _EDM_NS}

    _REQUIRED_SCHEMA_KEYS = {
        "namespace",
        "alias",
        "entities",
        "enums",
        "complex_types"
    }
    """required structure of cached metadata"""

    def __init__(self, source: Any):
        """
        :param source:
        source may be:
          - Path/str to .xml or .json
          - xml.etree.ElementTree .ElementTree or .Element (root)
          - raw xml or json text
          - already-parsed metadata object
        :type source: Any
        """
        self._metadata: List[Dict[str, Any]] = []

        # Normalize input into metadata (cached JSON) or XML
        loaded = self._load_source(source)

        if loaded.kind == "json":
            # Cache it
            self._metadata = loaded.metadata
        elif loaded.kind == "xml":
            # Parse it
            self._metadata = self._parse_edmx_file(loaded.root)
        else:
            # Unknown kind
            raise EdmxSourceError(f"Unsupported loaded kind: {loaded.kind}")

    @property
    def metadata(self) -> List[Dict[str, Any]]:
        return self._metadata

    @dataclass(frozen=True)
    class _Loaded:
        kind: str
        """xml or json"""
        root: Optional[ET.Element] = None
        metadata: Optional[List[Dict[str, Any]]] = None

    def _load_source(self, source: Any) -> "EdmxMetadata._Loaded":
        # ------- Existing metadata list -------- #
        if isinstance(source, list):
            # If passed already-parsed metadata list, use it.
            self._validate_cached_metadata(source)
            return self._Loaded(kind="json", metadata=source)

        # ------- ElementTree / Element -------- #
        if isinstance(source, ET.ElementTree):
            return self._Loaded(kind="xml", root=source.getroot())

        if isinstance(source, ET.Element):
            return self._Loaded(kind="xml", root=source)
        
        # ------- String-like -------- #
        if isinstance(source, str):
            # If it looks like a real path, treat it as path and try to load the file.
            possible_path = Path(source)
            if possible_path.exists():
                return self._load_source(possible_path)

            # otherwise treat as raw text.
            return self._load_from_text(source)

        # ------- Path-like -------- #
        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                raise EdmxSourceError(f"Source file does not exist: {path}")

            suffix = path.suffix.lower()
            if suffix == ".xml" or suffix == ".edmx":
                root = self._parse_xml_file(path)
                return self._Loaded(kind="xml", root=root)

            if suffix == ".json":
                metadata = self._load_and_validate_json(path)
                return self._Loaded(kind="json", metadata=metadata)

            raise EdmxSourceError(
                f"Unsupported file extension '{path.suffix}'. Expected .xml/.edmx or .json."
            )

        raise EdmxSourceError(
            "Unsupported source type. Provide a Provide a Path/str to an exising .xml/.json file, text from a .xml/.json file, or an xml.etree.ElementTree.ElementTree/Element."
        )
    
    def _load_from_text(self, text: str) -> "EdmxMetadata._Loaded":
        text = text.strip()
        if not text:
            raise EdmxSourceError("Provided text source is empty.")

        # ------- Try JSON -------- #
        if text[0] in "{[":
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    data = [data]
                self._validate_cached_metadata(data)
                return self._Loaded(kind="json", metadata=data)
            except json.JSONDecodeError:
                # invalid JSON
                pass
            except EdmxSourceError:
                # valid JSON but invalid structure
                raise

        # ------- Try XML -------- #
        if text[0] == "<":
            try:
                root = ET.fromstring(text)
                return self._Loaded(kind="xml", root=root)
            except ET.ParseError as e:
                raise EdmxSourceError(f"Text looked like XML but failed to parse: {e}") from e

        raise EdmxSourceError(
            "Text source is neither valid JSON nor XML."
        )

    
    def _parse_xml_file(self, path: Path) -> ET.Element:
        try:
            tree = ET.parse(path)
        except ET.ParseError as e:
            raise EdmxSourceError(f"Invalid XML in '{path}': {e}") from e
        except OSError as e:
            raise EdmxSourceError(f"Could not read '{path}': {e}") from e

        root = tree.getroot()

        # Check if file looks like EDMX
        if root.tag.endswith("Edmx") is False and "edmx" not in root.tag:
            logger.warning(f"XML from {path} does not look like an EDMX document.")
            pass

        return root

    def _load_and_validate_json(self, path: Path) -> List[Dict[str, Any]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise EdmxSourceError(f"Invalid JSON in '{path}': {e}") from e
        except OSError as e:
            raise EdmxSourceError(f"Could not read '{path}': {e}") from e

        if isinstance(data, dict):
            # if the parsed data is a dict, stuff it into a list to match expected format
            data = [data]

        self._validate_cached_metadata(data)
        return data

    def _validate_cached_metadata(self, data: Any) -> None:
        if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
            raise EdmxSourceError(
                "Cached metadata JSON must be a list of objects (or a single object)."
            )

        for i, schema in enumerate(data):
            missing = self._REQUIRED_SCHEMA_KEYS - set(schema.keys())
            if missing:
                raise EdmxSourceError(
                    f"Cached metadata schema at index {i} is missing keys: {sorted(missing)}"
                )

            # Light validation of cached metadata
            for key in ["entities", "enums", "entity_sets", "complex_types"]:
                if not isinstance(schema.get(key), dict):
                    raise EdmxSourceError(
                        f"Cached metadata schema at index {i}: '{key}' must be an object/dict."
                    )

            # namespace/alias can be None or str depending the EDMX
            if schema.get("namespace") is not None and not isinstance(schema["namespace"], str):
                raise EdmxSourceError(
                    f"Cached metadata schema at index {i}: 'namespace' must be a string or null."
                )
            if schema.get("alias") is not None and not isinstance(schema["alias"], str):
                raise EdmxSourceError(
                    f"Cached metadata schema at index {i}: 'alias' must be a string or null."
                )
    
    def _parse_edmx_file(self, root):
        metadata = []
        # Get all schemas
        schemas = root.findall("edmx:DataServices/edm:Schema", self.NS)
        # Get the attributes for all EntityType elements
        for schema in schemas:
            schema_namespace = schema.get("Namespace")
            schema_alias = schema.get("Alias")
            self._entity_names[schema_alias] = []
            self._enum_names[schema_alias] = []
            self._entity_set_names[schema_alias] = []
            self._complex_type_names[schema_alias] = []


            result = {
                "namespace": schema_namespace,
                "alias": schema_alias,
                "entities": {}, # EntityTypes (aka entities) store raw data in the system and can be exposed to the API via EntitySets.
                "enums": {}, # EnumTypes are system-level enumerators. They can be decoded using special calls to ([NAMESPACE].[ENUM NAME] 'enum_string') -> enum_int
                "entity_sets": {}, # EntitySets expose entities and special navigation properties to the API. e.g. the EntityDefinitions entity-set returns 
                "complex_types": {} # ComplexTypes are Entity-like structures which lack a key. They are often a special collection populated by a function or action. e.g. The WhoAmI function returns the complex type WhoAmIResponse.
            }

            # Get a list of names of all entities, entity-sets, enums, and complex types early on to help with property classification.
            for ct in schema.findall("edm:ComplexType", self.NS):
                complex_type_name = ct.get("Name")
                if complex_type_name and complex_type_name not in self._complex_type_names[schema_alias]:
                    self._complex_type_names[schema_alias].append(complex_type_name)

            for em in schema.findall("edm:EnumType", self.NS):
                enum_name = em.get("Name")
                if enum_name and enum_name not in self._enum_names[schema_alias]:
                    self._enum_names[schema_alias].append(enum_name)

            for et in schema.findall("edm:EntityType", self.NS):
                entity_name = et.get("Name")
                if entity_name and entity_name not in self._entity_names[schema_alias]:
                    self._entity_names[schema_alias].append(entity_name)

            if entity_containers := schema.findall("edm:EntityContainer", self.NS):
                entity_container = entity_containers[0]
                for es in entity_container.findall("edm:EntitySet", self.NS):
                    entity_set_name = es.get("Name")
                    if entity_set_name and entity_set_name not in self._entity_set_names[schema_alias]:
                        self._entity_set_names[schema_alias].append(entity_set_name)

            # ------- Complex Types -------- #
            for ct in schema.findall("edm:ComplexType", self.NS):
                complex_type_name = ct.get("Name")
                complex_base_type = ct.get("BaseType", None)
                complex_base_type_info = self.get_type_info(type_str=complex_base_type, namespace=schema_namespace, alias=schema_alias)
                result["complex_types"][complex_type_name] = {
                    "base_type": complex_base_type_info.get("stripped_type"),
                    "full_base_type": complex_base_type,
                    "base_type_element": complex_base_type_info.get("type_element"),
                    "properties": self.get_properties(element=ct, namespace=schema_namespace, alias=schema_alias)
                }

            # ------- Enums -------- #
            for em in schema.findall("edm:EnumType", self.NS):
                # When IsFlags is True, a combined value is equivalent to the bitwise OR (often denoted "|" ) of the discrete values.
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

            # ------- Entities with Attributes and Navigation Properties -------- #
            for et in schema.findall("edm:EntityType", self.NS):
                entity_name = et.get("Name")
                entity_edm = schema.find(f"edm:EntityType[@Name='{entity_name}']", self.NS)
                entity_keys = []
                entity_attributes = {}
                navigation_properties = {}

                if entity_edm:
                    entity_keys = self.get_entity_keys(entity_edm, entity_name)
                    entity_attributes = self.get_properties(element=entity_edm, namespace=schema_namespace, alias=schema_alias)
                    navigation_properties = self.get_navigation_properties(entity_edm, entity_name, namespace=schema_namespace, alias=schema_alias)

                base_type = et.get("BaseType")
                base_type_info = self.get_type_info(type_str=base_type, namespace=schema_namespace, alias=schema_alias)

                entity = {
                    "primary_key": entity_keys[0] if entity_keys else None,
                    "base_type": base_type_info.get("stripped_type"),
                    "full_base_type": base_type,
                    "base_type_element": base_type_info.get("type_element"),
                    "abstract": bool(et.get("Abstract",False)), # Abstract entities allow for property inheritance. Most abstract entities are not exposed to the API via EntitySets, but some are (ActivityPointer, RelationshipMetadataBase).
                    "entity_set_name": None, # If entity set name is missing it means it is not exposed to the API.
                    "attributes": entity_attributes,
                    "navigation_properties": navigation_properties, # Navigation properties can be referenced by name to expand that attribute.
                }

                result["entities"][entity_name] = entity
            
            if entity_containers := schema.findall("edm:EntityContainer", self.NS):
                # ------- Entity Sets -------- #
                entity_container = entity_containers[0]
                for es in entity_container.findall("edm:EntitySet", self.NS):
                    entity_set_name = es.get("Name")
                    full_entity_set_type = es.get("EntityType")
                    entity_set_type = self.cleanup_name(name=full_entity_set_type, namespace=schema_namespace, alias=schema_alias)

                    if result["entities"].get(entity_set_type):
                        current_entity_set_name = result["entities"][entity_set_type]["entity_set_name"]
                        if current_entity_set_name and entity_set_name != current_entity_set_name:
                            logger.warning(f"Entity {entity_set_type} already had an entity set name, but another was found.\n It was: {current_entity_set_name} It is now: {entity_set_name}.")
                        result["entities"][entity_set_type]["entity_set_name"] = entity_set_name

                    navigation_property_bindings = {}
                    for n in es.findall("edm:NavigationPropertyBinding", self.NS):
                        set_path = n.get("Path")
                        set_target = n.get("Target")
                        if set_path and set_target:
                            navigation_property_bindings[set_path] = set_target

                    result["entity_sets"][entity_set_name] = navigation_property_bindings

            metadata.append(result)
        return metadata
    
    def type_is_custom(self, type_str: str, alias: str, custom_types: List[str]):
        if type_str and type_str.startswith(f"{alias}."):
            clean_type = self.cleanup_name(name=type_str, alias=alias)
            return (clean_type in custom_types)
        return False
    
    # Remove preceeding namespace or alias values from element names
    def cleanup_name(self, name: str, namespace: Optional[str] = "", alias: Optional[str] = "") -> Optional[str]:
        if not name:
            return None
        
        if namespace and name.startswith(namespace + "."):
            clean_name = name.removeprefix(namespace + ".")
            return clean_name
        
        if alias and name.startswith(alias + "."):
            clean_name = name.removeprefix(alias + ".")
            return clean_name
            
        return name
    
    # Get key elements
    def get_entity_keys(self, entity_type_elem, entity_name):
        key = entity_type_elem.find("edm:Key", self.NS)
        if key is None:
            return []
        
        keys = [pr.get("Name") for pr in key.findall("edm:PropertyRef", self.NS)]
        if len(keys) > 1:
            print(f"Found more than one key for entity {entity_name} ")
        return keys
    
    def normalize_property_name(self, name: str, edm_type: str = None, force: bool = False) -> str:
        """
        If the property type is a Guid, the logical name may be of the form _[name]_value; which needs to be removed.
        
        :param name: Property name to be normalized
        :type name: str
        :param edm_type: Edm.[type]
        :type edm_type: str
        :param force: If true, force-use the GUID regex match. Useful if the property is structured like a GUID but not flagged explicitly as Edm.Guid.
        :type force: bool
        :return: Returns name from _[name]_value. Otherwise returns unaltered name.
        :rtype: str
        """
        if edm_type != "Edm.Guid" and not force:
            return name
        match = self._GUID_NAME_RE.match(name)
        return match.group(1) if match else name
    
    def check_collection_type(self, type_str: str):
        m = self._COLLECTION_RE.match(type_str)
        if m:
            return True, m.group("inner")
        return False, None
    
    def get_type_info(self, type_str: str, namespace, alias):
        if not type_str:
            return {}
        
        is_collection, collection_type = self.check_collection_type(type_str)
        actual_type_str = collection_type if is_collection is True and collection_type else type_str

        stripped_type_str = self.cleanup_name(name=actual_type_str, namespace=namespace, alias=alias)

        if stripped_type_str.startswith("Edm."):
            type_element = "edm"
            # Remove Edm indicator for stripped version
            stripped_type_str = stripped_type_str.removeprefix("Edm.")
        elif stripped_type_str in self._enum_names[alias]:
            type_element = "enum_type"
        elif stripped_type_str in self._entity_names[alias]:
            # It is rare (and annoying) but you can have EntitySets with the same name as their corresponding EntityType.
            # Check for EntityType first if that is the case.
            type_element = "entity_type"
        elif stripped_type_str in self._entity_set_names[alias]:
            type_element = "entity_set"
        elif stripped_type_str in self._complex_type_names[alias]:
            type_element = "complex_type"
        else:
            type_element = None
            
        return {
            "stripped_type": stripped_type_str,
            "is_collection": is_collection,
            "type_element": type_element
    }
    
    
    # Get the properties of a given element
    def get_properties(self, element, namespace, alias):
        all_props = {}
        for p in element.findall("edm:Property", self.NS):
            property_name = p.get("Name")
            property_type = p.get("Type")
            type_info = self.get_type_info(type_str=property_type, namespace=namespace, alias=alias)

            normalized_name = self.normalize_property_name(property_name, property_type)
            property = {
                "api_name":property_name,
                "type": type_info.get("stripped_type"),
                "full_type": property_type,
                "is_collection": type_info.get("is_collection"),
                "type_element": type_info.get("type_element")
            }
            all_props[normalized_name] = property
        return all_props
    
    # Get EntityType Navigation Properties. These are used in $expand odata queries.
    def get_navigation_properties(self, element, entity_name, namespace, alias):
        navs = {}
        for np in element.findall("edm:NavigationProperty", self.NS):
            nav_name = np.get("Name")
            if not nav_name:
                continue
            partner = np.get("Partner")

            constraints = []
            for rc in np.findall("edm:ReferentialConstraint", self.NS):
                from_property_name = rc.get("Property")
                to_property_name = rc.get("ReferencedProperty")
                constraints.append({
                    "from_name": self.normalize_property_name(from_property_name, force=True),
                    "to_name": self.normalize_property_name(to_property_name, force=True),
                    "from_api_name": from_property_name,
                    "to_api_name": to_property_name
                })

            if len(constraints) > 1:
                print(f"Found more than one constraint for {entity_name} on property {nav_name}")
            
            nav_type = np.get("Type")
            nav_type_info = self.get_type_info(type_str=nav_type, namespace=namespace, alias=alias)
            
            from_property = constraints[0]['from_name'] if constraints else None
            to_property = constraints[0]['to_name'] if constraints else None
                        
            navs[nav_name] = {
                "partner": partner, # Name of the reciprocal relationship
                "from_property": from_property,
                "to_property": to_property,
                "to_entity_type": (nav_type_info.get("stripped_type") or nav_type),
                "to_entity_full_type": nav_type,
                "to_entity_is_collection": nav_type_info.get("is_collection")
            }
        return navs