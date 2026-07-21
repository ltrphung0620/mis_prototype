"""Side-effect-free Risk Agent with pre-scan and dependency-gated finalization."""

from opc_mis.business.agents.risk.context_loader import (
    RiskContext,
    RiskContextError,
    RiskContextLoader,
)
from opc_mis.business.agents.risk.rule_engine import TypedRiskRuleEngine, rule_dependency
from opc_mis.business.agents.risk.severity_policy import aggregate_case_severity
from opc_mis.business.agents.risk.source_scanner import RiskSourceScanner
from opc_mis.domain.approvals import ApprovalCondition, ApprovalSignal
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ApprovalTriggerEvent,
    ArtifactType,
    ComponentStatus,
    ProtectedAction,
    RiskAssessmentStatus,
    RiskDependency,
    RiskExecutionMode,
    RiskScope,
    RiskSeverity,
    RuleEvaluationStatus,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.risk_models import (
    HumanConfirmationPoint,
    InitialRiskAssessment,
    RiskComponentResult,
    RiskEvidenceLimitation,
    RiskFinding,
    RiskGlobalSignal,
    RiskPreScan,
    RiskRuleEvaluationSet,
    RiskSourceAlert,
    RiskSourceRule,
    RuleEvaluation,
)
from opc_mis.domain.team_pack import SheetRegistry


