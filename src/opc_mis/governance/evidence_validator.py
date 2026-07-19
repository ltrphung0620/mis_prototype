"""Validate artifact schema and evidence lineage before persistence."""

import json
import re
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from math import isfinite

from opc_mis.domain.approvals import ApprovalCheckpointSet
from opc_mis.domain.artifacts import ArtifactDraft
from opc_mis.domain.banking_models import (
    BankingCatalogPolicy,
    BankingDiscoveryRequest,
    BankingDiscoveryResult,
    BankingInputSupplement,
    BankingOptionAdvice,
    BankingOptionMatrix,
    BankingOptionPrecheckReadiness,
    BankingPrecheckFieldResolution,
    BankingPrecheckReadiness,
)
from opc_mis.domain.banking_precheck_execution_models import (
    BankingCompanyProfileField,
    BankingPrecheckNormalizedResult,
    BankingPrecheckResultSet,
    BankingPrecheckSimulationPolicy,
    BankingPrecheckSimulationScenario,
    banking_precheck_idempotency_key,
    banking_precheck_request_hash,
    banking_precheck_response_hash,
)
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckFieldBindingReference,
    BankingPrecheckSubmissionCandidate,
    BankingPrecheckSubmissionProposal,
)
from opc_mis.domain.data_classification_models import ClassificationDecision
from opc_mis.domain.decision_models import AIDecisionAnalysis, DecisionCard
from opc_mis.domain.decision_post_banking_models import DecisionPostBankingReview
from opc_mis.domain.decision_post_precheck_models import (
    DecisionPostPrecheckReview,
    decision_post_precheck_evidence_id,
    decision_post_precheck_item_id,
    decision_post_precheck_review_id,
)
from opc_mis.domain.decision_route_models import DecisionRoutePlan
from opc_mis.domain.document_models import (
    DocumentChecklist,
    DocumentEvidenceSupplement,
    DocumentPackageDraft,
    DocumentPreparationRequest,
    DocumentReleasePackage,
    document_checklist_id,
    document_package_draft_id,
    document_preparation_request_id,
)
from opc_mis.domain.enums import (
    ArtifactType,
    BankingAdviceSource,
    BankingAdviceStatus,
    BankingCriterionCode,
    BankingCriterionStatus,
    BankingDataGapCode,
    BankingDiscoveryStatus,
    BankingPrecheckExecutionMode,
    BankingPrecheckFieldSource,
    BankingPrecheckFieldStatus,
    BankingPrecheckOutcome,
    BankingPrecheckReadinessStatus,
    BankingPrecheckResultAuthority,
    BankingPrecheckStatus,
    BankingPrecheckSupportedAmountStrategy,
    CurrencyCode,
    DecisionCapability,
    DecisionHandoffMode,
    DecisionPostBankingOutcome,
    DecisionRouteOutcome,
    FinalRiskControlCode,
    MajorExceptionStatus,
    MissingRequestStatus,
    MissingSeverity,
    ProtectedAction,
    ProviderEligibilityStatus,
    ProviderGuaranteeDecision,
    RequirementAmountSemantics,
    RiskLevel,
    RiskScope,
    RiskSeverity,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.final_risk_models import (
    FinalRiskAssessment,
    final_risk_assessment_id,
)
from opc_mis.domain.finance_models import FinanceAssessment, FinanceFacts
from opc_mis.domain.internal_decision_package_models import (
    InternalDecisionPackage,
    InternalDecisionPackageReadiness,
    internal_decision_governance_identity,
    internal_decision_package_id,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.masking_models import (
    MaskableScalar,
    MaskedPayload,
    MaskingAction,
    MaskingAlgorithmId,
    MaskingManifest,
    MaskingPolicyDocument,
    MaskingReasonCode,
    masking_policy_document_sha256,
)
from opc_mis.domain.operations_models import OperationsAssessment, OperationsFacts
from opc_mis.domain.planner_models import EvaluationCase
from opc_mis.domain.post_decision_models import (
    ExternalDocumentSubmissionProposal,
    PostDecisionUpdate,
    approval_business_identity,
)
from opc_mis.domain.risk_models import (
    InitialRiskAssessment,
    RiskPreScan,
    RiskRuleEvaluationSet,
)
from opc_mis.domain.serialization import json_safe
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.domain.validation_reports import ValidationReport
from opc_mis.ports.masking_service import MaskingService

_UNCONFIGURED_SCENARIO_ID = "SIMULATION-SCENARIO-NOT-CONFIGURED"
_UNCONFIGURED_REASON_CODES = ("SIMULATION_SCENARIO_NOT_CONFIGURED",)
_UNCONFIGURED_MESSAGE = (
    "Simulated precheck service is unavailable because no server scenario matches "
    "this API/provider; no provider decision was made."
)


class EvidenceValidator:
    """Minimal deterministic validator for Planner artifact drafts."""

    def __init__(
        self,
        *,
        banking_policy: BankingCatalogPolicy | None = None,
        banking_precheck_simulation_policy: (
            BankingPrecheckSimulationPolicy | None
        ) = None,
        masking_policy: MaskingPolicyDocument | None = None,
        masking_service: MaskingService | None = None,
    ) -> None:
        self._banking_policy = banking_policy
        self._banking_precheck_simulation_policy = (
            banking_precheck_simulation_policy
        )
        self._masking_policy = masking_policy
        self._masking_service = masking_service

    async def validate(self, draft: ArtifactDraft) -> ValidationReport:
        """Reject non-JSON payloads and broken derived-evidence references."""
        checks: list[str] = []
        blocking_errors: list[str] = []
        warnings: list[str] = []

        try:
            json_inputs = {
                "payload": draft.payload,
                "identity_inputs": draft.identity_inputs,
                "evidence_refs": tuple(
                    item.model_dump(mode="python") for item in draft.evidence_refs
                ),
            }
            non_finite_paths = self._non_finite_paths(json_inputs)
            if non_finite_paths:
                raise ValueError(
                    "non-finite numeric values at " + ", ".join(non_finite_paths)
                )
            json.dumps(
                json_safe(json_inputs),
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            checks.append("SCHEMA_JSON_SAFE")
        except (TypeError, ValueError) as exc:
            blocking_errors.append(
                f"Artifact payload or lineage is not strict JSON: {exc}"
            )

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

        if draft.artifact_type is ArtifactType.EVALUATION_CASE:
            self._validate_evaluation_case(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.FINANCE_FACTS:
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
        elif draft.artifact_type is ArtifactType.RISK_PRE_SCAN:
            self._validate_risk_pre_scan(draft, evidence_ids, checks, blocking_errors)
        elif draft.artifact_type is ArtifactType.APPROVAL_CHECKPOINTS:
            self._validate_approval_checkpoints(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.RISK_RULE_EVALUATION:
            self._validate_risk_rule_evaluations(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.INITIAL_RISK_ASSESSMENT:
            self._validate_initial_risk_assessment(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.DECISION_ROUTE_PLAN:
            self._validate_decision_route_plan(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.BANKING_DISCOVERY_REQUEST:
            self._validate_banking_discovery_request(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.BANKING_OPTION_MATRIX:
            self._validate_banking_option_matrix(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.BANKING_DISCOVERY_RESULT:
            self._validate_banking_discovery_result(draft, checks, blocking_errors)
        elif draft.artifact_type is ArtifactType.BANKING_OPTION_ADVICE:
            self._validate_banking_option_advice(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.BANKING_INPUT_SUPPLEMENT:
            self._validate_banking_input_supplement(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.BANKING_PRECHECK_READINESS:
            self._validate_banking_precheck_readiness(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.DECISION_POST_BANKING_REVIEW:
            self._validate_decision_post_banking_review(
                draft, evidence_ids, checks, blocking_errors
            )
        elif (
            draft.artifact_type
            is ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL
        ):
            self._validate_banking_precheck_submission_proposal(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.BANKING_PRECHECK_RESULT_SET:
            self._validate_banking_precheck_result_set(
                draft,
                evidence_ids,
                checks,
                blocking_errors,
                self._banking_precheck_simulation_policy,
            )
        elif draft.artifact_type is ArtifactType.DECISION_POST_PRECHECK_REVIEW:
            self._validate_decision_post_precheck_review(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.DOCUMENT_PREPARATION_REQUEST:
            self._validate_document_preparation_request(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.DOCUMENT_CHECKLIST:
            self._validate_document_checklist(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.DOCUMENT_PACKAGE_DRAFT:
            self._validate_document_package_draft(
                draft,
                evidence_ids,
                checks,
                blocking_errors,
                self._masking_policy,
                self._masking_service,
            )
        elif draft.artifact_type is ArtifactType.DOCUMENT_RELEASE_PACKAGE:
            self._validate_document_release_package(
                draft,
                evidence_ids,
                checks,
                blocking_errors,
                self._masking_policy,
                self._masking_service,
            )
        elif draft.artifact_type is ArtifactType.DOCUMENT_EVIDENCE_SUPPLEMENT:
            self._validate_document_evidence_supplement(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.INTERNAL_DECISION_PACKAGE:
            self._validate_internal_decision_package(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.FINAL_RISK_ASSESSMENT:
            self._validate_final_risk_assessment(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.AI_DECISION_ANALYSIS:
            self._validate_ai_decision_analysis(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.DECISION_CARD:
            self._validate_decision_card(
                draft, evidence_ids, checks, blocking_errors
            )
        elif draft.artifact_type is ArtifactType.POST_DECISION_UPDATE:
            self._validate_post_decision_update(
                draft, evidence_ids, checks, blocking_errors
            )
        elif (
            draft.artifact_type
            is ArtifactType.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL
        ):
            self._validate_external_document_submission_proposal(
                draft, evidence_ids, checks, blocking_errors
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
    def _validate_evaluation_case(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate Planner requirement identity and exact credit-amount lineage."""
        try:
            evaluation_case = EvaluationCase.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid EVALUATION_CASE schema: {exc}")
            return
        if evaluation_case.evaluation_case_id != draft.evaluation_case_id:
            errors.append("EVALUATION_CASE identity does not match its draft.")
        requirement_ids = tuple(
            requirement.requirement_id
            for requirement in evaluation_case.contract_requirements
        )
        if len(set(requirement_ids)) != len(requirement_ids):
            errors.append("EVALUATION_CASE contains duplicate contract requirement IDs.")
        related_credit_ids = set(evaluation_case.related_credit_case_ids)
        evidence_by_id = {item.evidence_id: item for item in draft.evidence_refs}
        for requirement in evaluation_case.contract_requirements:
            if not set(requirement.evidence_ids).issubset(evidence_ids):
                errors.append(
                    f"Contract requirement {requirement.requirement_id} references "
                    "unknown evidence."
                )
                continue
            for record_id, field in zip(
                requirement.source_record_ids,
                requirement.source_fields,
                strict=True,
            ):
                source_matches = tuple(
                    evidence_by_id[evidence_id]
                    for evidence_id in requirement.evidence_ids
                    if evidence_id in evidence_by_id
                    and evidence_by_id[evidence_id].source_type
                    is SourceType.TEAM_PACK
                    and evidence_by_id[evidence_id].record_id == record_id
                    and evidence_by_id[evidence_id].field == field
                )
                if len(source_matches) != 1:
                    errors.append(
                        f"Contract requirement {requirement.requirement_id} lacks "
                        f"one exact source for {record_id}.{field}."
                    )
            if requirement.credit_case_id is None:
                continue
            if requirement.credit_case_id not in related_credit_ids:
                errors.append(
                    f"Contract requirement {requirement.requirement_id} references an "
                    "unselected credit profile."
                )
                continue
            relationship_matches = tuple(
                evidence_by_id[evidence_id]
                for evidence_id in requirement.evidence_ids
                if evidence_id in evidence_by_id
                and evidence_by_id[evidence_id].source_type is SourceType.DERIVED
                and evidence_by_id[evidence_id].sheet
                == SheetRegistry.CREDIT_PROFILES.sheet_name
                and evidence_by_id[evidence_id].record_id
                == requirement.credit_case_id
                and evidence_by_id[evidence_id].field
                == "contract_requirement_relationship"
                and evidence_by_id[evidence_id].display_value
                == {
                    "contract_id": evaluation_case.contract_id,
                    "credit_case_id": requirement.credit_case_id,
                }
            )
            if len(relationship_matches) != 1:
                errors.append(
                    f"Contract requirement {requirement.requirement_id} lacks one exact "
                    "contract-to-credit relationship evidence item."
                )
            else:
                relationship_sources = set(
                    relationship_matches[0].source_evidence_ids
                )
                contract_sources = {
                    evidence_id
                    for evidence_id in requirement.evidence_ids
                    if evidence_id in evidence_by_id
                    and evidence_by_id[evidence_id].source_type
                    is SourceType.TEAM_PACK
                    and evidence_by_id[evidence_id].sheet
                    == SheetRegistry.CONTRACTS.sheet_name
                    and evidence_by_id[evidence_id].record_id
                    == evaluation_case.contract_id
                    and evidence_by_id[evidence_id].field == "contract_id"
                }
                collateral_sources = {
                    evidence_id
                    for evidence_id in requirement.evidence_ids
                    if evidence_id in evidence_by_id
                    and evidence_by_id[evidence_id].source_type
                    is SourceType.TEAM_PACK
                    and evidence_by_id[evidence_id].sheet
                    == SheetRegistry.CREDIT_PROFILES.sheet_name
                    and evidence_by_id[evidence_id].record_id
                    == requirement.credit_case_id
                    and evidence_by_id[evidence_id].field == "collateral_or_basis"
                }
                if (
                    len(contract_sources) != 1
                    or len(collateral_sources) != 1
                    or relationship_sources
                    != contract_sources | collateral_sources
                ):
                    errors.append(
                        f"Contract requirement {requirement.requirement_id} relationship "
                        "does not derive exactly from contract_id and collateral_or_basis."
                    )
            if requirement.requested_amount is None:
                continue
            if requirement.requested_amount_currency is not CurrencyCode.VND:
                errors.append(
                    f"Contract requirement {requirement.requirement_id} amount is not VND."
                )
            if (
                requirement.amount_semantics
                is not RequirementAmountSemantics.CREDIT_PROFILE_REQUESTED_AMOUNT
            ):
                errors.append(
                    f"Contract requirement {requirement.requirement_id} changes the "
                    "credit-profile requested-amount semantics."
                )
            amount_matches = tuple(
                evidence_by_id[evidence_id]
                for evidence_id in requirement.evidence_ids
                if evidence_id in evidence_by_id
                and evidence_by_id[evidence_id].source_type is SourceType.TEAM_PACK
                and evidence_by_id[evidence_id].sheet
                == SheetRegistry.CREDIT_PROFILES.sheet_name
                and evidence_by_id[evidence_id].record_id
                == requirement.credit_case_id
                and evidence_by_id[evidence_id].field == "requested_amount"
                and EvidenceValidator._same_json_scalar(
                    evidence_by_id[evidence_id].display_value,
                    requirement.requested_amount,
                )
            )
            if len(amount_matches) != 1:
                errors.append(
                    f"Contract requirement {requirement.requirement_id} lacks one exact "
                    "10_CREDIT_PROFILE.requested_amount evidence item."
                )
        if not errors:
            checks.append("EVALUATION_CASE_REQUIREMENT_LINEAGE_VALID")

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
            any(term in text.casefold() for term in forbidden_terms) for text in narrative_texts
        ):
            errors.append("Finance narrative contains downstream text.")
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

    @staticmethod
    def _non_finite_paths(value: object, path: str = "artifact") -> tuple[str, ...]:
        """Return exact paths whose numeric values cannot be represented in JSON."""
        if isinstance(value, float):
            return () if isfinite(value) else (path,)
        if isinstance(value, Decimal):
            return () if value.is_finite() else (path,)
        if isinstance(value, dict):
            return tuple(
                child
                for key, item in value.items()
                for child in EvidenceValidator._non_finite_paths(
                    item, f"{path}.{key}"
                )
            )
        if isinstance(value, (list, tuple, set, frozenset)):
            return tuple(
                child
                for index, item in enumerate(value)
                for child in EvidenceValidator._non_finite_paths(
                    item, f"{path}[{index}]"
                )
            )
        return ()

    @staticmethod
    def _same_json_scalar(actual: object, expected: object) -> bool:
        """Compare evidence scalars without accepting bool as an integer alias."""
        if isinstance(expected, int) and not isinstance(expected, bool):
            return (
                isinstance(actual, int)
                and not isinstance(actual, bool)
                and actual == expected
            )
        return type(actual) is type(expected) and actual == expected

    @staticmethod
    def _validate_risk_pre_scan(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        try:
            pre_scan = RiskPreScan.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid RISK_PRE_SCAN schema: {exc}")
            return
        if len(set(pre_scan.source_rule_ids)) != len(pre_scan.source_rule_ids):
            errors.append("RISK_PRE_SCAN contains duplicate rule IDs.")
        if set(pre_scan.source_rule_ids) != {item.rule_id for item in pre_scan.source_rules}:
            errors.append("RISK_PRE_SCAN source rule index does not match its rule records.")
        referenced = {
            evidence_id
            for rule in pre_scan.source_rules
            for evidence_id in rule.evidence_ids
        } | {
            evidence_id
            for alert in (*pre_scan.case_alerts, *pre_scan.global_alerts)
            for evidence_id in alert.evidence_ids
        } | {
            evidence_id
            for signal in pre_scan.global_signals
            for evidence_id in signal.evidence_ids
        }
        if not referenced.issubset(evidence_ids):
            errors.append("RISK_PRE_SCAN references unknown evidence.")
        if any(
            alert.relation_scope is not RiskScope.CASE_SPECIFIC
            for alert in pre_scan.case_alerts
        ):
            errors.append("RISK_PRE_SCAN case alert has a non-case scope.")
        if any(
            alert.relation_scope is not RiskScope.OPC_GLOBAL
            for alert in pre_scan.global_alerts
        ):
            errors.append("RISK_PRE_SCAN global alert has a non-global scope.")
        if not errors:
            checks.append("RISK_PRE_SCAN_REFERENCES_VERIFIED")

    @staticmethod
    def _validate_approval_checkpoints(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        try:
            checkpoint_set = ApprovalCheckpointSet.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid APPROVAL_CHECKPOINTS schema: {exc}")
            return
        checkpoint_ids = {item.checkpoint_id for item in checkpoint_set.checkpoints}
        if len(checkpoint_ids) != len(checkpoint_set.checkpoints):
            errors.append("APPROVAL_CHECKPOINTS contains duplicate checkpoint IDs.")
        rule_scopes = {
            (item.source_rule_id, item.protected_action)
            for item in checkpoint_set.checkpoints
        }
        if len(rule_scopes) != len(checkpoint_set.checkpoints):
            errors.append(
                "APPROVAL_CHECKPOINTS registers one source rule/action more than once."
            )
        referenced = {
            evidence_id
            for checkpoint in checkpoint_set.checkpoints
            for evidence_id in checkpoint.evidence_ids
        } | {
            evidence_id
            for coverage in checkpoint_set.policy_coverages
            for evidence_id in coverage.evidence_ids
        }
        if not referenced.issubset(evidence_ids):
            errors.append("APPROVAL_CHECKPOINTS references unknown evidence.")
        if any(
            checkpoint.evaluation_case_id != checkpoint_set.evaluation_case_id
            for checkpoint in checkpoint_set.checkpoints
        ):
            errors.append("APPROVAL_CHECKPOINTS contains a checkpoint for another case.")
        if any(
            coverage.evaluation_case_id != checkpoint_set.evaluation_case_id
            for coverage in checkpoint_set.policy_coverages
        ):
            errors.append("APPROVAL_CHECKPOINTS contains policy coverage for another case.")
        if not errors:
            checks.append("APPROVAL_CHECKPOINTS_REFERENCES_VERIFIED")

    @staticmethod
    def _validate_risk_rule_evaluations(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        try:
            rule_set = RiskRuleEvaluationSet.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid RISK_RULE_EVALUATION schema: {exc}")
            return
        ids = {item.evaluation_id for item in rule_set.evaluations}
        if len(ids) != len(rule_set.evaluations):
            errors.append("RISK_RULE_EVALUATION contains duplicate evaluation IDs.")
        rule_ids = {item.rule_id for item in rule_set.evaluations}
        if len(rule_ids) != len(rule_set.evaluations):
            errors.append("RISK_RULE_EVALUATION evaluates a source rule more than once.")
        referenced = {
            evidence_id
            for evaluation in rule_set.evaluations
            for evidence_id in evaluation.evidence_ids
        }
        if not referenced.issubset(evidence_ids):
            errors.append("RISK_RULE_EVALUATION references unknown evidence.")
        if not errors:
            checks.append("RISK_RULE_EVALUATION_REFERENCES_VERIFIED")

    @staticmethod
    def _validate_initial_risk_assessment(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        try:
            assessment = InitialRiskAssessment.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid INITIAL_RISK_ASSESSMENT schema: {exc}")
            return
        referenced = (
            {
                evidence_id
                for finding in assessment.findings
                for evidence_id in finding.evidence_ids
            }
            | {
                evidence_id
                for alert in assessment.source_alerts
                for evidence_id in alert.evidence_ids
            }
            | {
                evidence_id
                for signal in assessment.global_context_signals
                for evidence_id in signal.evidence_ids
            }
            | {
                evidence_id
                for point in assessment.human_confirmation_points
                for evidence_id in point.evidence_ids
            }
            | {
                evidence_id
                for limitation in assessment.limitations
                for evidence_id in limitation.evidence_ids
            }
        )
        if not referenced.issubset(evidence_ids):
            errors.append("INITIAL_RISK_ASSESSMENT references unknown evidence.")
        expected = RiskLevel.NO_CASE_SIGNAL
        if assessment.findings:
            order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
            highest = max(assessment.findings, key=lambda item: order[item.severity])
            expected = RiskLevel(highest.severity)
        if assessment.overall_risk_level is not expected:
            errors.append("INITIAL_RISK_ASSESSMENT overall level violates max-severity policy.")
        finding_rule_ids = {
            item.source_rule_id
            for item in assessment.findings
            if item.source_rule_id is not None
        }
        if set(assessment.triggered_rule_ids) != finding_rule_ids:
            errors.append("INITIAL_RISK_ASSESSMENT triggered rules do not match findings.")
        if any(
            alert.relation_scope is not RiskScope.CASE_SPECIFIC
            for alert in assessment.source_alerts
        ):
            errors.append("INITIAL_RISK_ASSESSMENT contains a non-case source alert.")
        forbidden = {
            "approval_request",
            "approval_decision",
            "banking_option",
            "document_package",
            "decision_card",
        }
        present = EvidenceValidator._recursive_keys(draft.payload)
        if forbidden & present:
            errors.append(
                "INITIAL_RISK_ASSESSMENT contains downstream fields: "
                + ", ".join(sorted(forbidden & present))
            )
        if not errors:
            checks.append("INITIAL_RISK_ASSESSMENT_BOUNDARY_VALID")

    @staticmethod
    def _validate_decision_route_plan(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        try:
            plan = DecisionRoutePlan.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid DECISION_ROUTE_PLAN schema: {exc}")
            return
        reason_ids = {item.reason_id for item in plan.routing_reasons}
        if len(reason_ids) != len(plan.routing_reasons):
            errors.append("DECISION_ROUTE_PLAN contains duplicate reason IDs.")
        reason_evidence = {
            evidence_id
            for reason in plan.routing_reasons
            for evidence_id in reason.evidence_ids
        }
        if not reason_evidence.issubset(evidence_ids):
            errors.append("DECISION_ROUTE_PLAN references unknown evidence.")
        if len(set(plan.source_artifact_ids)) != len(plan.source_artifact_ids):
            errors.append("DECISION_ROUTE_PLAN contains duplicate source artifact IDs.")
        if len(set(plan.banking_need_types)) != len(plan.banking_need_types):
            errors.append("DECISION_ROUTE_PLAN contains duplicate banking need types.")
        if any(
            reason.source_artifact_id not in plan.source_artifact_ids
            for reason in plan.routing_reasons
        ):
            errors.append("DECISION_ROUTE_PLAN reason has an unknown source artifact.")
        evidence_by_id = {item.evidence_id: item for item in draft.evidence_refs}
        for reason in plan.routing_reasons:
            if not set(reason.amount_evidence_ids).issubset(reason.evidence_ids):
                errors.append(
                    f"Decision route reason {reason.reason_id} has undeclared amount evidence."
                )
                continue
            amount_matches = tuple(
                evidence_by_id[evidence_id]
                for evidence_id in reason.amount_evidence_ids
                if evidence_id in evidence_by_id
                and evidence_by_id[evidence_id].source_type is SourceType.TEAM_PACK
                and evidence_by_id[evidence_id].sheet
                == SheetRegistry.CREDIT_PROFILES.sheet_name
                and evidence_by_id[evidence_id].record_id == reason.credit_case_id
                and evidence_by_id[evidence_id].field == "requested_amount"
                and EvidenceValidator._same_json_scalar(
                    evidence_by_id[evidence_id].display_value,
                    reason.requested_amount,
                )
            )
            if len(amount_matches) != 1:
                errors.append(
                    f"Decision route reason {reason.reason_id} lacks one exact "
                    "credit-profile requested amount."
                )
        if len(set(plan.conditional_approval_checkpoint_ids)) != len(
            plan.conditional_approval_checkpoint_ids
        ):
            errors.append("DECISION_ROUTE_PLAN contains duplicate checkpoint IDs.")
        if plan.route_outcome is DecisionRouteOutcome.BANKING_DISCOVERY_REQUIRED:
            if plan.required_capabilities != (
                DecisionCapability.BANKING_INTERNAL_DISCOVERY,
            ):
                errors.append(
                    "Banking route must request BANKING_INTERNAL_DISCOVERY only."
                )
            if not plan.banking_need_types or not plan.routing_reasons:
                errors.append("Banking route requires an evidence-backed banking need.")
            if {item.banking_need_type for item in plan.routing_reasons} != set(
                plan.banking_need_types
            ):
                errors.append(
                    "Banking route need types do not match its typed reasons."
                )
        elif plan.route_outcome is DecisionRouteOutcome.DIRECT_INTERNAL_DECISION:
            if plan.required_capabilities != (
                DecisionCapability.INTERNAL_DECISION_PACKAGE,
            ):
                errors.append(
                    "Direct route must request INTERNAL_DECISION_PACKAGE only."
                )
            if plan.banking_need_types or plan.routing_reasons:
                errors.append("Direct route cannot contain a banking need or reason.")
        forbidden = {
            "next_node",
            "approval_request",
            "approval_required",
            "banking_option",
            "selected_bank",
            "document_package",
            "decision_card",
            "final_recommendation",
        }
        present = EvidenceValidator._recursive_keys(draft.payload)
        if forbidden & present:
            errors.append(
                "DECISION_ROUTE_PLAN contains out-of-bound fields: "
                + ", ".join(sorted(forbidden & present))
            )
        if not errors:
            checks.append("DECISION_ROUTE_PLAN_BOUNDARY_VALID")

    @staticmethod
    def _validate_banking_discovery_request(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        try:
            request = BankingDiscoveryRequest.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid BANKING_DISCOVERY_REQUEST schema: {exc}")
            return
        if request.execution_mode is not DecisionHandoffMode.BANKING_DISCOVERY:
            errors.append("Banking discovery request has an unsupported execution mode.")
        if (
            request.requested_capability
            is not DecisionCapability.BANKING_INTERNAL_DISCOVERY
        ):
            errors.append(
                "Banking discovery request must request BANKING_INTERNAL_DISCOVERY."
            )
        if len(set(request.need_types)) != len(request.need_types):
            errors.append("BANKING_DISCOVERY_REQUEST contains duplicate need types.")
        if len(set(request.evidence_ids)) != len(request.evidence_ids):
            errors.append("BANKING_DISCOVERY_REQUEST contains duplicate evidence IDs.")
        if not set(request.evidence_ids).issubset(evidence_ids):
            errors.append("BANKING_DISCOVERY_REQUEST references unknown evidence.")
        if len(set(request.source_artifact_ids)) != len(request.source_artifact_ids):
            errors.append("BANKING_DISCOVERY_REQUEST contains duplicate source artifacts.")
        if request.source_route_artifact_id not in request.source_artifact_ids:
            errors.append(
                "BANKING_DISCOVERY_REQUEST does not include its route artifact in lineage."
            )
        if request.requested_amount is not None:
            amount_matches = tuple(
                item
                for item in draft.evidence_refs
                if item.evidence_id in request.amount_evidence_ids
                and item.source_type is SourceType.TEAM_PACK
                and item.sheet == SheetRegistry.CREDIT_PROFILES.sheet_name
                and item.record_id == request.credit_case_id
                and item.field == "requested_amount"
                and EvidenceValidator._same_json_scalar(
                    item.display_value, request.requested_amount
                )
            )
            if len(amount_matches) != 1:
                errors.append(
                    "BANKING_DISCOVERY_REQUEST amount lacks one exact Planner-selected "
                    "credit-profile requested_amount evidence item."
                )
        if request.requested_amount_currency is not CurrencyCode.VND:
            errors.append("Banking request monetary values must use VND.")
        if request.constraints:
            errors.append("Decision handoff cannot invent Banking constraints.")
        forbidden = {
            "action_command",
            "approval_request",
            "approval_required",
            "banking_option",
            "selected_bank",
            "external_partner",
            "external_request",
            "document_package",
            "decision_card",
            "next_node",
            "recommendation",
        }
        present = EvidenceValidator._recursive_keys(draft.payload)
        if forbidden & present:
            errors.append(
                "BANKING_DISCOVERY_REQUEST contains out-of-bound fields: "
                + ", ".join(sorted(forbidden & present))
            )
        if not errors:
            checks.append("BANKING_DISCOVERY_REQUEST_BOUNDARY_VALID")

    def _validate_banking_option_matrix(
        self,
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        try:
            matrix = BankingOptionMatrix.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid BANKING_OPTION_MATRIX schema: {exc}")
            return
        if matrix.evaluation_case_id != draft.evaluation_case_id:
            errors.append("BANKING_OPTION_MATRIX case identity does not match its draft.")
        option_ids = tuple(item.option_id for item in matrix.candidates)
        if len(set(option_ids)) != len(option_ids):
            errors.append("BANKING_OPTION_MATRIX contains duplicate option IDs.")
        if len(set(matrix.source_artifact_ids)) != len(matrix.source_artifact_ids):
            errors.append("BANKING_OPTION_MATRIX contains duplicate source artifacts.")
        if len(set(matrix.explicit_credit_case_ids)) != len(
            matrix.explicit_credit_case_ids
        ):
            errors.append("BANKING_OPTION_MATRIX contains duplicate credit case IDs.")
        if len(set(matrix.evidence_ids)) != len(matrix.evidence_ids):
            errors.append("BANKING_OPTION_MATRIX contains duplicate evidence IDs.")
        amount_evidence_ids: set[str] = set()
        if matrix.requested_amount is not None:
            if matrix.requested_amount <= 0:
                errors.append(
                    "BANKING_OPTION_MATRIX requested amount must be a positive integer."
                )
            team_pack_amount_evidence_ids = {
                item.evidence_id
                for item in draft.evidence_refs
                if item.source_type is SourceType.TEAM_PACK
                and item.sheet == SheetRegistry.CREDIT_PROFILES.sheet_name
                and item.record_id in matrix.explicit_credit_case_ids
                and item.field == "requested_amount"
                and isinstance(item.display_value, int)
                and not isinstance(item.display_value, bool)
                and item.display_value == matrix.requested_amount
            }
            legacy_amount_evidence_ids = {
                item.evidence_id
                for item in draft.evidence_refs
                if item.source_type is SourceType.USER_INPUT
                and item.sheet == "BANKING_INPUT_SUPPLEMENT"
                and item.field == "requested_amount"
                and isinstance(item.display_value, int)
                and not isinstance(item.display_value, bool)
                and item.display_value == matrix.requested_amount
            }
            amount_evidence_ids = (
                team_pack_amount_evidence_ids | legacy_amount_evidence_ids
            )
            if not amount_evidence_ids:
                errors.append(
                    "BANKING_OPTION_MATRIX requested amount lacks exact credit-profile "
                    "or legacy supplement evidence."
                )
        referenced = set(matrix.evidence_ids)
        for candidate in matrix.candidates:
            referenced.update(candidate.evidence_ids)
            for criterion in candidate.criteria:
                referenced.update(criterion.evidence_ids)
            if candidate.precheck is not None:
                referenced.update(candidate.precheck.evidence_ids)
                if (
                    candidate.precheck.status
                    is not BankingPrecheckStatus.MOCK_AVAILABLE_NOT_EXECUTED
                    or candidate.precheck.precheck_executed
                ):
                    errors.append(
                        f"Banking option {candidate.option_id} claims a precheck execution."
                    )
            for guidance in candidate.handling_guidance:
                referenced.update(guidance.evidence_ids)
            minimum_checks = tuple(
                item
                for item in candidate.criteria
                if item.code is BankingCriterionCode.MINIMUM_AMOUNT
            )
            if len(minimum_checks) != 1:
                errors.append(
                    f"Banking option {candidate.option_id} requires one minimum-amount check."
                )
            else:
                minimum_check = minimum_checks[0]
                expected_minimum_status = BankingCriterionStatus.NOT_EVALUABLE
                if matrix.requested_amount is not None:
                    expected_minimum_status = (
                        BankingCriterionStatus.NOT_APPLICABLE
                        if candidate.minimum_amount is None
                        else BankingCriterionStatus.PASS
                        if matrix.requested_amount >= candidate.minimum_amount
                        else BankingCriterionStatus.FAIL
                    )
                if minimum_check.status is not expected_minimum_status:
                    errors.append(
                        f"Banking option {candidate.option_id} has a minimum-amount "
                        "status inconsistent with its numeric inputs."
                    )
                if (
                    matrix.requested_amount is not None
                    and not amount_evidence_ids.intersection(
                        minimum_check.evidence_ids
                    )
                ):
                    errors.append(
                        f"Banking option {candidate.option_id} minimum-amount check "
                        "does not cite exact requested-amount evidence."
                    )
            if candidate.minimum_amount_currency is not CurrencyCode.VND:
                errors.append(
                    f"Banking option {candidate.option_id} minimum amount is not VND."
                )
        for gap in matrix.data_gaps:
            referenced.update(gap.evidence_ids)
            if (
                gap.code is BankingDataGapCode.REQUESTED_AMOUNT_UNAVAILABLE
                and not gap.blocking_for_precheck
            ):
                errors.append(
                    f"Banking amount gap {gap.gap_id} must block later precheck readiness."
                )
            if (
                gap.code
                is BankingDataGapCode.CREDIT_PROFILE_RELATIONSHIP_UNCONFIRMED
                and gap.blocking_for_precheck
            ):
                errors.append(
                    f"Banking credit-profile gap {gap.gap_id} cannot block precheck "
                    "readiness."
                )
        amount_gap_count = sum(
            gap.code is BankingDataGapCode.REQUESTED_AMOUNT_UNAVAILABLE
            for gap in matrix.data_gaps
        )
        if matrix.requested_amount is None and amount_gap_count != 1:
            errors.append(
                "BANKING_OPTION_MATRIX without an amount requires exactly one amount gap."
            )
        if matrix.requested_amount is not None and amount_gap_count:
            errors.append(
                "BANKING_OPTION_MATRIX with an amount cannot retain an amount gap."
            )
        if not referenced.issubset(evidence_ids):
            errors.append("BANKING_OPTION_MATRIX references unknown evidence.")
        known_options = set(option_ids)
        canonical_combinations: set[tuple[str, ...]] = set()
        for combination in matrix.allowed_option_combinations:
            if len(combination) < 2 or len(set(combination)) != len(combination):
                errors.append("Banking allowed option combinations must be unique sets.")
            if not set(combination).issubset(known_options):
                errors.append("Banking option combination references an unknown option.")
            canonical = tuple(sorted(combination))
            if canonical in canonical_combinations:
                errors.append("BANKING_OPTION_MATRIX contains duplicate combinations.")
            canonical_combinations.add(canonical)
        expected_status = (
            BankingDiscoveryStatus.NO_CONFIGURED_OPTIONS
            if not matrix.candidates
            else BankingDiscoveryStatus.OPTIONS_READY_WITH_GAPS
            if matrix.data_gaps
            else BankingDiscoveryStatus.OPTIONS_READY
        )
        if matrix.discovery_status is not expected_status:
            errors.append("BANKING_OPTION_MATRIX discovery status is inconsistent.")
        if matrix.precheck_executed:
            errors.append("BANKING_OPTION_MATRIX cannot execute a precheck in Phase A.")
        if matrix.requested_amount_currency is not CurrencyCode.VND:
            errors.append("BANKING_OPTION_MATRIX monetary values must use VND.")
        self._validate_matrix_policy_alignment(matrix, errors)
        forbidden = {
            "action_command",
            "approval_request",
            "approval_decision",
            "selected_bank",
            "external_request",
            "external_response",
            "document_package",
            "decision_card",
            "final_decision",
            "protected_action",
        }
        present = self._recursive_keys(draft.payload)
        if forbidden & present:
            errors.append(
                "BANKING_OPTION_MATRIX contains out-of-bound fields: "
                + ", ".join(sorted(forbidden & present))
            )
        if not errors:
            checks.append("BANKING_OPTION_MATRIX_BOUNDARY_VALID")

    def _validate_matrix_policy_alignment(
        self, matrix: BankingOptionMatrix, errors: list[str]
    ) -> None:
        policy = self._banking_policy
        if policy is None:
            return
        if (
            matrix.mapping_policy_id,
            matrix.mapping_version,
            matrix.mapping_hash,
        ) != (policy.policy_id, policy.mapping_version, policy.policy_hash):
            errors.append("BANKING_OPTION_MATRIX mapping identity does not match policy.")
            return
        bindings = {item.need_type: item for item in policy.bindings}
        for candidate in matrix.candidates:
            binding = bindings.get(candidate.need_type)
            if binding is None or candidate.bank_product_id not in binding.bank_product_ids:
                errors.append(
                    f"Banking option {candidate.option_id} is not explicitly configured."
                )
                continue
            expected_api_id = binding.precheck_api_by_product.get(
                candidate.bank_product_id
            )
            actual_api_id = (
                candidate.precheck.api_id if candidate.precheck is not None else None
            )
            if actual_api_id != expected_api_id:
                errors.append(
                    f"Banking option {candidate.option_id} has an unconfigured API mapping."
                )
            actual_rule_ids = {item.rule_id for item in candidate.handling_guidance}
            if actual_rule_ids != set(binding.handling_rule_ids):
                errors.append(
                    f"Banking option {candidate.option_id} handling rules do not match policy."
                )

    @staticmethod
    def _validate_banking_discovery_result(
        draft: ArtifactDraft,
        checks: list[str],
        errors: list[str],
    ) -> None:
        try:
            result = BankingDiscoveryResult.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid BANKING_DISCOVERY_RESULT schema: {exc}")
            return
        if result.evaluation_case_id != draft.evaluation_case_id:
            errors.append("BANKING_DISCOVERY_RESULT case identity does not match its draft.")
        if len(set(result.candidate_option_ids)) != len(result.candidate_option_ids):
            errors.append("BANKING_DISCOVERY_RESULT contains duplicate option IDs.")
        if len(set(result.data_gap_ids)) != len(result.data_gap_ids):
            errors.append("BANKING_DISCOVERY_RESULT contains duplicate data-gap IDs.")
        forbidden = {
            "action_command",
            "approval_request",
            "selected_bank",
            "external_request",
            "external_response",
            "document_package",
            "decision_card",
            "final_decision",
        }
        present = EvidenceValidator._recursive_keys(draft.payload)
        if forbidden & present:
            errors.append(
                "BANKING_DISCOVERY_RESULT contains out-of-bound fields: "
                + ", ".join(sorted(forbidden & present))
            )
        if not errors:
            checks.append("BANKING_DISCOVERY_RESULT_BOUNDARY_VALID")

    @staticmethod
    def _validate_banking_option_advice(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        try:
            advice = BankingOptionAdvice.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid BANKING_OPTION_ADVICE schema: {exc}")
            return
        if advice.evaluation_case_id != draft.evaluation_case_id:
            errors.append("BANKING_OPTION_ADVICE case identity does not match its draft.")
        if advice.source is BankingAdviceSource.NOT_INVOKED:
            if advice.status is not BankingAdviceStatus.NOT_INVOKED:
                errors.append("Non-invoked Banking advice has an invalid status.")
            if advice.suggestions:
                errors.append("Non-invoked Banking advice cannot contain suggestions.")
        elif advice.status is not BankingAdviceStatus.ADVISORY_ONLY:
            errors.append("Banking advisor output must remain ADVISORY_ONLY.")
        suggestion_ids = tuple(item.suggestion_id for item in advice.suggestions)
        if len(set(suggestion_ids)) != len(suggestion_ids):
            errors.append("BANKING_OPTION_ADVICE contains duplicate suggestion IDs.")
        if any(len(set(item.option_ids)) != len(item.option_ids) for item in advice.suggestions):
            errors.append("BANKING_OPTION_ADVICE suggestion contains duplicate options.")
        if advice.suggestions and not evidence_ids:
            errors.append("BANKING_OPTION_ADVICE suggestions require evidence lineage.")
        prose = (advice.overview, *(item.rationale for item in advice.suggestions))
        forbidden_terms = (
            "approval",
            "approved",
            "phê duyệt",
            "selected",
            "has been selected",
            "đã chọn",
            "được chọn",
            "final decision",
            "quyết định cuối cùng",
            "submitted",
            "đã gửi",
            "precheck passed",
            "precheck succeeded",
            "precheck successful",
            "đủ điều kiện ngân hàng",
        )
        if any(
            term in text.casefold()
            for text in prose
            for term in forbidden_terms
        ):
            errors.append(
                "BANKING_OPTION_ADVICE contains a decision, approval, submission, "
                "or precheck-success claim."
            )
        if any(
            re.search(r"\d", re.sub(r"BOPT-[A-F0-9]{24}", "", text))
            for text in prose
        ):
            errors.append(
                "BANKING_OPTION_ADVICE contains numeric prose outside an option ID."
            )
        forbidden = {
            "action_command",
            "approval_request",
            "approval_required",
            "selected_bank",
            "external_request",
            "external_response",
            "precheck_success",
            "document_package",
            "decision_card",
            "final_decision",
        }
        present = EvidenceValidator._recursive_keys(draft.payload)
        if forbidden & present:
            errors.append(
                "BANKING_OPTION_ADVICE contains out-of-bound fields: "
                + ", ".join(sorted(forbidden & present))
            )
        if not errors:
            checks.append("BANKING_OPTION_ADVICE_BOUNDARY_VALID")

    @staticmethod
    def _validate_banking_input_supplement(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate immutable typed input without treating it as a dataset patch."""
        try:
            supplement = BankingInputSupplement.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid BANKING_INPUT_SUPPLEMENT schema: {exc}")
            return
        if supplement.evaluation_case_id != draft.evaluation_case_id:
            errors.append(
                "BANKING_INPUT_SUPPLEMENT case identity does not match its draft."
            )
        if supplement.requested_amount_currency is not CurrencyCode.VND:
            errors.append("BANKING_INPUT_SUPPLEMENT monetary values must use VND.")
        if not set(supplement.evidence_ids).issubset(evidence_ids):
            errors.append("BANKING_INPUT_SUPPLEMENT references unknown evidence.")
        evidence_by_id = {
            item.evidence_id: item for item in draft.evidence_refs
        }
        if any(
            evidence_by_id[evidence_id].source_type is not SourceType.USER_INPUT
            for evidence_id in supplement.evidence_ids
            if evidence_id in evidence_by_id
        ):
            errors.append(
                "BANKING_INPUT_SUPPLEMENT values must have USER_INPUT evidence."
            )
        expected_user_values = (
            ("requested_amount", supplement.requested_amount),
            (
                "requested_amount_currency",
                supplement.requested_amount_currency.value,
            ),
            ("provider", supplement.provider),
            ("note", supplement.note),
            *(
                ("resolved_request_id", request_id)
                for request_id in supplement.resolved_request_ids
            ),
        )
        exact_evidence_ids: set[str] = set()
        for field, expected_value in expected_user_values:
            matches = tuple(
                item
                for item in draft.evidence_refs
                if item.evidence_id in supplement.evidence_ids
                and item.source_type is SourceType.USER_INPUT
                and item.sheet == "BANKING_INPUT_SUPPLEMENT"
                and item.record_id == supplement.supplement_id
                and item.field == field
                and EvidenceValidator._same_json_scalar(
                    item.display_value, expected_value
                )
            )
            if len(matches) != 1:
                errors.append(
                    "BANKING_INPUT_SUPPLEMENT requires one exact USER_INPUT "
                    f"evidence item for {field}."
                )
            exact_evidence_ids.update(item.evidence_id for item in matches)
        if exact_evidence_ids != set(supplement.evidence_ids):
            errors.append(
                "BANKING_INPUT_SUPPLEMENT evidence IDs do not exactly match its values."
            )
        source_artifact_ids = supplement.source_artifact_ids
        if len(set(source_artifact_ids)) != len(source_artifact_ids):
            errors.append(
                "BANKING_INPUT_SUPPLEMENT contains duplicate source artifacts."
            )
        forbidden = {
            "data_patch",
            "approval_request",
            "approval_required",
            "selected_bank",
            "selected_option",
            "external_request",
            "external_response",
            "document_package",
            "decision_card",
            "precheck_result",
        }
        present = EvidenceValidator._recursive_keys(draft.payload)
        if forbidden & present:
            errors.append(
                "BANKING_INPUT_SUPPLEMENT contains out-of-bound fields: "
                + ", ".join(sorted(forbidden & present))
            )
        if not errors:
            checks.append("BANKING_INPUT_SUPPLEMENT_BOUNDARY_VALID")

    def _validate_banking_precheck_readiness(
        self,
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate readiness as field availability, never as an API response."""
        try:
            readiness = BankingPrecheckReadiness.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid BANKING_PRECHECK_READINESS schema: {exc}")
            return
        if readiness.evaluation_case_id != draft.evaluation_case_id:
            errors.append(
                "BANKING_PRECHECK_READINESS case identity does not match its draft."
            )
        if readiness.precheck_executed:
            errors.append("BANKING_PRECHECK_READINESS cannot execute a precheck.")
        if readiness.requested_amount_currency is not CurrencyCode.VND:
            errors.append("BANKING_PRECHECK_READINESS monetary values must use VND.")
        if len(set(readiness.source_artifact_ids)) != len(
            readiness.source_artifact_ids
        ):
            errors.append(
                "BANKING_PRECHECK_READINESS contains duplicate source artifacts."
            )
        if len(set(readiness.evidence_ids)) != len(readiness.evidence_ids):
            errors.append("BANKING_PRECHECK_READINESS contains duplicate evidence IDs.")
        evidence_by_id = {
            item.evidence_id: item for item in draft.evidence_refs
        }
        referenced = set(readiness.evidence_ids)
        for option in readiness.option_readiness:
            referenced.update(option.evidence_ids)
            expected_missing_fields = tuple(
                field.required_field
                for field in option.field_resolutions
                if field.status
                in {
                    BankingPrecheckFieldStatus.MISSING_INPUT,
                    BankingPrecheckFieldStatus.SOURCE_UNAVAILABLE,
                }
            )
            expected_unmapped_fields = tuple(
                field.required_field
                for field in option.field_resolutions
                if field.status is BankingPrecheckFieldStatus.UNMAPPED
            )
            expected_failed_codes = tuple(
                criterion.code
                for criterion in option.requirement_checks
                if criterion.status is BankingCriterionStatus.FAIL
            )
            if option.missing_fields != expected_missing_fields:
                errors.append(
                    f"Precheck readiness option {option.option_id} has an inconsistent "
                    "missing-field index."
                )
            if option.unmapped_fields != expected_unmapped_fields:
                errors.append(
                    f"Precheck readiness option {option.option_id} has an inconsistent "
                    "unmapped-field index."
                )
            if option.failed_requirement_codes != expected_failed_codes:
                errors.append(
                    f"Precheck readiness option {option.option_id} has an inconsistent "
                    "failed-requirement index."
                )
            expected_option_status = self._expected_option_readiness_status(option)
            if option.status is not expected_option_status:
                errors.append(
                    f"Precheck readiness option {option.option_id} has an inconsistent "
                    "status."
                )
            minimum_checks = tuple(
                item
                for item in option.requirement_checks
                if item.code is BankingCriterionCode.MINIMUM_AMOUNT
            )
            if option.api_id is not None and len(minimum_checks) != 1:
                errors.append(
                    f"Precheck readiness option {option.option_id} requires one "
                    "minimum-amount check."
                )
            elif minimum_checks:
                amount_resolutions = tuple(
                    item
                    for item in option.field_resolutions
                    if item.required_field == "amount"
                )
                amount_is_resolved = (
                    len(amount_resolutions) == 1
                    and amount_resolutions[0].status
                    is BankingPrecheckFieldStatus.RESOLVED
                )
                allowed_statuses = (
                    {
                        BankingCriterionStatus.PASS,
                        BankingCriterionStatus.FAIL,
                        BankingCriterionStatus.NOT_APPLICABLE,
                    }
                    if amount_is_resolved
                    else {BankingCriterionStatus.NOT_EVALUABLE}
                )
                if minimum_checks[0].status not in allowed_statuses:
                    errors.append(
                        f"Precheck readiness option {option.option_id} has a "
                        "minimum-amount status inconsistent with amount resolution."
                    )
            for field in option.field_resolutions:
                referenced.update(field.evidence_ids)
                self._validate_precheck_field_lineage(
                    readiness=readiness,
                    option_id=option.option_id,
                    field=field,
                    evidence_by_id=evidence_by_id,
                    errors=errors,
                )
        if not referenced.issubset(evidence_ids):
            errors.append("BANKING_PRECHECK_READINESS references unknown evidence.")
        expected_ready = tuple(
            item.option_id
            for item in readiness.option_readiness
            if item.status is BankingPrecheckReadinessStatus.READY
        )
        expected_pending = tuple(
            item.option_id
            for item in readiness.option_readiness
            if item.status is not BankingPrecheckReadinessStatus.READY
        )
        if readiness.ready_option_ids != expected_ready:
            errors.append("BANKING_PRECHECK_READINESS ready option index is inconsistent.")
        if readiness.pending_option_ids != expected_pending:
            errors.append(
                "BANKING_PRECHECK_READINESS pending option index is inconsistent."
            )
        expected_aggregate = self._expected_aggregate_readiness_status(
            readiness.option_readiness
        )
        if readiness.status is not expected_aggregate:
            errors.append("BANKING_PRECHECK_READINESS aggregate status is inconsistent.")
        self._validate_readiness_policy_alignment(
            readiness,
            evidence_by_id,
            errors,
        )
        forbidden = {
            "action_command",
            "approval_request",
            "approval_required",
            "selected_bank",
            "selected_option",
            "external_request",
            "external_response",
            "precheck_response",
            "precheck_success",
            "document_package",
            "decision_card",
            "final_decision",
        }
        present = EvidenceValidator._recursive_keys(draft.payload)
        if forbidden & present:
            errors.append(
                "BANKING_PRECHECK_READINESS contains out-of-bound fields: "
                + ", ".join(sorted(forbidden & present))
            )
        if not errors:
            checks.append("BANKING_PRECHECK_READINESS_BOUNDARY_VALID")

    @staticmethod
    def _expected_option_readiness_status(
        option: BankingOptionPrecheckReadiness,
    ) -> BankingPrecheckReadinessStatus:
        if option.api_id is None:
            return BankingPrecheckReadinessStatus.NOT_CONFIGURED
        if option.unmapped_fields or option.unexpected_policy_fields:
            return BankingPrecheckReadinessStatus.UNSUPPORTED_MAPPING
        if option.failed_requirement_codes:
            return BankingPrecheckReadinessStatus.OPTION_REQUIREMENTS_NOT_MET
        if option.missing_fields:
            return BankingPrecheckReadinessStatus.INPUT_REQUIRED
        return BankingPrecheckReadinessStatus.READY

    @staticmethod
    def _expected_aggregate_readiness_status(
        options: tuple[BankingOptionPrecheckReadiness, ...],
    ) -> BankingPrecheckReadinessStatus:
        statuses = {item.status for item in options}
        if not options or statuses == {BankingPrecheckReadinessStatus.NOT_CONFIGURED}:
            return BankingPrecheckReadinessStatus.NOT_CONFIGURED
        if statuses == {BankingPrecheckReadinessStatus.READY}:
            return BankingPrecheckReadinessStatus.READY
        if BankingPrecheckReadinessStatus.READY in statuses:
            return BankingPrecheckReadinessStatus.PARTIALLY_READY
        if BankingPrecheckReadinessStatus.UNSUPPORTED_MAPPING in statuses:
            return BankingPrecheckReadinessStatus.UNSUPPORTED_MAPPING
        if BankingPrecheckReadinessStatus.INPUT_REQUIRED in statuses:
            return BankingPrecheckReadinessStatus.INPUT_REQUIRED
        if BankingPrecheckReadinessStatus.OPTION_REQUIREMENTS_NOT_MET in statuses:
            return BankingPrecheckReadinessStatus.OPTION_REQUIREMENTS_NOT_MET
        return BankingPrecheckReadinessStatus.NOT_CONFIGURED

    @staticmethod
    def _resolution_source_evidence(
        field: BankingPrecheckFieldResolution,
        evidence_by_id: dict[str, EvidenceRef],
    ) -> tuple[EvidenceRef, ...]:
        source_ids = {
            source_id
            for evidence_id in field.evidence_ids
            if (evidence := evidence_by_id.get(evidence_id)) is not None
            for source_id in evidence.source_evidence_ids
        }
        return tuple(
            evidence_by_id[source_id]
            for source_id in sorted(source_ids)
            if source_id in evidence_by_id
        )

    @classmethod
    def _validate_precheck_field_lineage(
        cls,
        *,
        readiness: BankingPrecheckReadiness,
        option_id: str,
        field: BankingPrecheckFieldResolution,
        evidence_by_id: dict[str, EvidenceRef],
        errors: list[str],
    ) -> None:
        field_evidence = tuple(
            evidence_by_id[evidence_id]
            for evidence_id in field.evidence_ids
            if evidence_id in evidence_by_id
        )
        expected_display = {
            "status": field.status.value,
            "source": field.source.value if field.source is not None else None,
            "source_reference": field.source_reference,
        }
        exact_derived = tuple(
            evidence
            for evidence in field_evidence
            if evidence.source_type is SourceType.DERIVED
            and evidence.sheet == "BANKING_PRECHECK_READINESS"
            and evidence.record_id == readiness.matrix_id
            and evidence.field == field.required_field
            and evidence.display_value == expected_display
        )
        if len(field_evidence) != 1 or len(exact_derived) != 1:
            errors.append(
                f"Precheck field {option_id}.{field.required_field} lacks exact "
                "derived lineage."
            )

        if field.status is BankingPrecheckFieldStatus.UNMAPPED:
            if field.source_artifact_id is not None or field.source_record_ids:
                errors.append(
                    f"Unmapped precheck field {option_id}.{field.required_field} "
                    "cannot claim source records."
                )
            return

        expected_reference = {
            BankingPrecheckFieldSource.EVALUATION_CASE: "EvaluationCase.contract_id",
            BankingPrecheckFieldSource.BANKING_DISCOVERY_REQUEST: (
                "BankingDiscoveryRequest.requested_amount"
            ),
            BankingPrecheckFieldSource.BANKING_INPUT_SUPPLEMENT: (
                "BankingInputSupplement.requested_amount"
            ),
            BankingPrecheckFieldSource.OPC_PROFILE: "02_OPC_PROFILE[field,value]",
        }.get(field.source)
        if field.source_reference != expected_reference:
            errors.append(
                f"Precheck field {option_id}.{field.required_field} has an invalid "
                "source reference."
            )

        source_evidence = cls._resolution_source_evidence(field, evidence_by_id)
        if field.source is BankingPrecheckFieldSource.EVALUATION_CASE:
            if field.status is not BankingPrecheckFieldStatus.RESOLVED:
                errors.append(
                    f"EvaluationCase precheck field {option_id}.{field.required_field} "
                    "must be resolved."
                )
            if field.source_record_ids != (readiness.contract_id,):
                errors.append(
                    f"EvaluationCase precheck field {option_id}.{field.required_field} "
                    "does not reference the exact contract."
                )
            if (
                field.source_artifact_id is None
                or field.source_artifact_id not in readiness.source_artifact_ids
            ):
                errors.append(
                    f"EvaluationCase precheck field {option_id}.{field.required_field} "
                    "does not reference an upstream artifact."
                )
            return

        if field.source is BankingPrecheckFieldSource.BANKING_DISCOVERY_REQUEST:
            if (
                field.source_artifact_id is None
                or field.source_artifact_id not in readiness.source_artifact_ids
            ):
                errors.append(
                    f"Banking request amount field {option_id}.{field.required_field} "
                    "does not reference its upstream request artifact."
                )
            if field.status is BankingPrecheckFieldStatus.MISSING_INPUT:
                if field.source_record_ids:
                    errors.append(
                        f"Missing Banking request amount field "
                        f"{option_id}.{field.required_field} claims source records."
                    )
                if any(
                    evidence.source_type is SourceType.TEAM_PACK
                    and evidence.sheet == SheetRegistry.CREDIT_PROFILES.sheet_name
                    and evidence.field == "requested_amount"
                    for evidence in source_evidence
                ):
                    errors.append(
                        f"Missing Banking request amount field "
                        f"{option_id}.{field.required_field} contains amount evidence."
                    )
                return
            if (
                field.status is not BankingPrecheckFieldStatus.RESOLVED
                or len(field.source_record_ids) != 2
                or not all(field.source_record_ids)
            ):
                errors.append(
                    f"Resolved Banking request amount field "
                    f"{option_id}.{field.required_field} has an invalid requirement/credit "
                    "binding."
                )
                return
            credit_case_id = field.source_record_ids[1]
            amount_evidence = tuple(
                evidence
                for evidence in source_evidence
                if evidence.source_type is SourceType.TEAM_PACK
                and evidence.sheet == SheetRegistry.CREDIT_PROFILES.sheet_name
                and evidence.record_id == credit_case_id
                and evidence.field == "requested_amount"
                and isinstance(evidence.display_value, int)
                and not isinstance(evidence.display_value, bool)
                and evidence.display_value > 0
            )
            if len(amount_evidence) != 1:
                errors.append(
                    f"Resolved Banking request amount field "
                    f"{option_id}.{field.required_field} lacks exact credit-profile "
                    "requested_amount evidence."
                )
            return

        if field.source is BankingPrecheckFieldSource.BANKING_INPUT_SUPPLEMENT:
            if readiness.supplement_id is None:
                if (
                    field.status is not BankingPrecheckFieldStatus.MISSING_INPUT
                    or field.source_artifact_id is not None
                    or field.source_record_ids
                ):
                    errors.append(
                        f"Missing Banking amount field {option_id}.{field.required_field} "
                        "claims supplement data."
                    )
                if any(
                    evidence.source_type is SourceType.USER_INPUT
                    and evidence.field == "requested_amount"
                    for evidence in source_evidence
                ):
                    errors.append(
                        f"Missing Banking amount field {option_id}.{field.required_field} "
                        "contains USER_INPUT amount evidence."
                    )
                return
            if (
                field.status is not BankingPrecheckFieldStatus.RESOLVED
                or field.source_record_ids != (readiness.supplement_id,)
                or field.source_artifact_id is None
                or field.source_artifact_id not in readiness.source_artifact_ids
            ):
                errors.append(
                    f"Resolved Banking amount field {option_id}.{field.required_field} "
                    "does not reference the exact supplement."
                )
            amount_evidence = tuple(
                evidence
                for evidence in source_evidence
                if evidence.source_type is SourceType.USER_INPUT
                and evidence.sheet == "BANKING_INPUT_SUPPLEMENT"
                and evidence.record_id == readiness.supplement_id
                and evidence.field == "requested_amount"
                and isinstance(evidence.display_value, int)
                and not isinstance(evidence.display_value, bool)
                and evidence.display_value > 0
            )
            if len(amount_evidence) != 1:
                errors.append(
                    f"Resolved Banking amount field {option_id}.{field.required_field} "
                    "lacks exact USER_INPUT evidence."
                )
            return

        if field.source is BankingPrecheckFieldSource.OPC_PROFILE:
            if field.source_artifact_id is not None:
                errors.append(
                    f"OPC profile field {option_id}.{field.required_field} cannot "
                    "claim an artifact source."
                )
            if field.status is BankingPrecheckFieldStatus.SOURCE_UNAVAILABLE:
                if field.source_record_ids:
                    errors.append(
                        f"Unavailable OPC profile field {option_id}.{field.required_field} "
                        "cannot claim records."
                    )
                return
            if field.status is not BankingPrecheckFieldStatus.RESOLVED:
                errors.append(
                    f"OPC profile field {option_id}.{field.required_field} has an "
                    "invalid status."
                )
                return
            profile_fields = {
                (evidence.record_id, evidence.field)
                for evidence in source_evidence
                if evidence.source_type is SourceType.TEAM_PACK
                and evidence.sheet == "02_OPC_PROFILE"
            }
            expected_profile_fields = {
                (record_id, source_field)
                for record_id in field.source_record_ids
                for source_field in ("field", "value")
            }
            if not expected_profile_fields or not expected_profile_fields.issubset(
                profile_fields
            ):
                errors.append(
                    f"OPC profile field {option_id}.{field.required_field} lacks exact "
                    "02_OPC_PROFILE lineage."
                )

    def _validate_readiness_policy_alignment(
        self,
        readiness: BankingPrecheckReadiness,
        evidence_by_id: dict[str, EvidenceRef],
        errors: list[str],
    ) -> None:
        policy = self._banking_policy
        if policy is None:
            return
        bindings_by_product = {
            product_id: binding
            for binding in policy.bindings
            for product_id in binding.bank_product_ids
        }
        for option in readiness.option_readiness:
            binding = bindings_by_product.get(option.bank_product_id)
            if binding is None:
                errors.append(
                    f"Precheck readiness option {option.option_id} has no policy binding."
                )
                continue
            expected_api = binding.precheck_api_by_product.get(option.bank_product_id)
            if option.api_id != expected_api:
                errors.append(
                    f"Precheck readiness option {option.option_id} has an invalid API."
                )
                continue
            if option.api_id is None:
                continue
            configured_fields = binding.precheck_field_sources_by_api.get(
                option.api_id, {}
            )
            expected_unmapped = tuple(
                field
                for field in option.required_fields
                if field not in configured_fields
            )
            expected_unexpected = tuple(
                sorted(
                    field
                    for field in configured_fields
                    if field not in set(option.required_fields)
                )
            )
            if option.unmapped_fields != expected_unmapped:
                errors.append(
                    f"Precheck readiness option {option.option_id} does not expose "
                    "the exact unmapped policy fields."
                )
            if option.unexpected_policy_fields != expected_unexpected:
                errors.append(
                    f"Precheck readiness option {option.option_id} does not expose "
                    "the exact unexpected policy fields."
                )
            for field in option.field_resolutions:
                expected_source = configured_fields.get(field.required_field)
                if expected_source is None:
                    if (
                        field.status is not BankingPrecheckFieldStatus.UNMAPPED
                        or field.source is not None
                    ):
                        errors.append(
                            f"Precheck field {option.option_id}.{field.required_field} "
                            "invented a source absent from policy."
                        )
                    continue
                if field.source is not expected_source:
                    errors.append(
                        f"Precheck field {option.option_id}.{field.required_field} "
                        "does not use its exact policy source."
                    )
                source_evidence = self._resolution_source_evidence(
                    field, evidence_by_id
                )
                has_api_evidence = any(
                    evidence.source_type is SourceType.TEAM_PACK
                    and evidence.sheet == "12_API_CATALOG"
                    and evidence.record_id == option.api_id
                    and evidence.field == "required_fields"
                    for evidence in source_evidence
                )
                has_policy_evidence = any(
                    evidence.source_type is SourceType.POLICY_CONFIG
                    and evidence.sheet == "BANKING_CATALOG_POLICY"
                    and evidence.record_id == binding.binding_id
                    and evidence.field == "explicit_catalog_binding"
                    for evidence in source_evidence
                )
                if not has_api_evidence or not has_policy_evidence:
                    errors.append(
                        f"Precheck field {option.option_id}.{field.required_field} "
                        "lacks exact API and policy lineage."
                    )

    @staticmethod
    def _validate_decision_post_banking_review(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate Decision routing without allowing protected or external actions."""
        try:
            review = DecisionPostBankingReview.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid DECISION_POST_BANKING_REVIEW schema: {exc}")
            return
        if review.evaluation_case_id != draft.evaluation_case_id:
            errors.append(
                "DECISION_POST_BANKING_REVIEW case identity does not match its draft."
            )
        if review.precheck_executed:
            errors.append("DECISION_POST_BANKING_REVIEW cannot execute a precheck.")
        if len(set(review.source_artifact_ids)) != len(review.source_artifact_ids):
            errors.append(
                "DECISION_POST_BANKING_REVIEW contains duplicate source artifacts."
            )
        if len(set(review.evidence_ids)) != len(review.evidence_ids):
            errors.append(
                "DECISION_POST_BANKING_REVIEW contains duplicate evidence IDs."
            )
        referenced = set(review.evidence_ids)
        missing_requests = review.missing_data_requests
        referenced.update(
            evidence.evidence_id
            for request in missing_requests
            for evidence in request.evidence_refs
        )
        if not referenced.issubset(evidence_ids):
            errors.append("DECISION_POST_BANKING_REVIEW references unknown evidence.")
        evidence_by_id = {
            item.evidence_id: item for item in draft.evidence_refs
        }
        for request in missing_requests:
            if request.evaluation_case_id != review.evaluation_case_id:
                errors.append(
                    "DECISION_POST_BANKING_REVIEW contains a cross-case missing request."
                )
            if request.raised_by != "DECISION_POST_BANKING_REVIEW":
                errors.append(
                    "DECISION_POST_BANKING_REVIEW missing request has an invalid owner."
                )
            if request.target_record != review.banking_request_id:
                errors.append(
                    "DECISION_POST_BANKING_REVIEW missing request targets another "
                    "Banking request."
                )
            if (
                request.severity is not MissingSeverity.BLOCKING
                or request.status is not MissingRequestStatus.OPEN
            ):
                errors.append(
                    "DECISION_POST_BANKING_REVIEW may emit only open blocking requests."
                )
            if any(
                evidence_by_id.get(evidence.evidence_id) != evidence
                for evidence in request.evidence_refs
            ):
                errors.append(
                    "DECISION_POST_BANKING_REVIEW missing request has altered evidence."
                )
        if review.required_input_fields != tuple(
            request.field for request in missing_requests
        ):
            errors.append(
                "DECISION_POST_BANKING_REVIEW required inputs do not match its "
                "missing requests."
            )
        if review.outcome is DecisionPostBankingOutcome.BANKING_PRECHECK_READY:
            if not review.precheck_ready_option_ids:
                errors.append("A ready Banking review requires at least one ready option.")
            if review.required_input_fields or missing_requests:
                errors.append("A ready Banking review cannot retain missing input requests.")
        elif review.outcome is DecisionPostBankingOutcome.BANKING_INPUT_REQUIRED:
            if not review.required_input_fields or not missing_requests:
                errors.append(
                    "A Banking input-required review must persist its missing requests."
                )
        elif review.required_input_fields or missing_requests:
            errors.append(
                "A non-input Banking review cannot retain missing input requests."
            )
        forbidden = {
            "action_command",
            "approval_request",
            "approval_decision",
            "protected_action",
            "selected_bank",
            "selected_option",
            "recommended_option",
            "external_request",
            "external_response",
            "precheck_response",
            "document_package",
            "decision_card",
            "final_decision",
        }
        present = EvidenceValidator._recursive_keys(draft.payload)
        if forbidden & present:
            errors.append(
                "DECISION_POST_BANKING_REVIEW contains out-of-bound fields: "
                + ", ".join(sorted(forbidden & present))
            )
        if not errors:
            checks.append("DECISION_POST_BANKING_REVIEW_BOUNDARY_VALID")

    def _validate_banking_precheck_submission_proposal(
        self,
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate an all-READY reference manifest without allowing execution."""
        try:
            proposal = BankingPrecheckSubmissionProposal.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(
                f"Invalid BANKING_PRECHECK_SUBMISSION_PROPOSAL schema: {exc}"
            )
            return
        if proposal.evaluation_case_id != draft.evaluation_case_id:
            errors.append(
                "BANKING_PRECHECK_SUBMISSION_PROPOSAL case identity does not match "
                "its draft."
            )
        if proposal.proposed_action is not ProtectedAction.SUBMIT_BANKING_PRECHECK:
            errors.append(
                "BANKING_PRECHECK_SUBMISSION_PROPOSAL has an invalid protected action."
            )
        if proposal.precheck_executed or proposal.submission_executed:
            errors.append(
                "BANKING_PRECHECK_SUBMISSION_PROPOSAL cannot claim external execution."
            )
        if proposal.requested_amount_currency is not CurrencyCode.VND:
            errors.append(
                "BANKING_PRECHECK_SUBMISSION_PROPOSAL monetary values must use VND."
            )
        if set(proposal.evidence_ids) != evidence_ids:
            errors.append(
                "BANKING_PRECHECK_SUBMISSION_PROPOSAL evidence index must exactly "
                "match its draft lineage."
            )
        evidence_by_id = {
            item.evidence_id: item for item in draft.evidence_refs
        }
        referenced = set(proposal.evidence_ids)
        for candidate in proposal.candidates:
            referenced.update(candidate.evidence_ids)
            referenced.update(candidate.catalog_terms.evidence_ids)
            referenced.add(
                candidate.governance_source_facts.api_extension_rule_evidence_id
            )
            for handling_rule in candidate.governance_source_facts.handling_rules:
                referenced.update(handling_rule.evidence_ids)
            for binding in candidate.field_bindings:
                referenced.update(binding.evidence_ids)
            self._validate_submission_candidate(
                proposal=proposal,
                candidate=candidate,
                evidence_by_id=evidence_by_id,
                errors=errors,
            )
        if not referenced.issubset(evidence_ids):
            errors.append(
                "BANKING_PRECHECK_SUBMISSION_PROPOSAL references unknown evidence."
            )
        self._validate_submission_policy_alignment(proposal, errors)
        forbidden = {
            "action_command",
            "approval_required",
            "approval_decision",
            "approval_request",
            "bank_response",
            "decision_card",
            "external_request",
            "external_response",
            "field_value",
            "field_values",
            "final_decision",
            "precheck_result",
            "rank",
            "ranking",
            "recommended_option",
            "request_body",
            "request_payload",
            "response_payload",
            "selected_bank",
            "selected_option",
            "selected_option_id",
            "submission_result",
        }
        present = self._recursive_keys(draft.payload)
        if forbidden & present:
            errors.append(
                "BANKING_PRECHECK_SUBMISSION_PROPOSAL contains out-of-bound fields: "
                + ", ".join(sorted(forbidden & present))
            )
        if not errors:
            checks.append("BANKING_PRECHECK_SUBMISSION_PROPOSAL_BOUNDARY_VALID")

    def _validate_submission_candidate(
        self,
        *,
        proposal: BankingPrecheckSubmissionProposal,
        candidate: BankingPrecheckSubmissionCandidate,
        evidence_by_id: dict[str, EvidenceRef],
        errors: list[str],
    ) -> None:
        candidate_evidence = tuple(
            evidence_by_id[evidence_id]
            for evidence_id in candidate.evidence_ids
            if evidence_id in evidence_by_id
        )
        ready_claims = tuple(
            evidence
            for evidence in candidate_evidence
            if evidence.source_type is SourceType.DERIVED
            and evidence.sheet == "BANKING_PRECHECK_SUBMISSION_PROPOSAL"
            and evidence.record_id == candidate.proposal_item_id
            and evidence.field == "ready_option_included"
            and evidence.display_value
            == {
                "option_id": candidate.option_id,
                "readiness": "READY",
                "proposal_mode": "BATCH_ALL_READY_OPTIONS",
            }
        )
        if len(ready_claims) != 1:
            errors.append(
                f"Submission candidate {candidate.option_id} lacks one exact READY "
                "batch lineage item."
            )
        else:
            supporting_ids = set(candidate.evidence_ids) - {
                ready_claims[0].evidence_id
            }
            if set(ready_claims[0].source_evidence_ids) != supporting_ids:
                errors.append(
                    f"Submission candidate {candidate.option_id} READY lineage does "
                    "not cover its exact supporting evidence."
                )

        self._validate_submission_catalog_terms(
            proposal=proposal,
            candidate=candidate,
            evidence_by_id=evidence_by_id,
            errors=errors,
        )
        required_fields = self._validate_submission_api_metadata(
            candidate=candidate,
            evidence_by_id=evidence_by_id,
            errors=errors,
        )
        self._validate_submission_governance_source_facts(
            candidate=candidate,
            evidence_by_id=evidence_by_id,
            errors=errors,
        )
        binding_fields = tuple(
            binding.required_field for binding in candidate.field_bindings
        )
        if required_fields is not None and binding_fields != required_fields:
            errors.append(
                f"Submission candidate {candidate.option_id} field-reference manifest "
                "does not exactly match API required fields."
            )
        for binding in candidate.field_bindings:
            self._validate_submission_field_binding(
                proposal=proposal,
                candidate=candidate,
                binding=binding,
                evidence_by_id=evidence_by_id,
                errors=errors,
            )

    def _validate_submission_catalog_terms(
        self,
        *,
        proposal: BankingPrecheckSubmissionProposal,
        candidate: BankingPrecheckSubmissionCandidate,
        evidence_by_id: dict[str, EvidenceRef],
        errors: list[str],
    ) -> None:
        terms = candidate.catalog_terms
        expected_product_values = {
            "bank": candidate.provider,
            "product_name": candidate.product_name,
        }
        for field, expected_value in expected_product_values.items():
            matches = tuple(
                evidence
                for evidence_id in candidate.evidence_ids
                if (evidence := evidence_by_id.get(evidence_id)) is not None
                and evidence.source_type is SourceType.TEAM_PACK
                and evidence.sheet == "11_BANK_PRODUCTS"
                and evidence.record_id == candidate.bank_product_id
                and evidence.field == field
                and self._same_json_scalar(evidence.display_value, expected_value)
            )
            if len(matches) != 1:
                errors.append(
                    f"Submission candidate {candidate.option_id} lacks exact catalog "
                    f"evidence for {field}."
                )
        if terms.minimum_amount_currency is not CurrencyCode.VND:
            errors.append(
                f"Submission candidate {candidate.option_id} catalog minimum is not VND."
            )
        if (
            terms.minimum_amount is not None
            and proposal.requested_amount < terms.minimum_amount
        ):
            errors.append(
                f"Submission candidate {candidate.option_id} is below its catalog "
                "minimum and cannot be READY."
            )
        expected_values = {
            "annual_rate_or_fee": terms.annual_rate_or_fee,
            "processing_fee_rate": terms.processing_fee_rate,
            "collateral_ratio": terms.collateral_ratio,
            "minimum_amount": terms.minimum_amount,
        }
        exact_term_ids: set[str] = set()
        for field, expected_value in expected_values.items():
            matches = tuple(
                evidence
                for evidence_id in terms.evidence_ids
                if (evidence := evidence_by_id.get(evidence_id)) is not None
                and evidence.source_type is SourceType.TEAM_PACK
                and evidence.sheet == "11_BANK_PRODUCTS"
                and evidence.record_id == candidate.bank_product_id
                and evidence.field == field
                and self._same_json_scalar(
                    evidence.display_value, expected_value
                )
            )
            if len(matches) != 1:
                errors.append(
                    f"Submission candidate {candidate.option_id} lacks exact catalog "
                    f"evidence for {field}."
                )
            exact_term_ids.update(item.evidence_id for item in matches)
        if exact_term_ids != set(terms.evidence_ids):
            errors.append(
                f"Submission candidate {candidate.option_id} catalog-term evidence "
                "contains non-term references."
            )

    def _validate_submission_api_metadata(
        self,
        *,
        candidate: BankingPrecheckSubmissionCandidate,
        evidence_by_id: dict[str, EvidenceRef],
        errors: list[str],
    ) -> tuple[str, ...] | None:
        expected_api_values = {
            "provider": candidate.api_provider,
            "method": candidate.api_method,
            "endpoint": candidate.api_endpoint,
        }
        for field, expected_value in expected_api_values.items():
            matches = tuple(
                evidence
                for evidence_id in candidate.evidence_ids
                if (evidence := evidence_by_id.get(evidence_id)) is not None
                and evidence.source_type is SourceType.TEAM_PACK
                and evidence.sheet == "12_API_CATALOG"
                and evidence.record_id == candidate.api_id
                and evidence.field == field
                and self._same_json_scalar(
                    evidence.display_value, expected_value
                )
            )
            if len(matches) != 1:
                errors.append(
                    f"Submission candidate {candidate.option_id} lacks exact API "
                    f"evidence for {field}."
                )
        required_fields_evidence = tuple(
            evidence
            for evidence_id in candidate.evidence_ids
            if (evidence := evidence_by_id.get(evidence_id)) is not None
            and evidence.source_type is SourceType.TEAM_PACK
            and evidence.sheet == "12_API_CATALOG"
            and evidence.record_id == candidate.api_id
            and evidence.field == "required_fields"
            and isinstance(evidence.display_value, str)
        )
        if len(required_fields_evidence) != 1:
            errors.append(
                f"Submission candidate {candidate.option_id} lacks one exact API "
                "required-fields manifest."
            )
            return None
        return tuple(
            field.strip()
            for field in required_fields_evidence[0].display_value.split(",")
            if field.strip()
        )

    @staticmethod
    def _validate_submission_governance_source_facts(
        *,
        candidate: BankingPrecheckSubmissionCandidate,
        evidence_by_id: dict[str, EvidenceRef],
        errors: list[str],
    ) -> None:
        """Verify exact source policy facts without interpreting an approval outcome."""
        facts = candidate.governance_source_facts
        extension = evidence_by_id.get(facts.api_extension_rule_evidence_id)
        if (
            extension is None
            or extension.source_type is not SourceType.TEAM_PACK
            or extension.sheet != SheetRegistry.API_CATALOG.sheet_name
            or extension.record_id != candidate.api_id
            or extension.field != "extension_rule"
            or extension.display_value != facts.api_extension_rule
            or extension.evidence_id not in candidate.evidence_ids
        ):
            errors.append(
                f"Submission candidate {candidate.option_id} has invalid API "
                "extension-rule lineage."
            )
        for rule in facts.handling_rules:
            expected = {
                "rule_id": rule.rule_id,
                "applies_to": rule.applies_to,
                "requires_human_approval": rule.requires_human_approval_text,
            }
            matches = tuple(
                evidence_by_id[evidence_id]
                for evidence_id in rule.evidence_ids
                if evidence_id in evidence_by_id
                and evidence_by_id[evidence_id].source_type is SourceType.TEAM_PACK
                and evidence_by_id[evidence_id].sheet
                == SheetRegistry.API_HANDLING_RULES.sheet_name
                and evidence_by_id[evidence_id].record_id == rule.rule_id
                and evidence_by_id[evidence_id].field in expected
                and evidence_by_id[evidence_id].display_value
                == expected[evidence_by_id[evidence_id].field]
            )
            if (
                len(matches) != len(expected)
                or {item.field for item in matches} != set(expected)
                or not set(rule.evidence_ids).issubset(candidate.evidence_ids)
            ):
                errors.append(
                    f"Submission candidate {candidate.option_id} has invalid handling "
                    f"policy lineage for {rule.rule_id}."
                )

    def _validate_submission_field_binding(
        self,
        *,
        proposal: BankingPrecheckSubmissionProposal,
        candidate: BankingPrecheckSubmissionCandidate,
        binding: BankingPrecheckFieldBindingReference,
        evidence_by_id: dict[str, EvidenceRef],
        errors: list[str],
    ) -> None:
        expected_reference = {
            BankingPrecheckFieldSource.EVALUATION_CASE: "EvaluationCase.contract_id",
            BankingPrecheckFieldSource.BANKING_DISCOVERY_REQUEST: (
                "BankingDiscoveryRequest.requested_amount"
            ),
            BankingPrecheckFieldSource.BANKING_INPUT_SUPPLEMENT: (
                "BankingInputSupplement.requested_amount"
            ),
            BankingPrecheckFieldSource.OPC_PROFILE: "02_OPC_PROFILE[field,value]",
        }[binding.source]
        if binding.source_reference != expected_reference:
            errors.append(
                f"Submission field {candidate.option_id}.{binding.required_field} "
                "has an invalid source reference."
            )
        if (
            binding.source_artifact_id is not None
            and binding.source_artifact_id not in proposal.source_artifact_ids
        ):
            errors.append(
                f"Submission field {candidate.option_id}.{binding.required_field} "
                "references an artifact outside proposal lineage."
            )
        binding_evidence = tuple(
            evidence_by_id[evidence_id]
            for evidence_id in binding.evidence_ids
            if evidence_id in evidence_by_id
        )
        expected_display = {
            "status": BankingPrecheckFieldStatus.RESOLVED.value,
            "source": binding.source.value,
            "source_reference": binding.source_reference,
        }
        exact_resolution = tuple(
            evidence
            for evidence in binding_evidence
            if evidence.source_type is SourceType.DERIVED
            and evidence.sheet == "BANKING_PRECHECK_READINESS"
            and evidence.record_id == proposal.matrix_id
            and evidence.field == binding.required_field
            and evidence.display_value == expected_display
        )
        if len(binding_evidence) != 1 or len(exact_resolution) != 1:
            errors.append(
                f"Submission field {candidate.option_id}.{binding.required_field} "
                "lacks exact RESOLVED readiness lineage."
            )
            return
        source_evidence = tuple(
            evidence_by_id[source_id]
            for source_id in exact_resolution[0].source_evidence_ids
            if source_id in evidence_by_id
        )
        if binding.source is BankingPrecheckFieldSource.EVALUATION_CASE:
            if (
                binding.source_artifact_id is None
                or binding.source_record_ids != (proposal.contract_id,)
            ):
                errors.append(
                    f"Submission field {candidate.option_id}.{binding.required_field} "
                    "does not reference the exact EvaluationCase contract."
                )
        elif binding.source is BankingPrecheckFieldSource.BANKING_DISCOVERY_REQUEST:
            amount_evidence = tuple(
                evidence
                for evidence in source_evidence
                if evidence.source_type is SourceType.TEAM_PACK
                and evidence.sheet == SheetRegistry.CREDIT_PROFILES.sheet_name
                and len(binding.source_record_ids) == 2
                and evidence.record_id == binding.source_record_ids[1]
                and evidence.field == "requested_amount"
                and self._same_json_scalar(
                    evidence.display_value, proposal.requested_amount
                )
            )
            if (
                binding.source_artifact_id is None
                or len(binding.source_record_ids) != 2
                or not all(binding.source_record_ids)
                or len(amount_evidence) != 1
            ):
                errors.append(
                    f"Submission field {candidate.option_id}.{binding.required_field} "
                    "lacks exact BankingDiscoveryRequest credit-amount lineage."
                )
        elif binding.source is BankingPrecheckFieldSource.BANKING_INPUT_SUPPLEMENT:
            amount_evidence = tuple(
                evidence
                for evidence in source_evidence
                if evidence.source_type is SourceType.USER_INPUT
                and evidence.sheet == "BANKING_INPUT_SUPPLEMENT"
                and evidence.record_id in binding.source_record_ids
                and evidence.field == "requested_amount"
                and self._same_json_scalar(
                    evidence.display_value, proposal.requested_amount
                )
            )
            if binding.source_artifact_id is None or len(amount_evidence) != 1:
                errors.append(
                    f"Submission field {candidate.option_id}.{binding.required_field} "
                    "lacks exact USER_INPUT amount lineage."
                )
        else:
            profile_fields = {
                (evidence.record_id, evidence.field)
                for evidence in source_evidence
                if evidence.source_type is SourceType.TEAM_PACK
                and evidence.sheet == "02_OPC_PROFILE"
            }
            expected_profile_fields = {
                (record_id, field)
                for record_id in binding.source_record_ids
                for field in ("field", "value")
            }
            if (
                binding.source_artifact_id is not None
                or not expected_profile_fields.issubset(profile_fields)
            ):
                errors.append(
                    f"Submission field {candidate.option_id}.{binding.required_field} "
                    "lacks exact 02_OPC_PROFILE lineage."
                )

    def _validate_submission_policy_alignment(
        self,
        proposal: BankingPrecheckSubmissionProposal,
        errors: list[str],
    ) -> None:
        policy = self._banking_policy
        if policy is None:
            errors.append(
                "BANKING_PRECHECK_SUBMISSION_PROPOSAL requires active catalog policy "
                "validation."
            )
            return
        if (
            proposal.mapping_policy_id,
            proposal.mapping_version,
            proposal.mapping_hash,
        ) != (policy.policy_id, policy.mapping_version, policy.policy_hash):
            errors.append(
                "BANKING_PRECHECK_SUBMISSION_PROPOSAL mapping identity does not match "
                "policy."
            )
            return
        bindings_by_product = {
            product_id: binding
            for binding in policy.bindings
            for product_id in binding.bank_product_ids
        }
        for candidate in proposal.candidates:
            policy_binding = bindings_by_product.get(candidate.bank_product_id)
            if (
                policy_binding is None
                or policy_binding.need_type is not candidate.need_type
            ):
                errors.append(
                    f"Submission candidate {candidate.option_id} has no exact product "
                    "policy binding."
                )
                continue
            expected_api = policy_binding.precheck_api_by_product.get(
                candidate.bank_product_id
            )
            if expected_api != candidate.api_id:
                errors.append(
                    f"Submission candidate {candidate.option_id} has an unconfigured API."
                )
                continue
            configured_sources = policy_binding.precheck_field_sources_by_api.get(
                candidate.api_id, {}
            )
            actual_sources = {
                binding.required_field: binding.source
                for binding in candidate.field_bindings
            }
            if configured_sources != actual_sources:
                errors.append(
                    f"Submission candidate {candidate.option_id} field sources do not "
                    "exactly match policy."
                )
            configured_handling_ids = policy_binding.handling_rule_ids
            actual_handling_ids = tuple(
                item.rule_id
                for item in candidate.governance_source_facts.handling_rules
            )
            if configured_handling_ids != actual_handling_ids:
                errors.append(
                    f"Submission candidate {candidate.option_id} handling policy "
                    "references do not match the server mapping."
                )

    @staticmethod
    def _validate_banking_precheck_result_set(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
        simulation_policy: BankingPrecheckSimulationPolicy | None,
    ) -> None:
        """Validate simulated authority, exact lineage, and the Phase B1 boundary."""
        try:
            result_set = BankingPrecheckResultSet.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid BANKING_PRECHECK_RESULT_SET schema: {exc}")
            return
        if result_set.evaluation_case_id != draft.evaluation_case_id:
            errors.append(
                "BANKING_PRECHECK_RESULT_SET case identity does not match its draft."
            )
        if result_set.evidence_ids != tuple(
            item.evidence_id for item in draft.evidence_refs
        ):
            errors.append(
                "BANKING_PRECHECK_RESULT_SET evidence index must exactly match its draft."
            )
        if set(result_set.evidence_ids) != evidence_ids:
            errors.append(
                "BANKING_PRECHECK_RESULT_SET contains unindexed or unknown evidence."
            )
        if (
            not result_set.source_artifact_ids
            or result_set.source_artifact_ids[0] != result_set.proposal_artifact_id
        ):
            errors.append(
                "BANKING_PRECHECK_RESULT_SET must start lineage with its approved proposal."
            )
        if (
            result_set.execution_mode is not BankingPrecheckExecutionMode.SIMULATED
            or result_set.authority
            is not BankingPrecheckResultAuthority.SIMULATED_NON_BINDING
            or result_set.external_bank_submission
            or result_set.bank_approval_obtained
            or result_set.selection_performed
            or result_set.ranking_performed
            or result_set.documents_prepared
        ):
            errors.append(
                "BANKING_PRECHECK_RESULT_SET exceeds the simulated non-binding boundary."
            )
        expected_identity_inputs = {
            "source_artifact_ids": result_set.source_artifact_ids,
            "proposal_artifact_id": result_set.proposal_artifact_id,
            "proposal_id": result_set.proposal_id,
            "approval_request_id": result_set.approval_request_id,
            "permit_id": result_set.permit_id,
            "adapter_id": result_set.adapter_id,
            "adapter_config_hash": result_set.adapter_config_hash,
            "candidate_option_ids": result_set.candidate_option_ids,
            "request_hashes": tuple(
                item.request_hash for item in result_set.results
            ),
            "response_hashes": tuple(
                item.response_hash for item in result_set.results
            ),
            "execution_mode": result_set.execution_mode,
            "authority": result_set.authority,
        }
        if draft.identity_inputs != expected_identity_inputs:
            errors.append(
                "BANKING_PRECHECK_RESULT_SET artifact identity inputs are not exact."
            )

        policy = EvidenceValidator._validated_precheck_simulation_policy(
            result_set=result_set,
            simulation_policy=simulation_policy,
            errors=errors,
        )
        approval_evidence = tuple(
            item
            for item in draft.evidence_refs
            if item.source_type is SourceType.USER_INPUT
            and item.sheet == "APPROVAL_AUTHORIZATION"
            and item.record_id == result_set.approval_request_id
            and item.field == "authorized_action_permit"
        )
        if len(approval_evidence) != 1:
            errors.append(
                "BANKING_PRECHECK_RESULT_SET lacks one exact approval authorization item."
            )
            approval_item = None
        else:
            approval_item = approval_evidence[0]
            EvidenceValidator._validate_precheck_approval_evidence(
                result_set=result_set,
                evidence=approval_item,
                errors=errors,
            )
        evidence_by_id = {
            item.evidence_id: item for item in draft.evidence_refs
        }
        for result in result_set.results:
            if not set(result.evidence_ids).issubset(evidence_ids):
                errors.append(
                    f"Banking result {result.normalized_result_id} references unknown evidence."
                )
            if (
                approval_item is not None
                and approval_item.evidence_id not in result.evidence_ids
            ):
                errors.append(
                    f"Banking result {result.normalized_result_id} lacks approval lineage."
                )
            policy_item = EvidenceValidator._validate_precheck_policy_evidence(
                result_set=result_set,
                result=result,
                evidence_by_id=evidence_by_id,
                simulation_policy=policy,
                errors=errors,
            )
            EvidenceValidator._validate_precheck_result_identity(
                result_set=result_set,
                result=result,
                evidence_by_id=evidence_by_id,
                simulation_policy=policy,
                errors=errors,
            )
            EvidenceValidator._validate_precheck_derived_evidence(
                result_set=result_set,
                result=result,
                evidence_by_id=evidence_by_id,
                approval_evidence=approval_item,
                policy_evidence=policy_item,
                errors=errors,
            )
        forbidden = {
            "approval_decision",
            "company_profile",
            "decision_card",
            "documents",
            "external_request",
            "final_decision",
            "rank",
            "ranking",
            "raw_responses",
            "recommended_option",
            "request_body",
            "request_payload",
            "requests",
            "response_payload",
            "selected_bank",
            "selected_option",
            "selected_option_id",
        }
        present = EvidenceValidator._recursive_keys(draft.payload)
        if forbidden & present:
            errors.append(
                "BANKING_PRECHECK_RESULT_SET contains out-of-bound fields: "
                + ", ".join(sorted(forbidden & present))
            )
        expected_result_set_id = deterministic_id(
            "BPRS",
            result_set.proposal_artifact_id,
            result_set.proposal_id,
            result_set.approval_request_id,
            result_set.permit_id,
            result_set.adapter_id,
            result_set.adapter_config_hash,
            tuple(item.normalized_result_id for item in result_set.results),
            result_set.source_artifact_ids,
        )
        if result_set.result_set_id != expected_result_set_id:
            errors.append("BANKING_PRECHECK_RESULT_SET has an unstable result_set_id.")
        if not errors:
            checks.append("BANKING_PRECHECK_RESULT_SET_BOUNDARY_VALID")

    @staticmethod
    def _validate_decision_post_precheck_review(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate result routing while preserving exact non-binding candidates."""
        try:
            review = DecisionPostPrecheckReview.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid DECISION_POST_PRECHECK_REVIEW schema: {exc}")
            return
        if review.evaluation_case_id != draft.evaluation_case_id:
            errors.append(
                "DECISION_POST_PRECHECK_REVIEW case identity does not match its draft."
            )
        draft_evidence_ids = tuple(item.evidence_id for item in draft.evidence_refs)
        if review.evidence_ids != draft_evidence_ids:
            errors.append(
                "DECISION_POST_PRECHECK_REVIEW evidence index must exactly match its draft."
            )
        if set(review.evidence_ids) != evidence_ids:
            errors.append(
                "DECISION_POST_PRECHECK_REVIEW contains unindexed or unknown evidence."
            )
        if review.source_artifact_ids != (
            review.result_set_artifact_id,
            review.proposal_artifact_id,
        ):
            errors.append(
                "DECISION_POST_PRECHECK_REVIEW source artifact order is invalid."
            )
        expected_identity_inputs = {
            "source_artifact_ids": review.source_artifact_ids,
            "result_set_id": review.result_set_id,
            "proposal_id": review.proposal_id,
            "review_item_ids": tuple(
                item.review_item_id for item in review.option_reviews
            ),
            "outcome": review.outcome,
            "missing_data_request_ids": tuple(
                item.request_id for item in review.missing_data_requests
            ),
            "source_authority": review.source_authority,
        }
        if draft.identity_inputs != expected_identity_inputs:
            errors.append(
                "DECISION_POST_PRECHECK_REVIEW artifact identity inputs are not exact."
            )
        evidence_by_id = {
            item.evidence_id: item for item in draft.evidence_refs
        }
        derived_by_result: dict[str, EvidenceRef] = {}
        for item in review.option_reviews:
            expected_item_id = decision_post_precheck_item_id(
                result_set_id=review.result_set_id,
                normalized_result_id=item.normalized_result_id,
                proposal_item_id=item.proposal_item_id,
                option_id=item.option_id,
                bank_product_id=item.bank_product_id,
                source_outcome=item.source_outcome,
                disposition=item.disposition,
                required_follow_up_fields=item.required_follow_up_fields,
            )
            if item.review_item_id != expected_item_id:
                errors.append(
                    f"Post-precheck item {item.normalized_result_id} has an unstable ID."
                )
            if len(item.evidence_ids) != 1:
                errors.append(
                    f"Post-precheck item {item.review_item_id} must reference one "
                    "derived classification evidence item."
                )
                continue
            derived = evidence_by_id.get(item.evidence_ids[0])
            if derived is None:
                errors.append(
                    f"Post-precheck item {item.review_item_id} references unknown evidence."
                )
                continue
            display = {
                "review_item_id": item.review_item_id,
                "normalized_result_id": item.normalized_result_id,
                "proposal_item_id": item.proposal_item_id,
                "option_id": item.option_id,
                "bank_product_id": item.bank_product_id,
                "source_outcome": item.source_outcome.value,
                "disposition": item.disposition.value,
                "non_binding": True,
            }
            if (
                derived.source_type is not SourceType.DERIVED
                or derived.sheet != "DECISION_POST_PRECHECK_REVIEW"
                or derived.row_number != 0
                or derived.record_id != item.review_item_id
                or derived.field != "precheck_disposition"
                or derived.display_value != display
                or not derived.source_evidence_ids
            ):
                errors.append(
                    f"Post-precheck item {item.review_item_id} has invalid derived evidence."
                )
                continue
            result_lineage = tuple(
                evidence_by_id.get(source_id)
                for source_id in derived.source_evidence_ids
                if (
                    evidence_by_id.get(source_id) is not None
                    and evidence_by_id[source_id].sheet
                    == "BANKING_PRECHECK_RESULT_SET"
                    and evidence_by_id[source_id].record_id
                    == item.normalized_result_id
                    and evidence_by_id[source_id].field == "normalized_result"
                )
            )
            if len(result_lineage) != 1:
                errors.append(
                    f"Post-precheck item {item.review_item_id} lacks exact result lineage."
                )
            expected_evidence_id = decision_post_precheck_evidence_id(
                dataset_id=review.dataset_id,
                review_item_id=item.review_item_id,
                display=display,
                source_evidence_ids=derived.source_evidence_ids,
            )
            if derived.evidence_id != expected_evidence_id:
                errors.append(
                    f"Post-precheck item {item.review_item_id} has unstable evidence."
                )
            derived_by_result[item.normalized_result_id] = derived
        for request in review.missing_data_requests:
            option = next(
                (
                    item
                    for item in review.option_reviews
                    if item.normalized_result_id == request.target_record
                ),
                None,
            )
            if option is None:
                errors.append(
                    "DECISION_POST_PRECHECK_REVIEW missing request targets an "
                    "unknown result."
                )
                continue
            expected_request_id = deterministic_id(
                "MDR",
                review.evaluation_case_id,
                review.result_set_id,
                option.normalized_result_id,
                option.option_id,
                option.bank_product_id,
                request.field,
            )
            if request.request_id != expected_request_id:
                errors.append(
                    "DECISION_POST_PRECHECK_REVIEW has an unstable missing request ID."
                )
            expected_evidence = derived_by_result.get(option.normalized_result_id)
            if expected_evidence is None or request.evidence_refs != (
                expected_evidence,
            ):
                errors.append(
                    "DECISION_POST_PRECHECK_REVIEW missing request has altered evidence."
                )
            if request.requirement_code != (
                "BANKING_PRECHECK_FOLLOW_UP_EVIDENCE_REQUIRED"
            ):
                errors.append(
                    "DECISION_POST_PRECHECK_REVIEW missing request code is invalid."
                )
            expected_reason = (
                "The non-binding precheck result explicitly identifies "
                f"{request.field} as missing for option {option.option_id}."
            )
            if request.reason != expected_reason:
                errors.append(
                    "DECISION_POST_PRECHECK_REVIEW missing request reason is invalid."
                )
        expected_review_id = decision_post_precheck_review_id(
            result_set_artifact_id=review.result_set_artifact_id,
            result_set_id=review.result_set_id,
            proposal_artifact_id=review.proposal_artifact_id,
            item_ids=tuple(
                item.review_item_id for item in review.option_reviews
            ),
            outcome=review.outcome,
            missing_request_ids=tuple(
                item.request_id for item in review.missing_data_requests
            ),
        )
        if review.review_id != expected_review_id:
            errors.append("DECISION_POST_PRECHECK_REVIEW has an unstable review ID.")
        forbidden = {
            "action_command",
            "approval_decision",
            "approval_request",
            "bank_approved",
            "decision_card",
            "document_package",
            "external_request",
            "final_decision",
            "ranked_option_ids",
            "recommended_option",
            "recommended_option_ids",
            "selected_bank",
            "selected_option",
            "selected_option_id",
            "selected_option_ids",
        }
        present = EvidenceValidator._recursive_keys(draft.payload)
        if forbidden & present:
            errors.append(
                "DECISION_POST_PRECHECK_REVIEW contains out-of-bound fields: "
                + ", ".join(sorted(forbidden & present))
            )
        if not errors:
            checks.append("DECISION_POST_PRECHECK_REVIEW_BOUNDARY_VALID")

    @staticmethod
    def _validated_precheck_simulation_policy(
        *,
        result_set: BankingPrecheckResultSet,
        simulation_policy: BankingPrecheckSimulationPolicy | None,
        errors: list[str],
    ) -> BankingPrecheckSimulationPolicy | None:
        """Require the exact server-owned policy before accepting provider claims."""
        if simulation_policy is None:
            errors.append(
                "BANKING_PRECHECK_RESULT_SET requires the server simulation policy."
            )
            return None
        policy_document = simulation_policy.model_dump(
            mode="json",
            exclude={"configuration_hash"},
        )
        encoded = json.dumps(
            policy_document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        expected_configuration_hash = sha256(encoded).hexdigest()
        if simulation_policy.configuration_hash != expected_configuration_hash:
            errors.append("Banking precheck simulation policy hash is not canonical.")
        if result_set.adapter_config_hash != simulation_policy.configuration_hash:
            errors.append(
                "BANKING_PRECHECK_RESULT_SET adapter config does not match server policy."
            )
        return simulation_policy

    @staticmethod
    def _validate_precheck_approval_evidence(
        *,
        result_set: BankingPrecheckResultSet,
        evidence: EvidenceRef,
        errors: list[str],
    ) -> None:
        """Validate the complete permit display and its deterministic evidence ID."""
        display = evidence.display_value
        required_keys = {
            "permit_id",
            "approval_request_id",
            "protected_action",
            "subject_artifact_id",
            "subject_artifact_version",
            "subject_input_hash",
            "authorized_by",
            "authorized_at",
        }
        if not isinstance(display, dict) or set(display) != required_keys:
            errors.append(
                "BANKING_PRECHECK_RESULT_SET approval evidence has an invalid display."
            )
            return
        exact_values = (
            display["permit_id"] == result_set.permit_id
            and display["approval_request_id"] == result_set.approval_request_id
            and display["protected_action"]
            == ProtectedAction.SUBMIT_BANKING_PRECHECK.value
            and display["subject_artifact_id"]
            == result_set.proposal_artifact_id
            and isinstance(display["subject_artifact_version"], int)
            and not isinstance(display["subject_artifact_version"], bool)
            and display["subject_artifact_version"] >= 1
            and isinstance(display["subject_input_hash"], str)
            and bool(display["subject_input_hash"])
            and isinstance(display["authorized_by"], str)
            and bool(display["authorized_by"])
            and isinstance(display["authorized_at"], str)
            and bool(display["authorized_at"])
        )
        if not exact_values:
            errors.append(
                "BANKING_PRECHECK_RESULT_SET approval lineage does not match its permit."
            )
            return
        try:
            authorized_at = datetime.fromisoformat(display["authorized_at"])
        except ValueError:
            authorized_at = None
        if (
            authorized_at is None
            or authorized_at.tzinfo is None
            or authorized_at.isoformat() != display["authorized_at"]
        ):
            errors.append(
                "BANKING_PRECHECK_RESULT_SET approval timestamp is not canonical."
            )
        expected_evidence_id = deterministic_id(
            "EVD",
            result_set.dataset_id,
            SourceType.USER_INPUT,
            "APPROVAL_AUTHORIZATION",
            result_set.approval_request_id,
            display,
        )
        if (
            evidence.evidence_id != expected_evidence_id
            or evidence.source_evidence_ids
        ):
            errors.append(
                "BANKING_PRECHECK_RESULT_SET approval evidence identity is invalid."
            )

    @staticmethod
    def _validate_precheck_policy_evidence(
        *,
        result_set: BankingPrecheckResultSet,
        result: BankingPrecheckNormalizedResult,
        evidence_by_id: dict[str, EvidenceRef],
        simulation_policy: BankingPrecheckSimulationPolicy | None,
        errors: list[str],
    ) -> EvidenceRef | None:
        """Bind one normalized result to one exact server policy scenario."""
        policy_items = tuple(
            evidence_by_id[evidence_id]
            for evidence_id in result.evidence_ids
            if evidence_id in evidence_by_id
            and evidence_by_id[evidence_id].source_type is SourceType.POLICY_CONFIG
            and evidence_by_id[evidence_id].sheet
            == "BANKING_PRECHECK_SIMULATION_POLICY"
            and evidence_by_id[evidence_id].record_id == result.scenario_id
            and evidence_by_id[evidence_id].field == "scenario"
        )
        if len(policy_items) != 1:
            errors.append(
                f"Banking result {result.normalized_result_id} lacks exact scenario lineage."
            )
            return None
        policy_item = policy_items[0]
        if simulation_policy is None:
            return policy_item
        scenario = next(
            (
                item
                for item in simulation_policy.scenarios
                if item.api_id == result.api_id
                and item.api_provider == result.api_provider
            ),
            None,
        )
        expected = EvidenceValidator._expected_precheck_scenario(
            result=result,
            policy=simulation_policy,
            scenario=scenario,
        )
        expected_display = {
            "adapter_id": result_set.adapter_id,
            "adapter_config_hash": result_set.adapter_config_hash,
            "api_id": result.api_id,
            "api_provider": result.api_provider,
            "provider_reference": expected["provider_reference"],
            "scenario_id": expected["scenario_id"],
            "scenario_version": simulation_policy.configuration_version,
            "scenario_hash": expected["scenario_hash"],
            "outcome": expected["outcome"].value,
            "message": expected["message"],
            "reason_codes": list(expected["reason_codes"]),
            "required_follow_up_fields": list(
                expected["required_follow_up_fields"]
            ),
            "requested_amount": result.requested_amount,
            "supported_amount": expected["supported_amount"],
            "currency": expected["currency"].value,
            "eligibility_status": expected["eligibility_status"].value,
            "guarantee_decision": expected["guarantee_decision"].value,
            "required_documents": list(expected["required_documents"]),
            "approval_conditions": list(expected["approval_conditions"]),
            "authority": BankingPrecheckResultAuthority.SIMULATED_NON_BINDING.value,
            "non_binding": True,
        }
        expected_evidence_id = deterministic_id(
            "EVD",
            result_set.dataset_id,
            SourceType.POLICY_CONFIG,
            "BANKING_PRECHECK_SIMULATION_POLICY",
            expected["scenario_id"],
            expected_display,
        )
        if (
            policy_item.display_value != expected_display
            or policy_item.evidence_id != expected_evidence_id
            or policy_item.source_evidence_ids
        ):
            errors.append(
                f"Banking result {result.normalized_result_id} scenario evidence is stale."
            )
        return policy_item

    @staticmethod
    def _expected_precheck_scenario(
        *,
        result: BankingPrecheckNormalizedResult,
        policy: BankingPrecheckSimulationPolicy,
        scenario: BankingPrecheckSimulationScenario | None,
    ) -> dict[str, object]:
        if scenario is None:
            scenario_id = _UNCONFIGURED_SCENARIO_ID
            scenario_hash = deterministic_id(
                "BPSCNH",
                policy.configuration_hash,
                scenario_id,
                result.api_id,
                result.api_provider,
            )
            outcome = BankingPrecheckOutcome.SERVICE_UNAVAILABLE
            message = _UNCONFIGURED_MESSAGE
            reason_codes = _UNCONFIGURED_REASON_CODES
            required_follow_up_fields: tuple[str, ...] = ()
            supported_amount = None
            currency = result.currency
            eligibility_status = ProviderEligibilityStatus.NOT_EVALUABLE
            guarantee_decision = ProviderGuaranteeDecision.NO_DECISION
            required_documents: tuple[str, ...] = ()
            approval_conditions: tuple[str, ...] = ()
        else:
            scenario_id = scenario.scenario_id
            scenario_hash = deterministic_id(
                "BPSCNH",
                policy.configuration_hash,
                scenario.model_dump(mode="json"),
            )
            outcome = scenario.outcome
            message = scenario.message
            reason_codes = tuple(scenario.reason_codes)
            required_follow_up_fields = tuple(
                scenario.required_follow_up_fields
            )
            supported_amount = (
                result.requested_amount
                if scenario.supported_amount_strategy
                is BankingPrecheckSupportedAmountStrategy.ECHO_REQUESTED_AMOUNT
                else None
            )
            currency = scenario.currency
            eligibility_status = scenario.eligibility_status
            guarantee_decision = scenario.guarantee_decision
            required_documents = tuple(scenario.required_documents)
            approval_conditions = tuple(scenario.approval_conditions)
        provider_reference = deterministic_id(
            "SIMREF",
            policy.configuration_hash,
            scenario_id,
            result.request_hash,
        )
        return {
            "scenario_id": scenario_id,
            "scenario_hash": scenario_hash,
            "provider_reference": provider_reference,
            "outcome": outcome,
            "message": message,
            "reason_codes": reason_codes,
            "required_follow_up_fields": required_follow_up_fields,
            "supported_amount": supported_amount,
            "currency": currency,
            "eligibility_status": eligibility_status,
            "guarantee_decision": guarantee_decision,
            "required_documents": required_documents,
            "approval_conditions": approval_conditions,
        }

    @staticmethod
    def _validate_precheck_result_identity(
        *,
        result_set: BankingPrecheckResultSet,
        result: BankingPrecheckNormalizedResult,
        evidence_by_id: dict[str, EvidenceRef],
        simulation_policy: BankingPrecheckSimulationPolicy | None,
        errors: list[str],
    ) -> None:
        inputs = EvidenceValidator._precheck_request_evidence_inputs(
            result_set=result_set,
            result=result,
            evidence_by_id=evidence_by_id,
            errors=errors,
        )
        if inputs is not None:
            api_method, api_endpoint, requested_amount, company_profile = inputs
            expected_request_hash = banking_precheck_request_hash(
                dataset_id=result_set.dataset_id,
                evaluation_case_id=result_set.evaluation_case_id,
                contract_id=result_set.contract_id,
                proposal_artifact_id=result_set.proposal_artifact_id,
                proposal_id=result_set.proposal_id,
                proposal_item_id=result.proposal_item_id,
                option_id=result.option_id,
                bank_product_id=result.bank_product_id,
                api_id=result.api_id,
                api_provider=result.api_provider,
                api_method=api_method,
                api_endpoint=api_endpoint,
                requested_amount=requested_amount,
                requested_amount_currency=CurrencyCode.VND,
                company_profile=company_profile,
            )
            if result.request_hash != expected_request_hash:
                errors.append(
                    f"Banking result {result.normalized_result_id} has an invalid request hash."
                )
        else:
            expected_request_hash = result.request_hash
        expected_request_id = deterministic_id(
            "BPRQ",
            result_set.proposal_artifact_id,
            result.proposal_item_id,
            expected_request_hash,
        )
        expected_idempotency_key = banking_precheck_idempotency_key(
            permit_id=result_set.permit_id,
            proposal_artifact_id=result_set.proposal_artifact_id,
            proposal_item_id=result.proposal_item_id,
            request_hash=expected_request_hash,
        )
        if result.request_id != expected_request_id:
            errors.append(
                f"Banking result {result.normalized_result_id} has an invalid request ID."
            )
        if result.idempotency_key != expected_idempotency_key:
            errors.append(
                f"Banking result {result.normalized_result_id} has invalid idempotency."
            )
        expected_response_hash = banking_precheck_response_hash(
            request_id=result.request_id,
            idempotency_key=result.idempotency_key,
            api_id=result.api_id,
            api_provider=result.api_provider,
            execution_mode=result.execution_mode,
            provider_reference=result.provider_reference,
            scenario_id=result.scenario_id,
            scenario_version=result.scenario_version,
            scenario_hash=result.scenario_hash,
            outcome=result.outcome,
            message=result.message,
            reason_codes=result.reason_codes,
            required_follow_up_fields=result.required_follow_up_fields,
            requested_amount=result.requested_amount,
            supported_amount=result.supported_amount,
            currency=result.currency,
            eligibility_status=result.eligibility_status,
            guarantee_decision=result.guarantee_decision,
            required_documents=result.required_documents,
            approval_conditions=result.approval_conditions,
            authority=result.authority,
            non_binding=result.non_binding,
        )
        if result.response_hash != expected_response_hash:
            errors.append(
                f"Banking result {result.normalized_result_id} has an invalid response hash."
            )
        expected_normalized_id = deterministic_id(
            "BPNR",
            result_set.proposal_artifact_id,
            result.proposal_item_id,
            result.request_id,
            result.request_hash,
            result.response_hash,
        )
        if result.normalized_result_id != expected_normalized_id:
            errors.append("Banking normalized result ID is not stable.")
        if simulation_policy is not None:
            scenario = next(
                (
                    item
                    for item in simulation_policy.scenarios
                    if item.api_id == result.api_id
                    and item.api_provider == result.api_provider
                ),
                None,
            )
            expected = EvidenceValidator._expected_precheck_scenario(
                result=result,
                policy=simulation_policy,
                scenario=scenario,
            )
            scenario_identity = (
                result.scenario_id,
                result.scenario_version,
                result.scenario_hash,
                result.outcome,
                result.message,
                result.reason_codes,
                result.required_follow_up_fields,
                result.supported_amount,
                result.currency,
                result.eligibility_status,
                result.guarantee_decision,
                result.required_documents,
                result.approval_conditions,
                result.provider_reference,
            )
            expected_scenario_identity = (
                expected["scenario_id"],
                simulation_policy.configuration_version,
                expected["scenario_hash"],
                expected["outcome"],
                expected["message"],
                expected["reason_codes"],
                expected["required_follow_up_fields"],
                expected["supported_amount"],
                expected["currency"],
                expected["eligibility_status"],
                expected["guarantee_decision"],
                expected["required_documents"],
                expected["approval_conditions"],
                expected["provider_reference"],
            )
            if scenario_identity != expected_scenario_identity:
                errors.append(
                    f"Banking result {result.normalized_result_id} does not match "
                    "the server simulation scenario."
                )

    @staticmethod
    def _precheck_request_evidence_inputs(
        *,
        result_set: BankingPrecheckResultSet,
        result: BankingPrecheckNormalizedResult,
        evidence_by_id: dict[str, EvidenceRef],
        errors: list[str],
    ) -> tuple[
        str,
        str,
        int,
        tuple[BankingCompanyProfileField, ...],
    ] | None:
        result_evidence = tuple(
            evidence_by_id[evidence_id]
            for evidence_id in result.evidence_ids
            if evidence_id in evidence_by_id
        )
        api_values: dict[str, str] = {}
        for field in ("provider", "method", "endpoint"):
            matches = tuple(
                item
                for item in result_evidence
                if item.source_type in {SourceType.TEAM_PACK, SourceType.USER_INPUT}
                and item.sheet == SheetRegistry.API_CATALOG.sheet_name
                and item.record_id == result.api_id
                and item.field == field
                and isinstance(item.display_value, str)
                and bool(item.display_value)
            )
            if len(matches) != 1:
                errors.append(
                    f"Banking result {result.normalized_result_id} lacks exact API "
                    f"{field} evidence."
                )
            else:
                api_values[field] = matches[0].display_value
        if api_values.get("provider") != result.api_provider:
            errors.append(
                f"Banking result {result.normalized_result_id} API provider is not evidence-bound."
            )

        contract_binding = EvidenceValidator._one_precheck_binding_evidence(
            result=result,
            result_evidence=result_evidence,
            required_field="contract_id",
            source=BankingPrecheckFieldSource.EVALUATION_CASE,
            source_reference="EvaluationCase.contract_id",
            errors=errors,
        )
        uses_discovery_request_amount = any(
            evidence.source_type is SourceType.DERIVED
            and evidence.sheet == "BANKING_PRECHECK_READINESS"
            and evidence.field == "amount"
            and isinstance(evidence.display_value, dict)
            and evidence.display_value.get("source")
            == BankingPrecheckFieldSource.BANKING_DISCOVERY_REQUEST.value
            for evidence in result_evidence
        )
        amount_source = (
            BankingPrecheckFieldSource.BANKING_DISCOVERY_REQUEST
            if uses_discovery_request_amount
            else BankingPrecheckFieldSource.BANKING_INPUT_SUPPLEMENT
        )
        amount_source_reference = (
            "BankingDiscoveryRequest.requested_amount"
            if uses_discovery_request_amount
            else "BankingInputSupplement.requested_amount"
        )
        amount_binding = EvidenceValidator._one_precheck_binding_evidence(
            result=result,
            result_evidence=result_evidence,
            required_field="amount",
            source=amount_source,
            source_reference=amount_source_reference,
            errors=errors,
        )
        profile_binding = EvidenceValidator._one_precheck_binding_evidence(
            result=result,
            result_evidence=result_evidence,
            required_field="company_profile",
            source=BankingPrecheckFieldSource.OPC_PROFILE,
            source_reference="02_OPC_PROFILE[field,value]",
            errors=errors,
        )
        contract_is_bound = False
        if contract_binding is not None:
            contract_sources = tuple(
                evidence_by_id[evidence_id]
                for evidence_id in contract_binding.source_evidence_ids
                if evidence_id in evidence_by_id
                and (
                    (
                        evidence_by_id[evidence_id].source_type
                        is SourceType.TEAM_PACK
                        and evidence_by_id[evidence_id].sheet
                        == SheetRegistry.CONTRACTS.sheet_name
                    )
                    or (
                        evidence_by_id[evidence_id].source_type
                        is SourceType.DERIVED
                        and evidence_by_id[evidence_id].sheet
                        == "EVALUATION_CASE"
                    )
                )
                and evidence_by_id[evidence_id].field == "contract_id"
                and evidence_by_id[evidence_id].record_id
                == result_set.contract_id
                and evidence_by_id[evidence_id].display_value
                == result_set.contract_id
            )
            contract_is_bound = len(contract_sources) == 1
            if not contract_is_bound:
                errors.append(
                    f"Banking result {result.normalized_result_id} contract is not "
                    "evidence-bound."
                )
        requested_amount: int | None = None
        if amount_binding is not None:
            amount_sources = tuple(
                evidence_by_id[evidence_id]
                for evidence_id in amount_binding.source_evidence_ids
                if evidence_id in evidence_by_id
                and (
                    (
                        uses_discovery_request_amount
                        and evidence_by_id[evidence_id].source_type
                        is SourceType.TEAM_PACK
                        and evidence_by_id[evidence_id].sheet
                        == SheetRegistry.CREDIT_PROFILES.sheet_name
                    )
                    or (
                        not uses_discovery_request_amount
                        and evidence_by_id[evidence_id].source_type
                        is SourceType.USER_INPUT
                        and evidence_by_id[evidence_id].sheet
                        == "BANKING_INPUT_SUPPLEMENT"
                    )
                )
                and evidence_by_id[evidence_id].field == "requested_amount"
                and isinstance(evidence_by_id[evidence_id].display_value, int)
                and not isinstance(evidence_by_id[evidence_id].display_value, bool)
            )
            if len(amount_sources) != 1 or amount_sources[0].display_value <= 0:
                errors.append(
                    f"Banking result {result.normalized_result_id} lacks one exact amount."
                )
            else:
                requested_amount = amount_sources[0].display_value
                legacy_currency_is_valid = True
                if not uses_discovery_request_amount:
                    currency_sources = tuple(
                        evidence_by_id[evidence_id]
                        for evidence_id in amount_binding.source_evidence_ids
                        if evidence_id in evidence_by_id
                        and evidence_by_id[evidence_id].source_type
                        is SourceType.USER_INPUT
                        and evidence_by_id[evidence_id].sheet
                        == "BANKING_INPUT_SUPPLEMENT"
                        and evidence_by_id[evidence_id].record_id
                        == amount_sources[0].record_id
                        and evidence_by_id[evidence_id].field
                        == "requested_amount_currency"
                    )
                    legacy_currency_is_valid = (
                        len(currency_sources) == 1
                        and currency_sources[0].display_value
                        == CurrencyCode.VND.value
                    )
                if (
                    result.currency is not CurrencyCode.VND
                    or not legacy_currency_is_valid
                ):
                    errors.append(
                        f"Banking result {result.normalized_result_id} amount is not VND."
                    )
        company_profile = EvidenceValidator._precheck_company_profile(
            result=result,
            binding=profile_binding,
            evidence_by_id=evidence_by_id,
            errors=errors,
        )
        if (
            set(api_values) != {"provider", "method", "endpoint"}
            or not contract_is_bound
            or requested_amount is None
            or company_profile is None
        ):
            return None
        return (
            api_values["method"],
            api_values["endpoint"],
            requested_amount,
            company_profile,
        )

    @staticmethod
    def _one_precheck_binding_evidence(
        *,
        result: BankingPrecheckNormalizedResult,
        result_evidence: tuple[EvidenceRef, ...],
        required_field: str,
        source: BankingPrecheckFieldSource,
        source_reference: str,
        errors: list[str],
    ) -> EvidenceRef | None:
        expected_display = {
            "status": BankingPrecheckFieldStatus.RESOLVED.value,
            "source": source.value,
            "source_reference": source_reference,
        }
        matches = tuple(
            item
            for item in result_evidence
            if item.source_type is SourceType.DERIVED
            and item.sheet == "BANKING_PRECHECK_READINESS"
            and item.field == required_field
            and item.display_value == expected_display
        )
        if len(matches) != 1:
            errors.append(
                f"Banking result {result.normalized_result_id} lacks exact "
                f"{required_field} binding evidence."
            )
            return None
        return matches[0]

    @staticmethod
    def _precheck_company_profile(
        *,
        result: BankingPrecheckNormalizedResult,
        binding: EvidenceRef | None,
        evidence_by_id: dict[str, EvidenceRef],
        errors: list[str],
    ) -> tuple[BankingCompanyProfileField, ...] | None:
        if binding is None:
            return None
        source_positions = {
            evidence_id: position
            for position, evidence_id in enumerate(binding.source_evidence_ids)
        }
        field_items = tuple(
            item
            for evidence_id in binding.source_evidence_ids
            if (item := evidence_by_id.get(evidence_id)) is not None
            and item.source_type in {SourceType.TEAM_PACK, SourceType.USER_INPUT}
            and item.sheet == SheetRegistry.OPC_PROFILE.sheet_name
            and item.field == "field"
        )
        if not field_items or len({item.record_id for item in field_items}) != len(
            field_items
        ):
            errors.append(
                f"Banking result {result.normalized_result_id} has ambiguous OPC profile lineage."
            )
            return None
        ordered_fields = sorted(
            field_items,
            key=lambda item: (
                item.row_number,
                source_positions[item.evidence_id],
            ),
        )
        profile: list[BankingCompanyProfileField] = []
        for field_item in ordered_fields:
            value_items = tuple(
                item
                for evidence_id in binding.source_evidence_ids
                if (item := evidence_by_id.get(evidence_id)) is not None
                and item.source_type in {SourceType.TEAM_PACK, SourceType.USER_INPUT}
                and item.sheet == SheetRegistry.OPC_PROFILE.sheet_name
                and item.record_id == field_item.record_id
                and item.field == "value"
            )
            if field_item.display_value != field_item.record_id or len(value_items) != 1:
                errors.append(
                    f"Banking result {result.normalized_result_id} has incomplete "
                    "OPC profile lineage."
                )
                return None
            try:
                profile.append(
                    BankingCompanyProfileField(
                        field=field_item.record_id,
                        value=value_items[0].display_value,
                    )
                )
            except ValueError:
                errors.append(
                    f"Banking result {result.normalized_result_id} has a non-scalar "
                    "OPC profile value."
                )
                return None
        return tuple(profile)

    @staticmethod
    def _validate_precheck_derived_evidence(
        *,
        result_set: BankingPrecheckResultSet,
        result: BankingPrecheckNormalizedResult,
        evidence_by_id: dict[str, EvidenceRef],
        approval_evidence: EvidenceRef | None,
        policy_evidence: EvidenceRef | None,
        errors: list[str],
    ) -> None:
        derived_items = tuple(
            evidence_by_id[evidence_id]
            for evidence_id in result.evidence_ids
            if evidence_id in evidence_by_id
            and evidence_by_id[evidence_id].source_type is SourceType.DERIVED
            and evidence_by_id[evidence_id].sheet == "BANKING_PRECHECK_RESULT_SET"
            and evidence_by_id[evidence_id].record_id
            == result.normalized_result_id
            and evidence_by_id[evidence_id].field == "normalized_result"
        )
        if len(derived_items) != 1:
            errors.append(
                f"Banking result {result.normalized_result_id} lacks normalized lineage."
            )
            return
        derived = derived_items[0]
        expected_display = {
            "option_id": result.option_id,
            "outcome": result.outcome.value,
            "eligibility_status": result.eligibility_status.value,
            "guarantee_decision": result.guarantee_decision.value,
            "requested_amount": result.requested_amount,
            "supported_amount": result.supported_amount,
            "currency": result.currency.value,
            "required_documents": list(result.required_documents),
            "approval_conditions": list(result.approval_conditions),
            "execution_mode": result.execution_mode.value,
            "authority": result.authority.value,
            "non_binding": True,
        }
        expected_sources = tuple(
            evidence_id
            for evidence_id in result.evidence_ids
            if evidence_id != derived.evidence_id
        )
        expected_evidence_id = deterministic_id(
            "EVD",
            result_set.dataset_id,
            SourceType.DERIVED,
            "BANKING_PRECHECK_RESULT_SET",
            result.normalized_result_id,
            expected_display,
            expected_sources,
        )
        if (
            result.evidence_ids[-1] != derived.evidence_id
            or derived.display_value != expected_display
            or derived.source_evidence_ids != expected_sources
            or derived.evidence_id != expected_evidence_id
        ):
            errors.append(
                f"Banking result {result.normalized_result_id} normalized lineage is invalid."
            )
        if (
            approval_evidence is not None
            and approval_evidence.evidence_id not in expected_sources
        ) or (
            policy_evidence is not None
            and policy_evidence.evidence_id not in expected_sources
        ):
            errors.append(
                f"Banking result {result.normalized_result_id} derived lineage is incomplete."
            )

    @staticmethod
    def _validate_document_preparation_request(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate a non-selective Decision handoff from exact provider artifacts."""
        try:
            request = DocumentPreparationRequest.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid DOCUMENT_PREPARATION_REQUEST schema: {exc}")
            return
        if request.evaluation_case_id != draft.evaluation_case_id:
            errors.append(
                "DOCUMENT_PREPARATION_REQUEST case identity does not match its draft."
            )
        if not set(request.evidence_ids).issubset(evidence_ids):
            errors.append(
                "DOCUMENT_PREPARATION_REQUEST references unknown evidence."
            )
        expected_identity = {
            "source_artifact_ids": request.source_artifact_ids,
            "normalized_result_id": request.normalized_result_id,
            "review_item_id": request.review_item_id,
            "option_id": request.option_id,
            "required_document_codes": request.required_document_codes,
            "approval_condition_codes": request.approval_condition_codes,
        }
        if draft.identity_inputs != expected_identity:
            errors.append(
                "DOCUMENT_PREPARATION_REQUEST artifact identity inputs are not exact."
            )
        expected_request_id = document_preparation_request_id(
            result_set_artifact_id=request.source_artifact_ids[1],
            review_artifact_id=request.source_artifact_ids[0],
            normalized_result_id=request.normalized_result_id,
            review_item_id=request.review_item_id,
            option_id=request.option_id,
            required_document_codes=request.required_document_codes,
            approval_condition_codes=request.approval_condition_codes,
        )
        if request.request_id != expected_request_id:
            errors.append("DOCUMENT_PREPARATION_REQUEST has an unstable request_id.")
        derived = tuple(
            item
            for item in draft.evidence_refs
            if item.source_type is SourceType.DERIVED
            and item.sheet == "DOCUMENT_PREPARATION_REQUEST"
            and item.record_id == request.request_id
            and item.field == "provider_document_handoff"
        )
        expected_display = {
            "request_id": request.request_id,
            "normalized_result_id": request.normalized_result_id,
            "review_item_id": request.review_item_id,
            "option_id": request.option_id,
            "contract_id": request.contract_id,
            "bank_product_id": request.bank_product_id,
            "requested_amount": request.requested_amount,
            "currency": request.currency.value,
            "request_type": "PERFORMANCE_BOND",
            "required_document_codes": [
                item.value for item in request.required_document_codes
            ],
            "approval_condition_codes": list(request.approval_condition_codes),
            "non_binding": True,
        }
        if len(derived) != 1:
            errors.append(
                "DOCUMENT_PREPARATION_REQUEST requires one derived handoff evidence item."
            )
        else:
            item = derived[0]
            expected_evidence_id = deterministic_id(
                "EVD",
                request.dataset_id,
                SourceType.DERIVED,
                "DOCUMENT_PREPARATION_REQUEST",
                request.request_id,
                expected_display,
                item.source_evidence_ids,
            )
            if (
                request.evidence_ids != (item.evidence_id,)
                or item.display_value != expected_display
                or not item.source_evidence_ids
                or not set(item.source_evidence_ids).issubset(evidence_ids)
                or item.evidence_id != expected_evidence_id
            ):
                errors.append(
                    "DOCUMENT_PREPARATION_REQUEST handoff evidence is invalid."
                )
        if not errors:
            checks.append("DOCUMENT_PREPARATION_REQUEST_BOUNDARY_VALID")

    @staticmethod
    def _validate_document_checklist(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate exact provider requirements and blocking-document classification."""
        try:
            checklist = DocumentChecklist.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid DOCUMENT_CHECKLIST schema: {exc}")
            return
        if checklist.evaluation_case_id != draft.evaluation_case_id:
            errors.append("DOCUMENT_CHECKLIST case identity does not match its draft.")
        if checklist.evidence_ids != tuple(
            item.evidence_id for item in draft.evidence_refs
        ) or set(checklist.evidence_ids) != evidence_ids:
            errors.append("DOCUMENT_CHECKLIST evidence index is not exact.")
        if len(checklist.source_artifact_ids) < 2:
            errors.append(
                "DOCUMENT_CHECKLIST requires EvaluationCase and preparation-request lineage."
            )
            return
        expected_identity = {
            "preparation_request_id": checklist.preparation_request_id,
            "source_artifact_ids": checklist.source_artifact_ids,
            "item_ids": tuple(item.item_id for item in checklist.items),
            "missing_document_codes": checklist.missing_document_codes,
            "approval_condition_codes": checklist.approval_condition_codes,
            "limitation_codes": checklist.limitation_codes,
        }
        if draft.identity_inputs != expected_identity:
            errors.append("DOCUMENT_CHECKLIST artifact identity inputs are not exact.")
        expected_checklist_id = document_checklist_id(
            request_artifact_id=checklist.source_artifact_ids[1],
            request_id=checklist.preparation_request_id,
            item_ids=tuple(item.item_id for item in checklist.items),
        )
        if checklist.checklist_id != expected_checklist_id:
            errors.append("DOCUMENT_CHECKLIST has an unstable checklist_id.")
        evidence_by_id = {item.evidence_id: item for item in draft.evidence_refs}
        for item in checklist.items:
            expected_missing_id = (
                deterministic_id(
                    "MDR",
                    checklist.evaluation_case_id,
                    "DOCUMENT_SKILL",
                    checklist.preparation_request_id,
                    item.document_code,
                )
                if item.status.value == "MISSING"
                else None
            )
            expected_item_id = deterministic_id(
                "DCI",
                checklist.source_artifact_ids[1],
                checklist.preparation_request_id,
                item.document_code,
                item.status,
                item.source_reference_ids,
                item.limitation_codes,
                expected_missing_id,
            )
            if (
                item.item_id != expected_item_id
                or item.missing_request_id != expected_missing_id
                or not set(item.evidence_ids).issubset(evidence_ids)
            ):
                errors.append(
                    f"Document checklist item {item.document_code.value} has unstable identity."
                )
            derived = tuple(
                evidence_by_id[evidence_id]
                for evidence_id in item.evidence_ids
                if evidence_id in evidence_by_id
                and evidence_by_id[evidence_id].source_type is SourceType.DERIVED
                and evidence_by_id[evidence_id].sheet == "DOCUMENT_CHECKLIST"
                and evidence_by_id[evidence_id].record_id == item.item_id
                and evidence_by_id[evidence_id].field == item.document_code.value
            )
            expected_display = {
                "document_code": item.document_code.value,
                "status": item.status.value,
                "limitation_codes": list(item.limitation_codes),
                "missing_request_id": item.missing_request_id,
            }
            if (
                len(derived) != 1
                or derived[0].display_value != expected_display
                or not set(derived[0].source_evidence_ids).issubset(evidence_ids)
            ):
                errors.append(
                    f"Document checklist item {item.document_code.value} lacks exact lineage."
                )
        if not errors:
            checks.append("DOCUMENT_CHECKLIST_BOUNDARY_VALID")

    @staticmethod
    def _validate_document_package_draft(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
        masking_policy: MaskingPolicyDocument | None,
        masking_service: MaskingService | None,
    ) -> None:
        """Validate a masked internal package and its exact blocking state."""
        try:
            package = DocumentPackageDraft.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid DOCUMENT_PACKAGE_DRAFT schema: {exc}")
            return
        EvidenceValidator._validate_document_package_common(
            draft=draft,
            package=package,
            evidence_ids=evidence_ids,
            masking_policy=masking_policy,
            masking_service=masking_service,
            errors=errors,
        )
        if len(package.source_artifact_ids) < 2:
            errors.append(
                "DOCUMENT_PACKAGE_DRAFT requires EvaluationCase and request lineage."
            )
            return
        expected_id = document_package_draft_id(
            request_artifact_id=package.source_artifact_ids[1],
            request_id=package.preparation_request_id,
            checklist_id=package.checklist_id,
            supplement_artifact_ids=package.source_artifact_ids[2:],
            classification_decision_ids=package.classification_decision_ids,
            masking_manifest_id=package.masking_manifest_id,
        )
        if package.package_draft_id != expected_id:
            errors.append("DOCUMENT_PACKAGE_DRAFT has an unstable package_draft_id.")
        expected_identity = {
            "preparation_request_id": package.preparation_request_id,
            "checklist_id": package.checklist_id,
            "source_artifact_ids": package.source_artifact_ids,
            "readiness": package.readiness,
            "approval_condition_codes": package.approval_condition_codes,
            "limitation_codes": package.limitation_codes,
            "classification_decision_ids": package.classification_decision_ids,
            "masking_manifest_id": package.masking_manifest_id,
        }
        if draft.identity_inputs != expected_identity:
            errors.append(
                "DOCUMENT_PACKAGE_DRAFT artifact identity inputs are not exact."
            )
        for missing in package.missing_data_requests:
            expected_request_id = deterministic_id(
                "MDR",
                package.evaluation_case_id,
                "DOCUMENT_SKILL",
                package.preparation_request_id,
                missing.field,
            )
            if (
                missing.request_id != expected_request_id
                or missing.raised_by != "DOCUMENT_SKILL"
                or missing.target_record != package.preparation_request_id
                or not set(
                    item.evidence_id for item in missing.evidence_refs
                ).issubset(evidence_ids)
            ):
                errors.append(
                    f"Document missing-data request {missing.request_id} is invalid."
                )
        if not errors:
            checks.append("DOCUMENT_PACKAGE_DRAFT_BOUNDARY_VALID")

    @staticmethod
    def _validate_document_release_package(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
        masking_policy: MaskingPolicyDocument | None,
        masking_service: MaskingService | None,
    ) -> None:
        """Validate a complete package that still carries no release authority."""
        try:
            package = DocumentReleasePackage.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid DOCUMENT_RELEASE_PACKAGE schema: {exc}")
            return
        EvidenceValidator._validate_document_package_common(
            draft=draft,
            package=package,
            evidence_ids=evidence_ids,
            masking_policy=masking_policy,
            masking_service=masking_service,
            errors=errors,
        )
        expected_release_id = deterministic_id(
            "DRP",
            package.package_draft_id,
            package.preparation_request_id,
            package.checklist_id,
            package.masking_manifest_id,
        )
        if package.release_package_id != expected_release_id:
            errors.append("DOCUMENT_RELEASE_PACKAGE has an unstable release_package_id.")
        expected_identity = {
            "package_draft_id": package.package_draft_id,
            "preparation_request_id": package.preparation_request_id,
            "checklist_id": package.checklist_id,
            "source_artifact_ids": package.source_artifact_ids,
            "document_codes": package.document_codes,
            "document_manifest_item_ids": tuple(
                item.manifest_item_id for item in package.document_manifest
            ),
            "approval_condition_codes": package.approval_condition_codes,
            "limitation_codes": package.limitation_codes,
            "masking_manifest_id": package.masking_manifest_id,
        }
        if draft.identity_inputs != expected_identity:
            errors.append(
                "DOCUMENT_RELEASE_PACKAGE artifact identity inputs are not exact."
            )
        for item in package.document_manifest:
            if (
                not set(item.evidence_ids).issubset(evidence_ids)
                or any(
                    "/" in reference
                    or "\\" in reference
                    or "://" in reference
                    for reference in item.source_reference_ids
                )
            ):
                errors.append(
                    f"Document release manifest item {item.manifest_item_id} "
                    "has unsafe or unavailable references."
                )
        if not errors:
            checks.append("DOCUMENT_RELEASE_PACKAGE_BOUNDARY_VALID")

    @staticmethod
    def _validate_internal_decision_package(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate a read-only evidence dossier with no decision authority."""
        try:
            package = InternalDecisionPackage.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid INTERNAL_DECISION_PACKAGE schema: {exc}")
            return
        if package.evaluation_case_id != draft.evaluation_case_id:
            errors.append(
                "INTERNAL_DECISION_PACKAGE case identity does not match its draft."
            )
        ordered_evidence_ids = tuple(
            evidence.evidence_id for evidence in draft.evidence_refs
        )
        if (
            package.evidence_ids != ordered_evidence_ids
            or set(package.evidence_ids) != evidence_ids
        ):
            errors.append(
                "INTERNAL_DECISION_PACKAGE evidence index is not exact."
            )
        if any(
            not set(source.evidence_ids).issubset(evidence_ids)
            for source in package.source_artifacts
        ):
            errors.append(
                "INTERNAL_DECISION_PACKAGE source references unknown evidence."
            )
        expected_package_id = internal_decision_package_id(
            assembly_path=package.assembly_path,
            source_artifacts=package.source_artifacts,
            governance_references=package.governance_references,
        )
        if package.package_id != expected_package_id:
            errors.append("INTERNAL_DECISION_PACKAGE has an unstable package_id.")
        expected_identity = {
            "assembly_path": package.assembly_path,
            "source_artifacts": tuple(
                item.model_dump(mode="json") for item in package.source_artifacts
            ),
            "governance_references": tuple(
                internal_decision_governance_identity(item)
                for item in package.governance_references
            ),
        }
        if draft.identity_inputs != expected_identity:
            errors.append(
                "INTERNAL_DECISION_PACKAGE artifact identity inputs are not exact."
            )
        if (
            package.readiness is not InternalDecisionPackageReadiness.READY
            or package.missing_data_requests
            or package.recommendation_performed
            or package.selection_performed
            or package.approval_requested
            or package.external_action_performed
        ):
            errors.append(
                "INTERNAL_DECISION_PACKAGE exceeds its read-only assembly boundary."
            )
        if not errors:
            checks.append("INTERNAL_DECISION_PACKAGE_BOUNDARY_VALID")

    @staticmethod
    def _validate_final_risk_assessment(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate Final Risk's conservative, evidence-bound handoff contract."""
        try:
            assessment = FinalRiskAssessment.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid FINAL_RISK_ASSESSMENT schema: {exc}")
            return

        if assessment.evaluation_case_id != draft.evaluation_case_id:
            errors.append(
                "FINAL_RISK_ASSESSMENT case identity does not match its draft."
            )
        ordered_evidence_ids = tuple(
            evidence.evidence_id for evidence in draft.evidence_refs
        )
        if (
            assessment.evidence_ids != ordered_evidence_ids
            or set(assessment.evidence_ids) != evidence_ids
        ):
            errors.append("FINAL_RISK_ASSESSMENT evidence index is not exact.")

        expected_identity = {
            "internal_decision_package_artifact_id": (
                assessment.internal_decision_package_artifact_id
            ),
            "internal_decision_package_artifact_version": (
                assessment.internal_decision_package_artifact_version
            ),
            "internal_decision_package_input_hash": (
                assessment.internal_decision_package_input_hash
            ),
            "internal_decision_package_id": (
                assessment.internal_decision_package_id
            ),
        }
        if draft.identity_inputs != expected_identity:
            errors.append(
                "FINAL_RISK_ASSESSMENT artifact identity inputs are not exact."
            )

        referenced = {
            evidence_id
            for item in (
                *assessment.residual_findings,
                *assessment.unresolved_approval_gates,
                *assessment.required_controls,
                *assessment.limitations,
            )
            for evidence_id in item.evidence_ids
        }
        if assessment.major_exception_signal is not None:
            referenced.update(assessment.major_exception_signal.evidence_ids)
        if not referenced.issubset(evidence_ids):
            errors.append("FINAL_RISK_ASSESSMENT references unknown evidence.")

        severity_order = {
            RiskSeverity.LOW: 1,
            RiskSeverity.MEDIUM: 2,
            RiskSeverity.HIGH: 3,
            RiskSeverity.CRITICAL: 4,
        }
        expected_level = RiskLevel.NO_CASE_SIGNAL
        if assessment.residual_findings:
            highest = max(
                assessment.residual_findings,
                key=lambda item: severity_order[item.severity],
            )
            expected_level = RiskLevel(highest.severity)
        if (
            assessment.initial_risk_level is not expected_level
            or assessment.residual_risk_level is not expected_level
        ):
            errors.append(
                "FINAL_RISK_ASSESSMENT residual findings contradict its risk level."
            )

        for finding in assessment.residual_findings:
            expected_finding_id = deterministic_id(
                "RRF",
                assessment.internal_decision_package_id,
                finding.source_finding_id,
                finding.status,
                finding.evidence_ids,
            )
            if finding.residual_finding_id != expected_finding_id:
                errors.append(
                    "FINAL_RISK_ASSESSMENT contains an unstable residual finding ID."
                )
            if not finding.evidence_ids:
                errors.append(
                    "FINAL_RISK_ASSESSMENT residual findings require explicit evidence."
                )

        for control in assessment.required_controls:
            expected_control_id = deterministic_id(
                "FRC",
                assessment.internal_decision_package_id,
                control.code,
                control.source_reference_ids,
                control.protected_action,
                control.evidence_ids,
            )
            if control.control_id != expected_control_id:
                errors.append(
                    "FINAL_RISK_ASSESSMENT contains an unstable required-control ID."
                )
            requires_action = control.code in {
                FinalRiskControlCode.GOVERNANCE_EVALUATION_BEFORE_PROTECTED_ACTION,
                FinalRiskControlCode.GOVERNANCE_REJECTION_MUST_BE_HONORED,
                FinalRiskControlCode.DOCUMENT_RELEASE_REQUIRES_SEPARATE_AUTHORIZATION,
            }
            if requires_action != (control.protected_action is not None):
                errors.append(
                    "FINAL_RISK_ASSESSMENT required-control action binding is invalid."
                )
            if (
                control.code
                is FinalRiskControlCode.DOCUMENT_RELEASE_REQUIRES_SEPARATE_AUTHORIZATION
                and control.protected_action
                is not ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER
            ):
                errors.append(
                    "FINAL_RISK_ASSESSMENT Document release control has the wrong "
                    "protected action."
                )

        critical = tuple(
            item
            for item in assessment.residual_findings
            if item.severity is RiskSeverity.CRITICAL
        )
        if assessment.major_exception_status is MajorExceptionStatus.DETECTED:
            signal = assessment.major_exception_signal
            if signal is None:  # pragma: no cover - domain model also enforces this
                errors.append(
                    "FINAL_RISK_ASSESSMENT detected a major exception without a signal."
                )
            else:
                expected_signal_evidence = tuple(
                    dict.fromkeys(
                        evidence_id
                        for finding in critical
                        for evidence_id in finding.evidence_ids
                    )
                )
                expected_signal_id = deterministic_id(
                    "MES",
                    assessment.internal_decision_package_id,
                    tuple(item.residual_finding_id for item in critical),
                    expected_signal_evidence,
                )
                if (
                    signal.evidence_ids != expected_signal_evidence
                    or signal.signal_id != expected_signal_id
                ):
                    errors.append(
                        "FINAL_RISK_ASSESSMENT major-exception lineage is not exact."
                    )

        # The current ready-package schema can contain dormant checkpoint
        # registrations and resolved rejections, but it cannot contain a live
        # PENDING/EXPIRED ApprovalRequest. Treating registrations as active gates
        # would invent workflow state.
        if assessment.unresolved_approval_gates:
            errors.append(
                "FINAL_RISK_ASSESSMENT invents unresolved approval gates from a "
                "ready package."
            )

        expected_assessment_id = final_risk_assessment_id(
            internal_decision_package_artifact_id=(
                assessment.internal_decision_package_artifact_id
            ),
            internal_decision_package_artifact_version=(
                assessment.internal_decision_package_artifact_version
            ),
            internal_decision_package_input_hash=(
                assessment.internal_decision_package_input_hash
            ),
            internal_decision_package_id=assessment.internal_decision_package_id,
            assessment_status=assessment.assessment_status,
            residual_risk_level=assessment.residual_risk_level,
            residual_findings=assessment.residual_findings,
            unresolved_approval_gates=assessment.unresolved_approval_gates,
            required_controls=assessment.required_controls,
            major_exception_status=assessment.major_exception_status,
            major_exception_signal=assessment.major_exception_signal,
            limitations=assessment.limitations,
            evidence_ids=assessment.evidence_ids,
        )
        if assessment.assessment_id != expected_assessment_id:
            errors.append("FINAL_RISK_ASSESSMENT has an unstable assessment_id.")
        if (
            assessment.recommendation_performed
            or assessment.approval_requested
            or assessment.external_action_performed
        ):
            errors.append("FINAL_RISK_ASSESSMENT exceeds the Risk boundary.")
        if not errors:
            checks.append("FINAL_RISK_ASSESSMENT_BOUNDARY_VALID")

    @staticmethod
    def _validate_ai_decision_analysis(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate guarded AI output without treating it as a final Decision."""
        try:
            analysis = AIDecisionAnalysis.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid AI_DECISION_ANALYSIS schema: {exc}")
            return
        if analysis.evaluation_case_id != draft.evaluation_case_id:
            errors.append("AI_DECISION_ANALYSIS case identity does not match its draft.")
        expected_referenced_evidence = tuple(
            dict.fromkeys(
                evidence_id
                for item in (
                    *analysis.reasons,
                    *analysis.conditions,
                    *analysis.selected_negotiation_strategies,
                    *analysis.human_attention_points,
                )
                for evidence_id in item.evidence_ids
            )
        )
        if analysis.evidence_ids != expected_referenced_evidence:
            errors.append("AI_DECISION_ANALYSIS selected evidence index is not exact.")
        if not set(analysis.evidence_ids).issubset(evidence_ids):
            errors.append("AI_DECISION_ANALYSIS references unknown evidence.")
        expected_identity = {
            "packet_id": analysis.packet_id,
            "internal_decision_package_artifact": (
                analysis.internal_decision_package_artifact.model_dump(mode="json")
            ),
            "final_risk_artifact": analysis.final_risk_artifact.model_dump(
                mode="json"
            ),
            "analysis_source": analysis.source,
            "model": analysis.model,
            "prompt_version": analysis.prompt_version,
            "composer_input_hash": analysis.input_hash,
            "composer_configuration_hash": (
                draft.identity_inputs.get("composer_configuration_hash")
                if draft.identity_inputs is not None
                else None
            ),
        }
        if draft.identity_inputs != expected_identity:
            errors.append(
                "AI_DECISION_ANALYSIS artifact identity inputs are not exact."
            )
        configuration_hash = expected_identity["composer_configuration_hash"]
        if not isinstance(configuration_hash, str) or not configuration_hash.startswith(
            "DACFG-"
        ):
            errors.append(
                "AI_DECISION_ANALYSIS lacks a valid composer configuration identity."
            )
        if (
            not analysis.deterministic_guard_passed
            or analysis.calculations_performed_by_model
            or analysis.approval_requested
            or analysis.external_action_performed
        ):
            errors.append("AI_DECISION_ANALYSIS exceeds its proposal boundary.")
        if not errors:
            checks.append("AI_DECISION_ANALYSIS_BOUNDARY_VALID")

    @staticmethod
    def _validate_decision_card(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate the detailed proposal shown to Founder before Governance."""
        try:
            card = DecisionCard.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid DECISION_CARD schema: {exc}")
            return
        if card.evaluation_case_id != draft.evaluation_case_id:
            errors.append("DECISION_CARD case identity does not match its draft.")
        ordered_evidence_ids = tuple(
            item.evidence_id for item in draft.evidence_refs
        )
        if card.evidence_ids != ordered_evidence_ids or set(card.evidence_ids) != evidence_ids:
            errors.append("DECISION_CARD evidence index is not exact.")
        referenced = {
            evidence_id
            for item in (
                *card.reasons,
                *card.conditions,
                *card.selected_negotiation_strategies,
                *card.selected_options,
                *card.finance_metrics,
                *card.operations_metrics,
                *card.calculations,
                *card.residual_findings,
                *card.required_controls,
                *card.limitations,
                *card.human_attention_points,
            )
            for evidence_id in item.evidence_ids
        }
        if card.document_release_package is not None:
            referenced.update(card.document_release_package.evidence_ids)
        if not referenced.issubset(evidence_ids):
            errors.append("DECISION_CARD references unknown evidence.")
        expected_identity = {
            "ai_analysis_artifact": card.ai_analysis_artifact.model_dump(
                mode="json"
            ),
            "ai_analysis_id": card.ai_analysis_id,
            "internal_decision_package_artifact": (
                card.internal_decision_package_artifact.model_dump(mode="json")
            ),
            "final_risk_artifact": card.final_risk_artifact.model_dump(mode="json"),
        }
        if draft.identity_inputs != expected_identity:
            errors.append("DECISION_CARD artifact identity inputs are not exact.")
        if (
            card.founder_decision_recorded
            or card.approval_requested
            or card.document_release_authorized
            or card.external_action_performed
        ):
            errors.append("DECISION_CARD exceeds its proposal boundary.")
        if not errors:
            checks.append("DECISION_CARD_BOUNDARY_VALID")

    @staticmethod
    def _validate_post_decision_update(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate one approved Card route without permitting a protected action."""
        try:
            update = PostDecisionUpdate.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid POST_DECISION_UPDATE schema: {exc}")
            return
        if update.evaluation_case_id != draft.evaluation_case_id:
            errors.append("POST_DECISION_UPDATE case identity does not match its draft.")
        ordered_evidence_ids = tuple(
            item.evidence_id for item in draft.evidence_refs
        )
        if (
            update.evidence_ids != ordered_evidence_ids
            or set(update.evidence_ids) != evidence_ids
        ):
            errors.append("POST_DECISION_UPDATE evidence index is not exact.")
        expected_identity = {
            "decision_card_artifact": update.decision_card_artifact.model_dump(
                mode="json"
            ),
            "decision_card_id": update.decision_card_id,
            "founder_approval": approval_business_identity(
                update.founder_approval
            ),
            "recommendation": update.recommendation,
            "outcome": update.outcome,
            "approved_condition_ids": update.approved_condition_ids,
            "approved_negotiation_strategy_ids": (
                update.approved_negotiation_strategy_ids
            ),
            "selected_option_ids": update.selected_option_ids,
            "document_release_package": (
                None
                if update.document_release_package is None
                else update.document_release_package.model_dump(mode="json")
            ),
        }
        if draft.identity_inputs != expected_identity:
            errors.append(
                "POST_DECISION_UPDATE artifact identity inputs are not exact."
            )
        if (
            not update.founder_decision_recorded
            or update.external_document_submission_proposed
            or update.external_action_performed
        ):
            errors.append("POST_DECISION_UPDATE exceeds its routing boundary.")
        if not errors:
            checks.append("POST_DECISION_UPDATE_BOUNDARY_VALID")

    @staticmethod
    def _validate_external_document_submission_proposal(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate an exact masked release proposal without claiming authorization."""
        try:
            proposal = ExternalDocumentSubmissionProposal.model_validate(
                draft.payload
            )
        except ValueError as exc:
            errors.append(
                "Invalid EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL schema: "
                f"{exc}"
            )
            return
        if proposal.evaluation_case_id != draft.evaluation_case_id:
            errors.append(
                "EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL case identity does not "
                "match its draft."
            )
        ordered_evidence_ids = tuple(
            item.evidence_id for item in draft.evidence_refs
        )
        if (
            proposal.evidence_ids != ordered_evidence_ids
            or set(proposal.evidence_ids) != evidence_ids
        ):
            errors.append(
                "EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL evidence index is not exact."
            )
        expected_identity = {
            "post_decision_update_artifact": (
                proposal.post_decision_update_artifact.model_dump(mode="json")
            ),
            "post_decision_update_id": proposal.post_decision_update_id,
            "decision_card_artifact": proposal.decision_card_artifact.model_dump(
                mode="json"
            ),
            "decision_card_id": proposal.decision_card_id,
            "document_release_package": (
                proposal.document_release_package.model_dump(mode="json")
            ),
            "document_manifest_item_ids": proposal.document_manifest_item_ids,
            "masking_manifest_item_ids": proposal.masking_manifest_item_ids,
            "approval_condition_codes": proposal.approval_condition_codes,
        }
        if draft.identity_inputs != expected_identity:
            errors.append(
                "EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL artifact identity inputs "
                "are not exact."
            )
        if (
            proposal.governance_evaluated
            or proposal.approval_requested
            or proposal.release_authorized
            or proposal.external_submission_performed
        ):
            errors.append(
                "EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL exceeds its proposal boundary."
            )
        if not errors:
            checks.append(
                "EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL_BOUNDARY_VALID"
            )

    @staticmethod
    def _validate_document_package_common(
        *,
        draft: ArtifactDraft,
        package: DocumentPackageDraft | DocumentReleasePackage,
        evidence_ids: set[str],
        masking_policy: MaskingPolicyDocument | None,
        masking_service: MaskingService | None,
        errors: list[str],
    ) -> None:
        """Validate shared safe-payload, manifest, and evidence invariants."""
        if package.evaluation_case_id != draft.evaluation_case_id:
            errors.append("Document package case identity does not match its draft.")
        if package.evidence_ids != tuple(
            item.evidence_id for item in draft.evidence_refs
        ) or set(package.evidence_ids) != evidence_ids:
            errors.append("Document package evidence index is not exact.")
        try:
            MaskedPayload(
                values=package.sanitized_payload,
                classification_decisions=package.classification_decisions,
                manifest=package.masking_manifest,
            )
        except ValueError as exc:
            errors.append(f"Document masked payload is internally inconsistent: {exc}")
        forbidden_keys = {
            "access_token",
            "api_key",
            "biometric_reference",
            "raw_company_profile",
            "raw_document",
            "document_bytes",
            "filesystem_path",
        }
        present = EvidenceValidator._recursive_keys(package.sanitized_payload)
        if forbidden_keys & present:
            errors.append(
                "Document sanitized payload contains forbidden fields: "
                + ", ".join(sorted(forbidden_keys & present))
            )
        EvidenceValidator._validate_masking_manifest(
            payload=package.sanitized_payload,
            decisions=package.classification_decisions,
            manifest=package.masking_manifest,
            recipient=package.recipient,
            purpose=package.purpose,
            policy=masking_policy,
            masking_service=masking_service,
            evidence_by_id={item.evidence_id: item for item in draft.evidence_refs},
            errors=errors,
        )

    @staticmethod
    def _validate_masking_manifest(
        *,
        payload: dict[str, object],
        decisions: tuple[ClassificationDecision, ...],
        manifest: MaskingManifest,
        recipient: str,
        purpose: str,
        policy: MaskingPolicyDocument | None,
        masking_service: MaskingService | None,
        evidence_by_id: dict[str, EvidenceRef],
        errors: list[str],
    ) -> None:
        """Recompute masking from exact source evidence using trusted key material."""
        if policy is None:
            errors.append("Document package requires the server masking policy.")
            return
        expected_policy_sha256 = masking_policy_document_sha256(policy)
        if (
            manifest.policy_id != policy.policy_id
            or manifest.policy_version != policy.policy_version
            or manifest.policy_document_sha256 != expected_policy_sha256
            or manifest.recipient != recipient
            or manifest.purpose != purpose
        ):
            errors.append("Document masking manifest does not match server policy scope.")
        classification_by_field = {
            item.field_name: item for item in policy.classification_rules
        }
        masking_by_field = {item.field_name: item for item in policy.masking_rules}
        if len(decisions) != len(manifest.items):
            errors.append("Document masking decision and manifest counts differ.")
            return
        for decision, item in zip(decisions, manifest.items, strict=True):
            classification = classification_by_field.get(item.field_name)
            configured = masking_by_field.get(item.field_name)
            if classification is None or configured is None:
                errors.append(
                    f"Document masking field {item.field_name} is not server-configured."
                )
                continue
            expected_decision_id = deterministic_id(
                "CLASS",
                policy.policy_id,
                policy.policy_version,
                classification.rule_id,
                classification.field_name,
                classification.classification,
                classification.policy_reference,
                classification.source_evidence_ids,
            )
            if (
                decision.decision_id != expected_decision_id
                or decision.field_name != item.field_name
                or decision.classification is not classification.classification
                or decision.rule_id != classification.rule_id
                or decision.policy_reference != classification.policy_reference
                or item.classification_decision_id != decision.decision_id
                or item.classification is not decision.classification
                or item.purpose != purpose
                or item.recipient != recipient
                or item.policy_reference != decision.policy_reference
                or item.policy_evidence_ids != decision.source_evidence_ids
                or not item.source_evidence_ids
                or not set(item.source_evidence_ids).issubset(evidence_by_id)
            ):
                errors.append(
                    f"Document masking field {item.field_name} has invalid classification."
                )
            purpose_allowed = EvidenceValidator._masking_context_allowed(
                purpose, configured.allowed_purposes
            )
            recipient_allowed = EvidenceValidator._masking_context_allowed(
                recipient, configured.allowed_recipients
            )
            context_allowed = purpose_allowed and recipient_allowed
            included = item.included_in_payload
            if included:
                if (
                    item.field_name not in payload
                    or item.action is not configured.action
                    or item.algorithm_id is not configured.algorithm_id
                    or item.algorithm_version != configured.algorithm_version
                    or item.key_version != configured.key_version
                    or item.reason_code is not MaskingReasonCode.POLICY_ACTION
                    or not context_allowed
                ):
                    errors.append(
                        f"Document masking field {item.field_name} exceeds configured policy."
                    )
                output: object = payload.get(item.field_name)
            else:
                valid_omission_reason = (
                    item.reason_code
                    in {
                        MaskingReasonCode.NOT_REQUIRED_FOR_PURPOSE,
                        MaskingReasonCode.CONTEXT_NOT_ALLOWED,
                    }
                    if not context_allowed
                    else item.reason_code
                    is MaskingReasonCode.NOT_REQUIRED_FOR_PURPOSE
                    or (
                        item.reason_code is MaskingReasonCode.POLICY_ACTION
                        and configured.action is MaskingAction.OMIT
                    )
                )
                if (
                    item.field_name in payload
                    or item.action is not MaskingAction.OMIT
                    or item.algorithm_id
                    is not MaskingAlgorithmId.DATA_MINIMIZATION_OMIT
                    or item.algorithm_version != "v1"
                    or item.key_version is not None
                    or not valid_omission_reason
                ):
                    errors.append(
                        f"Omitted document field {item.field_name} is not fail-closed."
                    )
                output = None
            encoded = json.dumps(
                output,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            if item.output_digest != sha256(encoded).hexdigest():
                errors.append(
                    f"Document masking field {item.field_name} has an invalid digest."
                )
            expected_reference = (
                str(output)
                if included
                and item.action
                in {
                    MaskingAction.TOKENIZE,
                    MaskingAction.PARTIAL_MASK,
                    MaskingAction.GENERALIZE,
                    MaskingAction.VAULT_REFERENCE,
                }
                else None
            )
            if item.output_reference != expected_reference:
                errors.append(
                    f"Document masking field {item.field_name} has an unsafe output reference."
                )
            if included and item.action is MaskingAction.TOKENIZE and (
                not isinstance(output, str)
                or re.fullmatch(r"TOK-[A-Z0-9-]+-[A-Z0-9-]+-[A-Z2-7]{26,52}", output)
                is None
            ):
                errors.append(
                    f"Document masking field {item.field_name} has an invalid token."
                )
        expected_manifest_id = deterministic_id(
            "MASK",
            policy.policy_id,
            policy.policy_version,
            expected_policy_sha256,
            purpose,
            recipient,
            tuple(item.model_dump(mode="json") for item in manifest.items),
        )
        if manifest.manifest_id != expected_manifest_id:
            errors.append("Document masking manifest identity is unstable.")
        EvidenceValidator._validate_recomputed_masking(
            payload=payload,
            decisions=decisions,
            manifest=manifest,
            recipient=recipient,
            purpose=purpose,
            masking_service=masking_service,
            evidence_by_id=evidence_by_id,
            errors=errors,
        )

    @staticmethod
    def _validate_recomputed_masking(
        *,
        payload: dict[str, object],
        decisions: tuple[ClassificationDecision, ...],
        manifest: MaskingManifest,
        recipient: str,
        purpose: str,
        masking_service: MaskingService | None,
        evidence_by_id: dict[str, EvidenceRef],
        errors: list[str],
    ) -> None:
        """Rebuild the output from exact authoritative values, never self-digests."""
        if masking_service is None:
            errors.append(
                "Document package requires trusted masking recomputation service."
            )
            return
        raw_payload: dict[str, MaskableScalar] = {}
        source_ids_by_field: dict[str, tuple[str, ...]] = {}
        for item in manifest.items:
            source_items = tuple(
                evidence_by_id[evidence_id]
                for evidence_id in item.source_evidence_ids
                if evidence_id in evidence_by_id
            )
            if any(
                evidence.source_type is SourceType.DERIVED
                and (
                    not evidence.source_evidence_ids
                    or not set(evidence.source_evidence_ids).issubset(evidence_by_id)
                )
                for evidence in source_items
            ):
                errors.append(
                    f"Document masking field {item.field_name} has incomplete "
                    "derived source lineage."
                )
                continue
            values = tuple(
                value
                for evidence in source_items
                for found, value in (
                    EvidenceValidator._exact_masking_source_value(
                        evidence,
                        item.field_name,
                    ),
                )
                if found
            )
            canonical_values = {
                json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                for value in values
            }
            if not values or len(canonical_values) != 1:
                errors.append(
                    f"Document masking field {item.field_name} lacks one exact "
                    "authoritative source value."
                )
                continue
            raw_payload[item.field_name] = values[0]
            source_ids_by_field[item.field_name] = item.source_evidence_ids
        if len(raw_payload) != len(manifest.items):
            return
        try:
            recomputed = masking_service.mask_payload(
                raw_payload,
                recipient=recipient,
                purpose=purpose,
                required_fields=tuple(raw_payload),
                source_evidence_ids_by_field=source_ids_by_field,
            )
            claimed = MaskedPayload(
                values=payload,
                classification_decisions=decisions,
                manifest=manifest,
            )
        except (TypeError, ValueError):
            errors.append("Document masking recomputation failed closed.")
            return
        if recomputed != claimed:
            errors.append(
                "Document sanitized payload is not the exact trusted-policy output "
                "for its authoritative source evidence."
            )

    @staticmethod
    def _exact_masking_source_value(
        evidence: EvidenceRef,
        field_name: str,
    ) -> tuple[bool, MaskableScalar]:
        """Resolve only explicit field/value evidence; never guess by description."""
        found = False
        value: object = None
        if evidence.field == field_name or (
            evidence.record_id == field_name and evidence.field == "value"
        ):
            found = True
            value = evidence.display_value
        elif (
            isinstance(evidence.display_value, dict)
            and field_name in evidence.display_value
        ):
            found = True
            value = evidence.display_value[field_name]
        if not found:
            return False, None
        if value is None or isinstance(value, (str, bool, int)):
            return True, value
        if isinstance(value, float) and isfinite(value):
            return True, value
        return False, None

    @staticmethod
    def _masking_context_allowed(value: str, allowed: tuple[str, ...]) -> bool:
        return "*" in allowed or value in allowed

    @staticmethod
    def _validate_document_evidence_supplement(
        draft: ArtifactDraft,
        evidence_ids: set[str],
        checks: list[str],
        errors: list[str],
    ) -> None:
        """Validate reference-only document evidence without accepting file paths."""
        try:
            supplement = DocumentEvidenceSupplement.model_validate(draft.payload)
        except ValueError as exc:
            errors.append(f"Invalid DOCUMENT_EVIDENCE_SUPPLEMENT schema: {exc}")
            return
        if supplement.evaluation_case_id != draft.evaluation_case_id:
            errors.append(
                "DOCUMENT_EVIDENCE_SUPPLEMENT case identity does not match its draft."
            )
        if supplement.evidence_ids != tuple(
            item.evidence_id for item in draft.evidence_refs
        ) or set(supplement.evidence_ids) != evidence_ids:
            errors.append(
                "DOCUMENT_EVIDENCE_SUPPLEMENT evidence index is not exact."
            )
        expected_identity = {
            "preparation_request_id": supplement.preparation_request_id,
            "missing_request_id": supplement.missing_request_id,
            "document_reference_id": supplement.document_reference_id,
            "content_sha256": supplement.content_sha256,
            "document_type": supplement.document_type,
            "source_package_artifact_id": supplement.source_package_artifact_id,
        }
        if draft.identity_inputs != expected_identity:
            errors.append(
                "DOCUMENT_EVIDENCE_SUPPLEMENT artifact identity inputs are not exact."
            )
        if (
            "/" in supplement.document_reference_id
            or "\\" in supplement.document_reference_id
            or "://" in supplement.document_reference_id
        ):
            errors.append(
                "DOCUMENT_EVIDENCE_SUPPLEMENT contains a path or URL instead of an opaque ID."
            )
        expected_fields = (
            ("missing_request_id", supplement.missing_request_id),
            ("document_reference_id", supplement.document_reference_id),
            ("content_sha256", supplement.content_sha256),
            ("document_type", supplement.document_type.value),
            ("provided_by", supplement.provided_by),
            ("evidence_note", supplement.evidence_note),
        )
        evidence_by_field = {item.field: item for item in draft.evidence_refs}
        if len(evidence_by_field) != len(draft.evidence_refs):
            errors.append(
                "DOCUMENT_EVIDENCE_SUPPLEMENT evidence fields are ambiguous."
            )
        for field, value in expected_fields:
            item = evidence_by_field.get(field)
            display = json_safe(value)
            expected_evidence_id = deterministic_id(
                "EVD",
                supplement.dataset_id,
                SourceType.USER_INPUT,
                supplement.supplement_id,
                field,
                display,
            )
            if (
                item is None
                or item.evidence_id != expected_evidence_id
                or item.source_type is not SourceType.USER_INPUT
                or item.sheet != "DOCUMENT_EVIDENCE_SUPPLEMENT"
                or item.row_number != 0
                or item.record_id != supplement.supplement_id
                or item.display_value != display
                or item.source_evidence_ids
            ):
                errors.append(
                    f"DOCUMENT_EVIDENCE_SUPPLEMENT field {field} lacks exact lineage."
                )
        if not errors:
            checks.append("DOCUMENT_EVIDENCE_SUPPLEMENT_BOUNDARY_VALID")
