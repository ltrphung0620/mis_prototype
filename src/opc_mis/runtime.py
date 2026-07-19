"""Application composition root for the persisted OPC MIS workflow."""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Mapping
from datetime import UTC, date, datetime
from pathlib import Path

from opc_mis.business.agents.decision.analysis_component import DecisionAnalysisAgent
from opc_mis.business.agents.decision.analysis_context import (
    DecisionAnalysisContextLoader,
)
from opc_mis.business.agents.decision.banking_handoff_component import (
    DecisionBankingHandoff,
)
from opc_mis.business.agents.decision.banking_handoff_context import (
    BankingHandoffContextLoader,
)
from opc_mis.business.agents.decision.card_component import DecisionCardAssembler
from opc_mis.business.agents.decision.card_context import DecisionCardContextLoader
from opc_mis.business.agents.decision.component import DecisionInitialRoutePlanner
from opc_mis.business.agents.decision.context_loader import DecisionRouteContextLoader
from opc_mis.business.agents.decision.document_handoff_component import (
    DecisionDocumentHandoff,
)
from opc_mis.business.agents.decision.document_handoff_context import (
    DecisionDocumentHandoffContextLoader,
)
from opc_mis.business.agents.decision.internal_package_component import (
    InternalDecisionPackageAssembler,
)
from opc_mis.business.agents.decision.internal_package_context import (
    InternalDecisionPackageContextLoader,
)
from opc_mis.business.agents.decision.post_banking_component import (
    DecisionPostBankingReviewer,
)
from opc_mis.business.agents.decision.post_banking_context import (
    DecisionPostBankingContextLoader,
)
from opc_mis.business.agents.decision.post_decision_component import (
    ExternalDocumentSubmissionProposalComponent,
    ExternalSubmissionReadinessComponent,
    PostDecisionUpdateComponent,
)
from opc_mis.business.agents.decision.post_decision_context import (
    ApprovedDecisionCardContextLoader,
    ExternalReleaseProposalContextLoader,
    ExternalSubmissionReadinessContextLoader,
)
from opc_mis.business.agents.decision.post_precheck_component import (
    DecisionPostPrecheckReviewer,
)
from opc_mis.business.agents.decision.post_precheck_context import (
    DecisionPostPrecheckContextLoader,
)
from opc_mis.business.agents.decision.post_precheck_evidence_component import (
    BankingPrecheckEvidenceIntake,
)
from opc_mis.business.agents.finance.component import FinanceAgent
from opc_mis.business.agents.finance.context_loader import FinanceContextLoader
from opc_mis.business.agents.risk.component import RiskAgent
from opc_mis.business.agents.risk.context_loader import RiskContextLoader
from opc_mis.business.agents.risk.final_component import FinalRiskCheck
from opc_mis.business.agents.risk.final_context_loader import FinalRiskContextLoader
from opc_mis.business.skills.banking.advisor_component import (
    BankingOptionAdvisorSkill,
)
from opc_mis.business.skills.banking.advisor_context import (
    BankingAdvisorContextLoader,
)
from opc_mis.business.skills.banking.component import BankingDiscoverySkill
from opc_mis.business.skills.banking.context_loader import (
    BankingDiscoveryContextLoader,
)
from opc_mis.business.skills.banking.input_component import BankingAmountInputIntake
from opc_mis.business.skills.banking.precheck_readiness_component import (
    BankingPrecheckReadinessSkill,
)
from opc_mis.business.skills.banking.precheck_readiness_context import (
    BankingPrecheckReadinessContextLoader,
)
from opc_mis.business.skills.banking.precheck_request_resolver import (
    BankingPrecheckRequestResolver,
)
from opc_mis.business.skills.banking.precheck_result_component import (
    BankingPrecheckResultComponent,
)
from opc_mis.business.skills.banking.precheck_result_context import (
    BankingPrecheckResultContextLoader,
)
from opc_mis.business.skills.banking.precheck_submission_component import (
    BankingPrecheckSubmissionProposalSkill,
)
from opc_mis.business.skills.banking.precheck_submission_context import (
    BankingPrecheckSubmissionProposalContextLoader,
)
from opc_mis.business.skills.document import (
    DocumentContextLoader,
    DocumentEvidenceIntake,
    DocumentPackageBuilder,
    DocumentSkill,
)
from opc_mis.business.skills.operations.component import OperationsSkill
from opc_mis.business.skills.operations.context_loader import OperationsContextLoader
from opc_mis.business.skills.planner.component import PlannerSkill
from opc_mis.config import AppSettings
from opc_mis.domain.approvals import (
    ApprovalCheckpointSet,
    ApprovalDecision,
    ApprovalExecutionResult,
    ApprovalRequest,
)
from opc_mis.domain.artifacts import ArtifactEnvelope
from opc_mis.domain.banking_input_models import (
    BankingAmountInputCommand,
    BankingAmountInputSubmission,
    BankingInputExecutionResult,
)
from opc_mis.domain.banking_models import (
    BankingDiscoveryExecutionResult,
    BankingDiscoveryHandoffExecutionResult,
    BankingOptionMatrix,
    BankingPrecheckReadiness,
    BankingPrecheckReadinessExecutionResult,
)
from opc_mis.domain.banking_precheck_evidence_models import (
    BankingPrecheckEvidenceCommand,
    BankingPrecheckEvidenceExecutionResult,
    BankingPrecheckEvidenceSubmission,
    BankingPrecheckEvidenceSupplement,
)
from opc_mis.domain.banking_precheck_execution_models import (
    BankingPrecheckResultExecutionResult,
    BankingPrecheckResultSet,
)
from opc_mis.domain.banking_precheck_submission_models import (
    BankingPrecheckSubmissionProposal,
    BankingPrecheckSubmissionProposalExecutionResult,
    banking_precheck_action_payload,
)
from opc_mis.domain.case_workflow_models import (
    CaseWorkflowRun,
    WorkflowEvent,
    WorkflowRunSummary,
    WorkflowStartResult,
)
from opc_mis.domain.commands import ActionCommand
from opc_mis.domain.components import ExecutionContext
from opc_mis.domain.dataset import DatasetSnapshot
from opc_mis.domain.decision_models import (
    DecisionAnalysisExecutionResult,
    DecisionCard,
    DecisionCardExecutionResult,
    DecisionRecommendation,
)
from opc_mis.domain.decision_post_banking_models import (
    DecisionPostBankingExecutionResult,
    DecisionPostBankingReview,
)
from opc_mis.domain.decision_post_precheck_models import (
    DecisionPostPrecheckExecutionResult,
    DecisionPostPrecheckReview,
)
from opc_mis.domain.decision_route_models import (
    DecisionRouteExecutionResult,
    DecisionRoutePlan,
)
from opc_mis.domain.document_models import (
    DecisionDocumentHandoffExecutionResult,
    DocumentEvidenceCommand,
    DocumentEvidenceExecutionResult,
    DocumentEvidenceSubmission,
    DocumentEvidenceSupplement,
    DocumentPackageDraft,
    DocumentPreparationRequest,
    DocumentSkillExecutionResult,
)
from opc_mis.domain.enums import (
    ArtifactType,
    BankingDiscoveryStatus,
    ComponentStatus,
    CurrencyCode,
    DecisionHandoffMode,
    DecisionPostBankingOutcome,
    DecisionPostPrecheckOutcome,
    DecisionRouteMode,
    DecisionRouteOutcome,
    EvaluationScope,
    ProtectedAction,
    RiskRunStatus,
    ValidationStatus,
    WorkflowNodeStatus,
    WorkflowStatus,
)
from opc_mis.domain.final_risk_models import FinalRiskExecutionResult
from opc_mis.domain.finance_models import FinanceExecutionResult
from opc_mis.domain.internal_decision_package_models import (
    InternalDecisionAssemblyPath,
    InternalDecisionPackageExecutionResult,
)
from opc_mis.domain.lineage import deterministic_id
from opc_mis.domain.masking_models import MaskableScalar, MaskedPayload
from opc_mis.domain.operations_models import OperationsExecutionResult
from opc_mis.domain.planner_models import EvaluationCase, PlannerExecutionResult
from opc_mis.domain.post_decision_models import (
    ExternalDocumentSubmissionProposal,
    ExternalDocumentSubmissionProposalExecutionResult,
    ExternalSubmissionReadinessExecutionResult,
    PostDecisionUpdate,
    PostDecisionUpdateExecutionResult,
    external_document_release_action_payload,
    final_decision_action_payload,
)
from opc_mis.domain.risk_models import (
    InitialRiskAssessment,
    RiskExecutionResult,
    RiskPreScan,
    RiskRuleEvaluationSet,
)
from opc_mis.domain.team_pack import SheetRegistry
from opc_mis.domain.workflow import WorkflowNode
from opc_mis.governance.authorized_action import AuthorizedActionPermitIssuer
from opc_mis.governance.evidence_validator import EvidenceValidator
from opc_mis.governance.masking_policy import MaskingPolicy
from opc_mis.infrastructure.banking.simulated_precheck_adapter import (
    SimulatedBankingPrecheckAdapter,
)
from opc_mis.infrastructure.config.banking_catalog_policy import (
    BankingCatalogPolicyLoader,
)
from opc_mis.infrastructure.config.banking_precheck_simulation_policy import (
    BankingPrecheckSimulationPolicyLoader,
)
from opc_mis.infrastructure.config.decision_governance_policy import (
    DecisionGovernancePolicyLoader,
)
from opc_mis.infrastructure.config.masking_policy_loader import MaskingPolicyLoader
from opc_mis.infrastructure.excel.dataset_adapter import ExcelDatasetIngestion
from opc_mis.infrastructure.openai.banking_fallback import (
    DeterministicBankingOptionAdvisor,
)
from opc_mis.infrastructure.openai.banking_option_advisor import (
    OpenAIBankingOptionAdvisor,
    ResilientBankingOptionAdvisor,
)
from opc_mis.infrastructure.openai.client import create_openai_client
from opc_mis.infrastructure.openai.decision_composer import (
    OpenAIDecisionAnalysisComposer,
    ResilientDecisionAnalysisComposer,
)
from opc_mis.infrastructure.openai.decision_fallback import (
    DeterministicDecisionAnalysisComposer,
)
from opc_mis.infrastructure.openai.fallback import DeterministicFinanceNarrativeComposer
from opc_mis.infrastructure.openai.finance_composer import (
    OpenAIFinanceNarrativeComposer,
    ResilientFinanceNarrativeComposer,
)
from opc_mis.infrastructure.persistence.memory_dataset_repository import (
    InMemoryDatasetRepository,
)
from opc_mis.infrastructure.persistence.sqlite_approval_request_repository import (
    SQLiteApprovalRequestRepository,
)
from opc_mis.infrastructure.persistence.sqlite_artifact_repository import (
    SQLiteArtifactRepository,
)
from opc_mis.infrastructure.persistence.sqlite_database import SQLiteDatabase
from opc_mis.infrastructure.persistence.sqlite_risk_state_repository import (
    SQLiteRiskStateRepository,
)
from opc_mis.infrastructure.persistence.sqlite_runtime_event_repository import (
    SQLiteRuntimeEventRepository,
)
from opc_mis.infrastructure.persistence.sqlite_workflow_repository import (
    SQLiteCaseWorkflowRepository,
    SQLiteWorkflowStateRepository,
)
from opc_mis.infrastructure.security.free_text_redactor import (
    DeterministicFreeTextRedactor,
)
from opc_mis.infrastructure.security.hmac_tokenizer import HmacContextualTokenizer
from opc_mis.ports.masking_service import MaskingService
from opc_mis.workflow.approval_orchestrator import (
    ApprovalConflictError,
    ApprovalOrchestrator,
)
from opc_mis.workflow.banking_discovery_orchestrator import (
    BankingDiscoveryOrchestrator,
)
from opc_mis.workflow.banking_input_orchestrator import BankingInputOrchestrator
from opc_mis.workflow.banking_precheck_evidence_orchestrator import (
    BankingPrecheckEvidenceOrchestrator,
)
from opc_mis.workflow.banking_precheck_execution_orchestrator import (
    BankingPrecheckExecutionOrchestrator,
)
from opc_mis.workflow.banking_precheck_policy_orchestrator import (
    BankingPrecheckPolicyOrchestrator,
)
from opc_mis.workflow.banking_precheck_readiness_orchestrator import (
    BankingPrecheckReadinessOrchestrator,
)
from opc_mis.workflow.banking_precheck_submission_orchestrator import (
    BankingPrecheckSubmissionProposalOrchestrator,
)
from opc_mis.workflow.case_workflow_orchestrator import CaseWorkflowOrchestrator
from opc_mis.workflow.decision_analysis_orchestrator import (
    DecisionAnalysisOrchestrator,
)
from opc_mis.workflow.decision_approval_policy_orchestrator import (
    DecisionApprovalPolicyOrchestrator,
)
from opc_mis.workflow.decision_banking_handoff_orchestrator import (
    DecisionBankingHandoffOrchestrator,
)
from opc_mis.workflow.decision_document_handoff_orchestrator import (
    DecisionDocumentHandoffOrchestrator,
)
from opc_mis.workflow.decision_post_banking_orchestrator import (
    DecisionPostBankingOrchestrator,
)
from opc_mis.workflow.decision_post_precheck_orchestrator import (
    DecisionPostPrecheckOrchestrator,
)
from opc_mis.workflow.decision_route_orchestrator import DecisionRouteOrchestrator
from opc_mis.workflow.document_evidence_orchestrator import (
    DocumentEvidenceOrchestrator,
)
from opc_mis.workflow.document_orchestrator import DocumentOrchestrator
from opc_mis.workflow.final_risk_orchestrator import FinalRiskOrchestrator
from opc_mis.workflow.finance_orchestrator import FinanceAssessmentOrchestrator
from opc_mis.workflow.internal_decision_package_orchestrator import (
    InternalDecisionPackageOrchestrator,
)
from opc_mis.workflow.operations_orchestrator import OperationsAssessmentOrchestrator
from opc_mis.workflow.orchestrator import PlannerIntakeOrchestrator
from opc_mis.workflow.post_decision_orchestrator import PostDecisionOrchestrator
from opc_mis.workflow.risk_orchestrator import RiskAssessmentOrchestrator
from opc_mis.workflow.workflow_runner import WorkflowRunner


class FinanceCaseNotFoundError(LookupError):
    """Raised when Finance is requested before a completed Planner case exists."""


class OperationsCaseNotFoundError(LookupError):
    """Raised when Operations is requested before a completed Planner case exists."""


class RiskCaseNotFoundError(LookupError):
    """Raised when Risk is requested before Planner or before a scan exists."""


class DecisionRouteCaseNotFoundError(LookupError):
    """Raised when Decision Initial Route has no Planner evaluation case."""


