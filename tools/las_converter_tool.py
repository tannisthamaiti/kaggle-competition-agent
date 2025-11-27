"""
Agent tools that wrap existing LAS conversion functionality.
"""

import json
import sys
import os
from typing import Dict
from dataclasses import asdict

# Import your existing utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.models import Configuration, FileValidationError, Record
from utils.las_loader import LasParser, LocalFileLoader
from utils.record_mapper import LasToRecordMapper
from utils.service import convert_las_to_osdu_records

# Global variable to store last read content (to avoid token limits)
_LAST_READ_CONTENT = None
_LAST_READ_FILEPATH = None


def read_las_file_tool(file_path: str) -> dict:
    """
    Read a LAS file from disk and return summary (not full content).
    
    This tool reads LAS files from the test_data directory and stores
    the content internally. Returns only a summary to avoid token limits.
    
    Args:
        file_path: Name of the LAS file (e.g., "7_1-1.las") or full path.
    
    Returns:
        Dictionary with status and file summary
    
    Example:
        >>> result = read_las_file_tool("7_1-1.las")
        >>> # Content stored for other tools to process
    """
    global _LAST_READ_CONTENT, _LAST_READ_FILEPATH
    
    try:
        # If just filename provided, look in test_data
        if not os.path.dirname(file_path):
            file_path = os.path.join("test_data", file_path)
        
        # Check if file exists
        if not os.path.exists(file_path):
            available = ", ".join([f for f in os.listdir("test_data") if f.endswith('.las')])
            return {
                "status": "error",
                "error_message": f"File not found: {file_path}. Available: {available}"
            }
        
        # Read the file
        with open(file_path, 'r', encoding='latin-1') as f:
            content = f.read()
        
        # Store for other tools
        _LAST_READ_CONTENT = content
        _LAST_READ_FILEPATH = file_path
        
        # Extract basic info
        try:
            las_parser = LasParser(LocalFileLoader())
            las_obj = las_parser.load_las_file(content)
            
            well_name = "Unknown"
            if hasattr(las_obj, 'well') and hasattr(las_obj.well, 'WELL'):
                well_name = las_obj.well.WELL.value
            
            curve_count = len(las_obj.curves) if hasattr(las_obj, 'curves') else 0
            
            return {
                "status": "success",
                "file_path": file_path,
                "well_name": well_name,
                "curve_count": curve_count,
                "size_chars": len(content),
                "message": f"Loaded: {well_name}, {curve_count} curves, {len(content)} chars. Ready for processing."
            }
        except Exception as e:
            return {
                "status": "success",
                "file_path": file_path,
                "size_chars": len(content),
                "message": f"File loaded ({len(content)} chars). Ready for processing.",
                "parse_note": f"Quick parse failed: {str(e)}"
            }
        
    except Exception as e:
        return {
            "status": "error",
            "error_message": f"Error reading file: {str(e)}"
        }


def validate_las_file_tool(las_content: str = None) -> dict:
    """
    Validate LAS file content without performing full conversion.
    
    Args:
        las_content: LAS content string, or None to use last read file
    
    Returns:
        Dictionary with validation results
    
    Example:
        >>> read_las_file_tool("7_1-1.las")
        >>> result = validate_las_file_tool()  # Uses last read file
    """
    global _LAST_READ_CONTENT
    
    # Use stored content if not provided
    if las_content is None or las_content.strip() == "":
        if _LAST_READ_CONTENT is None:
            return {
                "status": "error",
                "error_message": "No LAS content provided. Use read_las_file_tool first."
            }
        las_content = _LAST_READ_CONTENT
    
    try:
        las_parser = LasParser(LocalFileLoader())
        las_obj = las_parser.load_las_file(las_content)
        
        # Extract validation info
        version = las_obj.version.VERS.value if hasattr(las_obj.version, 'VERS') else "Unknown"
        curve_count = len(las_obj.curves) if hasattr(las_obj, 'curves') else 0
        
        well_name = "Unknown"
        if hasattr(las_obj, 'well') and hasattr(las_obj.well, 'WELL'):
            well_name = las_obj.well.WELL.value
        
        return {
            "status": "success",
            "is_valid": True,
            "version": version,
            "well_name": well_name,
            "curve_count": curve_count,
            "message": "LAS file is valid and can be processed"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "is_valid": False,
            "error_message": f"LAS validation failed: {str(e)}"
        }


