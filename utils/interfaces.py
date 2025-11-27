"""
Contains Abstract Base Classes (ABCs) defining interfaces for the application.
"""

from abc import ABC, abstractmethod

class IFileLoader(ABC):
    """Interface for file loading strategies."""
    @abstractmethod
    def load(self, content: str) -> str:
        """Loads content from a source."""
        pass
