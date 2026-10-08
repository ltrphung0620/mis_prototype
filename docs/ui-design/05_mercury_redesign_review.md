# Founder Contract Decision Workspace — Implementation review

Ngày: 08/10/2026. Phạm vi: frontend presentation React/TypeScript/Vite và bundle frontend do FastAPI phục vụ. User cho phép redesign và triển khai trực tiếp; không còn yêu cầu giữ `opc-approved-layout.png`, layout ba cột, forest/emerald hoặc chờ duyệt ảnh AI.

## Design direction và lý do chọn layout

Workspace xoay quanh **một hợp đồng đang chọn**. Founder đi từ trạng thái/yêu cầu đang chờ tới đề xuất, rồi đối chiếu các kết quả và bằng chứng. Sidebar có Quyết định, Đánh giá, Bằng chứng, Quy trình và Dữ liệu đầu vào. Chúng là local views, không tạo portal nhiều hợp đồng hoặc năm API routes mới.

Quyết định là nội dung chính rộng toàn workspace. Các chỉ số là dải `dl` nhẹ; assessment là dòng thay vì card lồng nhau. Bằng chứng và quy trình có phần riêng, detail/approval mở panel trên overlay. Cách này ưu tiên đọc kết luận và bước cần làm, đồng thời giữ dữ liệu sâu trong tầm truy cập.

