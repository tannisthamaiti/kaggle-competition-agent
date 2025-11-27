"""
Handles the business logic of mapping from a LASFile object
to OSDU-like Record objects.
"""

import lasio
import urllib.parse
from typing import Dict, List, Union

from .models import Record, Configuration
from .utils import logger

class AttributeBuilder:
    """Builds specific attributes for the OSDU record."""

    # Common
    def build_acl(self, config: Configuration) -> Dict[str, List[str]]:
        """Builds the Access Control List (ACL) block."""
        if None in [config.data_default_viewers, config.data_default_owners]:
            raise ValueError("Config missing 'data_default_viewers' or 'data_default_owners'")
        return {"viewers": config.data_default_viewers, "owners": config.data_default_owners}

    def build_legal(self, config: Configuration) -> Dict[str, Union[List[str], str]]:
        """Builds the Legal block."""
        if None in [config.legal_tags, config.legal_relevant_data_countries, config.legal_status]:
            raise ValueError("Config missing 'legal_tags', 'legal_relevant_data_countries', or 'legal_status'")
        return {
            "legaltags": config.legal_tags,
            "otherRelevantDataCountries": config.legal_relevant_data_countries,
            "status": config.legal_status
        }

    # Wellbore
    def _get_uwi(self, las: lasio.LASFile) -> str:
        """Safely extracts the UWI from the LAS file."""
        try:
            uwi = las.well.UWI.value
            return uwi if uwi and uwi.strip() else None
        except AttributeError:
            return None

    def _build_name_aliases(self, uwi: str, config: Configuration) -> List[Dict[str, str]]:
        """Builds the NameAliases list using the UWI."""
        if uwi:
            if config.data_partition_id is None:
                raise ValueError("Config missing 'data_partition_id'")
            return [{
                "AliasName": uwi,
                "AliasNameTypeID": f"{config.data_partition_id}:reference-data--AliasNameType:UniqueIdentifier:",
            }]
        return []

    def build_wellbore_data(self, las: lasio.LASFile, config: Configuration) -> Dict[str, any]:
        """Builds the main 'data' block for a Wellbore record."""
        well_name = las.well.WELL.value
        uwi = self._get_uwi(las)
        name_aliases = self._build_name_aliases(uwi, config)
        return {"FacilityName": well_name, "NameAliases": name_aliases}

    # Well Log
    def _build_curves(self, las: lasio.LASFile, data_partition_id: str) -> List[Dict[str, str]]:
        """Builds the list of Curves for a WellLog record."""
        if data_partition_id is None:
            raise ValueError("Config missing 'data_partition_id'")
        curves = []
        try:
            for curve in las.curves:
                unit = urllib.parse.quote(curve.unit, safe="").replace(" ", "-")
                if unit == "": unit = "UNITLESS"
                curves.append({
                    "CurveID": curve.mnemonic,
                    "CurveUnit": f"{data_partition_id}:reference-data--UnitOfMeasure:{unit}:",
                    "Mnemonic": curve.mnemonic,
                })
        except AttributeError:
            return []
        return curves

    def build_well_log_data(self, las: lasio.LASFile, config: Configuration, wellbore_id: str) -> Dict[str, any]:
        """Builds the main 'data' block for a WellLog record."""
        if not wellbore_id:
            raise ValueError("Wellbore ID is required")
        if las.curves and len(las.curves) > 0 and las.curves[0].mnemonic:
            ref_curve_id = las.curves[0].mnemonic
        else:
            raise ValueError("Failed to extract reference curve ID from LAS file.")
        
        if config.data_partition_id is None:
             raise ValueError("Config missing 'data_partition_id' for building curves")

        return {
            "ReferenceCurveID": ref_curve_id,
            "Curves": self._build_curves(las, config.data_partition_id),
            "WellboreID": f"{config.data_partition_id}:master-data--Wellbore:{wellbore_id}:",
        }

class LasToRecordMapper:
    """Orchestrates mapping a LASFile to a Record."""
    def __init__(self, las: lasio.LASFile, configuration: Configuration) -> None:
        if not isinstance(las, lasio.LASFile):
            raise TypeError("Please provide a LAS data object as input.")
        self.config = configuration
        self.las = las
        self.attr_builder = AttributeBuilder()

    def map_to_wellbore_record(self) -> Record:
        """Maps the loaded LAS file to a Wellbore Record object."""
        kind = "osdu:wks:master-data--Wellbore:1.0.0"
        acl = self.attr_builder.build_acl(self.config)
        legal = self.attr_builder.build_legal(self.config)
        data = self.attr_builder.build_wellbore_data(self.las, self.config)
        return Record(kind, acl, legal, data)
    
    def map_to_well_log_record(self, wellbore_id: str) -> Record:
        """Maps the loaded LAS file to a WellLog Record object."""
        kind = "osdu:wks:work-product-component--WellLog:1.0.0"
        acl = self.attr_builder.build_acl(self.config)
        legal = self.attr_builder.build_legal(self.config)
        data = self.attr_builder.build_well_log_data(self.las, self.config, wellbore_id)
        
        # Create a derived ID for the well log
        log_id = f"{wellbore_id}-log"
        
        return Record(kind, acl, legal, data, id=log_id)