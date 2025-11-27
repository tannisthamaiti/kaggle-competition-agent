"""
Contains the core data structures and custom exceptions for the application.
"""

import lasio
from dataclasses import dataclass
from typing import Dict, List, Union, Optional

# --- Custom Exception ---

class FileValidationError(Exception):
    """Raised when a file fails a domain-specific validation rule."""
    def __init__(self, message="File must have a valid Well Name populated."):
        super().__init__(message)

# --- Configuration Model ---

class Configuration:
    """
    Configuration class. Assumes config_data is a dictionary
    loaded from the uploaded config JSON.
    """
    def __init__(self, config_data: dict):
        self.data_default_viewers = config_data.get("data_default_viewers")
        self.data_default_owners = config_data.get("data_default_owners")
        self.legal_tags = config_data.get("legal_tags")
        self.legal_relevant_data_countries = config_data.get("legal_relevant_data_countries")
        self.legal_status = config_data.get("legal_status")
        self.data_partition_id = config_data.get("data_partition_id")

# --- OSDU Record Model ---

@dataclass
class Record:
    """A dataclass representing the OSDU-like JSON record."""
    kind: str
    acl: Dict[str, List[str]]
    legal: Dict[str, Union[List[str], str]]
    data: Dict[str, any]
    id: Optional[str] = None