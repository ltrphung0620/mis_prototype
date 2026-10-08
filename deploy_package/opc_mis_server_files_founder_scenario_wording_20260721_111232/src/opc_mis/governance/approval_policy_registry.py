"""Deterministic, evidence-backed registration of approval checkpoints."""

from dataclasses import dataclass
from numbers import Real
from typing import ClassVar

from opc_mis.domain.approvals import (
    ApprovalCheckpoint,
    ApprovalCheckpointSet,
    ApprovalCondition,
    ApprovalPolicyCoverage,
    ApprovalSignal,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckGovernanceSourceFacts,
    BankingPrecheckSubmissionProposal,
)
from opc_mis.domain.enums import (
    ApprovalTriggerEvent,
    ArtifactType,
    ProtectedAction,
    RuleOperator,
    SourceType,
    ValidationStatus,
)
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.risk_models import RiskPreScan
from opc_mis.domain.team_pack import SheetRegistry

DEFAULT_HUMAN_APPROVER_ROLE = "FOUNDER"
BANKING_PRECHECK_SUBMISSION_POLICY_ID = "TEAM_PACK_BANKING_PRECHECK_SUBMISSION"
_VALID_ARTIFACT_STATUSES = {
    ValidationStatus.VALID,
    ValidationStatus.VALID_WITH_WARNINGS,
}


class ApprovalPolicyError(ValueError):
    """Raised when source facts cannot form one safe, exact Governance policy."""


@dataclass(frozen=True)
class _RegisteredPolicy:
    trigger_event: ApprovalTriggerEvent
    protected_action: ProtectedAction
    operators: frozenset[RuleOperator]
    boolean_threshold: bool | None = None


