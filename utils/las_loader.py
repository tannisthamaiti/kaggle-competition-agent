"""
Handles loading and parsing .las file content.
"""

import lasio
from lasio.las import LASFile

from utils.interfaces import IFileLoader
from utils.models import FileValidationError
from utils.utils import logger

class LocalFileLoader(IFileLoader):
    """
    Modified to load content from a string instead of a path
    to work with file uploads.
    """
    def load(self, content: str) -> str:
        if content is None:
            raise FileNotFoundError("No content provided.")
        return content

class LasParser:
    """Parses a string content into a LASFile object."""
    def __init__(self, file_loader: IFileLoader):
        self._file_loader = file_loader

    def validate_las_file(self, las: LASFile):
        """Performs basic validation on the LAS file."""
        well_name = las.well.WELL.value
        if not well_name or well_name == " ":
# In a real app, you might want to raise FileValidationError here
            logger.warning("File validation: Well Name (WELL) is missing.")
# Not raising error as per original file, but logging it.
            pass

    def load_las_file(self, content: str) -> LASFile:
        """
        Loads and validates LAS content from a string.
        """
        file_content_str = self._file_loader.load(content)
        las = lasio.read(file_content_str)
        self.validate_las_file(las)
        return las
