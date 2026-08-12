from .capacity import DatabasePoolExhaustedRule
from .database import DatabaseUniqueViolationRule
from .network import DownstreamUnavailableRule
from .performance import SlowDatabaseQueryRule

RULES = [
    DatabasePoolExhaustedRule(),
    DatabaseUniqueViolationRule(),
    DownstreamUnavailableRule(),
    SlowDatabaseQueryRule(),
]

__all__ = ["RULES"]
