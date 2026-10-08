"""Case-only severity aggregation for initial Risk."""

from opc_mis.domain.enums import RiskLevel, RiskSeverity

_WEIGHT = {
    RiskSeverity.LOW: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.HIGH: 3,
    RiskSeverity.CRITICAL: 4,
}


def aggregate_case_severity(severities: tuple[RiskSeverity, ...]) -> RiskLevel:
    """Use the maximum case-specific severity without inventing a score."""
    if not severities:
        return RiskLevel.NO_CASE_SIGNAL
    highest = max(severities, key=_WEIGHT.__getitem__)
    return RiskLevel(highest.value)
