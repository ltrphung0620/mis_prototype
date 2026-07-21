"""Evidence-validation tests for governed Banking precheck proposals."""

import asyncio
from copy import deepcopy

import pytest

from opc_mis.domain.enums import SourceType, ValidationStatus
from opc_mis.governance.evidence_validator import EvidenceValidator
from tests.unit.test_banking_precheck_submission_proposal import (
    _proposal_policy,
    _setup,
)


def test_validator_accepts_exact_all_ready_batch_with_pending_options_retained() -> None:
    async def scenario() -> None:
        _, skill, execution = await _setup(ready_count=2, pending_count=1)
        result = await skill.execute(execution)

        report = await EvidenceValidator(
            banking_policy=_proposal_policy(3)
        ).validate(result.artifacts[0])

        assert report.status is ValidationStatus.VALID
        assert "BANKING_PRECHECK_SUBMISSION_PROPOSAL_BOUNDARY_VALID" in report.checks
        assert result.proposal is not None
        assert result.proposal.candidate_option_ids == ("OPTION-1", "OPTION-2")
        assert result.proposal.non_ready_option_ids == ("OPTION-3",)
        assert result.approval_signals == ()
        assert result.action_commands == ()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("path", "replacement", "expected_error"),
    (
        (
            ("candidates", 0, "provider"),
            "UNRELATED-BANK",
            "exact catalog evidence for bank",
        ),
        (
            ("candidates", 0, "catalog_terms", "minimum_amount"),
            310_000_000,
            "exact catalog evidence for minimum_amount",
        ),
        (
            ("candidates", 0, "api_endpoint"),
            "/unconfigured/precheck",
            "exact API evidence for endpoint",
        ),
        (
            ("requested_amount",),
            360_000_000,
            "exact USER_INPUT amount lineage",
        ),
    ),
)
def test_validator_blocks_catalog_api_and_input_lineage_substitution(
    path: tuple[str | int, ...],
    replacement: object,
    expected_error: str,
) -> None:
    async def scenario() -> None:
        _, skill, execution = await _setup()
        result = await skill.execute(execution)
        draft = result.artifacts[0]
        payload = deepcopy(draft.payload)
        target: object = payload
        for key in path[:-1]:
            target = target[key]  # type: ignore[index]
        target[path[-1]] = replacement  # type: ignore[index]

        report = await EvidenceValidator(
            banking_policy=_proposal_policy()
        ).validate(draft.model_copy(update={"payload": payload}))

        assert report.status is ValidationStatus.BLOCKED
        assert any(expected_error in error for error in report.blocking_errors)

    asyncio.run(scenario())


def test_validator_blocks_tampered_ready_batch_derived_lineage() -> None:
    async def scenario() -> None:
        _, skill, execution = await _setup()
        result = await skill.execute(execution)
        draft = result.artifacts[0]
        changed_evidence = tuple(
            evidence.model_copy(
                update={"source_evidence_ids": evidence.source_evidence_ids[:-1]}
            )
            if evidence.source_type is SourceType.DERIVED
            and evidence.sheet == "BANKING_PRECHECK_SUBMISSION_PROPOSAL"
            else evidence
            for evidence in draft.evidence_refs
        )

        report = await EvidenceValidator(
            banking_policy=_proposal_policy()
        ).validate(draft.model_copy(update={"evidence_refs": changed_evidence}))

        assert report.status is ValidationStatus.BLOCKED
        assert any(
            "READY lineage does not cover its exact supporting evidence" in error
            for error in report.blocking_errors
        )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "forbidden_field",
    ("selected_option_id", "external_response", "approval_required"),
)
def test_validator_blocks_selection_and_external_result_claims(
    forbidden_field: str,
) -> None:
    async def scenario() -> None:
        _, skill, execution = await _setup()
        result = await skill.execute(execution)
        draft = result.artifacts[0]
        payload = deepcopy(draft.payload)
        payload[forbidden_field] = "NOT-ALLOWED"

        report = await EvidenceValidator(
            banking_policy=_proposal_policy()
        ).validate(draft.model_copy(update={"payload": payload}))

        assert report.status is ValidationStatus.BLOCKED
        assert any(
            "Invalid BANKING_PRECHECK_SUBMISSION_PROPOSAL schema" in error
            for error in report.blocking_errors
        )

    asyncio.run(scenario())


def test_validator_blocks_tampered_governance_source_facts() -> None:
    async def scenario() -> None:
        _, skill, execution = await _setup()
        result = await skill.execute(execution)
        draft = result.artifacts[0]
        payload = deepcopy(draft.payload)
        payload["candidates"][0]["governance_source_facts"][
            "api_extension_rule"
        ] = "No human approval required"

        report = await EvidenceValidator(
            banking_policy=_proposal_policy()
        ).validate(draft.model_copy(update={"payload": payload}))

        assert report.status is ValidationStatus.BLOCKED
        assert any(
            "invalid API extension-rule lineage" in error
            for error in report.blocking_errors
        )

    asyncio.run(scenario())


def test_validator_requires_matching_server_owned_banking_policy() -> None:
    async def scenario() -> None:
        _, skill, execution = await _setup()
        result = await skill.execute(execution)
        draft = result.artifacts[0]

        without_policy = await EvidenceValidator().validate(draft)
        wrong_policy = await EvidenceValidator(
            banking_policy=_proposal_policy().model_copy(
                update={"policy_hash": "WRONG-POLICY-HASH"}
            )
        ).validate(draft)

        assert without_policy.status is ValidationStatus.BLOCKED
        assert wrong_policy.status is ValidationStatus.BLOCKED
        assert any(
            "requires active catalog policy" in error
            for error in without_policy.blocking_errors
        )
        assert any(
            "mapping identity does not match policy" in error
            for error in wrong_policy.blocking_errors
        )

    asyncio.run(scenario())