Mercury là visual reference chính qua ba ảnh user cung cấp (Home, Capital, detail panel). Màu gần trắng, khoảng trống, line icons, sidebar nhỏ, controls periwinkle và table borders nhẹ được áp dụng. Linear định hướng object workspace/progressive disclosure; tham khảo tài liệu chính thức [Custom views](https://linear.app/docs/custom-views) và [Display options](https://linear.app/docs/display-options). Không sao chép chức năng chuyển tiền, profile, thông báo hoặc banking portal của Mercury.

## Đã thay đổi

- Shell, sidebar, breadcrumb/header, responsive navigation và contract context.
- Toàn bộ CSS tokens, base styles, typography và hierarchy.
- Decision Dashboard, recommendation/properties và giới hạn bằng chứng.
- Decision Card review, approval styling, exact identity/version, summary và limitations trước quyết định.
- Dải metrics, AssessmentIndex, EvidenceIndex và workflow event log từ endpoint hiện hữu.
- Presentation cho input, timeline, artifact detail và các interaction forms.
- Focus trap/restore, Escape, body scroll lock, skip link, reduced motion và favicon.
- Sửa vòng lặp effect trong playback khi chưa có workflow; có regression test. Không thay đổi trạng thái workflow backend.

Các file chính: `frontend/src/app/App.tsx`, `frontend/src/features/workspace/`, `frontend/src/shared/useDialogFocus.ts`, `frontend/src/styles/`. Design tokens đầy đủ trong [03_design_system.md](03_design_system.md).

## Ranh giới nghiệp vụ được giữ

Dashboard projection vẫn là nguồn trạng thái; artifact hiện hành cung cấp chi tiết. Không tính lại margin/risk trong browser. Formatting số dùng unit đã có. Recommendation không thành approved outcome.

Giữ exact artifact/version/action matching, NOT_EVALUABLE và stale guards, chống submit trùng, automatic pause/review, resume, missing-data và negotiation handlers. Giữ final decision approval riêng external release approval; prototype không gửi hồ sơ. Không sửa Python, public API/schema, dependency declarations hoặc TeamPack.

## Screenshots và dữ liệu

| Artifact | Nội dung |
|---|---|
| [Desktop](../../output/playwright/founder-desktop.png) | 1440px, full page, final approval pending |
| [Mobile](../../output/playwright/founder-mobile.png) | 390px, full page |
| [Evidence](../../output/playwright/founder-evidence.png) | Workspace bằng chứng, 1920px |
| [Decision review](../../output/playwright/founder-decision-review.png) | Panel review, exact approval có sẵn nhưng không submit |
| [Live workspace](../../output/playwright/founder-live-workspace.png) | Production bundle + FastAPI thật, OpenAI tắt, NOT_EVALUABLE |
| [Live assessments](../../output/playwright/founder-live-assessments.png) | Finance/Operations/Risk và artifacts từ TeamPack thật |

Bốn screenshot visual review đầu dùng API fixtures trong `output/playwright/mercury-review.js`, với badge **Dữ liệu minh họa · kiểm thử UI**. Mọi số liệu/kết luận ở đó là synthetic. Fixture analysis source là dữ liệu giả phục vụ kiểm tra màn review, không phải kết quả một lần gọi OpenAI. Không có phê duyệt hoặc external-send thật. Scripts này không được import vào production.

Smoke thật chạy FastAPI bằng memory DB, `OPENAI_ENABLED=false`, đọc workbook gốc. Frontend build load, catalog load, start evaluation, assessments/evidence hiện; NOT_EVALUABLE review không có nút Phê duyệt. DB local hiện hữu và workbook không bị sửa. Screenshot thật không được trình bày như ví dụ ACCEPT.

## Visual comparison và tinh chỉnh

Sau screenshot đầu: bỏ tabs trùng trên desktop, giảm chiều cao banner/panel, căn metric cùng mép nhãn, thay generic assessment captions bằng summary từ artifact, dùng label validation có nghĩa và thêm identity/limitations ở review. Mobile header thu gọn, table scroll giới hạn trong container. Accent CTA được làm đậm hơn Mercury reference để chữ trắng dễ đọc.

Còn khác references: Segoe UI thay vì font Mercury chưa xác minh; CTA vuông mềm thay vì pill; workflow/evidence cần nhiều chữ nghiệp vụ hơn banking Home; trang cuộn theo nội dung thay vì cố ép một ảnh 16:9; không có charts/transfers/profile/notifications. Sidebar object workspace và detail review có chủ đích riêng cho OPC MIS. Không khẳng định pixel-perfect.

## Verification

Frontend: **20 test files, 77 tests passed** (`npm test -- --run`). **TypeScript + Vite production build passed** (`npm run build`). `git diff --check` passed; Git chỉ báo chuẩn hóa LF/CRLF trên Windows. Các kiểm tra browser dùng CLI Playwright/Chrome, không thêm UI library/dependency vào ứng dụng.

- Responsive: 390/768/1440/1920px, không tràn ngang toàn trang; bảng và nav cuộn trong container.
- Keyboard: focus vào review, Tab được giữ trong dialog, Escape đóng và trả focus về opener.
- Fixture workflow log hiển thị; chỉ artifacts hiện hành xuất hiện; approval chỉ có trong review khớp exact version, không submit.
- Frontend regression suite bao gồm identity/version/stale/NOT_EVALUABLE, chống submit trùng, missing input, pause/resume, negotiation và external-release boundaries; bổ sung test workspace/event/focus/playback.
- Kiểm tra màu CTA strong/white khoảng 6,09:1. Chưa audit screen-reader đầy đủ hoặc tất cả cặp màu bằng automated accessibility scanner.
- Pytest: **481 passed, 4 failed**, 1 deprecation warning; 485 tests. Các Python files/tests/pyproject không có diff so với HEAD.
- Ruff 0.16.10: **2 I001** trong `domain/case_workflow_models.py` và `governance/evidence_validator.py`, đều là source Python không thay đổi. Không auto-fix backend ngoài phạm vi.

Các test backend fail:

1. `test_exact_decision_card_requires_founder_then_routes_to_negotiation` — kỳ vọng COMPLETED, nhận WAITING_FOR_INPUT.
2. `test_con004_card_carries_one_precomputed_margin_negotiation_strategy` — kỳ vọng NEGOTIATION_IN_PROGRESS, nhận NEGOTIATION_TERMS_SENT.
3. `test_openai_adapter_retries_ungrounded_numeric_free_prose` — assertion chữ số trong executive summary.
4. `test_external_proposal_rejects_non_accept_route` — regex lỗi kỳ vọng khác message backend hiện hành.

Không sửa backend để làm các kiểm tra này xanh trong task presentation. Đây là hạn chế của kết quả kiểm tra toàn repo, cần review riêng.

## Reproduce

Frontend: `cd frontend`, `npm ci`, `npm test -- --run`, `npm run build`, `npm run dev -- --host 127.0.0.1`.

Visual fixture: mở `http://127.0.0.1:5173/dashboard-assets/` bằng Playwright CLI session `opc-redesign`, chạy `run-code --filename output/playwright/mercury-review.js` rồi `run-code --filename output/playwright/workspace-validation.js`. Reload do HMR sẽ reset state/fixture badge; chạy lại fixture trước validation.

Live smoke: FastAPI memory DB/OpenAI off ở port 8000, mở `/dashboard` bằng session `opc-live`, chạy `run-code --filename output/playwright/live-smoke.js`. Script chạy đánh giá thường và xem dữ liệu, không phê duyệt.

User đã yêu cầu commit/push bản hiện tại và bàn giao công việc tiếp tục. Backlog, cách chạy và phân biệt API thật/demo nằm trong [06_frontend_handoff.md](06_frontend_handoff.md); quy tắc cho agents nằm trong [style.md](../../style.md). Các thay đổi lớn tiếp theo vẫn cần owner review.
