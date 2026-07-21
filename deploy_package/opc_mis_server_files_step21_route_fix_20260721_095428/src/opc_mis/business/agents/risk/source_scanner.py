"""Pre-scan TeamPack rules and alerts using exact record identifiers."""

from dataclasses import dataclass
from numbers import Real

from opc_mis.business.agents.risk.context_loader import RiskContext, RiskContextError
from opc_mis.domain.dataset import DatasetRecord
from opc_mis.domain.enums import RiskScope, RiskSeverity
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import LineageFactory
from opc_mis.domain.risk_models import RiskSourceAlert, RiskSourceRule
from opc_mis.domain.team_pack import SheetRegistry


@dataclass(frozen=True)
class RiskSourceScan:
    rules: tuple[RiskSourceRule, ...]
    case_alerts: tuple[RiskSourceAlert, ...]
    global_alerts: tuple[RiskSourceAlert, ...]
    evidence_refs: tuple[EvidenceRef, ...]


def parse_related_record(value: object) -> tuple[str, ...]:
    """Split only explicit comma-delimited identifiers; never use substrings."""
    if value is None:
        return ()
    return tuple(token for item in str(value).split(",") if (token := item.strip()))


def parse_severity(value: object) -> RiskSeverity:
    """Normalize the finite TeamPack severity vocabulary."""
    try:
        return RiskSeverity(str(value).strip().upper())
    except ValueError as exc:
        raise RiskContextError(f"Unsupported Risk severity: {value!r}.") from exc


class RiskSourceScanner:
    """Build a traceable pre-scan without interpreting natural-language descriptions."""

    RULE_FIELDS = (
        "rule_id",
        "risk_type",
        "trigger_condition",
        "severity",
        "required_action",
        "owner_agent",
    )
    ALERT_FIELDS = (
        "alert_id",
        "alert_type",
        "related_record",
        "severity",
        "risk_score",
        "description",
        "recommended_action",
    )

    def scan(self, context: RiskContext, lineage: LineageFactory) -> RiskSourceScan:
        evidence: dict[str, EvidenceRef] = {}
        rules = tuple(
            self._rule(record, lineage, evidence)
            for record in context.dataset.records(SheetRegistry.RISK_RULES)
        )
        if len({item.rule_id for item in rules}) != len(rules):
            raise RiskContextError("Risk rule primary keys are not unique.")

        transaction_ids = {
            record.record_id
            for record in context.dataset.records(SheetRegistry.BANK_TRANSACTIONS)
        }
        cashflow_ids = {
            record.record_id for record in context.dataset.records(SheetRegistry.CASHFLOW)
        }
        case_alerts: list[RiskSourceAlert] = []
        global_alerts: list[RiskSourceAlert] = []
        for record in context.dataset.records(SheetRegistry.ALERTS):
            tokens = parse_related_record(record.values.get("related_record"))
            if set(tokens) & context.case_entity_ids:
                case_alerts.append(
                    self._alert(record, tokens, RiskScope.CASE_SPECIFIC, lineage, evidence)
                )
            elif set(tokens) & (transaction_ids | cashflow_ids):
                global_alerts.append(
                    self._alert(record, tokens, RiskScope.OPC_GLOBAL, lineage, evidence)
                )
        selected_alerts = (*case_alerts, *global_alerts)
        if len({item.alert_id for item in selected_alerts}) != len(selected_alerts):
            raise RiskContextError("Selected Risk alert primary keys are not unique.")
        return RiskSourceScan(
            rules=rules,
            case_alerts=tuple(case_alerts),
            global_alerts=tuple(global_alerts),
            evidence_refs=tuple(evidence[key] for key in sorted(evidence)),
        )

    def _rule(
        self,
        record: DatasetRecord,
        lineage: LineageFactory,
        evidence: dict[str, EvidenceRef],
    ) -> RiskSourceRule:
        refs = tuple(lineage.record_field(record, field) for field in self.RULE_FIELDS)
        evidence.update((item.evidence_id, item) for item in refs)
        values = record.values
        required = tuple(field for field in self.RULE_FIELDS if values.get(field) is None)
        if required:
            raise RiskContextError(
                f"Risk rule {record.record_id} is missing: {', '.join(required)}."
            )
        return RiskSourceRule(
            rule_id=str(values["rule_id"]),
            risk_type=str(values["risk_type"]),
            declared_condition=str(values["trigger_condition"]),
            severity=parse_severity(values["severity"]),
            required_action=str(values["required_action"]),
            owner_agent=str(values["owner_agent"]),
            evidence_ids=tuple(item.evidence_id for item in refs),
        )

    def _alert(
        self,
        record: DatasetRecord,
        tokens: tuple[str, ...],
        scope: RiskScope,
        lineage: LineageFactory,
        evidence: dict[str, EvidenceRef],
    ) -> RiskSourceAlert:
        refs = tuple(lineage.record_field(record, field) for field in self.ALERT_FIELDS)
        evidence.update((item.evidence_id, item) for item in refs)
        values = record.values
        raw_score = values.get("risk_score")
        score = (
            None
            if isinstance(raw_score, bool) or not isinstance(raw_score, Real)
            else raw_score
        )
        return RiskSourceAlert(
            alert_id=record.record_id,
            alert_type=str(values.get("alert_type") or ""),
            related_entity_ids=tokens,
            relation_scope=scope,
            severity=parse_severity(values.get("severity")),
            source_risk_score=score,
            description=str(values.get("description") or ""),
            recommended_action=str(values.get("recommended_action") or ""),
            evidence_ids=tuple(item.evidence_id for item in refs),
        )
