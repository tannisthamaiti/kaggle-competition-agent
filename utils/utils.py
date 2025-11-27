"""
Contains utility classes, such as the mock logger.
"""

# Mocked knack.log.get_logger
# In a real app, you might replace this with:
# import logging
# logger = logging.getLogger(__name__)

class MockLogger:
    """Mocked logger to replace knack.log.get_logger."""
    def info(self, msg): print(f"INFO: {msg}")
    def warning(self, msg): print(f"WARNING: {msg}")
    def error(self, msg): print(f"ERROR: {msg}")

logger = MockLogger()
