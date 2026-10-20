# Rà soát wording và UI — 20/10/2026

Đã triển khai theo hướng và các điều chỉnh được duyệt trong chat. Giữ thiết kế Mercury, API/database và logic nghiệp vụ/phê duyệt. Không sửa workbook, Python implementation, dependency hoặc lockfile. Chưa commit/push.

## Thay đổi đã hoàn thành

| Nhóm | Kết quả |
|---|---|
| Ngôn ngữ | Tài chính, Vận hành, Rủi ro, Ngân hàng, Hồ sơ, Quy trình; Phiếu đề xuất quyết định. Việt hóa nhãn, bộ lọc, biểu đồ, bảng, trạng thái, thông báo và hộp thoại, kể cả tên truy cập cho bàn phím/trình đọc màn hình. |
| Nhãn đã chốt | Giá trị ghi nhận; Tổng quan công ty; Lần xử lý; Nguồn gốc dữ liệu; Trạng thái xử lý. Kỳ snapshot hiển thị Kỳ dữ liệu. |
| Hóa đơn / đơn hàng | Dùng nhãn chung cho bảng, bộ lọc và biểu đồ. Paid → Đã thanh toán; Open → Đang mở; Not issued → Chưa phát hành. Giá trị lọc/URL vẫn là giá trị gốc. Không suy diễn đã thu tiền, quá hạn hoặc doanh thu. |
| Thông báo mô phỏng | Gỡ phần giới thiệu bản xem trước và giải thích mock/fixtures/backend trên UI chính. Giữ Dữ liệu mô phỏng ở đầu trang và thông báo Kết quả mô phỏng trong hộp thoại. Thao tác mô phỏng không báo đã lưu, đã phê duyệt hoặc đã gửi thực tế. |
| Công cụ kiểm thử | Ẩn bộ chọn trạng thái, tình huống xem xét và kịch bản quy trình trong chế độ xem thông thường. Thêm `&ui_test=1` trước `#` để kiểm thử lại các tình huống; cờ này không phải phân quyền và không thay đổi quyền thực hiện hành động. |
| Tương tác | Đổi bộ lọc/kỳ/vùng sơ đồ không tự đưa cả trang về đầu; chuyển trang/tab/hợp đồng mới cuộn về đầu. Giữ kỳ dữ liệu giữa các tab công ty và liên kết phân tích dòng tiền. Tab đang chọn tự vào vùng nhìn khi chuyển tab hoặc đổi kích thước màn hình. |
| Số đếm và tìm kiếm | Số việc và số hợp đồng lấy từ danh sách tương ứng; tìm bằng chứng bằng tên tiếng Việt hoặc mã. Giữ native links và hành vi mở tab mới. |
| Kiểm soát | Giữ exact artifact/version/request/action/source, stale/resolved, NOT_EVALUABLE và chống gửi lặp. Phê duyệt quyết định và cho phép gửi hồ sơ vẫn là hai bước riêng. |

Các nhãn cũ từ API cũng được đổi ở lớp trình bày. Không đổi enum/status/action/ID/endpoint/payload gốc. Các mã tra cứu và trạng thái chưa biết được giữ nguyên, không đoán nghĩa. Kiểm tra riêng xác nhận các khóa tra bản dịch và trạng thái gốc trong fixtures không đổi.

## Kết quả kiểm thử

| Kiểm tra | Kết quả hiện tại |
|---|---|
| `npm.cmd test` trong frontend | **170 passed / 28 files**; trước thay đổi: 155 passed / 25 files. Bổ sung 15 kiểm thử về nhãn, trạng thái gốc, bộ lọc, cuộn, kỳ dữ liệu, thông báo mô phỏng, tìm kiếm và identity phê duyệt. |
| `npm.cmd run build` | **Đạt** TypeScript và Vite. Bundle sinh tự động trong `src/opc_mis/api/static/react/`; không sửa bundle bằng tay. |
| `node --test tools/ui-demo-preview.test.mjs` | **2 passed**; API fixture cô lập và thao tác bảo vệ vẫn bị chặn. |
| Toàn bộ `pytest -q` | **481 passed, 4 failed, 1 warning**. Bốn failures giống baseline trước thay đổi. |
| `ruff check . --output-format concise` | **2 I001 có sẵn** về import ordering, giữ nguyên. |
| `git diff --check` | **Đạt**. |
| Browser — trang và responsive | **54 kiểm tra đạt**: 13 trang × 390/768/1440/1920 px, cộng kiểm tra dialog mobile và đóng inspector bằng Escape. Không tràn ngang toàn trang, lỗi JavaScript hoặc business API request từ preview. |
| Browser — tương tác và quy trình | **23 kiểm tra đạt**: vị trí cuộn, giá trị lọc gốc, giữ kỳ dữ liệu, tab mobile, 9 tình huống × mobile/desktop, zoom/fit và reduced motion với dialog màn hẹp. |

