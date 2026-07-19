# Document Skill — internal outbound dossier and Decision handoff

## Scope

Document Skill prepares a bank-facing dossier candidate **inside OPC** from one validated Decision
handoff. It classifies provider requirements, creates blocking requests for genuinely missing
documents, applies data minimization and deterministic masking, and produces a release candidate
that Workflow can pass to Internal Decision Package assembly.

Document Skill does not select a bank/product, approve a protected action, persist artifacts,
change workflow state, call an external connector, send a file, or create the final Decision Card.
Business components return drafts/signals; Workflow validates and persists them and owns
pause/resume; Governance owns Founder approval.

## End-to-end flow

```text
BANKING_PRECHECK_RESULT_SET (SIMULATED_NON_BINDING)
→ DECISION_POST_PRECHECK_REVIEW
→ DECISION_DOCUMENT_HANDOFF
→ exactly one DOCUMENT_PREPARATION_REQUEST
→ DOCUMENT_PREPARATION
    → DOCUMENT_CHECKLIST
    → DOCUMENT_PACKAGE_DRAFT
    ├── blocking document gap
    │     → MissingDataRequest
    │     → WAITING_FOR_INPUT at DOCUMENT_PREPARATION
    │     → DOCUMENT_EVIDENCE_SUPPLEMENT
    │     → rebuild checklist/package without mutating old artifacts
    └── no blocking gap
          → DOCUMENT_RELEASE_PACKAGE_READY
          → INTERNAL_DECISION_PACKAGE_ASSEMBLY
          → persist as the conditional path's masked source
          → no approval request and no external send
```

Document Skill itself stops at the internal package-ready boundary. Master Workflow may then
assemble `INTERNAL_DECISION_PACKAGE`; that downstream artifact is an evidence dossier only. The
implemented downstream Decision flow may later reference the exact package after Final Risk. That
does not expand Document's boundary: the real VietinBank call and external send remain
unimplemented.

## 1. Decision-to-Document handoff

The handoff consumes the validated provider result set and matching Decision post-precheck review.
It creates one `DOCUMENT_PREPARATION_REQUEST` per viable full-coverage conditional result. Each
request retains exact identifiers for result, review item, option, bank product, API/provider,
requested/supported amount, provider document/condition codes and upstream evidence.

The request always states:

```text
provider_result_authority = SIMULATED_NON_BINDING
non_binding               = true
selection_performed       = false
bank_approval_obtained    = false
documents_prepared        = false
external_release_performed = false
```

The component does not select among requests. The Master Workflow auto-runs Document only when the
handoff produces exactly one request. On a conditional branch, zero requests fails safe with
`CONDITIONAL_RESULT_HAS_NO_DOCUMENT_PREPARATION_REQUEST`; more than one fails safe with
`MULTIPLE_DOCUMENT_OPTIONS_REQUIRE_DECISION_SELECTION`. Multi-option selection is future Decision
work.

The phase requires `supported_amount == requested_amount`. Partial coverage and funding-gap
combination are deliberately deferred; they must not be silently treated as full coverage.

## 2. Provider requirements in the current scenario

The TeamPack has no real provider response. The server-owned `API-002` scenario supplies these
simulated, non-binding codes:

| Document code | Current deterministic handling |
|---|---|
| `SIGNED_CONTRACT` | `MISSING` until exact opaque reference metadata is supplied; then `AVAILABLE_WITH_LIMITATIONS` with `DOCUMENT_REFERENCE_NOT_REPOSITORY_VERIFIED` because repository/signature verification is not implemented |
| `COMPANY_PROFILE` | `AVAILABLE` only from exact configured `02_OPC_PROFILE` fields; if those fields are absent, an exact opaque supplement resolves the document requirement as `AVAILABLE_WITH_LIMITATIONS` without inventing structured profile values |
| `PERFORMANCE_BOND_REQUEST_FORM` | `DRAFTED` with limitation `DRAFT_NOT_SIGNED` |
| `CASHFLOW_BUFFER_EVIDENCE` | `AVAILABLE_WITH_LIMITATIONS` when OPC-global cashflow exists; never attributed to the contract |

