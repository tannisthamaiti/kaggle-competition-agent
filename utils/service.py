"""
Contains the main business logic/service layer function
that orchestrates the conversion process.
"""

from .models import Configuration, FileValidationError, Record
from .las_loader import LasParser, LocalFileLoader
from .record_mapper import LasToRecordMapper
from .utils import logger

def convert_las_to_osdu_records(las_content: str, wellbore_id: str, config_content: dict) -> dict:
    """
    Orchestrates the conversion from LAS string content to a Wellbore 
    and WellLog Record.
    
    Args:
        las_content: The string content of the .las file.
        wellbore_id: The ID to assign to the wellbore.
        config_content: The dictionary parsed from the config JSON.

    Returns:
        A dictionary containing the 'wellbore_record' and 'welllog_record'.
    
    Raises:
        ValueError, TypeError, FileValidationError: If validation or mapping fails.
    """
    try:
        # 1. Load Config
        config = Configuration(config_content)

        # 2. Load LAS
        las_parser = LasParser(LocalFileLoader())
        las_data = las_parser.load_las_file(las_content)

        # 3. Map to Records
        mapper = LasToRecordMapper(las_data, config)
        
        # --- Create Wellbore Record ---
        wellbore_record = mapper.map_to_wellbore_record()
        wellbore_record.id = wellbore_id # Set the ID
        
        # --- Create Well Log Record ---
        # Pass the wellbore_id for mapping
        welllog_record = mapper.map_to_well_log_record(wellbore_id)
        
        # 4. Return both records
        return {
            "wellbore_record": wellbore_record,
            "welllog_record": welllog_record
        }

    except (ValueError, TypeError, FileValidationError) as e:
        logger.error(f"Mapping/Validation Error: {e}")
        # Re-raise for the API layer to handle
        raise e
    except Exception as e:
        logger.error(f"Internal Server Error: {e}")
        # Re-raise as a generic exception
        raise Exception(f"An unexpected error occurred: {e}")