Lần chạy pytest đầu tiên gặp lỗi quyền thư mục tạm mặc định trên máy; đã chạy lại bằng thư mục tạm riêng trong output. Lệnh tái hiện (đường dẫn thư mục tạm cần riêng cho mỗi lần chạy):

```powershell
.\.venv\Scripts\python.exe -m pytest -q -o cache_dir=output/wording-pytest-cache --basetemp=output/wording-pytest-verified
```

Hai assertions trong `tests/integration/test_dashboard_api.py` được cập nhật từ chuỗi tiếng Anh cũ sang nhãn tiếng Việt đã duyệt. Giữ toàn bộ assertions về endpoints, không giả trạng thái sẵn sàng và không đưa OpenAI secret/call vào browser. Không thay assertion của bốn failures baseline.

## Các vấn đề còn tồn tại

Bốn kiểm thử backend đã fail ở baseline và tiếp tục fail sau thay đổi:

- `tests/integration/test_decision_final_workflow.py::test_exact_decision_card_requires_founder_then_routes_to_negotiation`
- `tests/integration/test_decision_final_workflow.py::test_con004_card_carries_one_precomputed_margin_negotiation_strategy`
- `tests/unit/test_decision_openai_composer.py::test_openai_adapter_retries_ungrounded_numeric_free_prose`
- `tests/unit/test_post_decision_release.py::test_external_proposal_rejects_non_accept_route`

Hai lỗi Ruff I001:

- `src/opc_mis/domain/case_workflow_models.py:3`
- `src/opc_mis/governance/evidence_validator.py:3`

Còn cảnh báo Starlette về việc dùng httpx với TestClient. Không đổi backend/dependency để xử lý các vấn đề ngoài phạm vi UI.

Browser review dùng dữ liệu mô phỏng, không xác minh kết quả tài chính thực tế, toàn bộ live workflow hoặc kết nối ngân hàng. Không công bố kiểm định accessibility đầy đủ bằng screen reader/zoom trình duyệt thực tế. Nội dung tự do và mã nguồn lạ chưa có bản dịch vẫn được giữ để tránh diễn giải sai.

## Ảnh và bằng chứng

- [Bảng điều hành desktop](../../output/playwright/wording-dashboard-1440.png)
- [Hóa đơn mobile](../../output/playwright/wording-invoices-390.png)
- [Quy trình desktop](../../output/playwright/wording-workflow-1440.png)
- [Hộp thoại xem xét mobile](../../output/playwright/wording-review-390.png)
- [Chi tiết bước xử lý mobile](../../output/playwright/wording-inspector-390.png)
- [54 kiểm tra browser](../../output/playwright/wording-browser-results.json) — [script tái hiện](../../output/playwright/wording-review.js)
- [23 kiểm tra tương tác](../../output/playwright/wording-interactions-results.json) — [script tái hiện](../../output/playwright/wording-interactions.js)
- [Frontend tests](../../output/ui-wording-tests.log), [build](../../output/ui-wording-build.log), [tooling tests](../../output/ui-wording-tool-tests.log), [pytest](../../output/ui-wording-pytest.log), [Ruff](../../output/ui-wording-ruff.log)
- [Baseline pytest trước thay đổi bundle](../../output/wording-pytest-baseline.log)

Các script browser dùng địa chỉ local port 5183 của phiên kiểm tra. Khi tái hiện, đổi base URL nếu chạy Vite ở cổng khác. Toàn bộ ảnh là UI có dữ liệu mô phỏng.

## Danh sách file thay đổi

### Frontend — 63 file nguồn và kiểm thử