The provider condition codes carried into the handoff are `CONTRACT_SIGNED` and
`CASHFLOW_BUFFER_CONFIRMED`. They are scenario facts, not conditions inferred by OpenAI.
They are preserved unchanged in `DOCUMENT_CHECKLIST`, `DOCUMENT_PACKAGE_DRAFT`,
`DOCUMENT_RELEASE_PACKAGE`. Their presence does **not** mean Document has verified or satisfied
either condition, and package readiness does not ask the Founder to accept them.

The current composition root treats `company_id` and `company_name` as the minimum profile fields
needed to build this prototype package. This is a server-side prototype assumption because neither
TeamPack nor VietinBank response schema defines an official company-profile document contract.
Missing required fields fail closed unless authorized staff supplies an exact opaque reference for
the `COMPANY_PROFILE` requirement. That reference is preserved with
`DOCUMENT_REFERENCE_NOT_REPOSITORY_VERIFIED`; it does not imply or populate `company_id`,
`company_name`, or any other structured value. A real integration must move the profile-field
assumption into a versioned provider schema/policy; Document must not fuzzy-match other fields or
use unrelated profile or credit data as a substitute.

## 3. Checklist and blocking behavior

`DOCUMENT_CHECKLIST` contains one ordered `DocumentChecklistItem` per provider code. The principal
enums are:

| Enum | Meaning |
|---|---|
| `AVAILABLE` | Exact evidence/reference is available. |
| `DRAFTED` | OPC can create an internal unsigned draft. |
| `MISSING` | Required evidence is absent; the item has an exact `missing_request_id`. |
| `AVAILABLE_WITH_LIMITATIONS` | Evidence exists but its scope/authority must remain explicit. |
| `NOT_APPLICABLE` | Requirement does not apply to the current request. |

Only `MISSING` items produce blocking `MissingDataRequest` objects. The package readiness is then:

| `DocumentPackageReadiness` | Meaning |
|---|---|
| `WAITING_FOR_INPUT` | At least one blocking document request remains open. |
| `READY_FOR_INTERNAL_DECISION` | No blocking request remains; the package can become an internal Decision input. This is not release review or authorization. |
| `READY_FOR_RELEASE_REVIEW` | Legacy persisted value accepted for backward compatibility; new runs do not emit it. |

With the current TeamPack, structured contract rows are not proof of a signed file. Therefore the
first `API-002` Document run pauses for `SIGNED_CONTRACT` rather than inventing a file reference.
Non-blocking limitations are aggregated without being converted into risk conclusions or satisfied
conditions. The current release review can therefore expose `DRAFT_NOT_SIGNED`,
`CASHFLOW_OPC_GLOBAL_NOT_CONTRACT_ATTRIBUTABLE`, and after a reference supplement,
`DOCUMENT_REFERENCE_NOT_REPOSITORY_VERIFIED`.

## 4. Reference-only document intake and resume

The typed route is:

```http
POST /api/cases/{evaluation_case_id}/documents/evidence-supplements
```

The evidence-intake contract accepts metadata only:

```json
{
  "workflow_run_id": "CWF-...",
  "missing_request_id": "MDR-...",
  "document_reference_id": "DOCREF-550e8400-e29b-41d4-a716-446655440000",
  "content_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "document_type": "SIGNED_CONTRACT",
  "evidence_note": "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED"
}
```

The prototype overwrites `provided_by` with the fixed server-side label `AUTHORIZED_STAFF`, but it
does not yet authenticate that principal or provide RBAC. `evidence_note` is the controlled enum
`REQUESTED_DOCUMENT_REFERENCE_SUPPLIED`, not free text. `document_reference_id` must use the
`DOCREF-<UUIDv4>` namespace; it is still caller-declared metadata, not a path, URL, or verified
repository object.
Raw file bytes are outside this API contract. The intake validates the exact open request, case,
workflow, document type and package draft, then persists an immutable
`DOCUMENT_EVIDENCE_SUPPLEMENT` through the Orchestrator.