class DecisionHandoffCaseNotFoundError(LookupError):
    """Raised when Decision Banking handoff has no Planner evaluation case."""


class BankingDiscoveryCaseNotFoundError(LookupError):
    """Raised when Banking discovery has no Planner evaluation case."""


class BankingPrecheckCaseNotFoundError(LookupError):
    """Raised when Banking readiness has no validated matrix or case."""


class DecisionPostBankingCaseNotFoundError(LookupError):
    """Raised when post-Banking Decision review has no readiness inputs."""


class DecisionPostPrecheckCaseNotFoundError(LookupError):
    """Raised when Decision cannot resolve an exact precheck result/proposal pair."""


class BankingPrecheckSubmissionCaseNotFoundError(LookupError):
    """Raised when a governed Banking proposal has no complete validated context."""


class DocumentCaseNotFoundError(LookupError):
    """Raised when Decision or Document inputs cannot be resolved exactly."""


class InternalDecisionPackageCaseNotFoundError(LookupError):
    """Raised when exact package assembly inputs cannot be resolved."""


class FinalDecisionCaseNotFoundError(LookupError):
    """Raised when final Decision or post-Decision inputs cannot be resolved."""


class _UnavailableMaskingService:
    """Fail closed when the server has no configured HMAC key material."""

    def mask_payload(
        self,
        payload: Mapping[str, MaskableScalar],
        *,
        recipient: str,
        purpose: str,
        required_fields: Collection[str],
        source_evidence_ids_by_field: Mapping[str, Collection[str]],
    ) -> MaskedPayload:
        del (
            payload,
            recipient,
            purpose,
            required_fields,
            source_evidence_ids_by_field,
        )
        raise ValueError(
            "Outbound Document masking is unavailable because the server HMAC key "
            "is not configured."
        )