- [frontend/src/api/normalize.interactions.test.ts](../../frontend/src/api/normalize.interactions.test.ts)
- [frontend/src/api/normalize.ts](../../frontend/src/api/normalize.ts)
- [frontend/src/app/App.interactions.test.tsx](../../frontend/src/app/App.interactions.test.tsx)
- [frontend/src/app/App.tsx](../../frontend/src/app/App.tsx)
- [frontend/src/app/dashboardIntegration.test.ts](../../frontend/src/app/dashboardIntegration.test.ts)
- [frontend/src/app/dashboardIntegration.ts](../../frontend/src/app/dashboardIntegration.ts)
- [frontend/src/app/dashboardState.test.ts](../../frontend/src/app/dashboardState.test.ts)
- [frontend/src/features/artifacts/ArtifactCompatibility.test.tsx](../../frontend/src/features/artifacts/ArtifactCompatibility.test.tsx)
- [frontend/src/features/artifacts/ArtifactDetailDialog.tsx](../../frontend/src/features/artifacts/ArtifactDetailDialog.tsx)
- [frontend/src/features/artifacts/AssessmentViews.test.tsx](../../frontend/src/features/artifacts/AssessmentViews.test.tsx)
- [frontend/src/features/artifacts/AssessmentViews.tsx](../../frontend/src/features/artifacts/AssessmentViews.tsx)
- [frontend/src/features/artifacts/DecisionTraceViews.test.tsx](../../frontend/src/features/artifacts/DecisionTraceViews.test.tsx)
- [frontend/src/features/artifacts/DecisionTraceViews.tsx](../../frontend/src/features/artifacts/DecisionTraceViews.tsx)
- [frontend/src/features/artifacts/PostDecisionViews.test.tsx](../../frontend/src/features/artifacts/PostDecisionViews.test.tsx)
- [frontend/src/features/artifacts/PostDecisionViews.tsx](../../frontend/src/features/artifacts/PostDecisionViews.tsx)
- [frontend/src/features/artifacts/SupplementViews.tsx](../../frontend/src/features/artifacts/SupplementViews.tsx)
- [frontend/src/features/artifacts/WorkflowArtifactViews.tsx](../../frontend/src/features/artifacts/WorkflowArtifactViews.tsx)
- [frontend/src/features/decision/DecisionCardModal.test.tsx](../../frontend/src/features/decision/DecisionCardModal.test.tsx)
- [frontend/src/features/decision/DecisionCardModal.tsx](../../frontend/src/features/decision/DecisionCardModal.tsx)
- [frontend/src/features/decision/DecisionDashboard.test.tsx](../../frontend/src/features/decision/DecisionDashboard.test.tsx)
- [frontend/src/features/decision/DecisionDashboard.tsx](../../frontend/src/features/decision/DecisionDashboard.tsx)
- [frontend/src/features/governance/ApprovalDialog.test.tsx](../../frontend/src/features/governance/ApprovalDialog.test.tsx)
- [frontend/src/features/governance/ApprovalDialog.tsx](../../frontend/src/features/governance/ApprovalDialog.tsx)
- [frontend/src/features/input/InputPanel.test.tsx](../../frontend/src/features/input/InputPanel.test.tsx)
- [frontend/src/features/input/InputPanel.tsx](../../frontend/src/features/input/InputPanel.tsx)
- [frontend/src/features/missing-data/MissingDataForms.test.tsx](../../frontend/src/features/missing-data/MissingDataForms.test.tsx)
- [frontend/src/features/negotiation/NegotiationConfirmDialog.tsx](../../frontend/src/features/negotiation/NegotiationConfirmDialog.tsx)
- [frontend/src/features/negotiation/NegotiationOutcomeForm.tsx](../../frontend/src/features/negotiation/NegotiationOutcomeForm.tsx)
- [frontend/src/features/workflow/StageAccordion.test.tsx](../../frontend/src/features/workflow/StageAccordion.test.tsx)
- [frontend/src/features/workflow/StageAccordion.tsx](../../frontend/src/features/workflow/StageAccordion.tsx)
- [frontend/src/features/workflow/WorkflowTimeline.tsx](../../frontend/src/features/workflow/WorkflowTimeline.tsx)
- [frontend/src/features/workflow/useWorkflowPlayback.test.ts](../../frontend/src/features/workflow/useWorkflowPlayback.test.ts)
- [frontend/src/features/workflow/workflowModel.test.ts](../../frontend/src/features/workflow/workflowModel.test.ts)
- [frontend/src/features/workspace/ContractWorkspace.test.tsx](../../frontend/src/features/workspace/ContractWorkspace.test.tsx)
- [frontend/src/features/workspace/ContractWorkspace.tsx](../../frontend/src/features/workspace/ContractWorkspace.tsx)
- [frontend/src/features/workspace/WorkflowEvents.test.tsx](../../frontend/src/features/workspace/WorkflowEvents.test.tsx)
- [frontend/src/features/workspace/WorkflowEvents.tsx](../../frontend/src/features/workspace/WorkflowEvents.tsx)
- [frontend/src/preview/Charts.tsx](../../frontend/src/preview/Charts.tsx)
- [frontend/src/preview/Company.tsx](../../frontend/src/preview/Company.tsx)
- [frontend/src/preview/Contracts.tsx](../../frontend/src/preview/Contracts.tsx)
- [frontend/src/preview/Dashboard.tsx](../../frontend/src/preview/Dashboard.tsx)
- [frontend/src/preview/PreviewApp.test.tsx](../../frontend/src/preview/PreviewApp.test.tsx)
- [frontend/src/preview/PreviewApp.tsx](../../frontend/src/preview/PreviewApp.tsx)
- [frontend/src/preview/PreviewEntry.tsx](../../frontend/src/preview/PreviewEntry.tsx)
- [frontend/src/preview/components.tsx](../../frontend/src/preview/components.tsx)
- [frontend/src/preview/fixtures.ts](../../frontend/src/preview/fixtures.ts)
- [frontend/src/preview/navigation.ts](../../frontend/src/preview/navigation.ts)
- [frontend/src/preview/testing.ts](../../frontend/src/preview/testing.ts)
- [frontend/src/preview/workflow/WorkflowViewer.test.tsx](../../frontend/src/preview/workflow/WorkflowViewer.test.tsx)
- [frontend/src/preview/workflow/WorkflowViewer.tsx](../../frontend/src/preview/workflow/WorkflowViewer.tsx)
- [frontend/src/preview/workflow/fixtures.ts](../../frontend/src/preview/workflow/fixtures.ts)
- [frontend/src/preview/workflow/labels.ts](../../frontend/src/preview/workflow/labels.ts)
- [frontend/src/preview/workflow/topology.ts](../../frontend/src/preview/workflow/topology.ts)
- [frontend/src/shared/artifactLabels.ts](../../frontend/src/shared/artifactLabels.ts)
- [frontend/src/shared/businessLabels.ts](../../frontend/src/shared/businessLabels.ts)
- [frontend/src/shared/displayText.test.ts](../../frontend/src/shared/displayText.test.ts)
- [frontend/src/shared/displayText.ts](../../frontend/src/shared/displayText.ts)
- [frontend/src/shared/eventLabels.ts](../../frontend/src/shared/eventLabels.ts)
- [frontend/src/shared/sourceLabels.test.ts](../../frontend/src/shared/sourceLabels.test.ts)
- [frontend/src/shared/sourceLabels.ts](../../frontend/src/shared/sourceLabels.ts)
- [frontend/src/shared/translate.test.ts](../../frontend/src/shared/translate.test.ts)
- [frontend/src/shared/translate.ts](../../frontend/src/shared/translate.ts)
- [frontend/src/shared/workflowLabels.ts](../../frontend/src/shared/workflowLabels.ts)