Repeated identical metadata is idempotent. Conflicting metadata for an already resolved request is
rejected. Once all requests are resolved, the same workflow is queued to rebuild Document artifacts;
previous checklist/package versions remain immutable for audit.

This prototype does not yet implement file upload, malware scanning, signature verification or a
document repository. The opaque reference and content digest prove metadata binding only, not the
legal validity of the referenced signed contract. `DOCUMENT_RELEASE_PACKAGE` does not embed or
transmit the referenced bytes; a future connector must resolve an authorized repository reference
through a dedicated secure document port.

## 5. Package artifacts

`DOCUMENT_PACKAGE_DRAFT` contains:

- exact case/request/checklist and upstream artifact references;
- recipient and purpose;
- provider `approval_condition_codes` and aggregated `limitation_codes`;
- `sanitized_payload` only;
- classification decisions and a `MaskingManifest`;
- blocking `missing_data_requests`, when present;
- stable identity derived from business inputs, supplements and masking policy outputs; and
- `internal_draft = true`, `release_authorized = false`,
  `external_release_performed = false`.

When readiness becomes `READY_FOR_INTERNAL_DECISION`, Document also returns
`DOCUMENT_RELEASE_PACKAGE`. It is a complete internal candidate consumed by the conditional
Internal Decision Package path, not an approval subject or proof of release. It retains exact
checklist/document codes, provider conditions, limitations and the same sanitized payload/masking
proof. Its typed per-document manifest contains only document code/status,
limitation codes, opaque source reference IDs and evidence IDs. It contains no raw bytes or
filesystem path. `AVAILABLE_WITH_LIMITATIONS` proves only that reference metadata/evidence exists;
it does not prove repository existence, signature validity or legal acceptability. The package
still keeps:

```text
release_authorized         = false
external_release_performed = false
```

Evidence Validator runs before either artifact is persisted. It checks deterministic IDs, exact
source-artifact/evidence closure, checklist partition, blocking/readiness consistency, masking
decisions, manifest alignment and forbidden secret/raw fields.

## 6. Data minimization and masking

The package purpose is `PERFORMANCE_BOND_DOCUMENT_RELEASE`. Document declares the exact recipient,
purpose and minimum required fields before masking. Fields not required for the purpose are omitted;
unknown fields or missing exact policy rules fail closed.

Every declared required field must be present in the flat input payload. The recipient must pass
the global exact-recipient allowlist and the exact allowlist on each included field rule; wildcard
recipient rules are forbidden. `required_fields` cannot override either allowlist. Company-profile
fields are selected and required only when the provider request includes `COMPANY_PROFILE` and
structured profile evidence is used. Unknown/unrelated OPC profile records are ignored before the
masking input is formed. When the provider does not request a company profile, or an opaque profile
document supplement resolves that requirement, structured profile fields are minimized away and
cannot be inferred from the reference.

The executable policy is server-owned at `config/data_protection/masking_policy.json`. It may be
overridden with `MASKING_POLICY_PATH`. Sheet `21_MASKING_EXAMPLES` contains examples only: it is not
an executable policy, does not choose algorithms and cannot change behavior when edited.

The current controls include:

- data minimization before transformation;
- `ALLOW_EXACT` only for exact field/purpose/recipient allowlists;
- contextual `HMAC-SHA256` tokenization for restricted identifiers;
- configured VND banding for generalized amounts;
- deterministic free-text redaction;
- omission of restricted secrets;
- `vault://` references instead of raw connector credentials; and
- a per-field `MaskingManifest` with safe output digest, exact upstream source-evidence IDs,
  canonical policy SHA-256 and `raw_value_persisted = false`;
