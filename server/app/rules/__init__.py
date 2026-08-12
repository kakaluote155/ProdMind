from .database import DatabaseUniqueViolationRule
from .network import DownstreamUnavailableRule

RULES = [
    DatabaseUniqueViolationRule(),
    DownstreamUnavailableRule(),
]

__all__ = ["RULES"]