### Tài liệu và kiểm thử bundle

- [style.md](../../style.md): quy ước wording và thông báo mô phỏng hiện hành.
- [docs/ui-design/06_frontend_handoff.md](06_frontend_handoff.md): liên kết sang review này.
- `docs/ui-design/18_wording_localization_review.md`: báo cáo và inventory.
- [tests/integration/test_dashboard_api.py](../../tests/integration/test_dashboard_api.py): chỉ cập nhật hai chuỗi hiển thị kỳ vọng.

### Bundle tự sinh

- `src/opc_mis/api/static/react/assets/PreviewApp-CAM7oVTL.js` — bundle cũ được thay thế khi build
- [src/opc_mis/api/static/react/assets/PreviewApp-DM8xoSHY.js](../../src/opc_mis/api/static/react/assets/PreviewApp-DM8xoSHY.js)
- [src/opc_mis/api/static/react/assets/WorkflowViewer-BVXKlQ25.js](../../src/opc_mis/api/static/react/assets/WorkflowViewer-BVXKlQ25.js)
- `src/opc_mis/api/static/react/assets/WorkflowViewer-C0ys1lzU.js` — bundle cũ được thay thế khi build
- [src/opc_mis/api/static/react/assets/index-CSaIlftZ.js](../../src/opc_mis/api/static/react/assets/index-CSaIlftZ.js)
- `src/opc_mis/api/static/react/assets/index-DompW74u.js` — bundle cũ được thay thế khi build
- [src/opc_mis/api/static/react/assets/jsx-runtime-D_io6lAH.js](../../src/opc_mis/api/static/react/assets/jsx-runtime-D_io6lAH.js)
- `src/opc_mis/api/static/react/assets/navigation-BPoIaTCC.js` — bundle cũ được thay thế khi build
- [src/opc_mis/api/static/react/assets/testing-BWwAMkJF.js](../../src/opc_mis/api/static/react/assets/testing-BWwAMkJF.js)
- [src/opc_mis/api/static/react/index.html](../../src/opc_mis/api/static/react/index.html)

### Giới hạn Git

Không stage, commit, push hoặc tạo PR. Giữ nguyên hai script local có trước: `output/playwright/workflow-interactions.js` và `output/playwright/workflow-review.js`. Không cleanup dữ liệu hoặc các artifact cũ của repository.