class PlannerRuntime:
    """Compose adapters and expose application services to CLI/API interfaces."""

    def __init__(
        self,
        *,
        workbook_path: Path,
        dataset_id: str,
        settings: AppSettings | None = None,
        database_path: Path | str | None = None,
    ) -> None:
        self.workbook_path = workbook_path.resolve()
        self.dataset_id = dataset_id
        resolved_settings = settings or AppSettings.from_environment()
        self._decision_governance_policy = DecisionGovernancePolicyLoader().load(
            resolved_settings.decision_governance_policy_path
        )
        self._masking_policy_configuration = MaskingPolicyLoader().load(
            resolved_settings.masking_policy_path
        )
        token_rules = tuple(
            item
            for item in self._masking_policy_configuration.document.masking_rules
            if item.key_version is not None
        )
        key_versions = tuple(dict.fromkeys(item.key_version for item in token_rules))
        token_sizes = tuple(dict.fromkeys(item.token_bytes for item in token_rules))
        if len(key_versions) != 1 or len(token_sizes) != 1:
            raise ValueError(
                "Document tokenization policy requires one explicit key version and size."
            )
        self._document_tokenizer_key_version = key_versions[0]
        document_masking_verification_service: MaskingService | None
        if resolved_settings.masking_hmac_key is None:
            document_masking_service = _UnavailableMaskingService()
            document_masking_verification_service = None
        else:
            configured_masking_service = MaskingPolicy(
                document=self._masking_policy_configuration.document,
                tokenizer=HmacContextualTokenizer(
                    secret_key=resolved_settings.masking_hmac_key,
                    token_bytes=token_sizes[0],
                ),
                redactor=DeterministicFreeTextRedactor(),
            )
            document_masking_service = configured_masking_service
            document_masking_verification_service = configured_masking_service
        self._banking_policy = BankingCatalogPolicyLoader().load(
            resolved_settings.banking_catalog_policy_path
        )
        self._banking_precheck_simulation_policy = (
            BankingPrecheckSimulationPolicyLoader().load(
                resolved_settings.banking_precheck_simulation_policy_path
            )
        )
        self._database = SQLiteDatabase(database_path or resolved_settings.database_path)
        self._datasets = InMemoryDatasetRepository()
        self._artifacts = SQLiteArtifactRepository(self._database)
        self._workflows = SQLiteWorkflowStateRepository(self._database)
        self._case_workflows = SQLiteCaseWorkflowRepository(self._database)
        self._risk_states = SQLiteRiskStateRepository(self._database)
        self._approval_requests = SQLiteApprovalRequestRepository(self._database)
        self._runtime_events = SQLiteRuntimeEventRepository(self._database)
        self._ingestion = ExcelDatasetIngestion(self._datasets)
        self._orchestrator = PlannerIntakeOrchestrator(
            planner=PlannerSkill(dataset_port=self._datasets),
            artifact_repository=self._artifacts,
            workflow_repository=self._workflows,
        )
        fallback = DeterministicFinanceNarrativeComposer()
        if resolved_settings.openai_enabled and resolved_settings.openai_api_key:
            primary = OpenAIFinanceNarrativeComposer(
                client=create_openai_client(
                    api_key=resolved_settings.openai_api_key,
                    timeout_seconds=resolved_settings.openai_timeout_seconds,
                    max_retries=resolved_settings.openai_max_retries,
                ),
                model=resolved_settings.openai_model,
                prompt_path=resolved_settings.finance_prompt_path,
                prompt_version=resolved_settings.finance_prompt_version,
            )
            narrative_composer = ResilientFinanceNarrativeComposer(primary, fallback)
        else:
            narrative_composer = fallback
        self._finance_orchestrator = FinanceAssessmentOrchestrator(
            finance=FinanceAgent(
                context_loader=FinanceContextLoader(
                    datasets=self._datasets,
                    artifacts=self._artifacts,
                ),
                narrative_composer=narrative_composer,
            ),
            artifacts=self._artifacts,
        )
        self._operations_orchestrator = OperationsAssessmentOrchestrator(
            operations=OperationsSkill(
                context_loader=OperationsContextLoader(
                    datasets=self._datasets,
                    artifacts=self._artifacts,
                )
            ),
            artifacts=self._artifacts,
        )
        self._risk_orchestrator = RiskAssessmentOrchestrator(
            risk=RiskAgent(
                context_loader=RiskContextLoader(
                    datasets=self._datasets,
                    artifacts=self._artifacts,
                )
            ),
            artifacts=self._artifacts,
            states=self._risk_states,
        )
        self._decision_route_orchestrator = DecisionRouteOrchestrator(
            planner=DecisionInitialRoutePlanner(
                context_loader=DecisionRouteContextLoader(artifacts=self._artifacts)
            ),
            artifacts=self._artifacts,
        )
        self._decision_banking_handoff_orchestrator = (
            DecisionBankingHandoffOrchestrator(
                handoff=DecisionBankingHandoff(
                    context_loader=BankingHandoffContextLoader(
                        artifacts=self._artifacts
                    )
                ),
                artifacts=self._artifacts,
            )
        )
        banking_fallback = DeterministicBankingOptionAdvisor()
        if resolved_settings.openai_enabled and resolved_settings.openai_api_key:
            banking_advisor_mode = "OPENAI_WITH_DETERMINISTIC_FALLBACK"
            banking_primary = OpenAIBankingOptionAdvisor(
                client=create_openai_client(
                    api_key=resolved_settings.openai_api_key,
                    timeout_seconds=resolved_settings.openai_timeout_seconds,
                    max_retries=resolved_settings.openai_max_retries,
                ),
                model=resolved_settings.openai_model,
                prompt_path=resolved_settings.banking_prompt_path,
                prompt_version=resolved_settings.banking_prompt_version,
            )
            banking_advisor = ResilientBankingOptionAdvisor(
                banking_primary, banking_fallback
            )
        else:
            banking_advisor_mode = "DETERMINISTIC_FALLBACK"
            banking_advisor = banking_fallback
        self._banking_advisor_configuration_hash = deterministic_id(
            "BACFG",
            banking_advisor_mode,
            (
                resolved_settings.openai_model
                if banking_advisor_mode == "OPENAI_WITH_DETERMINISTIC_FALLBACK"
                else banking_fallback.model_name
            ),
            (
                resolved_settings.banking_prompt_version
                if banking_advisor_mode == "OPENAI_WITH_DETERMINISTIC_FALLBACK"
                else banking_fallback.prompt_version
            ),
        )
        self._banking_discovery_orchestrator = BankingDiscoveryOrchestrator(
            discovery=BankingDiscoverySkill(
                context_loader=BankingDiscoveryContextLoader(
                    datasets=self._datasets,
                    artifacts=self._artifacts,
                ),
                policy=self._banking_policy,
            ),
            advisor=BankingOptionAdvisorSkill(
                context_loader=BankingAdvisorContextLoader(
                    artifacts=self._artifacts
                ),
                advisor=banking_advisor,
            ),
            artifacts=self._artifacts,
            policy=self._banking_policy,
            advisor_configuration_hash=self._banking_advisor_configuration_hash,
        )
        self._banking_precheck_readiness_orchestrator = (
            BankingPrecheckReadinessOrchestrator(
                readiness=BankingPrecheckReadinessSkill(
                    context_loader=BankingPrecheckReadinessContextLoader(
                        datasets=self._datasets,
                        artifacts=self._artifacts,
                    ),
                    policy=self._banking_policy,
                ),
                artifacts=self._artifacts,
                policy=self._banking_policy,
            )
        )
        self._decision_post_banking_orchestrator = DecisionPostBankingOrchestrator(
            reviewer=DecisionPostBankingReviewer(
                context_loader=DecisionPostBankingContextLoader(
                    artifacts=self._artifacts
                )
            ),
            artifacts=self._artifacts,
        )
        self._banking_precheck_submission_proposal_orchestrator = (
            BankingPrecheckSubmissionProposalOrchestrator(
                proposer=BankingPrecheckSubmissionProposalSkill(
                    context_loader=BankingPrecheckSubmissionProposalContextLoader(
                        artifacts=self._artifacts
                    )
                ),
                artifacts=self._artifacts,
                policy=self._banking_policy,
            )
        )
        self._banking_precheck_adapter = SimulatedBankingPrecheckAdapter(
            policy=self._banking_precheck_simulation_policy
        )
        self._banking_precheck_execution_orchestrator = (
            BankingPrecheckExecutionOrchestrator(
                result_component=BankingPrecheckResultComponent(
                    context_loader=BankingPrecheckResultContextLoader(
                        artifacts=self._artifacts
                    )
                ),
                request_resolver=BankingPrecheckRequestResolver(),
                permit_issuer=AuthorizedActionPermitIssuer(
                    artifacts=self._artifacts,
                    approval_requests=self._approval_requests,
                ),
                adapter=self._banking_precheck_adapter,
                datasets=self._datasets,
                artifacts=self._artifacts,
                evidence_validator=EvidenceValidator(
                    banking_policy=self._banking_policy,
                    banking_precheck_simulation_policy=(
                        self._banking_precheck_simulation_policy
                    ),
                ),
            )
        )
        self._decision_post_precheck_orchestrator = DecisionPostPrecheckOrchestrator(
            reviewer=DecisionPostPrecheckReviewer(
                context_loader=DecisionPostPrecheckContextLoader(
                    artifacts=self._artifacts
                )
            ),
            artifacts=self._artifacts,
        )
        self._decision_document_handoff_orchestrator = (
            DecisionDocumentHandoffOrchestrator(
                handoff=DecisionDocumentHandoff(
                    context_loader=DecisionDocumentHandoffContextLoader(
                        artifacts=self._artifacts
                    )
                ),
                artifacts=self._artifacts,
            )
        )
        self._document_orchestrator = DocumentOrchestrator(
            document=DocumentSkill(
                context_loader=DocumentContextLoader(
                    datasets=self._datasets,
                    artifacts=self._artifacts,
                ),
                package_builder=DocumentPackageBuilder(
                    masking_service=document_masking_service,
                    required_profile_fields=("company_id", "company_name"),
                ),
            ),
            artifacts=self._artifacts,
            evidence_validator=EvidenceValidator(
                masking_policy=self._masking_policy_configuration.document,
                masking_service=document_masking_verification_service,
            ),
        )
        self._document_evidence_orchestrator = DocumentEvidenceOrchestrator(
            intake=DocumentEvidenceIntake(
                artifacts=self._artifacts,
                redactor=DeterministicFreeTextRedactor(),
            ),
            artifacts=self._artifacts,
        )
        self._banking_precheck_evidence_orchestrator = (
            BankingPrecheckEvidenceOrchestrator(
                intake=BankingPrecheckEvidenceIntake(artifacts=self._artifacts),
                artifacts=self._artifacts,
            )
        )
        self._banking_input_orchestrator = BankingInputOrchestrator(
            intake=BankingAmountInputIntake(artifacts=self._artifacts),
            artifacts=self._artifacts,
        )
        self._approval_orchestrator = ApprovalOrchestrator(
            artifacts=self._artifacts,
            requests=self._approval_requests,
            case_workflows=self._case_workflows,
            events=self._runtime_events,
        )
        self._banking_precheck_policy_orchestrator = (
            BankingPrecheckPolicyOrchestrator(artifacts=self._artifacts)
        )
        self._internal_decision_package_orchestrator = (
            InternalDecisionPackageOrchestrator(
                assembler=InternalDecisionPackageAssembler(
                    context_loader=InternalDecisionPackageContextLoader(
                        artifacts=self._artifacts,
                        approvals=self._approval_requests,
                    )
                ),
                artifacts=self._artifacts,
                evidence_validator=EvidenceValidator(),
            )
        )
        self._final_risk_orchestrator = FinalRiskOrchestrator(
            final_risk=FinalRiskCheck(
                context_loader=FinalRiskContextLoader(artifacts=self._artifacts)
            ),
            artifacts=self._artifacts,
            evidence_validator=EvidenceValidator(),
        )
        decision_fallback = DeterministicDecisionAnalysisComposer()
        if resolved_settings.openai_enabled and resolved_settings.openai_api_key:
            decision_mode = "OPENAI_WITH_DETERMINISTIC_FALLBACK"
            decision_prompt = resolved_settings.decision_prompt_path.read_text(
                encoding="utf-8"
            )
            decision_primary = OpenAIDecisionAnalysisComposer(
                client=create_openai_client(
                    api_key=resolved_settings.openai_api_key,
                    timeout_seconds=resolved_settings.openai_timeout_seconds,
                    max_retries=resolved_settings.openai_max_retries,
                ),
                model=resolved_settings.openai_model,
                prompt_path=resolved_settings.decision_prompt_path,
                prompt_version=resolved_settings.decision_prompt_version,
            )
            decision_composer = ResilientDecisionAnalysisComposer(
                decision_primary, decision_fallback
            )
            decision_model = resolved_settings.openai_model
            decision_prompt_version = resolved_settings.decision_prompt_version
        else:
            decision_mode = "DETERMINISTIC_FALLBACK"
            decision_prompt = ""
            decision_composer = decision_fallback
            decision_model = decision_fallback.model_name
            decision_prompt_version = decision_fallback.prompt_version
        self._decision_analysis_configuration_hash = deterministic_id(
            "DACFG",
            decision_mode,
            decision_model,
            decision_prompt_version,
            decision_prompt,
        )
        self._decision_analysis_orchestrator = DecisionAnalysisOrchestrator(
            analysis_agent=DecisionAnalysisAgent(
                context_loader=DecisionAnalysisContextLoader(
                    artifacts=self._artifacts
                ),
                composer=decision_composer,
            ),
            card_assembler=DecisionCardAssembler(
                context_loader=DecisionCardContextLoader(
                    artifacts=self._artifacts
                )
            ),
            artifacts=self._artifacts,
            evidence_validator=EvidenceValidator(),
        )
        self._decision_approval_policy_orchestrator = (
            DecisionApprovalPolicyOrchestrator(
                artifacts=self._artifacts,
                policy=self._decision_governance_policy,
                validator=EvidenceValidator(),
            )
        )
        self._post_decision_orchestrator = PostDecisionOrchestrator(
            update_component=PostDecisionUpdateComponent(
                context_loader=ApprovedDecisionCardContextLoader(
                    artifacts=self._artifacts,
                    approvals=self._approval_requests,
                )
            ),
            proposal_component=ExternalDocumentSubmissionProposalComponent(
                context_loader=ExternalReleaseProposalContextLoader(
                    artifacts=self._artifacts
                )
            ),
            readiness_component=ExternalSubmissionReadinessComponent(
                context_loader=ExternalSubmissionReadinessContextLoader(
                    artifacts=self._artifacts,
                    approvals=self._approval_requests,
                )
            ),
            artifacts=self._artifacts,
            evidence_validator=EvidenceValidator(),
        )
        self._case_workflow_orchestrator = CaseWorkflowOrchestrator(
            services=self,
            workflows=self._case_workflows,
            artifacts=self._artifacts,
            approvals=self._approval_requests,
            events=self._runtime_events,
        )
        self._workflow_runner = WorkflowRunner(
            orchestrator=self._case_workflow_orchestrator,
            workflows=self._case_workflows,
        )
        self._runner_started = False
        self._risk_locks: dict[str, asyncio.Lock] = {}
        self._decision_route_locks: dict[str, asyncio.Lock] = {}
        self._decision_handoff_locks: dict[str, asyncio.Lock] = {}
        self._banking_discovery_locks: dict[str, asyncio.Lock] = {}
        self._banking_precheck_locks: dict[str, asyncio.Lock] = {}
        self._decision_post_banking_locks: dict[str, asyncio.Lock] = {}
        self._banking_precheck_submission_locks: dict[str, asyncio.Lock] = {}
        self._banking_precheck_execution_locks: dict[str, asyncio.Lock] = {}
        self._decision_post_precheck_locks: dict[str, asyncio.Lock] = {}
        self._decision_document_handoff_locks: dict[str, asyncio.Lock] = {}
        self._document_locks: dict[str, asyncio.Lock] = {}
        self._internal_decision_package_locks: dict[str, asyncio.Lock] = {}
        self._final_risk_locks: dict[str, asyncio.Lock] = {}
        self._decision_analysis_locks: dict[str, asyncio.Lock] = {}
        self._decision_card_locks: dict[str, asyncio.Lock] = {}
        self._post_decision_locks: dict[str, asyncio.Lock] = {}
        self._external_submission_locks: dict[str, asyncio.Lock] = {}
        self._document_evidence_locks: dict[str, asyncio.Lock] = {}
        self._document_evidence_submission_locks: dict[str, asyncio.Lock] = {}
        self._banking_input_locks: dict[str, asyncio.Lock] = {}
        self._banking_input_submission_locks: dict[str, asyncio.Lock] = {}
        self._banking_precheck_evidence_locks: dict[str, asyncio.Lock] = {}
        self._banking_precheck_evidence_submission_locks: dict[
            str, asyncio.Lock
        ] = {}
        self._snapshot: DatasetSnapshot | None = None

    async def startup(self, *, start_runner: bool = False) -> None:
        """Ingest and register the configured read-only TeamPack once."""
        await self._database.initialize()
        if self._snapshot is None:
            self._snapshot = await self._ingestion.ingest(
                dataset_id=self.dataset_id,
                workbook_path=self.workbook_path,
            )
        if start_runner and not self._runner_started:
            await self._workflow_runner.start(
                dataset_id=self.dataset_id,
                dataset_snapshot_hash=self.snapshot_hash,
            )
            self._runner_started = True

    async def shutdown(self) -> None:
        """Stop background execution before closing durable persistence."""
        if self._runner_started:
            await self._workflow_runner.stop()
            self._runner_started = False
        await self._database.close()

    def contract_ids(self) -> tuple[str, ...]:
        """Return exact contract IDs available in the configured snapshot."""
        snapshot = self._require_snapshot()
        return tuple(record.record_id for record in snapshot.records(SheetRegistry.CONTRACTS))

    @property
    def snapshot_hash(self) -> str:
        """Expose the active snapshot hash for API diagnostics."""
        return self._require_snapshot().snapshot_hash

    @property
    def banking_policy_hash(self) -> str:
        """Expose the server-owned mapping identity for workflow invalidation."""
        return self._banking_policy.policy_hash

    @property
    def banking_advisor_configuration_hash(self) -> str:
        """Expose non-secret advisor configuration identity for invalidation."""
        return self._banking_advisor_configuration_hash

    @property
    def decision_analysis_configuration_hash(self) -> str:
        """Expose non-secret Decision composer identity for node invalidation."""
        return self._decision_analysis_configuration_hash

    @property
    def banking_precheck_adapter_id(self) -> str:
        """Expose the stable Banking precheck adapter implementation identity."""
        return self._banking_precheck_adapter.adapter_id

    @property
    def banking_precheck_adapter_configuration_hash(self) -> str:
        """Expose the non-secret simulated adapter policy identity."""
        return self._banking_precheck_adapter.configuration_hash

    @property
    def document_masking_policy_hash(self) -> str:
        """Expose only the canonical non-secret policy identity."""
        return self._masking_policy_configuration.configuration_hash

    @property
    def document_tokenizer_key_version(self) -> str:
        """Expose the configured version label, never key material or a key digest."""
        return self._document_tokenizer_key_version

    async def evaluate(
        self,
        *,
        contract_id: str,
        evaluation_scope: tuple[EvaluationScope, ...],
    ) -> PlannerExecutionResult:
        """Execute Planner Intake for one contract through the Orchestrator."""
        snapshot = self._require_snapshot()
        context = ExecutionContext(
            dataset_id=self.dataset_id,
            workflow_run_id=deterministic_id(
                "RUN",
                self.dataset_id,
                snapshot.snapshot_hash,
                contract_id,
                evaluation_scope,
            ),
            input_artifact_ids=(
                deterministic_id("DSNAP", self.dataset_id, snapshot.snapshot_hash),
            ),
            requested_scope=evaluation_scope,
            component_input={"contract_id": contract_id},
            current_node=WorkflowNode.PLANNER_INTAKE.value,
        )
        return await self._orchestrator.run_planner(context)

    async def finance_assessment(
        self,
        *,
        evaluation_case_id: str,
        resume_risk: bool = True,
    ) -> FinanceExecutionResult:
        """Run Finance from validated Planner artifacts for one existing case."""
        snapshot = self._require_snapshot()
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
        planner_artifact = self._latest(artifacts, ArtifactType.PLANNER_RESULT)
        if case_artifact is None or planner_artifact is None:
            raise FinanceCaseNotFoundError(
                "Run Planner successfully before requesting Finance for this case."
            )
        evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
        input_ids = (case_artifact.artifact_id, planner_artifact.artifact_id)
        context = ExecutionContext(
            evaluation_case_id=evaluation_case_id,
            dataset_id=self.dataset_id,
            workflow_run_id=deterministic_id(
                "RUN",
                self.dataset_id,
                snapshot.snapshot_hash,
                evaluation_case_id,
                ArtifactType.FINANCE_ASSESSMENT,
                input_ids,
            ),
            input_artifact_ids=input_ids,
            requested_scope=evaluation_case.evaluation_scope,
            component_input={},
            current_node="FINANCE_ASSESSMENT",
        )
        result = await self._finance_orchestrator.run(context)
        if resume_risk:
            await self._resume_started_risk(evaluation_case_id, result.status)
        return result

    async def operations_assessment(
        self,
        *,
        evaluation_case_id: str,
        as_of_date: date | None = None,
        resume_risk: bool = True,
    ) -> OperationsExecutionResult:
        """Run Operations from validated Planner artifacts for one existing case."""
        snapshot = self._require_snapshot()
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
        planner_artifact = self._latest(artifacts, ArtifactType.PLANNER_RESULT)
        if case_artifact is None or planner_artifact is None:
            raise OperationsCaseNotFoundError(
                "Run Planner successfully before requesting Operations for this case."
            )
        evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
        input_ids = (case_artifact.artifact_id, planner_artifact.artifact_id)
        component_input = {"as_of_date": as_of_date.isoformat() if as_of_date is not None else None}
        context = ExecutionContext(
            evaluation_case_id=evaluation_case_id,
            dataset_id=self.dataset_id,
            workflow_run_id=deterministic_id(
                "RUN",
                self.dataset_id,
                snapshot.snapshot_hash,
                evaluation_case_id,
                ArtifactType.OPERATIONS_ASSESSMENT,
                input_ids,
                component_input,
            ),
            input_artifact_ids=input_ids,
            requested_scope=evaluation_case.evaluation_scope,
            component_input=component_input,
            current_node=WorkflowNode.OPERATIONS_ASSESSMENT.value,
        )
        result = await self._operations_orchestrator.run(context)
        if resume_risk:
            await self._resume_started_risk(evaluation_case_id, result.status)
        return result

    async def risk_assessment(self, *, evaluation_case_id: str) -> RiskExecutionResult:
        """Start or resume Risk from Planner and the latest available fact artifacts."""
        lock = self._risk_locks.setdefault(evaluation_case_id, asyncio.Lock())
        async with lock:
            return await self._risk_assessment_locked(evaluation_case_id)

    async def _risk_assessment_locked(
        self, evaluation_case_id: str
    ) -> RiskExecutionResult:
        """Select a Risk phase in workflow/application code, never inside Risk."""
        context = await self._risk_context(evaluation_case_id)
        state = await self._risk_orchestrator.get_state(evaluation_case_id)
        if state is None or state.pre_scan_artifact_id is None:
            pre_scan = await self._risk_orchestrator.run_pre_scan(context)
            if pre_scan.status is WorkflowStatus.FAILED_SAFE:
                return pre_scan
        pending = await self._risk_orchestrator.missing_dependencies(context)
        if pending:
            return await self._risk_orchestrator.wait_for_dependencies(context, pending)
        return await self._risk_orchestrator.finalize(context)

    async def risk_pre_scan(self, *, evaluation_case_id: str) -> RiskExecutionResult:
        """Run only the pre-scan phase selected by the Master Workflow."""
        lock = self._risk_locks.setdefault(evaluation_case_id, asyncio.Lock())
        async with lock:
            context = await self._risk_context(evaluation_case_id)
            return await self._risk_orchestrator.run_pre_scan(context)

    async def risk_finalize(self, *, evaluation_case_id: str) -> RiskExecutionResult:
        """Finalize Risk only after workflow-owned fact dependency checks."""
        lock = self._risk_locks.setdefault(evaluation_case_id, asyncio.Lock())
        async with lock:
            context = await self._risk_context(evaluation_case_id)
            return await self._risk_orchestrator.finalize(context)

    async def _risk_context(self, evaluation_case_id: str) -> ExecutionContext:
        """Build explicit Risk inputs without choosing business behavior."""
        snapshot = self._require_snapshot()
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
        planner_artifact = self._latest(artifacts, ArtifactType.PLANNER_RESULT)
        if case_artifact is None or planner_artifact is None:
            raise RiskCaseNotFoundError(
                "Run Planner successfully before requesting Risk for this case."
            )
        evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
        finance_artifact = self._latest(artifacts, ArtifactType.FINANCE_FACTS)
        operations_artifact = self._latest(artifacts, ArtifactType.OPERATIONS_FACTS)
        input_ids = tuple(
            item.artifact_id
            for item in (
                case_artifact,
                planner_artifact,
                finance_artifact,
                operations_artifact,
            )
            if item is not None
        )
        context = ExecutionContext(
            evaluation_case_id=evaluation_case_id,
            dataset_id=self.dataset_id,
            workflow_run_id=deterministic_id(
                "RSK-RUN",
                self.dataset_id,
                snapshot.snapshot_hash,
                evaluation_case_id,
            ),
            input_artifact_ids=input_ids,
            requested_scope=evaluation_case.evaluation_scope,
            component_input={},
            current_node=WorkflowNode.INITIAL_RISK_PRE_SCAN.value,
        )
        return context

    async def risk_status(self, *, evaluation_case_id: str) -> RiskExecutionResult:
        """Read the latest Risk checkpoint without mutating or resuming it."""
        state = await self._risk_orchestrator.get_state(evaluation_case_id)
        if state is None:
            raise RiskCaseNotFoundError(
                "Risk has not started for this case. Call initial-risk-assessment first."
            )
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        pre_scan_artifact = self._latest(artifacts, ArtifactType.RISK_PRE_SCAN)
        checkpoint_artifact = (
            await self._artifacts.get(state.approval_checkpoint_artifact_id)
            if state.approval_checkpoint_artifact_id is not None
            else None
        )
        rule_artifact = self._latest(artifacts, ArtifactType.RISK_RULE_EVALUATION)
        assessment_artifact = self._latest(
            artifacts, ArtifactType.INITIAL_RISK_ASSESSMENT
        )
        pre_scan = (
            RiskPreScan.model_validate(pre_scan_artifact.payload)
            if pre_scan_artifact is not None
            else None
        )
        checkpoint_set = (
            ApprovalCheckpointSet.model_validate(checkpoint_artifact.payload)
            if checkpoint_artifact is not None
            else None
        )
        rule_set = (
            RiskRuleEvaluationSet.model_validate(rule_artifact.payload)
            if rule_artifact is not None
            else None
        )
        assessment = (
            InitialRiskAssessment.model_validate(assessment_artifact.payload)
            if assessment_artifact is not None
            else None
        )
        if state.status is RiskRunStatus.WAITING_FOR_FACTS:
            workflow_status = WorkflowStatus.WAITING_FOR_DEPENDENCIES
            component_status = ComponentStatus.COMPLETED
            current_node = WorkflowNode.INITIAL_RISK_FINALIZATION.value
        elif state.status in {
            RiskRunStatus.COMPLETED,
            RiskRunStatus.COMPLETED_WITH_LIMITATIONS,
        }:
            workflow_status = WorkflowStatus.COMPLETED
            component_status = (
                ComponentStatus.COMPLETED_WITH_WARNINGS
                if state.status is RiskRunStatus.COMPLETED_WITH_LIMITATIONS
                else ComponentStatus.COMPLETED
            )
            current_node = WorkflowNode.INITIAL_RISK_FINALIZATION.value
        else:
            workflow_status = WorkflowStatus.FAILED_SAFE
            component_status = ComponentStatus.FAILED_SAFE
            current_node = (
                WorkflowNode.INITIAL_RISK_FINALIZATION.value
                if state.pre_scan_artifact_id is not None
                else WorkflowNode.INITIAL_RISK_PRE_SCAN.value
            )
        selected_artifacts = tuple(
            item
            for item in (
                pre_scan_artifact,
                checkpoint_artifact,
                rule_artifact,
                assessment_artifact,
            )
            if item is not None
        )
        return RiskExecutionResult(
            status=workflow_status,
            component_status=component_status,
            current_node=current_node,
            risk_run_id=state.risk_run_id,
            checkpoint_status=state.status,
            pre_scan=pre_scan,
            approval_checkpoints=checkpoint_set,
            rule_evaluations=rule_set,
            risk_assessment=assessment,
            pending_dependencies=state.pending_dependencies,
            generated_artifacts=selected_artifacts,
            validation_errors=(state.failure_reason,) if state.failure_reason else (),
        )

    async def decision_initial_route(
        self, *, evaluation_case_id: str
    ) -> DecisionRouteExecutionResult:
        """Run deterministic Initial Route from authoritative assessment artifacts."""
        lock = self._decision_route_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            snapshot = self._require_snapshot()
            artifacts = await self._artifacts.list_by_case(evaluation_case_id)
            case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
            if case_artifact is None:
                raise DecisionRouteCaseNotFoundError(
                    "Run Planner successfully before requesting Decision Initial Route."
                )
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            risk_state = await self._risk_states.get_by_case(evaluation_case_id)
            risk_checkpoint_artifact = (
                await self._artifacts.get(
                    risk_state.approval_checkpoint_artifact_id
                )
                if risk_state is not None
                and risk_state.approval_checkpoint_artifact_id is not None
                else None
            )
            input_artifacts = tuple(
                item
                for item in (
                    case_artifact,
                    self._latest(artifacts, ArtifactType.FINANCE_FACTS),
                    self._latest(artifacts, ArtifactType.OPERATIONS_FACTS),
                    self._latest(
                        artifacts, ArtifactType.INITIAL_RISK_ASSESSMENT
                    ),
                    risk_checkpoint_artifact,
                )
                if item is not None
            )
            input_ids = tuple(item.artifact_id for item in input_artifacts)
            component_input = {
                "execution_mode": DecisionRouteMode.INITIAL_ROUTE.value
            }
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=deterministic_id(
                    "DROUTE-RUN",
                    self.dataset_id,
                    snapshot.snapshot_hash,
                    evaluation_case_id,
                    input_ids,
                    component_input,
                ),
                input_artifact_ids=input_ids,
                requested_scope=evaluation_case.evaluation_scope,
                component_input=component_input,
                current_node=WorkflowNode.DECISION_ROUTE_PLANNING.value,
            )
            return await self._decision_route_orchestrator.run(context)

    async def decision_banking_handoff(
        self, *, evaluation_case_id: str
    ) -> BankingDiscoveryHandoffExecutionResult:
        """Create an internal Banking discovery request from a validated route."""
        lock = self._decision_handoff_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            snapshot = self._require_snapshot()
            artifacts = await self._artifacts.list_by_case(evaluation_case_id)
            case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
            if case_artifact is None:
                raise DecisionHandoffCaseNotFoundError(
                    "Run Planner successfully before requesting a Banking handoff."
                )
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            route_artifact = self._latest(
                artifacts, ArtifactType.DECISION_ROUTE_PLAN
            )
            input_ids = tuple(
                item.artifact_id
                for item in (case_artifact, route_artifact)
                if item is not None
            )
            component_input = {
                "execution_mode": DecisionHandoffMode.BANKING_DISCOVERY.value
            }
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=deterministic_id(
                    "DBH-RUN",
                    self.dataset_id,
                    snapshot.snapshot_hash,
                    evaluation_case_id,
                    input_ids,
                    component_input,
                ),
                input_artifact_ids=input_ids,
                requested_scope=evaluation_case.evaluation_scope,
                component_input=component_input,
                current_node=WorkflowNode.BANKING_DISCOVERY_HANDOFF.value,
            )
            return await self._decision_banking_handoff_orchestrator.run(context)

    async def banking_internal_discovery(
        self, *, evaluation_case_id: str
    ) -> BankingDiscoveryExecutionResult:
        """Build the internal catalog matrix without calling a bank or approval gate."""
        lock = self._banking_discovery_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            snapshot = self._require_snapshot()
            artifacts = await self._artifacts.list_by_case(evaluation_case_id)
            case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
            if case_artifact is None:
                raise BankingDiscoveryCaseNotFoundError(
                    "Run Planner successfully before requesting Banking discovery."
                )
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            route_artifact = self._latest(
                artifacts, ArtifactType.DECISION_ROUTE_PLAN
            )
            if route_artifact is not None:
                route_plan = DecisionRoutePlan.model_validate(route_artifact.payload)
                if (
                    route_plan.route_outcome
                    is DecisionRouteOutcome.DIRECT_INTERNAL_DECISION
                ):
                    return BankingDiscoveryExecutionResult(
                        status=WorkflowStatus.COMPLETED,
                        component_status=ComponentStatus.COMPLETED,
                        current_node=WorkflowNode.DECISION_ROUTE_PLANNED.value,
                        discovery_status=BankingDiscoveryStatus.NOT_APPLICABLE,
                        runtime_events=(
                            {
                                "event_type": "BANKING_DISCOVERY_NOT_APPLICABLE",
                                "message": (
                                    "The Decision route does not request Banking "
                                    "internal discovery."
                                ),
                                "metadata": {},
                            },
                        ),
                    )
            request_artifact = self._latest(
                artifacts, ArtifactType.BANKING_DISCOVERY_REQUEST
            )
            supplement_artifact = self._latest(
                artifacts, ArtifactType.BANKING_INPUT_SUPPLEMENT
            )
            input_ids = tuple(
                item.artifact_id
                for item in (case_artifact, request_artifact, supplement_artifact)
                if item is not None
            )
            component_input = {
                "mapping_policy_id": self._banking_policy.policy_id,
                "mapping_version": self._banking_policy.mapping_version,
                "mapping_hash": self._banking_policy.policy_hash,
            }
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=deterministic_id(
                    "BANK-DISC-RUN",
                    self.dataset_id,
                    snapshot.snapshot_hash,
                    evaluation_case_id,
                    input_ids,
                    component_input,
                ),
                input_artifact_ids=input_ids,
                requested_scope=evaluation_case.evaluation_scope,
                component_input=component_input,
                current_node=WorkflowNode.BANKING_INTERNAL_DISCOVERY.value,
            )
            return await self._banking_discovery_orchestrator.run(context)

    async def banking_precheck_readiness(
        self, *, evaluation_case_id: str
    ) -> BankingPrecheckReadinessExecutionResult:
        """Assess exact precheck inputs without calling the configured endpoint."""
        lock = self._banking_precheck_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            snapshot = self._require_snapshot()
            artifacts = await self._artifacts.list_by_case(evaluation_case_id)
            case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
            matrix_artifact = self._latest(
                artifacts, ArtifactType.BANKING_OPTION_MATRIX
            )
            if case_artifact is None or matrix_artifact is None:
                raise BankingPrecheckCaseNotFoundError(
                    "Run Banking internal discovery before precheck readiness."
                )
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            request_artifact = self._latest(
                artifacts, ArtifactType.BANKING_DISCOVERY_REQUEST
            )
            supplement_artifact = self._latest(
                artifacts, ArtifactType.BANKING_INPUT_SUPPLEMENT
            )
            input_ids = tuple(
                item.artifact_id
                for item in (
                    case_artifact,
                    request_artifact,
                    matrix_artifact,
                    supplement_artifact,
                )
                if item is not None
            )
            component_input = {
                "mapping_policy_id": self._banking_policy.policy_id,
                "mapping_version": self._banking_policy.mapping_version,
                "mapping_hash": self._banking_policy.policy_hash,
            }
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=deterministic_id(
                    "BANK-READY-RUN",
                    self.dataset_id,
                    snapshot.snapshot_hash,
                    evaluation_case_id,
                    input_ids,
                    component_input,
                ),
                input_artifact_ids=input_ids,
                requested_scope=evaluation_case.evaluation_scope,
                component_input=component_input,
                current_node=WorkflowNode.BANKING_PRECHECK_READINESS.value,
            )
            return await self._banking_precheck_readiness_orchestrator.run(context)

    async def decision_post_banking_review(
        self, *, evaluation_case_id: str
    ) -> DecisionPostBankingExecutionResult:
        """Classify Banking readiness without selecting or executing an option."""
        lock = self._decision_post_banking_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            snapshot = self._require_snapshot()
            artifacts = await self._artifacts.list_by_case(evaluation_case_id)
            case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
            matrix_artifact = self._latest(
                artifacts, ArtifactType.BANKING_OPTION_MATRIX
            )
            readiness_artifact = self._latest(
                artifacts, ArtifactType.BANKING_PRECHECK_READINESS
            )
            if (
                case_artifact is None
                or matrix_artifact is None
                or readiness_artifact is None
            ):
                raise DecisionPostBankingCaseNotFoundError(
                    "Run Banking precheck readiness before post-Banking Decision review."
                )
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            input_ids = (
                matrix_artifact.artifact_id,
                readiness_artifact.artifact_id,
            )
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=deterministic_id(
                    "POST-BANK-RUN",
                    self.dataset_id,
                    snapshot.snapshot_hash,
                    evaluation_case_id,
                    input_ids,
                ),
                input_artifact_ids=input_ids,
                requested_scope=evaluation_case.evaluation_scope,
                component_input={},
                current_node=WorkflowNode.DECISION_POST_BANKING_REVIEW.value,
            )
            return await self._decision_post_banking_orchestrator.run(context)

    async def banking_precheck_submission_proposal(
        self, *, evaluation_case_id: str
    ) -> BankingPrecheckSubmissionProposalExecutionResult:
        """Persist an all-ready proposal without authorizing or submitting it."""
        lock = self._banking_precheck_submission_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            snapshot = self._require_snapshot()
            artifacts = await self._artifacts.list_by_case(evaluation_case_id)
            case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
            matrix_artifact = self._latest(
                artifacts, ArtifactType.BANKING_OPTION_MATRIX
            )
            readiness_artifact = self._latest(
                artifacts, ArtifactType.BANKING_PRECHECK_READINESS
            )
            review_artifact = self._latest(
                artifacts, ArtifactType.DECISION_POST_BANKING_REVIEW
            )
            if any(
                item is None
                for item in (
                    case_artifact,
                    matrix_artifact,
                    readiness_artifact,
                    review_artifact,
                )
            ):
                raise BankingPrecheckSubmissionCaseNotFoundError(
                    "Run post-Banking Decision review before preparing a submission "
                    "proposal."
                )
            if (
                case_artifact is None
                or matrix_artifact is None
                or readiness_artifact is None
                or review_artifact is None
            ):  # pragma: no cover - narrowed by the guard above
                raise BankingPrecheckSubmissionCaseNotFoundError(
                    "Banking precheck proposal context is incomplete."
                )
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            matrix = BankingOptionMatrix.model_validate(matrix_artifact.payload)
            readiness = BankingPrecheckReadiness.model_validate(
                readiness_artifact.payload
            )
            review = DecisionPostBankingReview.model_validate(review_artifact.payload)
            core_ids = (
                matrix_artifact.artifact_id,
                readiness_artifact.artifact_id,
                review_artifact.artifact_id,
            )
            upstream_ids: list[str] = []
            for artifact_id in (
                *matrix.source_artifact_ids,
                *readiness.source_artifact_ids,
                *review.source_artifact_ids,
            ):
                if artifact_id not in core_ids and artifact_id not in upstream_ids:
                    upstream_ids.append(artifact_id)
            input_ids = (*core_ids, *upstream_ids)
            component_input = {
                "mapping_policy_id": self._banking_policy.policy_id,
                "mapping_version": self._banking_policy.mapping_version,
                "mapping_hash": self._banking_policy.policy_hash,
            }
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=deterministic_id(
                    "BANK-PRECHECK-PROPOSAL-RUN",
                    self.dataset_id,
                    snapshot.snapshot_hash,
                    evaluation_case_id,
                    input_ids,
                    component_input,
                ),
                input_artifact_ids=input_ids,
                requested_scope=evaluation_case.evaluation_scope,
                component_input=component_input,
                current_node=(
                    WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL.value
                ),
            )
            return await self._banking_precheck_submission_proposal_orchestrator.run(
                context
            )

    async def banking_precheck_execution(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        approval_request_id: str,
        proposal_artifact_id: str,
        reuse_existing_only: bool = False,
    ) -> BankingPrecheckResultExecutionResult:
        """Execute the exact approved proposal through the non-binding simulator."""
        lock = self._banking_precheck_execution_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            self._require_snapshot()
            proposal_artifact = await self._artifacts.get(proposal_artifact_id)
            if (
                proposal_artifact is None
                or proposal_artifact.evaluation_case_id != evaluation_case_id
                or proposal_artifact.artifact_type
                is not ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL
            ):
                raise BankingPrecheckSubmissionCaseNotFoundError(
                    "The authorized Banking precheck proposal was not found."
                )
            proposal = BankingPrecheckSubmissionProposal.model_validate(
                proposal_artifact.payload
            )
            input_ids = (
                proposal_artifact.artifact_id,
                *proposal.source_artifact_ids,
            )
            source_artifacts = tuple(
                [
                    await self._artifacts.get(artifact_id)
                    for artifact_id in proposal.source_artifact_ids
                ]
            )
            case_matches = tuple(
                item
                for item in source_artifacts
                if item is not None
                and item.artifact_type is ArtifactType.EVALUATION_CASE
            )
            if len(case_matches) != 1:
                raise BankingPrecheckSubmissionCaseNotFoundError(
                    "The authorized proposal lacks one exact EvaluationCase artifact."
                )
            evaluation_case = EvaluationCase.model_validate(case_matches[0].payload)
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=workflow_run_id,
                input_artifact_ids=input_ids,
                requested_scope=evaluation_case.evaluation_scope,
                component_input={
                    "approval_request_id": approval_request_id,
                    "reuse_existing_only": reuse_existing_only,
                },
                current_node=WorkflowNode.BANKING_PRECHECK_EXECUTION.value,
            )
            return await self._banking_precheck_execution_orchestrator.run(context)

    async def decision_post_precheck_review(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        result_set_artifact_id: str,
    ) -> DecisionPostPrecheckExecutionResult:
        """Classify one exact persisted precheck batch without downstream execution."""
        lock = self._decision_post_precheck_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            self._require_snapshot()
            result_artifact = await self._artifacts.get(result_set_artifact_id)
            if (
                result_artifact is None
                or result_artifact.evaluation_case_id != evaluation_case_id
                or result_artifact.artifact_type
                is not ArtifactType.BANKING_PRECHECK_RESULT_SET
            ):
                raise DecisionPostPrecheckCaseNotFoundError(
                    "The exact validated Banking precheck result set was not found."
                )
            result_set = BankingPrecheckResultSet.model_validate(
                result_artifact.payload
            )
            proposal_artifact = await self._artifacts.get(
                result_set.proposal_artifact_id
            )
            if (
                proposal_artifact is None
                or proposal_artifact.evaluation_case_id != evaluation_case_id
                or proposal_artifact.artifact_type
                is not ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL
            ):
                raise DecisionPostPrecheckCaseNotFoundError(
                    "The approved proposal for this precheck result was not found."
                )
            proposal = BankingPrecheckSubmissionProposal.model_validate(
                proposal_artifact.payload
            )
            source_artifacts = tuple(
                [
                    await self._artifacts.get(artifact_id)
                    for artifact_id in proposal.source_artifact_ids
                ]
            )
            case_matches = tuple(
                item
                for item in source_artifacts
                if item is not None
                and item.artifact_type is ArtifactType.EVALUATION_CASE
            )
            if len(case_matches) != 1:
                raise DecisionPostPrecheckCaseNotFoundError(
                    "The precheck proposal lacks one exact EvaluationCase artifact."
                )
            evaluation_case = EvaluationCase.model_validate(case_matches[0].payload)
            input_ids = (
                result_artifact.artifact_id,
                proposal_artifact.artifact_id,
            )
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=workflow_run_id,
                input_artifact_ids=input_ids,
                requested_scope=evaluation_case.evaluation_scope,
                component_input={},
                current_node=WorkflowNode.DECISION_POST_PRECHECK_REVIEW.value,
            )
            return await self._decision_post_precheck_orchestrator.run(context)

    async def decision_post_precheck_review_latest(
        self, *, evaluation_case_id: str
    ) -> DecisionPostPrecheckExecutionResult:
        """Swagger/debug entrypoint that resolves the latest validated result set."""
        snapshot = self._require_snapshot()
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        result_artifact = self._latest(
            artifacts, ArtifactType.BANKING_PRECHECK_RESULT_SET
        )
        if result_artifact is None:
            raise DecisionPostPrecheckCaseNotFoundError(
                "Run the governed Banking precheck before post-precheck review."
            )
        workflow_run_id = deterministic_id(
            "POST-PRECHECK-RUN",
            self.dataset_id,
            snapshot.snapshot_hash,
            evaluation_case_id,
            result_artifact.artifact_id,
            result_artifact.version,
            result_artifact.input_hash,
        )
        return await self.decision_post_precheck_review(
            evaluation_case_id=evaluation_case_id,
            workflow_run_id=workflow_run_id,
            result_set_artifact_id=result_artifact.artifact_id,
        )

    async def decision_document_handoff(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        review_artifact_id: str,
        result_set_artifact_id: str,
    ) -> DecisionDocumentHandoffExecutionResult:
        """Create exact internal Document requests from a conditional review."""
        lock = self._decision_document_handoff_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            review_artifact = await self._artifacts.get(review_artifact_id)
            result_artifact = await self._artifacts.get(result_set_artifact_id)
            if (
                review_artifact is None
                or result_artifact is None
                or review_artifact.evaluation_case_id != evaluation_case_id
                or result_artifact.evaluation_case_id != evaluation_case_id
                or review_artifact.artifact_type
                is not ArtifactType.DECISION_POST_PRECHECK_REVIEW
                or result_artifact.artifact_type
                is not ArtifactType.BANKING_PRECHECK_RESULT_SET
            ):
                raise DocumentCaseNotFoundError(
                    "The exact Decision review and Banking result set were not found."
                )
            artifacts = await self._artifacts.list_by_case(evaluation_case_id)
            case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
            if case_artifact is None:
                raise DocumentCaseNotFoundError(
                    "Document handoff requires a validated EvaluationCase."
                )
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=workflow_run_id,
                input_artifact_ids=(
                    review_artifact.artifact_id,
                    result_artifact.artifact_id,
                ),
                requested_scope=evaluation_case.evaluation_scope,
                component_input={
                    "execution_mode": DecisionHandoffMode.DOCUMENT_PREPARATION.value
                },
                current_node=WorkflowNode.DECISION_DOCUMENT_HANDOFF.value,
            )
            return await self._decision_document_handoff_orchestrator.run(context)

    async def decision_document_handoff_latest(
        self, *, evaluation_case_id: str
    ) -> DecisionDocumentHandoffExecutionResult:
        """Swagger entrypoint for the latest exact conditional result review."""
        snapshot = self._require_snapshot()
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        review_artifact = self._latest(
            artifacts, ArtifactType.DECISION_POST_PRECHECK_REVIEW
        )
        result_artifact = self._latest(
            artifacts, ArtifactType.BANKING_PRECHECK_RESULT_SET
        )
        if review_artifact is None or result_artifact is None:
            raise DocumentCaseNotFoundError(
                "Run Decision post-precheck review before Document handoff."
            )
        workflow_run_id = deterministic_id(
            "DOCUMENT-HANDOFF-RUN",
            self.dataset_id,
            snapshot.snapshot_hash,
            evaluation_case_id,
            review_artifact.artifact_id,
            result_artifact.artifact_id,
        )
        return await self.decision_document_handoff(
            evaluation_case_id=evaluation_case_id,
            workflow_run_id=workflow_run_id,
            review_artifact_id=review_artifact.artifact_id,
            result_set_artifact_id=result_artifact.artifact_id,
        )

    async def document_preparation(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        preparation_request_artifact_id: str,
    ) -> DocumentSkillExecutionResult:
        """Build one internal masked dossier from an exact Decision request."""
        lock = self._document_locks.setdefault(evaluation_case_id, asyncio.Lock())
        async with lock:
            artifacts = await self._artifacts.list_by_case(evaluation_case_id)
            case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
            request_artifact = await self._artifacts.get(
                preparation_request_artifact_id
            )
            if (
                case_artifact is None
                or request_artifact is None
                or request_artifact.evaluation_case_id != evaluation_case_id
                or request_artifact.artifact_type
                is not ArtifactType.DOCUMENT_PREPARATION_REQUEST
            ):
                raise DocumentCaseNotFoundError(
                    "The exact Document preparation request was not found."
                )
            request = DocumentPreparationRequest.model_validate(
                request_artifact.payload
            )
            supplements: list[ArtifactEnvelope] = []
            for artifact in artifacts:
                if artifact.artifact_type is not ArtifactType.DOCUMENT_EVIDENCE_SUPPLEMENT:
                    continue
                supplement = DocumentEvidenceSupplement.model_validate(
                    artifact.payload
                )
                if supplement.preparation_request_id == request.request_id:
                    supplements.append(artifact)
            supplements.sort(key=lambda item: (item.version, item.artifact_id))
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=workflow_run_id,
                input_artifact_ids=(
                    case_artifact.artifact_id,
                    request_artifact.artifact_id,
                    *(item.artifact_id for item in supplements),
                ),
                requested_scope=evaluation_case.evaluation_scope,
                component_input={
                    "masking_policy_hash": self.document_masking_policy_hash,
                    "tokenizer_key_version": self.document_tokenizer_key_version,
                },
                current_node=WorkflowNode.DOCUMENT_PREPARATION.value,
            )
            return await self._document_orchestrator.run(context)

    async def document_preparation_latest(
        self, *, evaluation_case_id: str
    ) -> DocumentSkillExecutionResult:
        """Swagger entrypoint that refuses to select among multiple requests."""
        snapshot = self._require_snapshot()
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        requests = tuple(
            item
            for item in artifacts
            if item.artifact_type is ArtifactType.DOCUMENT_PREPARATION_REQUEST
        )
        if len(requests) != 1:
            raise DocumentCaseNotFoundError(
                "Document preparation requires exactly one Decision request; "
                "the server will not select among alternatives."
            )
        request = requests[0]
        workflow_run_id = deterministic_id(
            "DOCUMENT-PREPARATION-RUN",
            self.dataset_id,
            snapshot.snapshot_hash,
            evaluation_case_id,
            request.artifact_id,
            self.document_masking_policy_hash,
            self.document_tokenizer_key_version,
        )
        return await self.document_preparation(
            evaluation_case_id=evaluation_case_id,
            workflow_run_id=workflow_run_id,
            preparation_request_artifact_id=request.artifact_id,
        )

    async def internal_decision_package(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        assembly_path: InternalDecisionAssemblyPath,
        input_artifact_ids: tuple[str, ...],
        approval_request_id: str | None = None,
    ) -> InternalDecisionPackageExecutionResult:
        """Assemble one exact, validated dossier selected by the workflow."""
        lock = self._internal_decision_package_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            artifacts = await self._artifacts.list_by_case(evaluation_case_id)
            case_artifact = self._latest(
                artifacts, ArtifactType.EVALUATION_CASE
            )
            if case_artifact is None:
                raise InternalDecisionPackageCaseNotFoundError(
                    "Internal Decision Package requires a validated EvaluationCase."
                )
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=workflow_run_id,
                input_artifact_ids=input_artifact_ids,
                requested_scope=evaluation_case.evaluation_scope,
                component_input={
                    "assembly_path": assembly_path.value,
                    "approval_request_id": approval_request_id,
                },
                current_node=(
                    WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY.value
                ),
            )
            return await self._internal_decision_package_orchestrator.run(context)

    async def final_risk_check(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        internal_decision_package_artifact_id: str,
    ) -> FinalRiskExecutionResult:
        """Run deterministic Final Risk from one exact validated internal package."""
        lock = self._final_risk_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            artifacts = await self._artifacts.list_by_case(evaluation_case_id)
            case_artifact = self._latest(
                artifacts, ArtifactType.EVALUATION_CASE
            )
            if case_artifact is None:
                raise InternalDecisionPackageCaseNotFoundError(
                    "Final Risk Check requires a validated EvaluationCase."
                )
            package_artifact = await self._artifacts.get(
                internal_decision_package_artifact_id
            )
            if (
                package_artifact is None
                or package_artifact.evaluation_case_id != evaluation_case_id
                or package_artifact.artifact_type
                is not ArtifactType.INTERNAL_DECISION_PACKAGE
            ):
                raise InternalDecisionPackageCaseNotFoundError(
                    "Final Risk Check requires this case's exact Internal Decision "
                    "Package."
                )
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=workflow_run_id,
                input_artifact_ids=(package_artifact.artifact_id,),
                requested_scope=evaluation_case.evaluation_scope,
                component_input={},
                current_node=WorkflowNode.FINAL_RISK_CHECK.value,
            )
            return await self._final_risk_orchestrator.run(context)

    async def decision_analysis(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        final_risk_artifact_id: str,
    ) -> DecisionAnalysisExecutionResult:
        """Create one guarded AI Decision analysis from exact Final Risk."""
        lock = self._decision_analysis_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            case_artifact, evaluation_case = await self._decision_case(
                evaluation_case_id
            )
            del case_artifact
            final_risk_artifact = await self._required_case_artifact(
                evaluation_case_id=evaluation_case_id,
                artifact_id=final_risk_artifact_id,
                artifact_type=ArtifactType.FINAL_RISK_ASSESSMENT,
            )
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=workflow_run_id,
                input_artifact_ids=(final_risk_artifact.artifact_id,),
                requested_scope=evaluation_case.evaluation_scope,
                component_input={
                    "composer_configuration_hash": (
                        self._decision_analysis_configuration_hash
                    )
                },
                current_node=WorkflowNode.DECISION_CARD_COMPOSITION.value,
            )
            return await self._decision_analysis_orchestrator.run_analysis(
                context
            )

    async def decision_card(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        analysis_artifact_id: str,
    ) -> DecisionCardExecutionResult:
        """Assemble one detailed Decision Card without requesting approval."""
        lock = self._decision_card_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            _, evaluation_case = await self._decision_case(evaluation_case_id)
            analysis_artifact = await self._required_case_artifact(
                evaluation_case_id=evaluation_case_id,
                artifact_id=analysis_artifact_id,
                artifact_type=ArtifactType.AI_DECISION_ANALYSIS,
            )
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=workflow_run_id,
                input_artifact_ids=(analysis_artifact.artifact_id,),
                requested_scope=evaluation_case.evaluation_scope,
                component_input={},
                current_node=WorkflowNode.DECISION_CARD_COMPOSITION.value,
            )
            return await self._decision_analysis_orchestrator.run_card(context)

    async def post_decision_update(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        decision_card_artifact_id: str,
        approval_request_id: str,
    ) -> PostDecisionUpdateExecutionResult:
        """Persist routing after Founder approves the exact Decision Card."""
        lock = self._post_decision_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            _, evaluation_case = await self._decision_case(evaluation_case_id)
            card_artifact = await self._required_case_artifact(
                evaluation_case_id=evaluation_case_id,
                artifact_id=decision_card_artifact_id,
                artifact_type=ArtifactType.DECISION_CARD,
            )
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=workflow_run_id,
                input_artifact_ids=(card_artifact.artifact_id,),
                requested_scope=evaluation_case.evaluation_scope,
                component_input={"approval_request_id": approval_request_id},
                current_node=WorkflowNode.POST_DECISION_UPDATE.value,
            )
            return await self._post_decision_orchestrator.run_update(context)

    async def external_document_submission_proposal(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        post_decision_update_artifact_id: str,
    ) -> ExternalDocumentSubmissionProposalExecutionResult:
        """Create one exact masked-package proposal for Governance."""
        lock = self._external_submission_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            _, evaluation_case = await self._decision_case(evaluation_case_id)
            update_artifact = await self._required_case_artifact(
                evaluation_case_id=evaluation_case_id,
                artifact_id=post_decision_update_artifact_id,
                artifact_type=ArtifactType.POST_DECISION_UPDATE,
            )
            update = PostDecisionUpdate.model_validate(update_artifact.payload)
            release_snapshot = update.document_release_package
            if release_snapshot is None:
                raise ValueError(
                    "External submission proposal requires an exact document release package."
                )
            card_artifact = await self._required_case_artifact(
                evaluation_case_id=evaluation_case_id,
                artifact_id=update.decision_card_artifact.artifact_id,
                artifact_type=ArtifactType.DECISION_CARD,
            )
            release_artifact = await self._required_case_artifact(
                evaluation_case_id=evaluation_case_id,
                artifact_id=release_snapshot.artifact.artifact_id,
                artifact_type=ArtifactType.DOCUMENT_RELEASE_PACKAGE,
            )
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=workflow_run_id,
                input_artifact_ids=(
                    update_artifact.artifact_id,
                    card_artifact.artifact_id,
                    release_artifact.artifact_id,
                ),
                requested_scope=evaluation_case.evaluation_scope,
                component_input={},
                current_node=(
                    WorkflowNode.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL.value
                ),
            )
            return await self._post_decision_orchestrator.run_external_proposal(
                context
            )

    async def external_submission_readiness(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str,
        proposal_artifact_id: str,
        approval_request_id: str,
    ) -> ExternalSubmissionReadinessExecutionResult:
        """Return READY after exact authorization; do not call an adapter."""
        lock = self._external_submission_locks.setdefault(
            evaluation_case_id, asyncio.Lock()
        )
        async with lock:
            _, evaluation_case = await self._decision_case(evaluation_case_id)
            proposal_artifact = await self._required_case_artifact(
                evaluation_case_id=evaluation_case_id,
                artifact_id=proposal_artifact_id,
                artifact_type=(
                    ArtifactType.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL
                ),
            )
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=workflow_run_id,
                input_artifact_ids=(proposal_artifact.artifact_id,),
                requested_scope=evaluation_case.evaluation_scope,
                component_input={"approval_request_id": approval_request_id},
                current_node=WorkflowNode.READY_FOR_EXTERNAL_SUBMISSION.value,
            )
            return await self._post_decision_orchestrator.run_external_readiness(
                context
            )

    async def document_evidence_supplement(
        self,
        *,
        evaluation_case_id: str,
        submission: DocumentEvidenceSubmission,
        allowed_pending_request_id: str,
    ) -> DocumentEvidenceExecutionResult:
        """Persist caller-declared opaque reference metadata without raw content."""
        lock = self._document_evidence_locks.setdefault(
            submission.workflow_run_id, asyncio.Lock()
        )
        async with lock:
            artifacts = await self._artifacts.list_by_case(evaluation_case_id)
            package_matches: list[ArtifactEnvelope] = []
            for artifact in artifacts:
                if artifact.artifact_type is not ArtifactType.DOCUMENT_PACKAGE_DRAFT:
                    continue
                package = DocumentPackageDraft.model_validate(artifact.payload)
                if allowed_pending_request_id in {
                    item.request_id for item in package.missing_data_requests
                }:
                    package_matches.append(artifact)
            package_artifact = max(
                package_matches, key=lambda item: item.version, default=None
            )
            if package_artifact is None:
                raise DocumentCaseNotFoundError(
                    "The workflow has no pending Document package request to resolve."
                )
            trusted = submission.model_copy(update={"provided_by": "AUTHORIZED_STAFF"})
            command = DocumentEvidenceCommand(
                submission=trusted,
                allowed_pending_request_id=allowed_pending_request_id,
            )
            case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
            if case_artifact is None:
                raise DocumentCaseNotFoundError(
                    "Document evidence intake requires an EvaluationCase."
                )
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=trusted.workflow_run_id,
                input_artifact_ids=(package_artifact.artifact_id,),
                requested_scope=evaluation_case.evaluation_scope,
                component_input=command.model_dump(mode="json"),
                current_node=WorkflowNode.DOCUMENT_INPUT_INTAKE.value,
            )
            return await self._document_evidence_orchestrator.run(context)

    async def banking_input_supplement(
        self,
        *,
        evaluation_case_id: str,
        submission: BankingAmountInputSubmission,
        allowed_pending_request_id: str,
    ) -> BankingInputExecutionResult:
        """Validate and persist typed human input; Master Workflow owns resumption."""
        lock = self._banking_input_locks.setdefault(
            submission.workflow_run_id, asyncio.Lock()
        )
        async with lock:
            artifacts = await self._artifacts.list_by_case(evaluation_case_id)
            case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
            review_artifact = self._latest(
                artifacts, ArtifactType.DECISION_POST_BANKING_REVIEW
            )
            supplement_artifact = self._latest(
                artifacts, ArtifactType.BANKING_INPUT_SUPPLEMENT
            )
            if case_artifact is None or review_artifact is None:
                raise DecisionPostBankingCaseNotFoundError(
                    "The workflow has no post-Banking missing-data review to resolve."
                )
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            input_ids = tuple(
                item.artifact_id
                for item in (case_artifact, review_artifact, supplement_artifact)
                if item is not None
            )
            command = BankingAmountInputCommand(
                submission=submission,
                allowed_pending_request_id=allowed_pending_request_id,
            )
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=submission.workflow_run_id,
                input_artifact_ids=input_ids,
                requested_scope=evaluation_case.evaluation_scope,
                component_input=command.model_dump(mode="json"),
                current_node=WorkflowNode.BANKING_INPUT_SUPPLEMENT.value,
            )
            return await self._banking_input_orchestrator.run(context)

    async def banking_precheck_evidence_supplement(
        self,
        *,
        evaluation_case_id: str,
        submission: BankingPrecheckEvidenceSubmission,
        allowed_pending_request_id: str,
    ) -> BankingPrecheckEvidenceExecutionResult:
        """Persist an exact evidence reference without changing provider results."""
        lock = self._banking_precheck_evidence_locks.setdefault(
            submission.workflow_run_id, asyncio.Lock()
        )
        async with lock:
            artifacts = await self._artifacts.list_by_case(evaluation_case_id)
            case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
            review_artifact = self._latest(
                artifacts, ArtifactType.DECISION_POST_PRECHECK_REVIEW
            )
            current_supplement: ArtifactEnvelope | None = None
            for item in artifacts:
                if (
                    item.artifact_type
                    is not ArtifactType.BANKING_PRECHECK_EVIDENCE_SUPPLEMENT
                ):
                    continue
                supplement = BankingPrecheckEvidenceSupplement.model_validate(
                    item.payload
                )
                if supplement.missing_request_id != allowed_pending_request_id:
                    continue
                if (
                    current_supplement is None
                    or item.version > current_supplement.version
                ):
                    current_supplement = item
            if case_artifact is None or review_artifact is None:
                raise DecisionPostPrecheckCaseNotFoundError(
                    "The workflow has no post-precheck evidence request to resolve."
                )
            evaluation_case = EvaluationCase.model_validate(case_artifact.payload)
            trusted_submission = submission.model_copy(
                update={"provided_by": "AUTHORIZED_STAFF"}
            )
            command = BankingPrecheckEvidenceCommand(
                submission=trusted_submission,
                allowed_pending_request_id=allowed_pending_request_id,
            )
            input_ids = (
                review_artifact.artifact_id,
                *((current_supplement.artifact_id,) if current_supplement else ()),
            )
            context = ExecutionContext(
                evaluation_case_id=evaluation_case_id,
                dataset_id=self.dataset_id,
                workflow_run_id=trusted_submission.workflow_run_id,
                input_artifact_ids=input_ids,
                requested_scope=evaluation_case.evaluation_scope,
                component_input=command.model_dump(mode="json"),
                current_node=WorkflowNode.BANKING_PRECHECK_EVIDENCE_INTAKE.value,
            )
            return await self._banking_precheck_evidence_orchestrator.run(context)

    async def request_protected_action(
        self,
        *,
        evaluation_case_id: str,
        workflow_run_id: str | None,
        action_type: ProtectedAction,
        payload_artifact_id: str,
        requested_by: str,
        payload: dict[str, object],
    ) -> ApprovalExecutionResult:
        """Route a protected action through Governance without executing it."""
        if action_type in {
            ProtectedAction.SUBMIT_BANKING_PRECHECK,
            ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER,
            ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION,
        }:
            raise ApprovalConflictError(
                f"{action_type.value} can only be proposed automatically from its "
                "validated package in the Master Workflow."
            )
        if not set(payload).issubset({"requested_amount"}):
            raise ApprovalConflictError(
                "The public financial-decision payload contains unsupported fields."
            )
        del requested_by
        result = await self._approval_orchestrator.request_action(
            ActionCommand(
                action_type=action_type,
                evaluation_case_id=evaluation_case_id,
                payload_artifact_id=payload_artifact_id,
                requested_by="PUBLIC_API_CLIENT",
                payload=payload,
            ),
            workflow_run_id=workflow_run_id,
        )
        await self._enqueue_approval_resume(result)
        return result

    async def request_workflow_protected_action(
        self,
        *,
        command: ActionCommand,
        workflow_run_id: str,
    ) -> ApprovalExecutionResult:
        """Gate the exact proposal emitted by the executing Master Workflow."""
        supported_actions = {
            ProtectedAction.SUBMIT_BANKING_PRECHECK,
            ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION,
            ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER,
        }
        if (
            command.requested_by != "CASE_WORKFLOW_ORCHESTRATOR"
            or command.action_type not in supported_actions
        ):
            raise ValueError(
                "The Master Workflow may gate only an exact internally generated "
                "protected-action proposal."
            )
        run = await self._case_workflows.get_run(workflow_run_id)
        expected_stages = {
            ProtectedAction.SUBMIT_BANKING_PRECHECK: (
                WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL.value
            ),
            ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION: (
                WorkflowNode.FINAL_DECISION_APPROVAL.value
            ),
            ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER: (
                WorkflowNode.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL.value
            ),
        }
        if (
            run is None
            or run.evaluation_case_id != command.evaluation_case_id
            or run.status is not WorkflowStatus.RUNNING
            or run.current_stage != expected_stages[command.action_type]
        ):
            raise ValueError(
                "The protected action is not attached to its active proposal node."
            )
        checkpoint_artifact_id: str | None = None
        artifact = await self._artifacts.get(command.payload_artifact_id)
        if (
            artifact is None
            or artifact.evaluation_case_id != command.evaluation_case_id
        ):
            raise ValueError(
                "The protected action must reference this case's persisted proposal."
            )
        if command.action_type is ProtectedAction.SUBMIT_BANKING_PRECHECK:
            if (
                artifact.artifact_type
                is not ArtifactType.BANKING_PRECHECK_SUBMISSION_PROPOSAL
            ):
                raise ValueError(
                    "Banking precheck must reference its exact proposal artifact."
                )
            proposal = BankingPrecheckSubmissionProposal.model_validate(
                artifact.payload
            )
            if (
                proposal.proposed_action
                is not ProtectedAction.SUBMIT_BANKING_PRECHECK
                or proposal.precheck_executed
                or proposal.submission_executed
                or command.payload != banking_precheck_action_payload(proposal)
            ):
                raise ValueError(
                    "The Banking precheck command differs from its unexecuted proposal."
                )
            checkpoint_artifact = (
                await self._banking_precheck_policy_orchestrator.register(
                    proposal_artifact=artifact,
                    context=ExecutionContext(
                        evaluation_case_id=command.evaluation_case_id,
                        dataset_id=self.dataset_id,
                        workflow_run_id=workflow_run_id,
                        input_artifact_ids=(artifact.artifact_id,),
                        requested_scope=run.requested_scope,
                        component_input={
                            "protected_action": command.action_type.value
                        },
                        current_node=WorkflowNode.APPROVAL_GATE.value,
                    ),
                )
            )
            checkpoint_artifact_id = checkpoint_artifact.artifact_id
        elif (
            command.action_type
            is ProtectedAction.CONFIRM_FINAL_CONTRACT_DECISION
        ):
            if artifact.artifact_type is not ArtifactType.DECISION_CARD:
                raise ValueError(
                    "Final Decision confirmation must reference a Decision Card."
                )
            card = DecisionCard.model_validate(artifact.payload)
            if (
                card.recommendation is DecisionRecommendation.NOT_EVALUABLE
                or card.founder_decision_recorded
                or card.approval_requested
                or command.payload != final_decision_action_payload(card)
            ):
                raise ValueError(
                    "The final Decision command differs from its approvable Card."
                )
            checkpoint_artifact = (
                await self._decision_approval_policy_orchestrator.register(
                    decision_card_artifact=artifact,
                    context=ExecutionContext(
                        evaluation_case_id=command.evaluation_case_id,
                        dataset_id=self.dataset_id,
                        workflow_run_id=workflow_run_id,
                        input_artifact_ids=(artifact.artifact_id,),
                        requested_scope=run.requested_scope,
                        component_input={
                            "protected_action": command.action_type.value
                        },
                        current_node=WorkflowNode.APPROVAL_GATE.value,
                    ),
                )
            )
            checkpoint_artifact_id = checkpoint_artifact.artifact_id
        else:
            if (
                artifact.artifact_type
                is not ArtifactType.EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL
            ):
                raise ValueError(
                    "External submission must reference its exact proposal artifact."
                )
            external_proposal = ExternalDocumentSubmissionProposal.model_validate(
                artifact.payload
            )
            if (
                external_proposal.proposed_action
                is not ProtectedAction.SEND_DOCUMENT_TO_EXTERNAL_PARTNER
                or external_proposal.approval_requested
                or external_proposal.release_authorized
                or external_proposal.external_submission_performed
                or command.payload
                != external_document_release_action_payload(external_proposal)
            ):
                raise ValueError(
                    "The external submission command differs from its exact proposal."
                )
        checkpoint_set = await self._approval_orchestrator.checkpoints(
            command.evaluation_case_id,
            checkpoint_artifact_id=checkpoint_artifact_id,
        )
        if not any(
            item.protected_action is command.action_type
            for item in checkpoint_set.checkpoints
        ):
            raise ValueError(
                "The case has no registered checkpoint for this protected action."
            )
        if (
            command.action_type is ProtectedAction.SUBMIT_BANKING_PRECHECK
            and not checkpoint_set.policy_coverages
        ):
            raise ValueError(
                "The case has no registered Banking precheck policy coverage."
            )
        return await self._approval_orchestrator.request_action(
            command,
            workflow_run_id=workflow_run_id,
            allow_running_workflow=True,
            checkpoint_artifact_id=checkpoint_artifact_id,
        )

    async def decide_approval(
        self,
        *,
        request_id: str,
        decision: ApprovalDecision,
        decided_by: str,
        reason: str,
    ) -> ApprovalExecutionResult:
        """Record a human decision and resume or reject the protected action."""
        result = await self._approval_orchestrator.decide(
            request_id=request_id,
            decision=decision,
            decided_by=decided_by,
            reason=reason,
        )
        await self._enqueue_approval_resume(result)
        return result

    async def approval_checkpoints(
        self, evaluation_case_id: str
    ) -> ApprovalCheckpointSet:
        """Return registered future approval gates for one case."""
        return await self._approval_orchestrator.checkpoints(evaluation_case_id)

    async def approval_requests(
        self, evaluation_case_id: str
    ) -> tuple[ApprovalRequest, ...]:
        """Return approval requests created by triggered checkpoints."""
        return await self._approval_orchestrator.list_requests(evaluation_case_id)

    async def start_case_workflow(
        self,
        *,
        contract_id: str,
        evaluation_scope: tuple[EvaluationScope, ...],
        as_of_date: date | None,
        run_request_id: str | None = None,
    ) -> WorkflowStartResult:
        """Create or reuse one durable automatic Initial Assessment workflow."""
        snapshot = self._require_snapshot()
        workflow_identity: tuple[object, ...] = (
            self.dataset_id,
            snapshot.snapshot_hash,
            contract_id,
            evaluation_scope,
            as_of_date,
        )
        if run_request_id is not None:
            workflow_identity = (*workflow_identity, "RUN_REQUEST", run_request_id)
        workflow_run_id = deterministic_id("CWF", *workflow_identity)
        run = await self._case_workflows.get_run(workflow_run_id)
        if run is None:
            now = datetime.now(UTC)
            run = CaseWorkflowRun(
                workflow_run_id=workflow_run_id,
                dataset_id=self.dataset_id,
                dataset_snapshot_hash=snapshot.snapshot_hash,
                contract_id=contract_id,
                status=WorkflowStatus.PENDING,
                current_stage=WorkflowNode.PLANNER_INTAKE.value,
                requested_scope=evaluation_scope,
                as_of_date=as_of_date,
                run_request_id=run_request_id,
                created_at=now,
                updated_at=now,
            )
            await self._case_workflows.save_run(run)
            await self._runtime_events.append(
                workflow_run_id=workflow_run_id,
                event_type="WORKFLOW_CREATED",
                node=None,
                metadata={"contract_id": contract_id},
                created_at=now,
            )
        elif (
            run.status is WorkflowStatus.COMPLETED
            and run.current_stage
            == WorkflowNode.INITIAL_ASSESSMENT_COMPLETED.value
        ):
            now = datetime.now(UTC)
            run = run.model_copy(
                update={
                    "status": WorkflowStatus.PENDING,
                    "current_stage": WorkflowNode.DECISION_ROUTE_PLANNING.value,
                    "updated_at": now,
                }
            )
            await self._case_workflows.save_run(run)
            await self._runtime_events.append(
                workflow_run_id=workflow_run_id,
                event_type="WORKFLOW_EXTENDED_TO_DECISION_INITIAL_ROUTE",
                node=WorkflowNode.DECISION_ROUTE_PLANNING,
                metadata={},
                created_at=now,
            )
        elif (
            run.status is WorkflowStatus.COMPLETED
            and run.current_stage
            in {
                WorkflowNode.FINAL_RISK_READY.value,
                WorkflowNode.DECISION_CARD_READY.value,
            }
            and run.evaluation_case_id is not None
        ):
            artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
            final_risk_artifact = self._latest(
                artifacts, ArtifactType.FINAL_RISK_ASSESSMENT
            )
            if final_risk_artifact is not None:
                identity_inputs = (
                    final_risk_artifact.artifact_id,
                    final_risk_artifact.version,
                    final_risk_artifact.input_hash,
                    self._decision_analysis_configuration_hash,
                )
                expected_node_hash = deterministic_id(
                    "NIN",
                    run.dataset_snapshot_hash,
                    run.evaluation_case_id,
                    WorkflowNode.DECISION_CARD_COMPOSITION,
                    run.as_of_date,
                    identity_inputs,
                )
                decision_node = await self._case_workflows.get_node(
                    run.workflow_run_id,
                    WorkflowNode.DECISION_CARD_COMPOSITION.value,
                )
                should_recompose = (
                    run.current_stage == WorkflowNode.FINAL_RISK_READY.value
                    or decision_node is None
                    or decision_node.input_hash != expected_node_hash
                )
                if not should_recompose:
                    return WorkflowStartResult(
                        workflow_run_id=run.workflow_run_id,
                        evaluation_case_id=run.evaluation_case_id,
                        contract_id=run.contract_id,
                        status=run.status,
                        status_url=f"/api/workflows/{run.workflow_run_id}",
                    )
                now = datetime.now(UTC)
                previous_stage = run.current_stage
                run = run.model_copy(
                    update={
                        "status": WorkflowStatus.PENDING,
                        "current_stage": (
                            WorkflowNode.DECISION_CARD_COMPOSITION.value
                        ),
                        "pending_request_ids": (),
                        "resume_stage": None,
                        "blocked_action": None,
                        "failure_reason": None,
                        "updated_at": now,
                    }
                )
                await self._case_workflows.save_run(run)
                await self._runtime_events.append(
                    workflow_run_id=workflow_run_id,
                    event_type=(
                        "WORKFLOW_EXTENDED_TO_DECISION_CARD"
                        if previous_stage == WorkflowNode.FINAL_RISK_READY.value
                        else "DECISION_CARD_RECOMPOSITION_REQUESTED"
                    ),
                    node=WorkflowNode.DECISION_CARD_COMPOSITION,
                    metadata={
                        "final_risk_artifact_id": final_risk_artifact.artifact_id
                    },
                    created_at=now,
                )
        elif (
            run.status is WorkflowStatus.COMPLETED
            and run.current_stage
            == WorkflowNode.INTERNAL_DECISION_PACKAGE_READY.value
            and run.evaluation_case_id is not None
        ):
            artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
            package_artifact = self._latest(
                artifacts, ArtifactType.INTERNAL_DECISION_PACKAGE
            )
            if package_artifact is not None:
                now = datetime.now(UTC)
                run = run.model_copy(
                    update={
                        "status": WorkflowStatus.PENDING,
                        "current_stage": WorkflowNode.FINAL_RISK_CHECK.value,
                        "pending_request_ids": (),
                        "resume_stage": None,
                        "blocked_action": None,
                        "failure_reason": None,
                        "updated_at": now,
                    }
                )
                await self._case_workflows.save_run(run)
                await self._runtime_events.append(
                    workflow_run_id=workflow_run_id,
                    event_type="WORKFLOW_EXTENDED_TO_FINAL_RISK_CHECK",
                    node=WorkflowNode.FINAL_RISK_CHECK,
                    metadata={
                        "internal_decision_package_artifact_id": (
                            package_artifact.artifact_id
                        )
                    },
                    created_at=now,
                )
        elif (
            run.status is WorkflowStatus.COMPLETED
            and run.current_stage == WorkflowNode.DECISION_ROUTE_PLANNED.value
            and run.evaluation_case_id is not None
        ):
            artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
            route_artifact = self._latest(
                artifacts, ArtifactType.DECISION_ROUTE_PLAN
            )
            request_artifact = self._latest(
                artifacts, ArtifactType.BANKING_DISCOVERY_REQUEST
            )
            route_plan = (
                DecisionRoutePlan.model_validate(route_artifact.payload)
                if route_artifact is not None
                else None
            )
            if (
                route_plan is not None
                and route_plan.route_outcome
                is DecisionRouteOutcome.BANKING_DISCOVERY_REQUIRED
            ):
                next_node = (
                    WorkflowNode.BANKING_INTERNAL_DISCOVERY
                    if request_artifact is not None
                    else WorkflowNode.BANKING_DISCOVERY_HANDOFF
                )
                now = datetime.now(UTC)
                run = run.model_copy(
                    update={
                        "status": WorkflowStatus.PENDING,
                        "current_stage": next_node.value,
                        "updated_at": now,
                    }
                )
                await self._case_workflows.save_run(run)
                await self._runtime_events.append(
                    workflow_run_id=workflow_run_id,
                    event_type=(
                        "WORKFLOW_EXTENDED_TO_BANKING_INTERNAL_DISCOVERY"
                        if request_artifact is not None
                        else "WORKFLOW_EXTENDED_TO_BANKING_DISCOVERY_HANDOFF"
                    ),
                    node=next_node,
                    metadata={},
                    created_at=now,
                )
            elif (
                route_plan is not None
                and route_plan.route_outcome
                is DecisionRouteOutcome.DIRECT_INTERNAL_DECISION
            ):
                now = datetime.now(UTC)
                run = run.model_copy(
                    update={
                        "status": WorkflowStatus.PENDING,
                        "current_stage": (
                            WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY.value
                        ),
                        "updated_at": now,
                    }
                )
                await self._case_workflows.save_run(run)
                await self._runtime_events.append(
                    workflow_run_id=workflow_run_id,
                    event_type=(
                        "WORKFLOW_EXTENDED_TO_INTERNAL_DECISION_PACKAGE"
                    ),
                    node=WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY,
                    metadata={"assembly_path": "DIRECT_ROUTE"},
                    created_at=now,
                )
        elif (
            run.status is WorkflowStatus.COMPLETED
            and run.current_stage == WorkflowNode.BANKING_DISCOVERY_REQUESTED.value
            and run.evaluation_case_id is not None
        ):
            artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
            request_artifact = self._latest(
                artifacts, ArtifactType.BANKING_DISCOVERY_REQUEST
            )
            next_node = (
                WorkflowNode.BANKING_INTERNAL_DISCOVERY
                if request_artifact is not None
                else WorkflowNode.BANKING_DISCOVERY_HANDOFF
            )
            now = datetime.now(UTC)
            run = run.model_copy(
                update={
                    "status": WorkflowStatus.PENDING,
                    "current_stage": next_node.value,
                    "updated_at": now,
                }
            )
            await self._case_workflows.save_run(run)
            await self._runtime_events.append(
                workflow_run_id=workflow_run_id,
                event_type=(
                    "WORKFLOW_EXTENDED_TO_BANKING_INTERNAL_DISCOVERY"
                    if request_artifact is not None
                    else "WORKFLOW_EXTENDED_TO_BANKING_DISCOVERY_HANDOFF"
                ),
                node=next_node,
                metadata={},
                created_at=now,
            )
        elif (
            run.status is WorkflowStatus.COMPLETED
            and run.current_stage == WorkflowNode.BANKING_PRECHECK_RESULTS_READY.value
            and run.evaluation_case_id is not None
        ):
            now = datetime.now(UTC)
            run = run.model_copy(
                update={
                    "status": WorkflowStatus.PENDING,
                    "current_stage": (
                        WorkflowNode.DECISION_POST_PRECHECK_REVIEW.value
                    ),
                    "pending_request_ids": (),
                    "resume_stage": None,
                    "failure_reason": None,
                    "updated_at": now,
                }
            )
            await self._case_workflows.save_run(run)
            await self._runtime_events.append(
                workflow_run_id=workflow_run_id,
                event_type="WORKFLOW_EXTENDED_TO_DECISION_POST_PRECHECK_REVIEW",
                node=WorkflowNode.DECISION_POST_PRECHECK_REVIEW,
                metadata={},
                created_at=now,
            )
        elif (
            run.status is WorkflowStatus.COMPLETED
            and run.current_stage
            == WorkflowNode.DECISION_POST_PRECHECK_REVIEW_COMPLETED.value
            and run.evaluation_case_id is not None
        ):
            artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
            review_artifact = self._latest(
                artifacts, ArtifactType.DECISION_POST_PRECHECK_REVIEW
            )
            review = (
                DecisionPostPrecheckReview.model_validate(review_artifact.payload)
                if review_artifact is not None
                else None
            )
            if (
                review is not None
                and review.outcome
                is DecisionPostPrecheckOutcome.CONDITIONAL_OPTIONS_AVAILABLE
            ):
                now = datetime.now(UTC)
                run = run.model_copy(
                    update={
                        "status": WorkflowStatus.PENDING,
                        "current_stage": WorkflowNode.DECISION_DOCUMENT_HANDOFF.value,
                        "pending_request_ids": (),
                        "resume_stage": None,
                        "blocked_action": None,
                        "failure_reason": None,
                        "updated_at": now,
                    }
                )
                await self._case_workflows.save_run(run)
                await self._runtime_events.append(
                    workflow_run_id=workflow_run_id,
                    event_type="WORKFLOW_EXTENDED_TO_DECISION_DOCUMENT_HANDOFF",
                    node=WorkflowNode.DECISION_DOCUMENT_HANDOFF,
                    metadata={},
                    created_at=now,
                )
            elif review is not None and review.outcome in {
                DecisionPostPrecheckOutcome.ALL_OPTIONS_NOT_ELIGIBLE,
                DecisionPostPrecheckOutcome.NO_PROVIDER_RECOMMENDATION,
                DecisionPostPrecheckOutcome.PRECHECK_SERVICE_UNAVAILABLE,
                DecisionPostPrecheckOutcome.MIXED_NON_ACTIONABLE_RESULTS,
            }:
                now = datetime.now(UTC)
                run = run.model_copy(
                    update={
                        "status": WorkflowStatus.PENDING,
                        "current_stage": (
                            WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY.value
                        ),
                        "pending_request_ids": (),
                        "resume_stage": None,
                        "blocked_action": None,
                        "failure_reason": None,
                        "updated_at": now,
                    }
                )
                await self._case_workflows.save_run(run)
                await self._runtime_events.append(
                    workflow_run_id=workflow_run_id,
                    event_type=(
                        "WORKFLOW_EXTENDED_TO_INTERNAL_DECISION_PACKAGE"
                    ),
                    node=WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY,
                    metadata={"assembly_path": "BANKING_NON_ACTIONABLE"},
                    created_at=now,
                )
        elif (
            run.status is WorkflowStatus.COMPLETED
            and run.current_stage
            in {
                WorkflowNode.DECISION_POST_BANKING_REVIEW.value,
                WorkflowNode.BANKING_PRECHECK_DECLINED.value,
                WorkflowNode.DOCUMENT_RELEASE_PACKAGE_READY.value,
                WorkflowNode.READY_FOR_INTERNAL_DECISION.value,
            }
            and run.evaluation_case_id is not None
        ):
            assembly_path: str | None = None
            if (
                run.current_stage
                == WorkflowNode.DECISION_POST_BANKING_REVIEW.value
            ):
                artifacts = await self._artifacts.list_by_case(
                    run.evaluation_case_id
                )
                review_artifact = self._latest(
                    artifacts, ArtifactType.DECISION_POST_BANKING_REVIEW
                )
                review = (
                    DecisionPostBankingReview.model_validate(
                        review_artifact.payload
                    )
                    if review_artifact is not None
                    else None
                )
                if review is not None and review.outcome in {
                    DecisionPostBankingOutcome.NO_VIABLE_OPTION,
                    DecisionPostBankingOutcome.NO_PRECHECK_PATH,
                }:
                    assembly_path = (
                        "BANKING_NO_VIABLE_OPTION"
                        if review.outcome
                        is DecisionPostBankingOutcome.NO_VIABLE_OPTION
                        else "BANKING_NO_PRECHECK_PATH"
                    )
            elif run.current_stage == WorkflowNode.BANKING_PRECHECK_DECLINED.value:
                assembly_path = "BANKING_PRECHECK_DECLINED"
            else:
                assembly_path = "CONDITIONAL_DOCUMENT_READY"
            if assembly_path is not None:
                now = datetime.now(UTC)
                run = run.model_copy(
                    update={
                        "status": WorkflowStatus.PENDING,
                        "current_stage": (
                            WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY.value
                        ),
                        "pending_request_ids": (),
                        "resume_stage": None,
                        "blocked_action": None,
                        "failure_reason": None,
                        "updated_at": now,
                    }
                )
                await self._case_workflows.save_run(run)
                await self._runtime_events.append(
                    workflow_run_id=workflow_run_id,
                    event_type=(
                        "WORKFLOW_EXTENDED_TO_INTERNAL_DECISION_PACKAGE"
                    ),
                    node=WorkflowNode.INTERNAL_DECISION_PACKAGE_ASSEMBLY,
                    metadata={"assembly_path": assembly_path},
                    created_at=now,
                )
        elif (
            run.status is WorkflowStatus.COMPLETED
            and run.current_stage
            == WorkflowNode.BANKING_PRECHECK_SUBMISSION_AUTHORIZED.value
            and run.evaluation_case_id is not None
        ):
            now = datetime.now(UTC)
            run = run.model_copy(
                update={
                    "status": WorkflowStatus.PENDING,
                    "current_stage": (
                        WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL.value
                    ),
                    "pending_request_ids": (),
                    "resume_stage": None,
                    "blocked_action": None,
                    "failure_reason": None,
                    "updated_at": now,
                }
            )
            await self._case_workflows.save_run(run)
            await self._runtime_events.append(
                workflow_run_id=workflow_run_id,
                event_type="WORKFLOW_EXTENDED_TO_BANKING_PRECHECK_EXECUTION",
                node=WorkflowNode.BANKING_PRECHECK_EXECUTION,
                metadata={},
                created_at=now,
            )
        elif (
            run.status is WorkflowStatus.COMPLETED
            and run.current_stage
            in {
                WorkflowNode.BANKING_PRECHECK_READY.value,
                WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL.value,
            }
            and run.evaluation_case_id is not None
        ):
            now = datetime.now(UTC)
            previous_stage = run.current_stage
            run = run.model_copy(
                update={
                    "status": WorkflowStatus.PENDING,
                    "current_stage": (
                        WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL.value
                    ),
                    "pending_request_ids": (),
                    "resume_stage": None,
                    "blocked_action": None,
                    "failure_reason": None,
                    "updated_at": now,
                }
            )
            await self._case_workflows.save_run(run)
            await self._runtime_events.append(
                workflow_run_id=workflow_run_id,
                event_type=(
                    "WORKFLOW_EXTENDED_TO_BANKING_PRECHECK_SUBMISSION_PROPOSAL"
                    if previous_stage == WorkflowNode.BANKING_PRECHECK_READY.value
                    else "BANKING_PRECHECK_SUBMISSION_PROPOSAL_RECOVERY_REQUESTED"
                ),
                node=WorkflowNode.BANKING_PRECHECK_SUBMISSION_PROPOSAL,
                metadata={},
                created_at=now,
            )
        elif (
            run.status is WorkflowStatus.COMPLETED
            and run.current_stage
            == WorkflowNode.BANKING_INTERNAL_OPTIONS_READY.value
            and run.evaluation_case_id is not None
        ):
            artifacts = await self._artifacts.list_by_case(run.evaluation_case_id)
            case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
            request_artifact = self._latest(
                artifacts, ArtifactType.BANKING_DISCOVERY_REQUEST
            )
            supplement_artifact = self._latest(
                artifacts, ArtifactType.BANKING_INPUT_SUPPLEMENT
            )
            expected_node_hash = deterministic_id(
                "NIN",
                run.dataset_snapshot_hash,
                run.evaluation_case_id,
                WorkflowNode.BANKING_INTERNAL_DISCOVERY,
                run.as_of_date,
                (
                    case_artifact.artifact_id if case_artifact is not None else None,
                    (
                        request_artifact.artifact_id
                        if request_artifact is not None
                        else None
                    ),
                    (
                        supplement_artifact.artifact_id
                        if supplement_artifact is not None
                        else None
                    ),
                    self.banking_policy_hash,
                    self.banking_advisor_configuration_hash,
                    CurrencyCode.VND,
                ),
            )
            banking_node = await self._case_workflows.get_node(
                workflow_run_id, WorkflowNode.BANKING_INTERNAL_DISCOVERY.value
            )
            discovery_is_current = (
                banking_node is not None
                and banking_node.status
                in {
                    WorkflowNodeStatus.COMPLETED,
                    WorkflowNodeStatus.COMPLETED_WITH_WARNINGS,
                }
                and banking_node.input_hash == expected_node_hash
            )
            next_node = (
                WorkflowNode.BANKING_PRECHECK_READINESS
                if discovery_is_current
                else WorkflowNode.BANKING_INTERNAL_DISCOVERY
            )
            now = datetime.now(UTC)
            run = run.model_copy(
                update={
                    "status": WorkflowStatus.PENDING,
                    "current_stage": next_node.value,
                    "pending_request_ids": (),
                    "resume_stage": None,
                    "failure_reason": None,
                    "updated_at": now,
                }
            )
            await self._case_workflows.save_run(run)
            await self._runtime_events.append(
                workflow_run_id=workflow_run_id,
                event_type=(
                    "WORKFLOW_EXTENDED_TO_BANKING_PRECHECK_READINESS"
                    if discovery_is_current
                    else "BANKING_INTERNAL_DISCOVERY_INVALIDATED"
                ),
                node=next_node,
                metadata={},
                created_at=now,
            )
        if run.status in {
            WorkflowStatus.PENDING,
            WorkflowStatus.RUNNING,
        }:
            if self._runner_started:
                await self._workflow_runner.enqueue(workflow_run_id)
            else:
                await self._case_workflow_orchestrator.execute(workflow_run_id)
            refreshed = await self._case_workflows.get_run(workflow_run_id)
            if refreshed is not None:
                run = refreshed
        return WorkflowStartResult(
            workflow_run_id=run.workflow_run_id,
            evaluation_case_id=run.evaluation_case_id,
            contract_id=run.contract_id,
            status=run.status,
            status_url=f"/api/workflows/{run.workflow_run_id}",
        )

    async def case_workflow_summary(self, workflow_run_id: str) -> WorkflowRunSummary:
        """Return durable automatic workflow progress and artifact references."""
        return await self._case_workflow_orchestrator.summary(workflow_run_id)

    async def resume_case_workflow(self, workflow_run_id: str) -> WorkflowStartResult:
        """Resume a workflow after its external blocking condition has changed."""
        run = await self._case_workflow_orchestrator.resume(workflow_run_id)
        if self._runner_started:
            await self._workflow_runner.enqueue(workflow_run_id)
        else:
            await self._case_workflow_orchestrator.execute(workflow_run_id)
            refreshed = await self._case_workflows.get_run(workflow_run_id)
            if refreshed is not None:
                run = refreshed
        return WorkflowStartResult(
            workflow_run_id=run.workflow_run_id,
            evaluation_case_id=run.evaluation_case_id,
            contract_id=run.contract_id,
            status=run.status,
            status_url=f"/api/workflows/{run.workflow_run_id}",
        )

    async def submit_banking_input(
        self,
        *,
        evaluation_case_id: str,
        submission: BankingAmountInputSubmission,
    ) -> tuple[BankingInputExecutionResult, WorkflowStartResult]:
        """Persist a typed supplement and automatically resume its exact workflow."""
        lock = self._banking_input_submission_locks.setdefault(
            submission.workflow_run_id, asyncio.Lock()
        )
        async with lock:
            result, run = await self._case_workflow_orchestrator.submit_banking_input(
                evaluation_case_id=evaluation_case_id,
                submission=submission,
            )
            if result.status is WorkflowStatus.COMPLETED and run.status in {
                WorkflowStatus.PENDING,
                WorkflowStatus.RUNNING,
            }:
                if self._runner_started:
                    await self._workflow_runner.enqueue(run.workflow_run_id)
                else:
                    await self._case_workflow_orchestrator.execute(
                        run.workflow_run_id
                    )
                    refreshed = await self._case_workflows.get_run(
                        run.workflow_run_id
                    )
                    if refreshed is not None:
                        run = refreshed
        workflow = WorkflowStartResult(
            workflow_run_id=run.workflow_run_id,
            evaluation_case_id=run.evaluation_case_id,
            contract_id=run.contract_id,
            status=run.status,
            status_url=f"/api/workflows/{run.workflow_run_id}",
        )
        return result, workflow

    async def submit_banking_precheck_evidence(
        self,
        *,
        evaluation_case_id: str,
        submission: BankingPrecheckEvidenceSubmission,
    ) -> tuple[BankingPrecheckEvidenceExecutionResult, WorkflowStartResult]:
        """Accept a staff evidence reference and expose the fresh-precheck handoff."""
        lock = self._banking_precheck_evidence_submission_locks.setdefault(
            submission.workflow_run_id, asyncio.Lock()
        )
        async with lock:
            trusted_submission = submission.model_copy(
                update={"provided_by": "AUTHORIZED_STAFF"}
            )
            result, run = (
                await self._case_workflow_orchestrator.submit_banking_precheck_evidence(
                    evaluation_case_id=evaluation_case_id,
                    submission=trusted_submission,
                )
            )
        workflow = WorkflowStartResult(
            workflow_run_id=run.workflow_run_id,
            evaluation_case_id=run.evaluation_case_id,
            contract_id=run.contract_id,
            status=run.status,
            status_url=f"/api/workflows/{run.workflow_run_id}",
        )
        return result, workflow

    async def submit_document_evidence(
        self,
        *,
        evaluation_case_id: str,
        submission: DocumentEvidenceSubmission,
    ) -> tuple[DocumentEvidenceExecutionResult, WorkflowStartResult]:
        """Accept metadata-only evidence and automatically resume Document preparation."""
        lock = self._document_evidence_submission_locks.setdefault(
            submission.workflow_run_id, asyncio.Lock()
        )
        async with lock:
            trusted = submission.model_copy(update={"provided_by": "AUTHORIZED_STAFF"})
            result, run = await self._case_workflow_orchestrator.submit_document_evidence(
                evaluation_case_id=evaluation_case_id,
                submission=trusted,
            )
            if result.status is WorkflowStatus.COMPLETED and run.status in {
                WorkflowStatus.PENDING,
                WorkflowStatus.RUNNING,
            }:
                if self._runner_started:
                    await self._workflow_runner.enqueue(run.workflow_run_id)
                else:
                    await self._case_workflow_orchestrator.execute(
                        run.workflow_run_id
                    )
                    refreshed = await self._case_workflows.get_run(run.workflow_run_id)
                    if refreshed is not None:
                        run = refreshed
        workflow = WorkflowStartResult(
            workflow_run_id=run.workflow_run_id,
            evaluation_case_id=run.evaluation_case_id,
            contract_id=run.contract_id,
            status=run.status,
            status_url=f"/api/workflows/{run.workflow_run_id}",
        )
        return result, workflow

    async def case_workflow_events(
        self, workflow_run_id: str, after_sequence: int
    ) -> tuple[WorkflowEvent, ...]:
        """Return ordered events after validating that the workflow exists."""
        await self._case_workflow_orchestrator.summary(workflow_run_id)
        return await self._runtime_events.list_after(workflow_run_id, after_sequence)

    async def _resume_started_risk(
        self,
        evaluation_case_id: str,
        upstream_status: WorkflowStatus,
    ) -> None:
        if upstream_status is not WorkflowStatus.COMPLETED:
            return
        state = await self._risk_orchestrator.get_state(evaluation_case_id)
        if state is not None and state.status is RiskRunStatus.WAITING_FOR_FACTS:
            await self.risk_assessment(evaluation_case_id=evaluation_case_id)

    async def _enqueue_approval_resume(
        self, result: ApprovalExecutionResult
    ) -> None:
        """Resume the exact Master Workflow authorized by Governance."""
        workflow_run_id = result.workflow_run_id
        if result.status is not WorkflowStatus.PENDING or workflow_run_id is None:
            return
        if await self._case_workflows.get_run(workflow_run_id) is None:
            return
        if self._runner_started:
            await self._workflow_runner.enqueue(workflow_run_id)
        else:
            await self._case_workflow_orchestrator.execute(workflow_run_id)

    async def artifacts_for_case(self, evaluation_case_id: str) -> tuple[ArtifactEnvelope, ...]:
        """Expose immutable case artifacts for prototype inspection."""
        return await self._artifacts.list_by_case(evaluation_case_id)

    async def _decision_case(
        self, evaluation_case_id: str
    ) -> tuple[ArtifactEnvelope, EvaluationCase]:
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        case_artifact = self._latest(artifacts, ArtifactType.EVALUATION_CASE)
        if (
            case_artifact is None
            or case_artifact.validation_status
            not in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
        ):
            raise FinalDecisionCaseNotFoundError(
                "Final Decision requires a validated EvaluationCase."
            )
        return case_artifact, EvaluationCase.model_validate(case_artifact.payload)

    async def _required_case_artifact(
        self,
        *,
        evaluation_case_id: str,
        artifact_id: str,
        artifact_type: ArtifactType,
    ) -> ArtifactEnvelope:
        artifact = await self._artifacts.get(artifact_id)
        if (
            artifact is None
            or artifact.evaluation_case_id != evaluation_case_id
            or artifact.artifact_type is not artifact_type
            or artifact.validation_status
            not in {ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS}
        ):
            raise FinalDecisionCaseNotFoundError(
                f"Final Decision requires this case's validated {artifact_type.value}."
            )
        artifacts = await self._artifacts.list_by_case(evaluation_case_id)
        latest = self._latest(artifacts, artifact_type)
        if latest is None or latest.artifact_id != artifact.artifact_id:
            raise FinalDecisionCaseNotFoundError(
                f"Final Decision requires the current {artifact_type.value}."
            )
        return artifact

    @staticmethod
    def _latest(
        artifacts: tuple[ArtifactEnvelope, ...], artifact_type: ArtifactType
    ) -> ArtifactEnvelope | None:
        matches = tuple(item for item in artifacts if item.artifact_type is artifact_type)
        return max(matches, key=lambda item: item.version, default=None)

    def _require_snapshot(self) -> DatasetSnapshot:
        if self._snapshot is None:
            raise RuntimeError("PlannerRuntime.startup() must run before API requests.")
        return self._snapshot