def extract_las_metadata_tool(las_content: str = None) -> dict:
    """
    Extract metadata and summary information from LAS file.
    
    Args:
        las_content: LAS content string, or None to use last read file
    
    Returns:
        Dictionary containing extracted metadata
    
    Example:
        >>> read_las_file_tool("7_1-1.las")
        >>> result = extract_las_metadata_tool()  # Uses last read file
    """
    global _LAST_READ_CONTENT
    
    # Use stored content if not provided
    if las_content is None or las_content.strip() == "":
        if _LAST_READ_CONTENT is None:
            return {
                "status": "error",
                "error_message": "No LAS content provided. Use read_las_file_tool first."
            }
        las_content = _LAST_READ_CONTENT
    
    try:
        las_parser = LasParser(LocalFileLoader())
        las_obj = las_parser.load_las_file(las_content)
        
        # Extract well information
        well_info = {}
        if hasattr(las_obj, 'well'):
            for item in las_obj.well:
                well_info[item.mnemonic] = item.value
        
        # Extract curves
        curves = []
        if hasattr(las_obj, 'curves'):
            curves = [curve.mnemonic for curve in las_obj.curves]
        
        metadata = {
            "well_name": well_info.get("WELL", "Unknown"),
            "field": well_info.get("FLD", "Unknown"),
            "country": well_info.get("CNTY", "Unknown"),
            "uwi": well_info.get("UWI", "Unknown"),
            "date": well_info.get("DATE", "Unknown"),
            "company": well_info.get("COMP", "Unknown"),
            "curves": curves,
            "curve_count": len(curves),
            "depth_range": {
                "start": well_info.get("STRT"),
                "stop": well_info.get("STOP"),
                "step": well_info.get("STEP")
            }
        }
        
        return {
            "status": "success",
            "metadata": metadata
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error_message": f"Metadata extraction failed: {str(e)}"
        }


def convert_las_to_osdu_tool(
    las_content: str = None,
    wellbore_id: str = None,
    config_json: str = None
) -> dict:
    """
    Convert LAS file content to OSDU Wellbore and WellLog records.
    
    Args:
        las_content: LAS content string, or None to use last read file
        wellbore_id: Unique identifier for the wellbore
        config_json: JSON config string, or None to use default config
    
    Returns:
        Dictionary with conversion results
    
    Example:
        >>> read_las_file_tool("7_1-1.las")
        >>> result = convert_las_to_osdu_tool(wellbore_id="wb-001")
    """
    global _LAST_READ_CONTENT, _LAST_READ_FILEPATH
    
    # Use stored content if not provided
    if las_content is None or las_content.strip() == "":
        if _LAST_READ_CONTENT is None:
            return {
                "status": "error",
                "error_message": "No LAS content provided. Use read_las_file_tool first."
            }
        las_content = _LAST_READ_CONTENT
    
    # Generate wellbore_id if not provided
    if wellbore_id is None:
        if _LAST_READ_FILEPATH:
            wellbore_id = f"wellbore-{os.path.basename(_LAST_READ_FILEPATH).replace('.las', '')}"
        else:
            wellbore_id = "wellbore-001"
    
    # Use default config if not provided
    if config_json is None:
        try:
            with open('config/default_config.json', 'r') as f:
                config_json = f.read()
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Could not load default config: {str(e)}"
            }
    
    try:
        # Parse configuration
        try:
            config_data = json.loads(config_json)
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "error_message": f"Invalid JSON configuration: {str(e)}",
                "error_type": "configuration_error"
            }
        
        # Use your existing service function
        try:
            records = convert_las_to_osdu_records(
                las_content=las_content,
                wellbore_id=wellbore_id,
                config_content=config_data
            )
            
            # Convert dataclasses to dicts
            wellbore_dict = asdict(records["wellbore_record"])
            welllog_dict = asdict(records["welllog_record"])
            
            return {
                "status": "success",
                "wellbore_record": wellbore_dict,
                "welllog_record": welllog_dict,
                "wellbore_id": wellbore_id,
                "message": "Conversion completed successfully"
            }
            
        except FileValidationError as e:
            return {
                "status": "error",
                "error_message": f"Validation error: {str(e)}",
                "error_type": "validation_error"
            }
        except Exception as e:
            return {
                "status": "error",
                "error_message": f"Conversion error: {str(e)}",
                "error_type": "mapping_error"
            }
            
    except Exception as e:
        return {
            "status": "error",
            "error_message": f"Unexpected error: {str(e)}",
            "error_type": "internal_error"
        }
