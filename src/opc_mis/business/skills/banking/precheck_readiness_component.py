"""Deterministic Banking precheck readiness without external execution."""

from collections.abc import Iterable

from opc_mis.business.skills.banking.precheck_readiness_context import (
    BankingPrecheckReadinessContext,
    BankingPrecheckReadinessContextError,
    BankingPrecheckReadinessContextLoader,
)
from opc_mis.domain.artifacts import ArtifactDraft, ArtifactEnvelope
from opc_mis.domain.banking_models import (
    BankingCatalogPolicy,
    BankingCriterion,
    BankingNeedBinding,
    BankingOptionCandidate,
    BankingOptionPrecheckReadiness,
    BankingPrecheckFieldResolution,
    BankingPrecheckReadiness,
    BankingPrecheckReadinessComponentResult,
)
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.enums import (
    ArtifactType,
    BankingCriterionCode,
    BankingCriterionStatus,
    BankingPrecheckFieldSource,
    BankingPrecheckFieldStatus,
    BankingPrecheckReadinessStatus,
    ComponentStatus,
)
from opc_mis.domain.events import RuntimeEvent
from opc_mis.domain.evidence import EvidenceRef
from opc_mis.domain.lineage import LineageFactory, deterministic_id
from opc_mis.domain.team_pack import SheetRegistry


class BankingPrecheckReadinessBuildError(RuntimeError):
    """Raised when validated inputs cannot support a deterministic assessment."""


