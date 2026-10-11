# API Gap Analysis — read expansion đề xuất

Audit HEAD `707f58a`, 10/10/2026. **Không endpoint/DTO/port/database nào được sửa trong bước này.** Paths/fields dưới đây là proposals để owner duyệt; giữ mọi existing API và Governance semantics.

## Existing capabilities và gaps

| Existing GET | Có thể dùng | Gap target |
|---|---|---|
| `/api/contracts` | Configured dataset, snapshot hash, exact contract IDs | Không metadata list/customer/value/status, quality tổng hợp hoặc run summary |
| `/api/workflows/{run}` | Nodes/status/current stage, compact artifact refs, pending controls | Chưa discover tất cả runs; summary không expose graph edges/topology version đầy đủ |
| `/api/workflows/{run}/dashboard` | Canonical stages/tasks, business vs execution status, interactions, input, selected metrics | Một run, không executive/global/company aggregation; metrics không chứa full cash series/lineage |
| `/api/workflows/{run}/events?after_sequence=N` | Ordered incremental events | Một run; events là audit detail, không authoritative topology hoặc state |
| `/api/cases/{case}/artifacts` | Payload/evidence/input lineage/version | Case-wide; frontend phải lọc exact run reference; không company dataset read API |
| `/api/cases/{case}/approval-requests` | Exact pending/resolved request detail | Không global enumeration; không thể quét unknown cases bằng API hiện hành |
| `/api/cases/{case}/approval-checkpoints` | Future gate registry | REGISTERED checkpoint không pending human request; không dùng làm Executive queue |

Không thêm GET bằng cách gọi POST planner/assessment/run để "chuẩn bị dữ liệu". `CaseWorkflowRepository.list_recoverable` chỉ restart PENDING/RUNNING, không full index của WAITING_FOR_INPUT/APPROVAL hoặc terminal runs; cần thêm read queries/ports sau duyệt. Pagination, filters và index/migration nhu cầu phải review, không khẳng định port/schema hiện đã đủ.

## Minimum read endpoints đề xuất

| Proposal | Output / consumer | Dependence và review |
|---|---|---|
| `GET /api/company/snapshot` | Identity, source/snapshot hashes, nullable data_as_of, per-sheet periods/quality, safe profile; cả ba global pages | Server-configured single-company context, allowlisted profile fields; không path supplied bởi client |
| `GET /api/company/overview` | Mapping C*/D7–D10: per-scope metrics, status distributions, cash series, coverage/drill-down; Company + Executive financial strip | Server aggregation không phụ thuộc chạy assessments; month window chỉ cashflow; shared computation không lặp Finance facts theo contract |
| `GET /api/company/records/{entity}` | Allowlist contracts/orders/invoices/alerts, paginated safe rows + field provenance, filters | Không arbitrary sheet/entity/path; explicit relation details và excluded coverage; reuse cho company tables |
| `GET /api/executive/overview` | Pending action counts by group, preview rows, contract attention reasons, read time/coverage | Read tất cả compatible persisted runs/requests trong configured scope; lấy projections/typed interactions để giữ meanings, không tạo urgency/business state |
| `GET /api/executive/actions` | Full paginated queue; exact run/case/request/subject binding và typed drill-down | Distinct request IDs và typed input interactions; cursor/group filters; matching count population với overview |
| `GET /api/contracts/overview` | List safe contract metadata + nullable representative run reference + coverage | Giữ `/api/contracts` nguyên vẹn; no run là absence, không domain state mới; contract source status tách workflow state |
| `GET /api/contracts/{contract_id}/runs` | Compatible run index với ID, snapshot, as_of_date, created/updated, statuses | Read all statuses, stable sorting/paging; selection policy explicit; không dùng recoverable-only query |
| `GET /api/workflows/{run}/graph` | Versioned canonical node/edge definitions + route applicability + run references | Dify-style read-only viewer; graph taxonomy mapping to existing enums/tasks, server branch truth; không node-editor/save/publish APIs |

Endpoint granularity có thể gom lại khi duyệt contracts, nhưng phải giữ coverage, consistency và pagination. `/company/overview` không mặc định trả toàn bộ sensitive record payload. Không thêm mutation nào cho ba trang mới; các mutations hiện hành chỉ qua existing exact review/forms.

## Proposed read schema requirements

- Snapshot response tách source_hash/snapshot_hash, company_id resolved, source_business_as_of nullable và response_generated_at. Ingestion/response time không business update time. BASE_SNAPSHOT và run overlay không âm thầm trộn.
- Metrics/series: metadata như [mapping](10_data_to_ui_mapping.md); source records theo canonical keys/fields, không filesystem locator. Quality phản ánh validation, không real bank/legal verification.
- Queue row: existing interaction_type và status nếu nguồn có; contract_id, workflow_run_id, evaluation_case_id, request/approval IDs, subject_artifact_id/version/input_hash, protected_action và evidence/detail link. Chưa xác minh authority thì CTA review disabled hoặc view-only kèm reason; không tạo domain state để biểu đạt khả năng UI.
- Rows/counters trả shared read token/time và total/scanned scope. Nếu action queries không transactional hoặc projection nguồn lệch phiên đọc, phải surface partial/stale và không claim complete queue. Submit vẫn re-fetch/revalidate ở existing approval flow.
- Run index: phân nhóm compatible với configured dataset/snapshot và historical/other snapshots có explicit badge/scope. **Đề xuất** default workspace dùng latest compatible `created_at`, deterministic tie-break run ID; owner chưa duyệt. Exact deep link không bị override bởi default selector.
- All pending queue không phụ thuộc representative run policy. Đề xuất enumerate pending trong configured dataset, tách nhóm snapshot hiện hành và snapshot cũ; không ngầm biến older-snapshot request thành actionable cho snapshot hiện hành. Request cũ phải xác minh riêng; không tự đóng/hide vì có run mới. Owner phải duyệt historical-snapshot authority/visibility trước implementation. Counts published phải phân biệt pending-source vs verified-actionable nếu verification coverage khác; unresolved historical policy không được trình bày như queue đã đầy đủ.
- Graph nodes/edges lấy executable orchestration + typed branch outcomes; summary hiện chưa contract dependency edges. `waiting_for` không phải graph topology đầy đủ. Unknown/undetermined branch ghi undetermined theo enum applicability đã có, không giả "đã thực thi"; terminal readiness không vẽ external-send node.

## Implementation boundaries sau duyệt

API translation → read application service → domain/ports → infrastructure. Aggregation/data quality ở server deterministic; business components không persist hay đổi workflow để đáp ứng dashboard. Reuse existing normalization/calculation khi semantics đúng nhưng không import concrete Excel/SQLite vào domain/business. New query ports/indexes chỉ read scope; migration là điểm review riêng nếu cần. Không sửa workbook, runtime DB thật hoặc secret/config để tạo demo.

No auth/RBAC ở HEAD: các global read surfaces vẫn trusted local prototype, không giả multi-user permissions. Apply data minimization/server allowlist; scope security cho deployment multi-user phải là task riêng, không được diễn giải Founder label thành authenticated owner.

## Gate trước implementation API

Owner cần duyệt: read endpoint scope; BASE snapshot vs overlays; pending all-runs population + historical visibility; representative run selection; financial units/date/quality rules; graph topology contract. Khi chưa duyệt API, chỉ có thể làm labelled UI fixtures/unavailable presentation nếu được cho phép; chưa đủ để gọi Executive Home connected hoàn chỉnh.