- Governance recomputation of the masked payload from exact upstream evidence using the trusted
  masking service, so recomputing only client/self-referential IDs cannot legitimize tampering.

HMAC namespace is exactly `provider | purpose | field_type | key_version`. Runtime key material is
loaded from `OPC_MIS_MASKING_HMAC_KEY_BASE64`, must decode to at least 32 bytes (256 bit), is hidden
from repr/log/artifacts, and is never stored in TeamPack or policy JSON. Token material is at least
16 bytes (128 bit). Missing/invalid key makes outbound Document masking unavailable and the
Document path fails closed; it never falls back to a public hash or constant key.

HMAC tokens are pseudonyms. They reduce direct identifier exposure but do not make the dossier
anonymous. `PARTIAL_MASK` is suitable only for display and is not a replacement for partner-payload
tokenization. Plain hashing, Base64, encryption alone and LLM rewriting are not masking algorithms.

See [Data Masking Policy](DATA_MASKING_POLICY.md) and
[Data Masking Algorithms](DATA_MASKING_ALGORITHMS.md) for the threat model and formulae.

## 7. Dormant checkpoint and implemented downstream Decision trigger

Creating `DOCUMENT_RELEASE_PACKAGE` does not propose an external release. Workflow persists it as
an internal input, then may assemble the Internal Decision Package without creating an
`ActionCommand`, `ApprovalRequest`, or Founder pause. At this boundary the summary remains:

```text
document_release_authorized         = false
document_external_release_performed = false
```

Initial Risk may already have registered the evidence-backed checkpoint for
`SEND_DOCUMENT_TO_EXTERNAL_PARTNER`. Registration is non-blocking, and that checkpoint remains
dormant while only `DOCUMENT_RELEASE_PACKAGE` exists. Approval for
`SUBMIT_BANKING_PRECHECK` cannot be reused for a later document send.

Internal Decision Package assembly preserves the validated release package and its masking proof,
but still does not activate `SEND_DOCUMENT_TO_EXTERNAL_PARTNER`. The downstream Decision phase now
builds an evidence-bound Card and presents an approvable recommendation to the Founder. Only an
approved `ACCEPT` Card that preserves this exact package may produce an
`EXTERNAL_DOCUMENT_SUBMISSION_PROPOSAL`; only that validated proposal activates the separate
Document-send checkpoint. Neither the raw release package nor the Internal Decision Package is an
external-release approval subject by itself, and the final-decision approval cannot be reused as
release approval.

After the separate proposal approval, Workflow stops at `READY_FOR_EXTERNAL_SUBMISSION`. The
authorization-to-real-connector transition, actual send, provider receipt, retry and delivery
reconciliation remain unimplemented. See
[Decision, Final Approval, and External-Release Readiness](DECISION_FINAL_APPROVAL_AND_RELEASE.md).

## 8. Responsibility boundary

This phase does not:

- call VietinBank or any external document API;
- make a banking recommendation or select among multiple options;
- fill a partial funding/guarantee gap;
- treat mock eligibility or supported amount as a real bank decision;
- verify a human signature or the legal validity of a document reference;
- let Founder approval bypass masking/secret suppression;
- send the artifact envelope or raw evidence closure as an outbound payload;
- assemble the Internal Decision Package or create a Decision Card;
- request Founder approval merely because a release package is ready; or
- perform an actual external release.

The internal artifact envelope may retain raw TeamPack evidence to preserve lineage. The current
artifact inspection API has no authentication/RBAC, so it must not be exposed beyond a trusted
prototype environment. A future connector must serialize only the validated `sanitized_payload`,
never the full artifact/evidence closure. Moving all raw evidence behind a reference-only evidence
vault is a known future hardening item.

See [Internal Decision Package](INTERNAL_DECISION_PACKAGE.md) for the downstream convergence and
evidence-bound assembly rules.
