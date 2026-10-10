# Updated Information Architecture — Executive Home + Drill-down

Ngày: 10/10/2026. Baseline source: HEAD `707f58a` (merge PR #3). **Kế hoạch tài liệu, chưa triển khai.** User đã chốt mô hình sản phẩm; routes, read APIs và policies đề xuất dưới đây chưa được duyệt để code. Backend/API hiện hành giữ nguyên.

## Bộ tài liệu và nguồn chuẩn

1. Tài liệu này: sitemap/navigation và audit HEAD.
2. [Executive Dashboard Specification](08_executive_dashboard_specification.md).
3. [Company Overview Specification](09_company_overview_specification.md).
4. [Data-to-UI Mapping](10_data_to_ui_mapping.md): classification, scope và chống double-count.
5. [API Gap Analysis](11_api_gap_analysis.md): đề xuất read contracts, không phải API đã có.
6. [Revised Implementation Roadmap](12_revised_implementation_roadmap.md): phases, acceptance, tests và review gates.

Style hiện hành: [style.md](../../style.md), [03_design_system.md](03_design_system.md). Hiện trạng UI: [handoff sau PR #3](06_frontend_handoff.md). Khi tài liệu cũ khác source, source HEAD là cơ sở về chức năng đã triển khai; phần target IA ở bộ 07–12 là kế hoạch tiếp theo.

| Source HEAD đã đối chiếu | Kết luận |
|---|---|
| `api/routes.py`, `api/schemas.py` | `/contracts` chỉ trả `dataset_id`, `snapshot_hash`, `contract_ids`; chưa list contract metadata, global actions, company overview hoặc run history |
| `api/dashboard_schemas.py`, `dashboard_projection.py` | Read model của **một run**, có business/execution status, stages/tasks, interactions, run artifact references; selected metrics chỉ Finance CASE_SPECIFIC và Banking request |
| `domain/case_workflow_models.py`, `approvals.py` | Run có dataset snapshot, contract, assessment date; request có exact run/case/subject version/hash/action; node states chưa có edge/dependency graph contract |
| `ports/case_workflow_repository.py`, SQLite implementation | Có `get_run`, `list_nodes`, `list_recoverable`; recoverable chỉ PENDING/RUNNING, không thay thế full run index hoặc action queue gồm các run đang chờ |
| `domain/team_pack.py`, `domain/dataset.py`, Excel ingestion | Named sheets/headers, source/snapshot hashes, records, duplicate/validation information; snapshot không chứa timestamp xác nhận dữ liệu nghiệp vụ được cập nhật |
| Finance `fact_builder.py`, `cashflow.py`, `receivables.py` | Contract/order/invoice facts và OPC_GLOBAL cash projection có nghĩa riêng; không có actual company balance/time series đã expose |
| `workflow/case_workflow_orchestrator.py`, `domain/workflow.py` | Topology/branches phải đối chiếu executable orchestration, không chỉ vẽ theo sequence trong docs |
| `frontend/src/app`, `features/workspace`, `shared`, `features/artifacts` | Hiện có single-contract local views; PR #3 bổ sung detail/lineage, focus semantics, incremental events và UI polish |

Một số prose cũ cần đọc như lịch sử: `FINANCE_AGENT.md` còn mô tả artifact repository process-local; hiện API dùng persisted infrastructure. `MASTER_WORKFLOW.md` tóm tắt negotiation, chưa đủ chi tiết gates hiện hành. Không copy những đoạn này để tạo state/topology mới.

## Sitemap target

```text
OPC MIS
├── Dashboard                         /dashboard (default Executive Home)
├── Tình hình công ty                 /company
│   ├── Tổng quan                     ?section=overview
│   ├── Tài chính & dòng tiền         ?section=finance
│   ├── Hợp đồng & đơn hàng           ?section=business
│   ├── Hóa đơn                       ?section=invoices
│   └── Cảnh báo & giới hạn dữ liệu    ?section=alerts
└── Hợp đồng                          /contracts
    └── Contract Decision Workspace   /contracts/:contractId
        ├── Tổng quan                 ?view=overview
        ├── Đánh giá                  ?view=assessments
        ├── Workflow                  ?view=workflow
        ├── Bằng chứng                ?view=evidence
        └── Lịch sử                   ?view=history
```

Các URL là **target presentation**, chưa tồn tại. Contract view có thể thêm `run=<workflow_run_id>`; review link thêm `request=<request_id>` hoặc `artifact=<artifact_id>&version=<N>` theo loại nội dung. Filter tài chính có `month_from/month_to`; không tự đưa filter này sang operational action queue.

### Navigation và context

- Sidebar cấp một chỉ ba mục: Dashboard, Tình hình công ty, Hợp đồng. Giữ palette Mercury, compact controls và typography hiện hành.
- Company sections là tabs/anchors, không tạo năm global modules. Contract tabs chỉ xuất hiện trong selected-contract workspace; Workflow không thành global editor.
- Breadcrumb: `Hợp đồng / <ID> / <view>`. Contract selector giữ view hợp lệ, reset artifact/request panel cũ; run selector ghi assessment date và execution/business status riêng.
- Workspace Tổng quan giữ Decision summary, limitations, pending actions, input readiness và CTA bắt đầu run. Form bổ sung dữ liệu chuyển thành contextual dialog/panel; không giữ Dữ liệu đầu vào là mục sidebar cấp một. Đánh giá giữ Finance/Operations/Risk; Bằng chứng giữ run-scoped artifacts; Lịch sử chứa events và links đến run cũ khi run-list API được duyệt.
- Chưa có run: hiện intake/readiness giới hạn theo dữ liệu hỗ trợ, CTA explicit **Bắt đầu đánh giá**. Mở hợp đồng/route không tự gọi POST hoặc sinh case.
- Unknown ID → not found; known contract chưa có run → empty evaluation state; unknown/khác-contract run → không fallback âm thầm sang run khác.
- Deep link từ approval queue luôn mang exact run/request. Đọc lại APIs hiện hữu trước khi mở action review; không gắn pending request vào current run khác.
- Back/forward/refresh giữ context; mobile sidebar thu gọn, contract tabs cuộn trong container. Không thêm login/profile/notifications/settings.

### Compatibility `/dashboard`

Hiện FastAPI `/dashboard` phục vụ **Contract Workspace**. Target dùng cùng path cho Executive Home nhưng chỉ đổi ý nghĩa sau khi phase tích hợp được duyệt. Không đổi base asset `/dashboard-assets/` tùy tiện. Cần server fallback cho routes mới trên cả Vite và FastAPI; route deployment là công việc presentation/interface riêng, không sửa workflow.

## Drill-down và giới hạn triển khai

Executive actions → exact contract/run/view/panel. KPI/chart → Company section với cùng snapshot/filter/source population. Company contract/order/invoice row → selected contract khi có **explicit relation hợp lệ**, nếu không giữ company detail và ghi giới hạn linkage. Không tạo route cho unlinked record bằng suy đoán tên/customer.

Workflow Viewer lấy [Dify Workflow Studio](https://dify.ai/workflows) làm reference cho connected canvas và node inspection. Đây là **read-only viewer**: pan/zoom/fit/select; không thêm/xóa/nối node, publish workflow hay chạy node riêng. Dify định hướng interaction; Mercury tiếp tục quyết định visual theme.

## Quyết định đã chốt và còn cần duyệt

Đã chốt: Executive Home mặc định, Company snapshot analysis, Contract drill-down, read-only actual topology, giữ governance và Mercury tokens. Cần duyệt: API read expansion, schema/query policies, default run selection, financial period rules và phạm vi release đầu. Danh sách quyết định cụ thể ở [roadmap](12_revised_implementation_roadmap.md).
