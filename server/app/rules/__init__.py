from .capacity import DatabasePoolExhaustedRule
from .database import DatabaseUniqueViolationRule
from .network import DownstreamUnavailableRule

RULES = [
    DatabasePoolExhaustedRule(),
    DatabaseUniqueViolationRule(),
    DownstreamUnavailableRule(),
]

__all__ = ["RULES"]
