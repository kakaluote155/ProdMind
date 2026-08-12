from .capacity import DatabasePoolExhaustedRule
from .database import DatabaseUniqueViolationRule
from .network import DownstreamUnavailableRule
from .performance import SlowDatabaseQueryRule, SlowDownstreamServiceRule

RULES = [
    DatabasePoolExhaustedRule(),
    DatabaseUniqueViolationRule(),
    DownstreamUnavailableRule(),
    SlowDownstreamServiceRule(),
    SlowDatabaseQueryRule(),
]

__all__ = ["RULES"]