class ApprovalPolicyRegistry:
    """Convert source policies into non-executing, evidence-bound checkpoints."""

    component_id = "GOVERNANCE_APPROVAL_POLICY_REGISTRY"

    _POLICIES: ClassVar[dict[str, _RegisteredPolicy]] = {
        "document_sent_to_partner": _RegisteredPolicy(
            trigger_event=ApprovalTriggerEvent.DOCUMENT_EXTERNAL_RELEASE_REQUESTED,
            protected_action=ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER,
            operators=frozenset({RuleOperator.EQUAL}),
            boolean_threshold=True,
        ),
        "requested_amount": _RegisteredPolicy(
            trigger_event=ApprovalTriggerEvent.LARGE_FINANCIAL_DECISION_REQUESTED,
            protected_action=ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION,
            operators=frozenset(
                {
                    RuleOperator.GREATER_THAN,
                    RuleOperator.GREATER_THAN_OR_EQUAL,
                }
            ),
        ),
    }

    _CATALOG_APPROVAL_DIRECTIVES: ClassVar[dict[str, bool]] = {
        "human approval before submission": True,
        "human approval before application": True,
        "no human approval required": False,
    }
    _HANDLING_APPROVAL_DIRECTIVES: ClassVar[dict[str, bool]] = {
        "yes before submission": True,
        "yes before application": True,
        "no": False,
    }

    def create_draft(
        self,
        *,
        pre_scan: RiskPreScan,
        signals: tuple[ApprovalSignal, ...],
    ) -> ArtifactDraft:
        """Validate Risk candidates without inventing an API approval policy."""
        checkpoints = tuple(
            self._checkpoint(pre_scan.evaluation_case_id, signal)
            for signal in signals
        )
        checkpoint_set = ApprovalCheckpointSet(
            evaluation_case_id=pre_scan.evaluation_case_id,
            dataset_id=pre_scan.dataset_id,
            contract_id=pre_scan.contract_id,
            checkpoints=checkpoints,
        )
        evidence = {
            item.evidence_id: item
            for signal in signals
            for item in signal.evidence_refs
        }
        return ArtifactDraft(
            artifact_type=ArtifactType.APPROVAL_CHECKPOINTS,
            evaluation_case_id=pre_scan.evaluation_case_id,
            producer=self.component_id,
            payload=checkpoint_set.model_dump(mode="json"),
            evidence_refs=tuple(evidence[key] for key in sorted(evidence)),
            identity_inputs={
                "dataset_id": pre_scan.dataset_id,
                "evaluation_case_id": pre_scan.evaluation_case_id,
                "checkpoint_ids": tuple(item.checkpoint_id for item in checkpoints),
            },
        )

    def create_banking_precheck_draft(
        self,
        *,
        proposal_artifact: ArtifactEnvelope,
        existing_checkpoint_artifact: ArtifactEnvelope | None,
    ) -> ArtifactDraft:
        """Evaluate exact API source facts and scope the amount policy to precheck."""
        proposal = self._validated_proposal(proposal_artifact)
        existing = self._validated_existing_registry(
            proposal=proposal,
            artifact=existing_checkpoint_artifact,
        )
        if existing_checkpoint_artifact is None:  # pragma: no cover - guarded above
            raise ApprovalPolicyError("Approval checkpoint registry is unavailable.")
        amount_source = self._unique_amount_checkpoint(existing)
        evidence = self._evidence_index(
            proposal_artifact.evidence_refs,
            existing_checkpoint_artifact.evidence_refs,
        )

        coverages: list[ApprovalPolicyCoverage] = []
        api_checkpoints: list[ApprovalCheckpoint] = []
        facts_by_api: dict[str, BankingPrecheckGovernanceSourceFacts] = {}
        for candidate in proposal.candidates:
            prior = facts_by_api.get(candidate.api_id)
            if prior is not None:
                if prior != candidate.governance_source_facts:
                    raise ApprovalPolicyError(
                        f"API {candidate.api_id} has conflicting Governance source facts."
                    )
                continue
            facts_by_api[candidate.api_id] = candidate.governance_source_facts
            coverage, policy_evidence = self._api_coverage(
                proposal_artifact=proposal_artifact,
                proposal=proposal,
                api_id=candidate.api_id,
                facts=candidate.governance_source_facts,
                evidence=evidence,
            )
            evidence[policy_evidence.evidence_id] = policy_evidence
            coverages.append(coverage)
            if coverage.requires_human_approval:
                api_checkpoints.append(self._api_checkpoint(proposal, coverage))

        coverage_ids = tuple(item.coverage_id for item in coverages)
        amount_checkpoint, amount_evidence = self._precheck_amount_checkpoint(
            proposal=proposal,
            proposal_artifact=proposal_artifact,
            source=amount_source,
            coverage_ids=coverage_ids,
        )
        evidence[amount_evidence.evidence_id] = amount_evidence
        base_checkpoints = tuple(
            checkpoint
            for checkpoint in existing.checkpoints
            if checkpoint.protected_action is not ProtectedAction.SUBMIT_BANKING_PRECHECK
        )
        checkpoint_set = ApprovalCheckpointSet(
            evaluation_case_id=proposal.evaluation_case_id,
            dataset_id=proposal.dataset_id,
            contract_id=proposal.contract_id,
            checkpoints=(
                *base_checkpoints,
                *api_checkpoints,
                amount_checkpoint,
            ),
            policy_coverages=tuple(coverages),
        )
        source_artifact = existing_checkpoint_artifact
        return ArtifactDraft(
            artifact_type=ArtifactType.APPROVAL_CHECKPOINTS,
            evaluation_case_id=proposal.evaluation_case_id,
            producer=self.component_id,
            payload=checkpoint_set.model_dump(mode="json"),
            evidence_refs=tuple(evidence[key] for key in sorted(evidence)),
            identity_inputs={
                "proposal_artifact_id": proposal_artifact.artifact_id,
                "proposal_artifact_version": proposal_artifact.version,
                "proposal_input_hash": proposal_artifact.input_hash,
                "source_checkpoint_artifact_id": source_artifact.artifact_id,
                "source_checkpoint_version": source_artifact.version,
                "source_checkpoint_input_hash": source_artifact.input_hash,
                "coverage_ids": coverage_ids,
                "checkpoint_ids": tuple(
                    item.checkpoint_id for item in checkpoint_set.checkpoints
                ),
            },
        )

    @staticmethod
    def _validated_proposal(
        artifact: ArtifactEnvelope,
    ) -> BankingPrecheckSubmissionProposal:
        if (
            artifact.artifact_type
            is not ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL
            or artifact.validation_status not in _VALID_ARTIFACT_STATUSES
        ):
            raise ApprovalPolicyError(
                "Banking policy evaluation requires a validated precheck proposal."
            )
        try:
            proposal = BankingPrecheckSubmissionProposal.model_validate(artifact.payload)
        except ValueError as exc:
            raise ApprovalPolicyError("Banking precheck proposal is invalid.") from exc
        if (
            proposal.evaluation_case_id != artifact.evaluation_case_id
            or proposal.proposed_action is not ProtectedAction.SUBMIT_BANKING_PRECHECK
            or proposal.precheck_executed
            or proposal.submission_executed
        ):
            raise ApprovalPolicyError("Banking precheck proposal scope is invalid.")
        return proposal

    @staticmethod
    def _validated_existing_registry(
        *,
        proposal: BankingPrecheckSubmissionProposal,
        artifact: ArtifactEnvelope | None,
    ) -> ApprovalCheckpointSet:
        if artifact is None:
            raise ApprovalPolicyError(
                "Banking precheck requires the TeamPack requested_amount checkpoint."
            )
        if (
            artifact.artifact_type is not ArtifactType.APPROVAL_CHECKPOINTS
            or artifact.validation_status not in _VALID_ARTIFACT_STATUSES
        ):
            raise ApprovalPolicyError(
                "Banking precheck requires a validated approval checkpoint registry."
            )
        try:
            checkpoint_set = ApprovalCheckpointSet.model_validate(artifact.payload)
        except ValueError as exc:
            raise ApprovalPolicyError("Approval checkpoint registry is invalid.") from exc
        if (
            checkpoint_set.evaluation_case_id != proposal.evaluation_case_id
            or checkpoint_set.dataset_id != proposal.dataset_id
            or checkpoint_set.contract_id != proposal.contract_id
            or artifact.evaluation_case_id != proposal.evaluation_case_id
        ):
            raise ApprovalPolicyError(
                "Approval checkpoint registry belongs to another proposal scope."
            )
        evidence_ids = {item.evidence_id for item in artifact.evidence_refs}
        if any(
            not set(checkpoint.evidence_ids).issubset(evidence_ids)
            for checkpoint in checkpoint_set.checkpoints
        ):
            raise ApprovalPolicyError(
                "Approval checkpoint registry has incomplete evidence lineage."
            )
        return checkpoint_set

    @staticmethod
    def _unique_amount_checkpoint(
        checkpoint_set: ApprovalCheckpointSet,
    ) -> ApprovalCheckpoint:
        matches = tuple(
            item
            for item in checkpoint_set.checkpoints
            if item.protected_action
            is ProtectedAction.COMMIT_LARGE_FINANCIAL_DECISION
            and item.condition.source_field == "requested_amount"
            and item.condition.operator
            in {RuleOperator.GREATER_THAN, RuleOperator.GREATER_THAN_OR_EQUAL}
            and isinstance(item.condition.threshold, Real)
            and not isinstance(item.condition.threshold, bool)
        )
        if len(matches) != 1:
            raise ApprovalPolicyError(
                "Banking precheck requires one unique numeric requested_amount policy."
            )
        return matches[0]

    @staticmethod
    def _evidence_index(*groups: tuple[EvidenceRef, ...]) -> dict[str, EvidenceRef]:
        indexed: dict[str, EvidenceRef] = {}
        for item in (item for group in groups for item in group):
            prior = indexed.get(item.evidence_id)
            if prior is not None and prior != item:
                raise ApprovalPolicyError(
                    f"Conflicting policy evidence payload for {item.evidence_id}."
                )
            indexed[item.evidence_id] = item
        return indexed

    def _api_coverage(
        self,
        *,
        proposal_artifact: ArtifactEnvelope,
        proposal: BankingPrecheckSubmissionProposal,
        api_id: str,
        facts: BankingPrecheckGovernanceSourceFacts,
        evidence: dict[str, EvidenceRef],
    ) -> tuple[ApprovalPolicyCoverage, EvidenceRef]:
        source_evidence_ids = self._validated_policy_source_ids(
            api_id=api_id,
            facts=facts,
            evidence=evidence,
        )
        directives = [
            self._CATALOG_APPROVAL_DIRECTIVES.get(
                self._normalize_policy_text(facts.api_extension_rule)
            )
        ]
        directives.extend(
            self._HANDLING_APPROVAL_DIRECTIVES.get(
                self._normalize_policy_text(rule.requires_human_approval_text)
            )
            for rule in facts.handling_rules
        )
        explicit = {item for item in directives if item is not None}
        if not explicit:
            raise ApprovalPolicyError(
                f"API {api_id} has no recognized human-approval policy directive."
            )
        if len(explicit) != 1:
            raise ApprovalPolicyError(
                f"API {api_id} has conflicting human-approval policy directives."
            )
        requires_human = explicit.pop()
        source_policy_ids = tuple(
            dict.fromkeys((api_id, *(item.rule_id for item in facts.handling_rules)))
        )
        coverage_id = deterministic_id(
            "APCOV",
            proposal.evaluation_case_id,
            proposal_artifact.artifact_id,
            ProtectedAction.SUBMIT_BANKING_PRECHECK,
            api_id,
            source_policy_ids,
            requires_human,
            source_evidence_ids,
        )
        display = {
            "api_id": api_id,
            "protected_action": ProtectedAction.SUBMIT_BANKING_PRECHECK.value,
            "requires_human_approval": requires_human,
            "approver_role": DEFAULT_HUMAN_APPROVER_ROLE,
            "source_policy_ids": list(source_policy_ids),
            "subject_artifact_id": proposal_artifact.artifact_id,
        }
        derived = EvidenceRef(
            evidence_id=deterministic_id(
                "EVD",
                proposal.dataset_id,
                SourceType.DERIVED,
                "GOVERNANCE_APPROVAL_POLICY",
                coverage_id,
                display,
                source_evidence_ids,
            ),
            source_type=SourceType.DERIVED,
            sheet="GOVERNANCE_APPROVAL_POLICY",
            row_number=0,
            record_id=coverage_id,
            field="api_human_approval_requirement",
            display_value=display,
            source_evidence_ids=source_evidence_ids,
        )
        coverage = ApprovalPolicyCoverage(
            coverage_id=coverage_id,
            evaluation_case_id=proposal.evaluation_case_id,
            protected_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
            subject_artifact_id=proposal_artifact.artifact_id,
            api_ids=(api_id,),
            source_policy_ids=source_policy_ids,
            requires_human_approval=requires_human,
            approver_role=DEFAULT_HUMAN_APPROVER_ROLE,
            evidence_ids=(*source_evidence_ids, derived.evidence_id),
        )
        return coverage, derived

    @staticmethod
    def _validated_policy_source_ids(
        *,
        api_id: str,
        facts: BankingPrecheckGovernanceSourceFacts,
        evidence: dict[str, EvidenceRef],
    ) -> tuple[str, ...]:
        extension = evidence.get(facts.api_extension_rule_evidence_id)
        if (
            extension is None
            or extension.source_type is not SourceType.TEAM_PACK
            or extension.sheet != SheetRegistry.API_CATALOG.sheet_name
            or extension.record_id != api_id
            or extension.field != "extension_rule"
            or extension.display_value != facts.api_extension_rule
        ):
            raise ApprovalPolicyError(
                f"API {api_id} extension policy evidence is missing or invalid."
            )
        source_ids = [extension.evidence_id]
        for rule in facts.handling_rules:
            expected = {
                "rule_id": rule.rule_id,
                "applies_to": rule.applies_to,
                "requires_human_approval": rule.requires_human_approval_text,
            }
            matches = tuple(
                evidence[evidence_id]
                for evidence_id in rule.evidence_ids
                if evidence_id in evidence
                and evidence[evidence_id].source_type is SourceType.TEAM_PACK
                and evidence[evidence_id].sheet
                == SheetRegistry.API_HANDLING_RULES.sheet_name
                and evidence[evidence_id].record_id == rule.rule_id
                and evidence[evidence_id].field in expected
                and evidence[evidence_id].display_value
                == expected[evidence[evidence_id].field]
            )
            if len(matches) != len(expected) or {item.field for item in matches} != set(
                expected
            ):
                raise ApprovalPolicyError(
                    f"Handling policy {rule.rule_id} evidence is missing or invalid."
                )
            source_ids.extend(item.evidence_id for item in matches)
        return tuple(dict.fromkeys(source_ids))

    @staticmethod
    def _normalize_policy_text(value: str) -> str:
        return " ".join(value.split()).casefold()

    @staticmethod
    def _api_checkpoint(
        proposal: BankingPrecheckSubmissionProposal,
        coverage: ApprovalPolicyCoverage,
    ) -> ApprovalCheckpoint:
        condition = ApprovalCondition(
            source_field="precheck_submission_requested",
            operator=RuleOperator.EQUAL,
            threshold=True,
        )
        return ApprovalCheckpoint(
            checkpoint_id=deterministic_id(
                "ACP",
                proposal.evaluation_case_id,
                coverage.coverage_id,
                condition.model_dump(mode="json"),
            ),
            evaluation_case_id=proposal.evaluation_case_id,
            source_rule_id=coverage.api_ids[0],
            approval_type="BANKING_PRECHECK_API_POLICY",
            trigger_event=ApprovalTriggerEvent.BANKING_PRECHECK_SUBMISSION_REQUESTED,
            protected_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
            condition=condition,
            evidence_ids=coverage.evidence_ids,
            policy_coverage_ids=(coverage.coverage_id,),
            approver_role=coverage.approver_role,
        )

    @staticmethod
    def _precheck_amount_checkpoint(
        *,
        proposal: BankingPrecheckSubmissionProposal,
        proposal_artifact: ArtifactEnvelope,
        source: ApprovalCheckpoint,
        coverage_ids: tuple[str, ...],
    ) -> tuple[ApprovalCheckpoint, EvidenceRef]:
        display = {
            "source_checkpoint_id": source.checkpoint_id,
            "source_rule_id": source.source_rule_id,
            "source_protected_action": source.protected_action.value,
            "protected_action": ProtectedAction.SUBMIT_BANKING_PRECHECK.value,
            "condition": source.condition.model_dump(mode="json"),
            "subject_artifact_id": proposal_artifact.artifact_id,
        }
        derived = EvidenceRef(
            evidence_id=deterministic_id(
                "EVD",
                proposal.dataset_id,
                SourceType.DERIVED,
                "GOVERNANCE_APPROVAL_POLICY",
                source.checkpoint_id,
                proposal_artifact.artifact_id,
                display,
                source.evidence_ids,
            ),
            source_type=SourceType.DERIVED,
            sheet="GOVERNANCE_APPROVAL_POLICY",
            row_number=0,
            record_id=source.checkpoint_id,
            field="banking_precheck_amount_scope",
            display_value=display,
            source_evidence_ids=source.evidence_ids,
        )
        checkpoint = ApprovalCheckpoint(
            checkpoint_id=deterministic_id(
                "ACP",
                proposal.evaluation_case_id,
                source.checkpoint_id,
                proposal_artifact.artifact_id,
                ProtectedAction.SUBMIT_BANKING_PRECHECK,
                source.condition.model_dump(mode="json"),
                coverage_ids,
            ),
            evaluation_case_id=proposal.evaluation_case_id,
            source_rule_id=source.source_rule_id,
            approval_type="BANKING_PRECHECK_AMOUNT_APPROVAL",
            trigger_event=ApprovalTriggerEvent.BANKING_PRECHECK_SUBMISSION_REQUESTED,
            protected_action=ProtectedAction.SUBMIT_BANKING_PRECHECK,
            condition=source.condition,
            evidence_ids=(*source.evidence_ids, derived.evidence_id),
            policy_coverage_ids=coverage_ids,
            approver_role=DEFAULT_HUMAN_APPROVER_ROLE,
        )
        return checkpoint, derived

    def _checkpoint(
        self,
        evaluation_case_id: str,
        signal: ApprovalSignal,
    ) -> ApprovalCheckpoint:
        policy = self._POLICIES.get(signal.condition.source_field)
        if policy is None:
            raise ApprovalPolicyError(
                f"No approval policy is registered for {signal.condition.source_field}."
            )
        if (
            signal.trigger_event is not policy.trigger_event
            or signal.protected_action is not policy.protected_action
            or signal.condition.operator not in policy.operators
        ):
            raise ApprovalPolicyError(
                f"Approval signal {signal.trigger_rule} conflicts with the policy registry."
            )
        if (
            policy.boolean_threshold is not None
            and signal.condition.threshold is not policy.boolean_threshold
        ):
            raise ApprovalPolicyError(
                f"Approval signal {signal.trigger_rule} has an invalid boolean threshold."
            )
        if signal.condition.source_field == "requested_amount" and (
            isinstance(signal.condition.threshold, bool)
            or not isinstance(signal.condition.threshold, (int, float))
        ):
            raise ApprovalPolicyError(
                f"Approval signal {signal.trigger_rule} requires a numeric threshold."
            )
        evidence_ids = tuple(item.evidence_id for item in signal.evidence_refs)
        return ApprovalCheckpoint(
            checkpoint_id=deterministic_id(
                "ACP",
                evaluation_case_id,
                signal.trigger_rule,
                signal.trigger_event,
                signal.protected_action,
                signal.condition.model_dump(mode="json"),
                evidence_ids,
            ),
            evaluation_case_id=evaluation_case_id,
            source_rule_id=signal.trigger_rule,
            approval_type=signal.approval_type,
            trigger_event=signal.trigger_event,
            protected_action=signal.protected_action,
            condition=signal.condition,
            evidence_ids=evidence_ids,
            approver_role=DEFAULT_HUMAN_APPROVER_ROLE,
        )