class BankingPrecheckReadinessSkill:
    """Assess all configured options without selecting or invoking one."""

    component_id = "BANKING_PRECHECK_READINESS_SKILL"

    def __init__(
        self,
        *,
        context_loader: BankingPrecheckReadinessContextLoader,
        policy: BankingCatalogPolicy,
    ) -> None:
        self._context_loader = context_loader
        self._policy = policy

    async def execute(
        self, context: ExecutionContext
    ) -> BankingPrecheckReadinessComponentResult:
        """Always return one assessment draft when authoritative inputs are valid."""
        try:
            readiness_context = await self._context_loader.load(context)
            readiness, evidence_refs = self._assess(readiness_context)
        except (
            BankingPrecheckReadinessContextError,
            BankingPrecheckReadinessBuildError,
        ) as exc:
            return BankingPrecheckReadinessComponentResult(
                status=ComponentStatus.FAILED_SAFE,
                runtime_events=(
                    RuntimeEvent(
                        event_type="BANKING_PRECHECK_READINESS_FAILED_SAFE",
                        message=str(exc),
                    ),
                ),
            )

        draft = ArtifactDraft(
            artifact_type=ArtifactType.BANKING_PRECHECK_READINESS,
            evaluation_case_id=readiness.evaluation_case_id,
            producer=self.component_id,
            payload=readiness.model_dump(mode="json"),
            evidence_refs=evidence_refs,
            identity_inputs={
                "source_artifact_ids": readiness.source_artifact_ids,
                "matrix_id": readiness.matrix_id,
                "supplement_id": readiness.supplement_id,
                "mapping_version": self._policy.mapping_version,
                "mapping_hash": self._policy.policy_hash,
                "dataset_snapshot_hash": readiness_context.dataset.snapshot_hash,
            },
        )
        warnings = (
            ()
            if readiness.status is BankingPrecheckReadinessStatus.READY
            else (f"BANKING_PRECHECK_{readiness.status.value}",)
        )
        return BankingPrecheckReadinessComponentResult(
            status=(
                ComponentStatus.COMPLETED
                if not warnings
                else ComponentStatus.COMPLETED_WITH_WARNINGS
            ),
            readiness=readiness,
            artifacts=(draft,),
            warnings=warnings,
            runtime_events=(
                RuntimeEvent(
                    event_type="BANKING_PRECHECK_READINESS_ASSESSED",
                    message=(
                        "Banking assessed precheck input readiness without executing "
                        "an external call."
                    ),
                    metadata={
                        "readiness_status": readiness.status.value,
                        "ready_option_count": len(readiness.ready_option_ids),
                        "pending_option_count": len(readiness.pending_option_ids),
                    },
                ),
            ),
        )

    def _assess(
        self,
        context: BankingPrecheckReadinessContext,
    ) -> tuple[BankingPrecheckReadiness, tuple[EvidenceRef, ...]]:
        matrix = context.matrix
        if (
            matrix.mapping_policy_id,
            matrix.mapping_version,
            matrix.mapping_hash,
        ) != (
            self._policy.policy_id,
            self._policy.mapping_version,
            self._policy.policy_hash,
        ):
            raise BankingPrecheckReadinessBuildError(
                "Banking option matrix does not match the active catalog policy."
            )
        lineage = LineageFactory(context.dataset.dataset_id, context.dataset.source_hash)
        evidence = self._upstream_evidence(context)
        bindings = {item.need_type: item for item in self._policy.bindings}
        option_readiness = tuple(
            self._assess_option(
                context=context,
                candidate=candidate,
                binding=bindings.get(candidate.need_type),
                lineage=lineage,
                evidence=evidence,
            )
            for candidate in matrix.candidates
        )
        ready_option_ids = tuple(
            item.option_id
            for item in option_readiness
            if item.status is BankingPrecheckReadinessStatus.READY
        )
        pending_option_ids = tuple(
            item.option_id
            for item in option_readiness
            if item.status is not BankingPrecheckReadinessStatus.READY
        )
        status = self._aggregate_status(option_readiness)
        evidence_refs = tuple(evidence[key] for key in sorted(evidence))
        readiness = BankingPrecheckReadiness(
            readiness_id=deterministic_id(
                "BPR",
                matrix.matrix_id,
                context.supplement.supplement_id if context.supplement else None,
                self._policy.policy_hash,
                tuple(
                    (item.option_id, item.status, item.failed_requirement_codes)
                    for item in option_readiness
                ),
            ),
            evaluation_case_id=matrix.evaluation_case_id,
            dataset_id=matrix.dataset_id,
            contract_id=matrix.contract_id,
            matrix_id=matrix.matrix_id,
            supplement_id=(
                context.supplement.supplement_id if context.supplement else None
            ),
            requested_amount_currency=(
                context.supplement.requested_amount_currency
                if context.supplement is not None
                else matrix.requested_amount_currency
            ),
            status=status,
            option_readiness=option_readiness,
            ready_option_ids=ready_option_ids,
            pending_option_ids=pending_option_ids,
            source_artifact_ids=context.source_artifact_ids,
            evidence_ids=tuple(item.evidence_id for item in evidence_refs),
            precheck_executed=False,
        )
        return readiness, evidence_refs

    def _assess_option(
        self,
        *,
        context: BankingPrecheckReadinessContext,
        candidate: BankingOptionCandidate,
        binding: BankingNeedBinding | None,
        lineage: LineageFactory,
        evidence: dict[str, EvidenceRef],
    ) -> BankingOptionPrecheckReadiness:
        precheck = candidate.precheck
        candidate_evidence = self._evidence_by_ids(
            context.matrix_artifact,
            candidate.evidence_ids,
        )
        self._merge_evidence(evidence, candidate_evidence)
        if precheck is None:
            return BankingOptionPrecheckReadiness(
                option_readiness_id=deterministic_id(
                    "BPRO", context.matrix.matrix_id, candidate.option_id, "NOT_CONFIGURED"
                ),
                option_id=candidate.option_id,
                bank_product_id=candidate.bank_product_id,
                status=BankingPrecheckReadinessStatus.NOT_CONFIGURED,
                precheck_executed=False,
                evidence_ids=tuple(item.evidence_id for item in candidate_evidence),
            )

        api_evidence = self._one_evidence(
            context.matrix_artifact,
            sheet=SheetRegistry.API_CATALOG.sheet_name,
            record_id=precheck.api_id,
            field="required_fields",
        )
        policy_evidence = self._policy_binding_evidence(
            context.matrix_artifact,
            binding,
        )
        baseline_evidence = self._unique_evidence(
            candidate_evidence,
            (api_evidence,),
            (policy_evidence,) if policy_evidence is not None else (),
        )
        self._merge_evidence(evidence, baseline_evidence)
        field_sources: dict[str, BankingPrecheckFieldSource] = {}
        configured_api_id = None
        if binding is not None:
            configured_api_id = binding.precheck_api_by_product.get(
                candidate.bank_product_id
            )
            field_sources = binding.precheck_field_sources_by_api.get(
                precheck.api_id,
                {},
            )
        required_fields = precheck.required_fields
        if len(set(required_fields)) != len(required_fields):
            raise BankingPrecheckReadinessBuildError(
                f"API {precheck.api_id} contains duplicate required fields."
            )
        missing_policy_fields = tuple(
            field for field in required_fields if field not in field_sources
        )
        unexpected_policy_fields = tuple(
            sorted(field for field in field_sources if field not in set(required_fields))
        )
        policy_mismatch = (
            binding is None
            or configured_api_id != precheck.api_id
            or bool(missing_policy_fields)
            or bool(unexpected_policy_fields)
        )
        resolutions = tuple(
            self._resolve_field(
                context=context,
                required_field=required_field,
                source=field_sources.get(required_field),
                api_evidence=api_evidence,
                policy_evidence=policy_evidence,
                lineage=lineage,
                evidence=evidence,
            )
            for required_field in required_fields
        )
        requirement_check = self._matrix_minimum_amount_check(
            context=context,
            candidate=candidate,
            evidence=evidence,
        )
        failed_requirement_codes = (
            (requirement_check.code,)
            if requirement_check.status is BankingCriterionStatus.FAIL
            else ()
        )
        missing_fields = tuple(
            item.required_field
            for item in resolutions
            if item.status
            in {
                BankingPrecheckFieldStatus.MISSING_INPUT,
                BankingPrecheckFieldStatus.SOURCE_UNAVAILABLE,
            }
        )
        unmapped_fields = tuple(
            item.required_field
            for item in resolutions
            if item.status is BankingPrecheckFieldStatus.UNMAPPED
        )
        if policy_mismatch or unmapped_fields:
            status = BankingPrecheckReadinessStatus.UNSUPPORTED_MAPPING
        elif failed_requirement_codes:
            status = BankingPrecheckReadinessStatus.OPTION_REQUIREMENTS_NOT_MET
        elif missing_fields:
            status = BankingPrecheckReadinessStatus.INPUT_REQUIRED
        else:
            status = BankingPrecheckReadinessStatus.READY
        referenced_ids = tuple(
            dict.fromkeys(
                (
                    *(item.evidence_id for item in baseline_evidence),
                    *(
                        evidence_id
                        for resolution in resolutions
                        for evidence_id in resolution.evidence_ids
                    ),
                    *requirement_check.evidence_ids,
                )
            )
        )
        return BankingOptionPrecheckReadiness(
            option_readiness_id=deterministic_id(
                "BPRO",
                context.matrix.matrix_id,
                candidate.option_id,
                precheck.api_id,
                context.supplement.supplement_id if context.supplement else None,
                status,
            ),
            option_id=candidate.option_id,
            bank_product_id=candidate.bank_product_id,
            api_id=precheck.api_id,
            status=status,
            required_fields=required_fields,
            field_resolutions=resolutions,
            requirement_checks=(requirement_check,),
            failed_requirement_codes=failed_requirement_codes,
            missing_fields=missing_fields,
            unmapped_fields=unmapped_fields,
            unexpected_policy_fields=unexpected_policy_fields,
            precheck_executed=False,
            evidence_ids=referenced_ids,
        )

    def _resolve_field(
        self,
        *,
        context: BankingPrecheckReadinessContext,
        required_field: str,
        source: BankingPrecheckFieldSource | None,
        api_evidence: EvidenceRef,
        policy_evidence: EvidenceRef | None,
        lineage: LineageFactory,
        evidence: dict[str, EvidenceRef],
    ) -> BankingPrecheckFieldResolution:
        common_sources = self._unique_evidence(
            (api_evidence,),
            (policy_evidence,) if policy_evidence is not None else (),
        )
        if source is None:
            return self._field_resolution(
                context=context,
                required_field=required_field,
                status=BankingPrecheckFieldStatus.UNMAPPED,
                source=None,
                source_reference=None,
                source_artifact_id=None,
                source_record_ids=(),
                source_evidence=common_sources,
                lineage=lineage,
                evidence=evidence,
            )
        if source is BankingPrecheckFieldSource.EVALUATION_CASE:
            source_evidence = self._unique_evidence(
                common_sources,
                context.evaluation_case_artifact.evidence_refs,
            )
            return self._field_resolution(
                context=context,
                required_field=required_field,
                status=BankingPrecheckFieldStatus.RESOLVED,
                source=source,
                source_reference="EvaluationCase.contract_id",
                source_artifact_id=context.evaluation_case_artifact.artifact_id,
                source_record_ids=(context.evaluation_case.contract_id,),
                source_evidence=source_evidence,
                lineage=lineage,
                evidence=evidence,
            )
        if source is BankingPrecheckFieldSource.BANKING_INPUT_SUPPLEMENT:
            supplement = context.supplement
            source_evidence = common_sources
            if supplement is not None and context.supplement_artifact is not None:
                source_evidence = self._unique_evidence(
                    common_sources,
                    self._evidence_by_ids(
                        context.supplement_artifact,
                        supplement.evidence_ids,
                    ),
                )
            return self._field_resolution(
                context=context,
                required_field=required_field,
                status=(
                    BankingPrecheckFieldStatus.RESOLVED
                    if supplement is not None
                    else BankingPrecheckFieldStatus.MISSING_INPUT
                ),
                source=source,
                source_reference="BankingInputSupplement.requested_amount",
                source_artifact_id=(
                    context.supplement_artifact.artifact_id
                    if context.supplement_artifact is not None
                    else None
                ),
                source_record_ids=(
                    (supplement.supplement_id,) if supplement is not None else ()
                ),
                source_evidence=source_evidence,
                lineage=lineage,
                evidence=evidence,
            )

        profile_valid, profile_ids, profile_evidence = self._opc_profile_source(
            context,
            lineage,
        )
        source_evidence = self._unique_evidence(common_sources, profile_evidence)
        return self._field_resolution(
            context=context,
            required_field=required_field,
            status=(
                BankingPrecheckFieldStatus.RESOLVED
                if profile_valid
                else BankingPrecheckFieldStatus.SOURCE_UNAVAILABLE
            ),
            source=source,
            source_reference="02_OPC_PROFILE[field,value]",
            source_artifact_id=None,
            source_record_ids=profile_ids if profile_valid else (),
            source_evidence=source_evidence,
            lineage=lineage,
            evidence=evidence,
        )

    @staticmethod
    def _field_resolution(
        *,
        context: BankingPrecheckReadinessContext,
        required_field: str,
        status: BankingPrecheckFieldStatus,
        source: BankingPrecheckFieldSource | None,
        source_reference: str | None,
        source_artifact_id: str | None,
        source_record_ids: tuple[str, ...],
        source_evidence: tuple[EvidenceRef, ...],
        lineage: LineageFactory,
        evidence: dict[str, EvidenceRef],
    ) -> BankingPrecheckFieldResolution:
        BankingPrecheckReadinessSkill._merge_evidence(evidence, source_evidence)
        derived = lineage.derived(
            sheet="BANKING_PRECHECK_READINESS",
            record_id=context.matrix.matrix_id,
            field=required_field,
            display={
                "status": status.value,
                "source": source.value if source is not None else None,
                "source_reference": source_reference,
            },
            sources=source_evidence,
        )
        evidence[derived.evidence_id] = derived
        return BankingPrecheckFieldResolution(
            required_field=required_field,
            status=status,
            source=source,
            source_reference=source_reference,
            source_artifact_id=source_artifact_id,
            source_record_ids=source_record_ids,
            evidence_ids=(derived.evidence_id,),
        )

    def _matrix_minimum_amount_check(
        self,
        *,
        context: BankingPrecheckReadinessContext,
        candidate: BankingOptionCandidate,
        evidence: dict[str, EvidenceRef],
    ) -> BankingCriterion:
        matches = tuple(
            item
            for item in candidate.criteria
            if item.code is BankingCriterionCode.MINIMUM_AMOUNT
        )
        if len(matches) != 1:
            raise BankingPrecheckReadinessBuildError(
                f"Option {candidate.option_id} must contain one minimum-amount criterion."
            )
        criterion = matches[0]
        if context.supplement is None:
            allowed = {BankingCriterionStatus.NOT_EVALUABLE}
        else:
            allowed = {
                BankingCriterionStatus.PASS,
                BankingCriterionStatus.FAIL,
                BankingCriterionStatus.NOT_APPLICABLE,
            }
        if criterion.status not in allowed:
            raise BankingPrecheckReadinessBuildError(
                f"Option {candidate.option_id} has an inconsistent minimum-amount status."
            )
        criterion_evidence = self._evidence_by_ids(
            context.matrix_artifact,
            criterion.evidence_ids,
        )
        self._merge_evidence(evidence, criterion_evidence)
        return criterion

    @staticmethod
    def _aggregate_status(
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
    def _opc_profile_source(
        context: BankingPrecheckReadinessContext,
        lineage: LineageFactory,
    ) -> tuple[bool, tuple[str, ...], tuple[EvidenceRef, ...]]:
        records = context.opc_profile_records
        record_ids = tuple(record.record_id for record in records)
        evidence = tuple(
            lineage.record_field(record, field)
            for record in records
            for field in ("field", "value")
        )
        valid = bool(records) and len(set(record_ids)) == len(record_ids) and all(
            isinstance(record.values.get("field"), str)
            and record.values.get("field") == record.record_id
            for record in records
        )
        return valid, record_ids, evidence

    @staticmethod
    def _upstream_evidence(
        context: BankingPrecheckReadinessContext,
    ) -> dict[str, EvidenceRef]:
        artifacts: tuple[ArtifactEnvelope, ...] = (
            context.evaluation_case_artifact,
            context.matrix_artifact,
            *(
                (context.supplement_artifact,)
                if context.supplement_artifact is not None
                else ()
            ),
        )
        return {
            item.evidence_id: item
            for artifact in artifacts
            for item in artifact.evidence_refs
        }

    @staticmethod
    def _policy_binding_evidence(
        artifact: ArtifactEnvelope,
        binding: BankingNeedBinding | None,
    ) -> EvidenceRef | None:
        if binding is None:
            return None
        matches = tuple(
            item
            for item in artifact.evidence_refs
            if item.sheet == "BANKING_CATALOG_POLICY"
            and item.record_id == binding.binding_id
            and item.field == "explicit_catalog_binding"
        )
        if len(matches) != 1:
            raise BankingPrecheckReadinessBuildError(
                f"Matrix is missing exact policy evidence for {binding.binding_id}."
            )
        return matches[0]

    @staticmethod
    def _one_evidence(
        artifact: ArtifactEnvelope,
        *,
        sheet: str,
        record_id: str,
        field: str,
    ) -> EvidenceRef:
        matches = tuple(
            item
            for item in artifact.evidence_refs
            if item.sheet == sheet
            and item.record_id == record_id
            and item.field == field
        )
        if len(matches) != 1:
            raise BankingPrecheckReadinessBuildError(
                f"Expected one evidence item for {sheet}.{record_id}.{field}."
            )
        return matches[0]

    @staticmethod
    def _evidence_by_ids(
        artifact: ArtifactEnvelope,
        evidence_ids: Iterable[str],
    ) -> tuple[EvidenceRef, ...]:
        by_id = {item.evidence_id: item for item in artifact.evidence_refs}
        requested = tuple(evidence_ids)
        missing = tuple(item for item in requested if item not in by_id)
        if missing:
            raise BankingPrecheckReadinessBuildError(
                "Artifact is missing referenced evidence: " + ", ".join(missing)
            )
        return tuple(by_id[item] for item in requested)

    @staticmethod
    def _merge_evidence(
        target: dict[str, EvidenceRef], source: Iterable[EvidenceRef]
    ) -> None:
        target.update((item.evidence_id, item) for item in source)

    @staticmethod
    def _unique_evidence(
        *groups: Iterable[EvidenceRef],
    ) -> tuple[EvidenceRef, ...]:
        by_id = {item.evidence_id: item for group in groups for item in group}
        return tuple(by_id[key] for key in sorted(by_id))
