"""Validate artifact schema and evidence lineage before persistence."""

import json
import re

from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.enums import ArtifactType, SourceType, ValidationStatus
from opc_mis.domain.finance_models import FinanceAssessment, FinanceFacts
from opc_mis.domain.operations_models import OperationsAssessment, OperationsFacts
from opc_mis.domain.serialization import json_safe
from opc_mis.domain.validation_reports import ValidationReport


class EvidenceValidator:
    """Minimal deterministic validator for Planner artifact drafts."""

    async def validate(self, draft: ArtifactDraft) -> ValidationReport:
        """Reject non-JSON payloads and broken derived-evidence references."""
        checks: list[str] = []
        blocking_errors: list[str] = []
        warnings: list[str] = []

        try:
            json.dumps(
                json_safe(draft.payload),
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            checks.append("SCHEMA_JSON_SAFE")
        except (TypeError, ValueError) as exc:
            blocking_errors.append(f"Artifact payload is not strict JSON: {exc}")

        evidence_ids = {evidence.evidence_id for evidence in draft.evidence_refs}
        if len(evidence_ids) != len(draft.evidence_refs):
            blocking_errors.append("Artifact contains duplicate evidence IDs.")
        else:
            checks.append("LINEAGE_IDS_UNIQUE")

        for evidence in draft.evidence_refs:
            if evidence.source_type is not SourceType.DERIVED:
                continue
            missing = tuple(
                source_id
                for source_id in evidence.source_evidence_ids
                if source_id not in evidence_ids
            )
            if missing:
                blocking_errors.append(
                    f"Derived evidence {evidence.evidence_id} has unknown sources: "
                    f"{', '.join(missing)}"
                )
        if not any("unknown sources" in error for error in blocking_errors):
            checks.append("LINEAGE_DERIVED_SOURCES_EXIST")

        if draft.artifact_type is ArtifactType.FINANCE_FACTS:
            self._validate_finance_facts(draft, evidence_ids, checks, blocking_errors)
        elif draft.artifact_type is ArtifactType.FINANCE_ASSESSMENT:
            self._validate_finance_assessment(draft, checks, blocking_errors)
        elif draft.artifact_type is ArtifactType.OPERATIONS_FACTS:
            self._validate_operations_facts(draft, evidence_ids, checks, blocking_errors)
        elif draft.artifact_type is ArtifactType.OPERATIONS_ASSESSMENT:
            self._validate_operations_assessment(
                draft,
                evidence_ids,
                checks,
                blocking_errors,
            )

        if blocking_errors:
            status = ValidationStatus.BLOCKED
        elif warnings:
            status = ValidationStatus.VALID_WITH_WARNINGS
        else:
            status = ValidationStatus.VALID
        return ValidationReport(
            status=status,
            checks=tuple(checks),
            blocking_errors=tuple(blocking_errors),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _validate_finance_facts(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        try:
            facts = FinanceFacts.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid FINANCE_FACTS schema: {exc}")
            return
        fact_ids = {fact.fact_id for fact in facts.facts}
        if len(fact_ids) != len(facts.facts):
            errors.append("FINANCE_FACTS contains duplicate fact IDs.")
        for fact in facts.facts:
            required = {fact.evidence_id, *fact.source_evidence_ids}
            missing = required - evidence_ids
            if missing:
                errors.append(
                    f"Finance fact {fact.fact_id} references unknown evidence: "
                    f"{', '.join(sorted(missing))}"
                )
        referenced_evidence = {
            evidence_id
            for observation in facts.observations
            for evidence_id in observation.evidence_ids
        } | {
            evidence_id
            for limitation in facts.limitations
            for evidence_id in limitation.evidence_ids
        }
        if not referenced_evidence.issubset(evidence_ids):
            errors.append("Finance observation or limitation references unknown evidence.")
        observation_fact_ids = {
            fact_id for observation in facts.observations for fact_id in observation.fact_ids
        }
        if not observation_fact_ids.issubset(fact_ids):
            errors.append("Finance observation references an unknown fact ID.")
        if not errors:
            checks.append("FINANCE_FACTS_REFERENCES_VERIFIED")

    @staticmethod
    def _validate_finance_assessment(
        draft: ArtifactDraft,
        checks: list[str],
        errors: list[str],
    ) -> None:
        try:
            assessment = FinanceAssessment.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid FINANCE_ASSESSMENT schema: {exc}")
            return
        known = set(assessment.fact_ids)
        if len(known) != len(assessment.fact_ids):
            errors.append("FINANCE_ASSESSMENT contains duplicate fact IDs.")
        forbidden_keys = {
            "risk_level",
            "risk_score",
            "severity",
            "triggered_rule_ids",
            "approval_required",
            "approval_request",
            "banking_option",
            "decision_card",
        }
        present_keys = EvidenceValidator._recursive_keys(draft.payload)
        forbidden_present = {
            key
            for key in present_keys
            if key in forbidden_keys
            or key.startswith(("risk_", "approval_", "banking_", "decision_", "triggered_rule"))
        }
        if forbidden_present:
            errors.append(
                "FINANCE_ASSESSMENT contains downstream fields: "
                + ", ".join(sorted(forbidden_present))
            )
        forbidden_terms = (
            "risk",
            "rủi ro",
            "severity",
            "approval",
            "phê duyệt",
            "ngân hàng",
            "banking",
            "khoản vay",
            "tín dụng",
            "rr-",
        )
        narrative_texts = (
            assessment.narrative.headline,
            *(statement.text for statement in assessment.narrative.statements),
        )
        if any(
            re.search(r"\d", text) or any(term in text.casefold() for term in forbidden_terms)
            for text in narrative_texts
        ):
            errors.append("Finance narrative contains unsupported numeric or downstream text.")
        observation_fact_ids = {
            fact_id for observation in assessment.observations for fact_id in observation.fact_ids
        }
        if not observation_fact_ids.issubset(known):
            errors.append("Finance assessment observation references an unknown fact.")
        for statement in assessment.narrative.statements:
            if not set(statement.fact_ids).issubset(known):
                errors.append(
                    f"Narrative statement {statement.statement_id} cites an unknown fact."
                )
        if not errors:
            checks.append("FINANCE_ASSESSMENT_BOUNDARY_VALID")

    @staticmethod
    def _validate_operations_facts(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        try:
            facts = OperationsFacts.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid OPERATIONS_FACTS schema: {exc}")
            return
        fact_ids = {fact.fact_id for fact in facts.facts}
        if len(fact_ids) != len(facts.facts):
            errors.append("OPERATIONS_FACTS contains duplicate fact IDs.")
        for fact in facts.facts:
            missing = {fact.evidence_id, *fact.source_evidence_ids} - evidence_ids
            if missing:
                errors.append(
                    f"Operations fact {fact.fact_id} references unknown evidence: "
                    f"{', '.join(sorted(missing))}"
                )
        referenced_evidence = (
            {
                evidence_id
                for schedule in facts.order_schedules
                for evidence_id in schedule.evidence_ids
            }
            | {note.evidence_id for note in facts.source_notes}
            | {
                evidence_id
                for observation in facts.observations
                for evidence_id in observation.evidence_ids
            }
            | {
                evidence_id
                for limitation in facts.limitations
                for evidence_id in limitation.evidence_ids
            }
        )
        if not referenced_evidence.issubset(evidence_ids):
            errors.append("Operations payload references unknown evidence.")
        observation_fact_ids = {
            fact_id for observation in facts.observations for fact_id in observation.fact_ids
        }
        if not observation_fact_ids.issubset(fact_ids):
            errors.append("Operations observation references an unknown fact ID.")
        if not errors:
            checks.append("OPERATIONS_FACTS_REFERENCES_VERIFIED")

    @staticmethod
    def _validate_operations_assessment(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        try:
            assessment = OperationsAssessment.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid OPERATIONS_ASSESSMENT schema: {exc}")
            return
        known = set(assessment.fact_ids)
        if len(known) != len(assessment.fact_ids):
            errors.append("OPERATIONS_ASSESSMENT contains duplicate fact IDs.")
        referenced_facts = {
            fact_id for observation in assessment.observations for fact_id in observation.fact_ids
        } | {fact_id for statement in assessment.summary for fact_id in statement.fact_ids}
        if not referenced_facts.issubset(known):
            errors.append("Operations assessment references an unknown fact ID.")
        referenced_evidence = {
            evidence_id
            for observation in assessment.observations
            for evidence_id in observation.evidence_ids
        } | {
            evidence_id
            for limitation in assessment.limitations
            for evidence_id in limitation.evidence_ids
        }
        if not referenced_evidence.issubset(evidence_ids):
            errors.append("Operations assessment references unknown evidence.")
        forbidden_keys = {
            "risk_level",
            "risk_score",
            "severity",
            "triggered_rule_ids",
            "approval_required",
            "approval_request",
            "banking_option",
            "decision_card",
            "penalty_amount",
            "capacity_score",
            "feasibility",
        }
        present_keys = EvidenceValidator._recursive_keys(draft.payload)
        forbidden_present = {
            key
            for key in present_keys
            if key in forbidden_keys
            or key.startswith(("risk_", "approval_", "banking_", "decision_"))
        }
        if forbidden_present:
            errors.append(
                "OPERATIONS_ASSESSMENT contains downstream fields: "
                + ", ".join(sorted(forbidden_present))
            )
        if not errors:
            checks.append("OPERATIONS_ASSESSMENT_BOUNDARY_VALID")

    @staticmethod
    def _recursive_keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value).union(
                *(EvidenceValidator._recursive_keys(item) for item in value.values())
            )
        if isinstance(value, (list, tuple)):
            return set().union(*(EvidenceValidator._recursive_keys(item) for item in value))
        return set()
