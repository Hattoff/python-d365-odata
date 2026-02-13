from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
import re
from pathlib import Path
import xml.etree.ElementTree as ET
import json
from .types import FunctionDef, FunctionParam

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
    entity_sets: Dict[str, str]          # entity_set -> entity_type_name
    entity_types: Dict[str, EntityType]  # entity_type_name -> EntityType
    functions: Dict[str, FunctionDef] = None    # api_name -> FunctionDef (or name -> FunctionDef)

    def entity_type_for_set(self, entity_set: str) -> EntityType:
        if entity_set not in self.entity_sets:
            raise KeyError(f"Unknown entity set: {entity_set}")
        et_name = self.entity_sets[entity_set]
        if et_name not in self.entity_types:
            raise KeyError(f"Entity type not found for set '{entity_set}': {et_name}")
        return self.entity_types[et_name]
    
    def function_for_api(self, api_name: str) -> FunctionDef:
        if not self.functions or api_name not in self.functions:
            raise KeyError(f"Unknown function: {api_name}")
        return self.functions[api_name]
    

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

    functions = {}
    for fname, f in schema["functions"].items():
        api_name = f["api_name"] or fname
        params = {
            pn: FunctionParam(
                name=pn,
                edm_type=p["type"],
                is_optional=p["is_optional"],
            )
            for pn, p in f["parameters"].items()
        }
        functions[api_name] = FunctionDef(
            name=fname,
            api_name=api_name,
            params=params,
            returns=bool(f["returns"]),
            return_type=f["return_type"],
        )

    return ServiceMetadata(
        entity_sets=entity_sets,
        entity_types=entity_types,
        functions=functions,
    )

    
# ------- Parse Metadata -------- #

class EdmxSourceError(ValueError):
    """Raised when the EDMX source cannot be loaded or validated."""

class EdmxMetadata:
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
        "entity_set_bindings",
        "complex_types",
        "functions"
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
            for key in ["entities", "enums", "entity_set_bindings", "complex_types", "functions"]:
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
            result = {
                "namespace": schema_namespace,
                "alias": schema_alias,
                "entities": {},
                "enums": {},
                "entity_set_bindings": {},
                "complex_types": {},
                "functions": {}
            }

            complex_types_prefetch = []
            for ct in schema.findall("edm:ComplexType", self.NS):
                complex_type_name = ct.get("Name")
                complex_types_prefetch.append(complex_type_name)

            enum_types_prefetch = []
            for em in schema.findall("edm:EnumType", self.NS):
                enum_name = em.get("Name")
                enum_types_prefetch.append(enum_name)

            # ------- Complex Types -------- #
            for ct in schema.findall("edm:ComplexType", self.NS):
                complex_type_name = ct.get("Name")
                complex_base_type = ct.get("BaseType", None)
                result["complex_types"][complex_type_name] = {
                    "base_type": complex_base_type,
                    "properties": self.get_properties(ct, schema_alias, complex_types=complex_types_prefetch, enum_types=enum_types_prefetch)
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
                    entity_attributes = self.get_properties(entity_edm, schema_alias, complex_types=complex_types_prefetch, enum_types=enum_types_prefetch)   
                    navigation_properties = self.get_navigation_properties(entity_edm, entity_name, schema_alias)

                entity = {
                    "name": entity_name,
                    "primary_key": entity_keys[0] if entity_keys else None,
                    "base_type": et.get("BaseType"),
                    "abstract": et.get("Abstract"),
                    "open_type": et.get("OpenType"),
                    "entity_set_name": None,
                    "attributes": entity_attributes,
                    "navigation_properties": navigation_properties,
                }

                result["entities"][entity_name] = entity

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
                            "is_complex": self.type_is_custom(type_str=param_type, alias=schema_alias, custom_types=complex_types_prefetch),
                            "is_enum":  self.type_is_custom(type_str=param_type, alias=schema_alias, custom_types=enum_types_prefetch),
                            "is_optional": is_optional,
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
    
    # Get the properties of a given element
    def get_properties(self, element, schema_alias, complex_types, enum_types):
        all_props = {}
        for p in element.findall("edm:Property", self.NS):
            property_name = p.get("Name")
            property_type = p.get("Type")
            is_collection, collection_type = self.check_collection_type(property_type)
            if is_collection:
                is_complex = self.type_is_custom(type_str=collection_type, alias=schema_alias, custom_types=complex_types)
                is_enum = self.type_is_custom(type_str=collection_type, alias=schema_alias, custom_types=enum_types)
            else:
                is_complex = self.type_is_custom(type_str=property_type, alias=schema_alias, custom_types=complex_types)
                is_enum = self.type_is_custom(type_str=property_type, alias=schema_alias, custom_types=enum_types)
                
            normalized_name = self.normalize_property_name(property_name, property_type)
            property = {
                "logical_name": self.normalize_property_name(property_name, property_type),
                "api_name":property_name,
                "type": property_type,
                "is_complex": is_complex,
                "is_enum": is_enum,
                "is_collection": is_collection,
                "collection_type": collection_type
            }
            all_props[normalized_name] = property
        return all_props
    
    # Get EntityType Navigation Properties. These are used in $expand odata queries.
    def get_navigation_properties(self, element, entity_name, schema_alias):
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
            if schema_alias is not None and schema_alias != "":
                _alias_re = re.compile(r"^" + schema_alias + r"\.([^\.]+?)$")
                match = _alias_re.match(nav_type)
                to_entity_name = match.group(1) if match else nav_type
            else:
                to_entity_name = nav_type
            
            from_property = constraints[0]['from_name'] if constraints else None
            to_property = constraints[0]['to_name'] if constraints else None

            navs[nav_name] = {
                "partner": partner,
                "from_property": from_property,
                "to_property": to_property,
                "to_entity_name": to_entity_name,
                "to_entity_base_type": nav_type,
                "nullable": np.get("Nullable"),
            }
        return navs