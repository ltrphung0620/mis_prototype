# Checkpoint 2 — Interactive Workflow Viewer

> Cập nhật bàn giao Git: source/evidence CP2 đã commit local trên `codex/frontend-checkpoint2-handoff` (`5d96f21`, `7f97f56`), chưa push hoặc tạo PR. Hai screenshot scripts absolute paths cố ý giữ local; reports/ảnh dưới đây là evidence lịch sử. Phần mô tả lần triển khai bên dưới giữ snapshot trước commit. Handoff hiện hành: [16](16_frontend_handoff_checkpoint2.md).

> Tài liệu này ghi nhận lần triển khai/review CP2. Cách tiếp quản, trạng thái Git và kiểm tra chạy lại: [handoff 16](16_frontend_handoff_checkpoint2.md). Các kết quả build/browser/screenshots dưới đây giữ thời điểm CP2, không phải một lần kiểm thử mới khi đọc tài liệu.

Ngày: 11/10/2026. Source audit: HEAD `0329574`, sau PR #3 và commit Checkpoint 1. Founder đã duyệt Checkpoint 1/polish, cho phép triển khai viewer. **Checkpoint 2 đã triển khai preview, chờ review; chưa nối backend. Không commit/push.**

## Trải nghiệm trực tiếp

- [Viewer local](http://127.0.0.1:5173/dashboard-assets/?preview=1#/contracts/CON-004?view=workflow).
- Vào Hợp đồng → chọn contract → Workflow. Mặc định CON-004 mở vùng Quyết định, chờ gate cuối.
- Chọn kịch bản; chọn vùng Đánh giá / Banking & hồ sơ / Quyết định / Sau quyết định hoặc Toàn quy trình. Scenario và phase nằm trong hash URL, hỗ trợ reload/back/forward.
- Click node mở inspector. Connections trong inspector mở thông tin node liên quan, kể cả ngoài vùng xem. Inspector là panel không modal; không khóa navigation.
- Kéo canvas để pan; nút +/−, pinch để zoom; Fit view để đưa các nodes về khung. Focus canvas rồi dùng phím mũi tên để pan, F để fit. Tab tới nút node, Enter/Space mở; Escape hoặc nút đóng trả focus về control hiện hành.
- Mobile ≤760px tự chuyển danh sách. Desktop cũng có chế độ Danh sách. Chưa có workflow thì empty state, không mượn run/artifacts của contract khác.
- Chọn trạng thái preview trên topbar để xem loading/empty/error của shell; không gọi API.

Vite được giữ chạy local. Logs/PID ở `C:/Users/Paul/.codex/visualizations/2026/10/08/01a11a07-e0d5-7402-9591-082b8890b399/ui-first-preview/`. Xem `vite.stdout.log`, `vite.stderr.log`. Nếu khởi chạy trong terminal riêng: `cd frontend`, `npm ci`, `npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`; dừng bằng Ctrl+C. Không cần FastAPI cho preview.

## Thiết kế và source of truth

Giữ shell, typography, periwinkle accents và Mercury tokens hiện hành. [Dify Workflow Studio](https://dify.ai/workflows) định hướng connected canvas/inspection; [React Flow](https://reactflow.dev/api-reference/react-flow) cung cấp viewport và directed edges. Không sao chép editor, run-node hoặc publish controls.

Graph có **27 nodes/checkpoints và 32 control-flow connections**. Chia vùng xem để đọc rõ labels; toàn quy trình là bản đồ định vị cần zoom, không giả vờ mọi nhánh đang thực thi. Hai instance `PRECHECK_GATE` và `EXTERNAL_GATE` chỉ là presentation của Governance `APPROVAL_GATE`, không phải persisted node IDs mới. Không dựng edges từ sequence của events hoặc thứ tự enum.

| Phần | Nguồn đã đọc | Quan hệ được xác minh |
|---|---|---|
| Intake, pre-scan | `case_workflow_orchestrator.py`: `_planner`, `_risk_pre_scan`, `execute` | Planner → Risk pre-scan trước initial assessment |
| Initial assessment | `execute`: `asyncio.gather(_finance, _operations)`; `_upstream_completed`; `_ensure_risk_finalization_wait`; `_finalize_risk` | Finance và Operations song song; Risk chờ cả hai facts; không có Finance → Operations |
| Routing | `execute`: `_decision_initial_route`, `DecisionRouteOutcome.BANKING_DISCOVERY_REQUIRED` | Direct route → package, hoặc conditional Banking discovery |
| Banking | `execute`: handoff → discovery → readiness → post-banking review | Proposal chỉ khi BANKING_PRECHECK_READY; NO_VIABLE_OPTION/NO_PRECHECK_PATH về package |
| Precheck gate | `execute`: `request_workflow_protected_action(SUBMIT_BANKING_PRECHECK)` | Exact authorization trước execution; decline về package; pending dừng workflow |
| Post-precheck | `execute`: `_decision_post_precheck_review` | Conditional options → Document; non-actionable outcomes → package |
| Document | `_document_flow` | Handoff trên exact review + result set → preparation → package; chờ input nếu thiếu |
| Internal package | `_assemble_internal_decision_package`, `_internal_decision_source_artifacts` | Converge branch với allowlist upstream artifact types; không có release authorization |
| Final decision | `_run_final_risk_check`, `_run_decision_card_flow`, `_request_final_decision_approval` | Package → Final Risk → Card → exact gate; NOT_EVALUABLE hoàn tất mà không mở approval |
| Post decision | `_route_post_decision_update`, `_run_negotiation_flow` | Sau exact Card approval: đóng case, đàm phán, hoặc release proposal tùy outcome |
| External boundary | `_run_external_submission_proposal`, `_continue_external_submission_proposal`, `_complete_external_submission_readiness` | Proposal → gate riêng → connector-safe readiness; không gọi adapter, không receipt, không gửi |

Định nghĩa node/edge/condition cụ thể ở `frontend/src/preview/workflow/topology.ts`. Node inspector có mục đối chiếu method và enum ID. Định nghĩa trạng thái đọc từ `domain/enums.py`; `WorkflowNodeState`, summary, events và artifact refs đọc từ `domain/case_workflow_models.py`. Unit test kiểm tra node/status/artifact identifiers có trong source hiện hành bằng cách đọc text, không import Python runtime.

### Phạm vi chưa biểu diễn đầy đủ

Không thể hiện mọi enum milestone như executable node: DATASET_INGESTION validation boundary, READY milestones, legacy release nodes, retry/evidence-intake/supplement helpers hoặc từng terminal reject event. Nhánh không actionable/declined được thể hiện bằng conditional edge về package. Terminal đóng case/accepted-without-release được mô tả trong Post Decision; không tạo execution node giả.

Viewer này không phải canonical graph API hoặc bằng chứng mọi route đã chạy. Graph live sau này phải phân biệt control-flow, artifact dependencies, gate instances, milestones, applicability và branch outcome. Không coi absence trong node summary là NOT_APPLICABLE.

## Các kịch bản có thể preview

| ID | Snapshot minh họa | Điểm hiện tại |
|---|---|---|
| `approval` | Direct route, Card sẵn sàng | FINAL_DECISION_APPROVAL chờ exact Card v1 |
| `assessment` | Initial assessment song song | Finance RUNNING; Operations COMPLETED; Risk WAITING_FOR_DEPENDENCIES |
| `banking` | Banking discovery/readiness/review/proposal hoàn tất | Gate SUBMIT_BANKING_PRECHECK pending; execution chưa chạy |
| `document` | Precheck đã authorization minh họa, có conditional options | DOCUMENT_PREPARATION chờ input; chưa assembly/Card |
| `input` | Intake chưa đủ dữ liệu | PLANNER_INTAKE WAITING_FOR_INPUT; downstream applicability chưa xác định |
| `failed` | Package đã có; output Final Risk không khớp exact input | FINAL_RISK_CHECK FAILED_SAFE, không có output được chấp nhận |
| `completed` | Card NOT_EVALUABLE | Workflow hoàn tất, chưa có quyết định Founder; approval không áp dụng |
| `negotiation` | Ví dụ riêng: Card có điều kiện đã được xác nhận | NEGOTIATION_OUTCOME_RECEIVED chờ input; chưa confirmation |
| `release` | Ví dụ riêng: conditional document branch, quyết định đã xác nhận | Gate SEND_DOCUMENT_TO_EXTERNAL_PARTNER pending; chưa external release |

Tất cả kịch bản là fixture của lượt minh họa **riêng** `UI-WF-{contract}-{scenario}`. Không ghi đè source status/workflow status của header, artifacts hay approval request của Contract Decision Workspace. Default scenario chọn theo preview contract state; contract chưa có run không hiển thị graph snapshot. Không tạo nghiệp vụ hay quan hệ entity mới.

`not-applicable` là **applicability presentation**, execution status null. `undetermined` hiển thị rõ trong inspector. Chưa bắt đầu dùng PENDING minh họa. Completion là execution completion, không phải đánh giá an toàn hoặc phê duyệt.

## Inspector và integration boundary

Inspector có nhiệm vụ, execution/applicability/validation, input/output refs có ID/version, evidence lineage minh họa, sự kiện theo node, blocker/pending request, exact subject/action và connections/conditions. IDs giữ scope contract+scenario. Output chỉ tạo ở nodes completed; failed/running/waiting không có output được chấp nhận. Gates không sinh business artifacts.

**Các phần dùng fixture:** run/current node, execution states, applicability, all artifacts/validation labels, evidence refs, events, blockers và approval subjects. Tham chiếu đầu vào là tập được chọn cho UI, không full artifact payload/schema. Evidence là placeholder lineage cấp artifact, chưa có record-level `EvidenceRef`. Không gọi Evidence Validator hoặc model thật; không timestamp, duration hay risk/confidence score giả.

**Code boundary:** `Contracts.tsx` lazy-load viewer trong `?preview=1`; viewer không import `api/client`, không fetch, không mutation handlers. Connected App, approval guards và business logic không đổi. `nodesDraggable=false`, `nodesConnectable=false`, `edgesReconnectable=false`, `deleteKeyCode=null`; không onConnect/onNodesChange, run/reset/retry/approve/release buttons. React Flow CSS/chunk chỉ tải khi cần viewer. Build assets được sinh bằng Vite, không sửa tay.

### API có thể nối sau review

| Nhu cầu | API hiện có / khoảng trống |
|---|---|
| Run state, nodes, output refs, pending/resume/failure | `GET /api/workflows/{workflow_run_id}` trả summary; giữ server authority |
| Founder status và exact governance binding | `GET /api/workflows/{workflow_run_id}/dashboard`; dùng projection hiện hành, không tính lại browser |
| Ordered events | `GET /api/workflows/{workflow_run_id}/events?after_sequence=…`; reuse incremental loading/dedupe; không suy edges từ events |
| Artifact envelopes/inputs/version/evidence | `GET /api/cases/{evaluation_case_id}/artifacts`; lọc đúng run refs + explicit lineage, không latest-by-type từ run khác |
| Approval requests | `GET /api/cases/{evaluation_case_id}/approval-requests`; subject ID/version/action/status exact; actions vẫn qua existing Governance UI |
| Canonical graph/branch applicability | Chưa có dependency graph/applicability contract trong `WorkflowRunSummary`. Cần duyệt read-only topology projection hoặc versioned audited adapter; không tự thêm endpoint ở checkpoint này |
| Record-level evidence inspection | Dùng validated envelope lineage sau khi có adapter; fixture không được chuyển thành evidence thật bằng cách bỏ badge |

Không resume, POST node/business actions, approval hoặc external release khi chỉ xem workflow. Review APIs/schema/grain riêng trước integration. Chưa xây thêm API hoặc sửa database/TeamPack.

## Validation và visual review

- Frontend tests: **155/155 tests, 25 files đạt**, gồm 19 tests mới cho topology/source identifiers, scenarios, exact subjects, inspector và preview boundaries. **TypeScript + Vite production build đạt.** Node types được reference riêng trong test source-contract, không đổi cấu hình runtime.
- Browser: **46 checks đạt**: 34 checks ở 1440/1920/390px trong `output/playwright/workflow-interaction-results.json`, thêm 12 checks trong `workflow-final-check-results.json`; requests/errors đều rỗng. Cover pointer/keyboard pan, zoom/fit, mouse/Enter/Space inspection, Escape focus restore, immutable nodes, full topology, 9 scenarios, desktop/mobile list, no-run, loading/empty/error, reload/back/forward, narrow viewport, Dashboard navigation, Company chart, contract filter/drill-down và existing Decision Review. Guard request xét endpoint pathname `/api/`, không nhầm các module dev `/dashboard-assets/src/api/` thành API calls.
- Typography: node title 14px, status/kind 12px; inspector body 13px, metadata/code 12px. Thu hẹp fit padding sau browser review: initial assessment fit ở 1440px tăng từ 87% lên 93%, labels vẫn 14px computed. Giữ contrast theo Mercury semantic tokens, status luôn có text/symbol bên cạnh màu. Focus return dùng control hiện hành vì React Flow có thể thay DOM node sau selection. `onNodeClick` bật pointer hit area trong read-only React Flow; child button chặn propagation để không mở hai lần. Không bật dragging/selection editing.
- Desktop theo vùng: nhánh Finance/Operations không chồng, Banking chạy trái → phải rồi trở về hàng dưới, inspector giữ không gian node được chọn. Full graph là bản đồ thu nhỏ; cần zoom hoặc vùng xem để đọc. Không coi full-fit overview là chế độ đọc toàn bộ labels ở 100%.
- Mobile 390px: list và inspector không horizontal overflow; vùng tabs cuộn trong container. Chưa audit screen reader thật hoặc chứng nhận WCAG.
- Ruff: **2 I001** ở `domain/case_workflow_models.py`, `governance/evidence_validator.py`, cùng baseline trước task.
- pytest: **481 passed, 4 failed, 1 warning**, 90.89s. Cùng baseline: hai integration final-decision/negotiation tests, numeric composer assertion và external-release regex. Không sửa backend ngoài scope.
- Production npm audit: **0 vulnerabilities**. npm install báo 6 advisory dev-toolchain đã có; không chạy force audit fix. Dependency mới: `@xyflow/react` 12.12.0 và `@types/node` chỉ cho development source-contract tests.

### Screenshots mới

- [Canvas assessment 1920](../../output/playwright/workflow-canvas-1920.png)
- [Decision canvas 1440](../../output/playwright/workflow-decision-1440.png)
- [Assessment canvas 1440](../../output/playwright/workflow-assessment-1440.png)
- [Node Inspector 1440](../../output/playwright/workflow-inspector-1440.png)
- [Banking 1920](../../output/playwright/workflow-banking-1920.png)
- [Full topology overview 1920](../../output/playwright/workflow-overview-1920.png)
- [Mobile list 390](../../output/playwright/workflow-mobile-390.png)
- [Mobile inspector 390](../../output/playwright/workflow-mobile-inspector-390.png)

Scripts trong `output/playwright/workflow-*.js` dùng Playwright CLI có sẵn ngoài repo; không thêm Playwright framework dependency. Dừng tại review Checkpoint 2. Backend integration, canonical graph, record-level evidence và các mutations cần scope/approval tiếp theo.