def _unique_evidence(*groups: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    by_id = {item.evidence_id: item for group in groups for item in group}
    return tuple(by_id[key] for key in sorted(by_id))


class RiskAgent:
    """Scan immediately, then finalize only after authoritative facts arrive."""

    component_id = "RISK_AGENT"

    def __init__(
        self,
        *,
        context_loader: RiskContextLoader,
        source_scanner: RiskSourceScanner | None = None,
        rule_engine: TypedRiskRuleEngine | None = None,
    ) -> None:
        self._context_loader = context_loader
        self._source_scanner = source_scanner or RiskSourceScanner()
        self._rule_engine = rule_engine or TypedRiskRuleEngine()

    async def execute(self, context: ExecutionContext) -> RiskComponentResult:
        """Return a stable pre-scan draft or finalized Risk artifact drafts."""
        try:
            mode = RiskExecutionMode(context.component_input["execution_mode"])
        except (KeyError, ValueError):
            return RiskComponentResult(
                status=ComponentStatus.FAILED_SAFE,
                runtime_events=(
                    RuntimeEvent(
                        event_type="RISK_FAILED_SAFE",
                        message="Risk requires an explicit PRE_SCAN or FINALIZE mode.",
                    ),
                ),
            )
        try:
            risk_context = await self._context_loader.load(context)
            lineage = LineageFactory(context.dataset_id, risk_context.dataset.source_hash)
            scan = self._source_scanner.scan(risk_context, lineage)
        except RiskContextError as exc:
            return RiskComponentResult(
                status=ComponentStatus.FAILED_SAFE,
                runtime_events=(RuntimeEvent(event_type="RISK_FAILED_SAFE", message=str(exc)),),
            )

        evaluations, engine_evidence = self._rule_engine.evaluate(
            risk_context,
            scan.rules,
            lineage,
        )
        global_signals = self._global_signals(
            pre_scan_case_id := risk_context.evaluation_case.evaluation_case_id,
            evaluations,
            scan.global_alerts,
        )
        rule_dependencies = tuple(rule_dependency(rule) for rule in scan.rules)
        pre_scan = RiskPreScan(
            evaluation_case_id=pre_scan_case_id,
            dataset_id=context.dataset_id,
            contract_id=risk_context.evaluation_case.contract_id,
            source_rule_ids=tuple(rule.rule_id for rule in scan.rules),
            source_rules=scan.rules,
            case_alerts=scan.case_alerts,
            global_alerts=scan.global_alerts,
            global_signals=global_signals,
            rule_dependencies=rule_dependencies,
            source_record_counts={
                SheetRegistry.RISK_RULES.sheet_name: len(scan.rules),
                SheetRegistry.ALERTS.sheet_name: len(
                    risk_context.dataset.records(SheetRegistry.ALERTS)
                ),
                SheetRegistry.BANK_TRANSACTIONS.sheet_name: len(
                    risk_context.dataset.records(SheetRegistry.BANK_TRANSACTIONS)
                ),
                SheetRegistry.DATA_CLASS.sheet_name: len(
                    risk_context.dataset.records(SheetRegistry.DATA_CLASS)
                ),
            },
        )
        upstream_evidence = tuple(
            evidence
            for artifact in (
                risk_context.finance_facts_artifact,
                risk_context.operations_facts_artifact,
            )
            if artifact is not None
            for evidence in artifact.evidence_refs
        )
        data_class_headers = risk_context.dataset.headers.get(
            SheetRegistry.DATA_CLASS.sheet_name, ()
        )
        data_class_evidence = (
            lineage.sheet_headers(SheetRegistry.DATA_CLASS.sheet_name, data_class_headers),
        ) if data_class_headers else ()
        pre_scan_evidence = _unique_evidence(
            scan.evidence_refs,
            engine_evidence,
            data_class_evidence,
        )
        evidence = _unique_evidence(pre_scan_evidence, upstream_evidence)
        pre_scan_draft = ArtifactDraft(
            artifact_type=ArtifactType.RISK_PRE_SCAN,
            evaluation_case_id=pre_scan.evaluation_case_id,
            producer=self.component_id,
            payload=pre_scan.model_dump(mode="json"),
            evidence_refs=pre_scan_evidence,
            identity_inputs={
                "dataset_source_hash": risk_context.dataset.source_hash,
                "evaluation_case_id": pre_scan.evaluation_case_id,
                "source_rule_ids": pre_scan.source_rule_ids,
                "case_alert_ids": tuple(item.alert_id for item in pre_scan.case_alerts),
                "global_alert_ids": tuple(item.alert_id for item in pre_scan.global_alerts),
            },
        )
        approval_signals = self._approval_signals(
            scan.rules,
            evaluations,
            pre_scan_evidence,
        )
        if mode is RiskExecutionMode.PRE_SCAN:
            return RiskComponentResult(
                status=ComponentStatus.COMPLETED,
                artifacts=(pre_scan_draft,),
                approval_signals=approval_signals,
                execution_mode=mode,
                pre_scan=pre_scan,
                runtime_events=(
                    RuntimeEvent(
                        event_type="RISK_PRE_SCAN_COMPLETED",
                        message="Risk pre-scan completed without owning dependency state.",
                    ),
                ),
            )

        pending = self._pending_dependencies(risk_context)
        if pending:
            return RiskComponentResult(
                status=ComponentStatus.FAILED_SAFE,
                execution_mode=mode,
                runtime_events=(
                    RuntimeEvent(
                        event_type="RISK_FAILED_SAFE",
                        message=(
                            "Risk FINALIZE was invoked without required workflow inputs: "
                            + ", ".join(item.value for item in pending)
                        ),
                    ),
                ),
            )

        rule_set = RiskRuleEvaluationSet(
            evaluation_case_id=pre_scan.evaluation_case_id,
            dataset_id=context.dataset_id,
            contract_id=pre_scan.contract_id,
            evaluations=evaluations,
        )
        limitations = self._limitations(pre_scan.evaluation_case_id, evaluations)
        findings = self._findings(pre_scan.evaluation_case_id, evaluations, scan.case_alerts)
        confirmations = self._confirmations(pre_scan.evaluation_case_id, scan.case_alerts)
        case_severities = tuple(
            evaluation.severity
            for evaluation in evaluations
            if evaluation.applicability_scope is RiskScope.CASE_SPECIFIC
            and evaluation.status is RuleEvaluationStatus.TRIGGERED
            and evaluation.severity is not None
        ) + tuple(alert.severity for alert in scan.case_alerts)
        finance_artifact = risk_context.finance_facts_artifact
        operations_artifact = risk_context.operations_facts_artifact
        if finance_artifact is None or operations_artifact is None:  # pragma: no cover
            raise RuntimeError("Dependency gate allowed Risk finalization without both facts.")
        assessment = InitialRiskAssessment(
            evaluation_case_id=pre_scan.evaluation_case_id,
            dataset_id=context.dataset_id,
            contract_id=pre_scan.contract_id,
            assessment_status=(
                RiskAssessmentStatus.LIMITED_BY_EVIDENCE
                if limitations
                else RiskAssessmentStatus.COMPLETE
            ),
            overall_risk_level=aggregate_case_severity(case_severities),
            triggered_rule_ids=tuple(
                evaluation.rule_id
                for evaluation in evaluations
                if evaluation.status is RuleEvaluationStatus.TRIGGERED
                and evaluation.applicability_scope is RiskScope.CASE_SPECIFIC
            ),
            findings=findings,
            source_alerts=scan.case_alerts,
            global_context_signals=global_signals,
            human_confirmation_points=confirmations,
            limitations=limitations,
            finance_facts_artifact_id=finance_artifact.artifact_id,
            operations_facts_artifact_id=operations_artifact.artifact_id,
        )
        drafts = (
            ArtifactDraft(
                artifact_type=ArtifactType.RISK_RULE_EVALUATION,
                evaluation_case_id=pre_scan.evaluation_case_id,
                producer=self.component_id,
                payload=rule_set.model_dump(mode="json"),
                evidence_refs=evidence,
            ),
            ArtifactDraft(
                artifact_type=ArtifactType.INITIAL_RISK_ASSESSMENT,
                evaluation_case_id=pre_scan.evaluation_case_id,
                producer=self.component_id,
                payload=assessment.model_dump(mode="json"),
                evidence_refs=evidence,
                identity_inputs={
                    "finance_facts_artifact_id": finance_artifact.artifact_id,
                    "operations_facts_artifact_id": operations_artifact.artifact_id,
                    "rule_evaluation_ids": tuple(
                        item.evaluation_id for item in evaluations
                    ),
                },
            ),
        )
        warnings = tuple(item.code for item in limitations)
        return RiskComponentResult(
            status=(
                ComponentStatus.COMPLETED_WITH_WARNINGS
                if warnings or confirmations
                else ComponentStatus.COMPLETED
            ),
            artifacts=drafts,
            execution_mode=mode,
            warnings=warnings,
            pre_scan=pre_scan,
            rule_evaluations=rule_set,
            risk_assessment=assessment,
            runtime_events=(
                RuntimeEvent(
                    event_type="RISK_FINALIZED",
                    message="Risk resumed and finalized from Finance and Operations facts.",
                ),
            ),
        )

    @staticmethod
    def _pending_dependencies(context: RiskContext) -> tuple[RiskDependency, ...]:
        pending: list[RiskDependency] = []
        if context.finance_facts is None:
            pending.append(RiskDependency.FINANCE_FACTS)
        if context.operations_facts is None:
            pending.append(RiskDependency.OPERATIONS_FACTS)
        return tuple(pending)

    @staticmethod
    def _global_signals(
        case_id: str,
        evaluations: tuple[RuleEvaluation, ...],
        global_alerts: tuple[RiskSourceAlert, ...],
    ) -> tuple[RiskGlobalSignal, ...]:
        signals: list[RiskGlobalSignal] = []
        for evaluation in evaluations:
            if (
                evaluation.applicability_scope is RiskScope.OPC_GLOBAL
                and evaluation.status is RuleEvaluationStatus.TRIGGERED
            ):
                signals.append(
                    RiskGlobalSignal(
                        signal_id=deterministic_id(
                            "RGS", case_id, evaluation.rule_id, evaluation.evidence_ids
                        ),
                        code="GLOBAL_RULE_TRIGGERED",
                        title=f"OPC-level rule {evaluation.rule_id} triggered",
                        detail=(
                            "The signal has no explicit relationship to this contract and is "
                            "excluded from its overall risk level."
                        ),
                        source_record_ids=(evaluation.rule_id,),
                        evidence_ids=evaluation.evidence_ids,
                    )
                )
        for alert in global_alerts:
            signals.append(
                RiskGlobalSignal(
                    signal_id=deterministic_id(
                        "RGS", case_id, alert.alert_id, alert.evidence_ids
                    ),
                    code="GLOBAL_SOURCE_ALERT",
                    title=f"OPC-level source alert {alert.alert_id}",
                    detail=(
                        "The alert relates to global records and is not attributed to this case."
                    ),
                    source_record_ids=(alert.alert_id, *alert.related_entity_ids),
                    evidence_ids=alert.evidence_ids,
                )
            )
        return tuple(signals)

    @staticmethod
    def _limitations(
        case_id: str, evaluations: tuple[RuleEvaluation, ...]
    ) -> tuple[RiskEvidenceLimitation, ...]:
        return tuple(
            RiskEvidenceLimitation(
                limitation_id=deterministic_id(
                    "RLM", case_id, item.rule_id, item.explanation, item.evidence_ids
                ),
                code="RULE_NOT_EVALUABLE",
                detail=item.explanation,
                scope=item.applicability_scope,
                rule_id=item.rule_id,
                evidence_ids=item.evidence_ids,
            )
            for item in evaluations
            if item.status is RuleEvaluationStatus.NOT_EVALUABLE
        )

    @staticmethod
    def _findings(
        case_id: str,
        evaluations: tuple[RuleEvaluation, ...],
        case_alerts: tuple[RiskSourceAlert, ...],
    ) -> tuple[RiskFinding, ...]:
        findings = [
            RiskFinding(
                finding_id=deterministic_id("RFN", case_id, item.rule_id, item.evidence_ids),
                code="RULE_TRIGGERED",
                title=f"Risk rule {item.rule_id} triggered",
                detail=item.explanation,
                severity=item.severity,
                source_rule_id=item.rule_id,
                evidence_ids=item.evidence_ids,
            )
            for item in evaluations
            if item.status is RuleEvaluationStatus.TRIGGERED
            and item.applicability_scope is RiskScope.CASE_SPECIFIC
            and item.severity is not None
        ]
        findings.extend(
            RiskFinding(
                finding_id=deterministic_id("RFN", case_id, alert.alert_id, alert.evidence_ids),
                code="EXPLICIT_SOURCE_ALERT",
                title=f"Source alert {alert.alert_id}: {alert.alert_type}",
                detail=alert.description,
                severity=alert.severity,
                source_alert_id=alert.alert_id,
                evidence_ids=alert.evidence_ids,
            )
            for alert in case_alerts
        )
        return tuple(findings)

    @staticmethod
    def _confirmations(
        case_id: str, case_alerts: tuple[RiskSourceAlert, ...]
    ) -> tuple[HumanConfirmationPoint, ...]:
        return tuple(
            HumanConfirmationPoint(
                confirmation_id=deterministic_id(
                    "HCP", case_id, alert.alert_id, alert.evidence_ids
                ),
                reason_code="HIGH_SEVERITY_SOURCE_ALERT_REVIEW",
                question=(
                    f"Please confirm the case context and supporting evidence for alert "
                    f"{alert.alert_id}; Risk has preserved the source statement without "
                    "treating its description as structured proof."
                ),
                severity=alert.severity,
                evidence_ids=alert.evidence_ids,
            )
            for alert in case_alerts
            if alert.severity in {RiskSeverity.HIGH, RiskSeverity.CRITICAL}
        )

    @staticmethod
    def _approval_signals(
        rules: tuple[RiskSourceRule, ...],
        evaluations: tuple[RuleEvaluation, ...],
        evidence: tuple[EvidenceRef, ...],
    ) -> tuple[ApprovalSignal, ...]:
        policies = {
            "document_sent_to_partner": (
                ApprovalTriggerEvent.DOCUMENT_EXTERNAL_RELEASE_REQUESTED,
                ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER,
            ),
            "requested_amount": (
                ApprovalTriggerEvent.LARGE_FINANCIAL_DECISION_REQUESTED,
                ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION,
            ),
        }
        by_rule = {rule.rule_id: rule for rule in rules}
        by_evidence = {item.evidence_id: item for item in evidence}
        signals: list[ApprovalSignal] = []
        for evaluation in evaluations:
            rule = by_rule[evaluation.rule_id]
            if (
                evaluation.status is not RuleEvaluationStatus.NOT_APPLICABLE
                or evaluation.applicability_scope is not RiskScope.EVENT_SPECIFIC
                or evaluation.source_field not in policies
                or evaluation.operator is None
                or evaluation.threshold is None
                or rule.required_action.strip().casefold() != "human approval required"
            ):
                continue
            trigger_event, protected_action = policies[evaluation.source_field]
            signals.append(
                ApprovalSignal(
                    approval_type="HUMAN_APPROVAL",
                    protected_action=protected_action,
                    trigger_event=trigger_event,
                    trigger_rule=rule.rule_id,
                    condition=ApprovalCondition(
                        source_field=evaluation.source_field,
                        operator=evaluation.operator,
                        threshold=evaluation.threshold,
                    ),
                    evidence_refs=tuple(
                        by_evidence[item]
                        for item in evaluation.evidence_ids
                        if item in by_evidence
                    ),
                )
            )
        return tuple(signals)
