"""ghostapi: catch hallucinated and deprecated API usage before it ships."""

__version__ = "0.1.0"

from .checker import Finding, ScanResult, check_file, check_source

__all__ = ["Finding", "ScanResult", "check_file", "check_source", "__version__"]
