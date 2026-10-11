# Git Handoff Readiness Audit — CP1/CP2

> **Update thực hiện theo owner approval, 11/10/2026:** đã tạo local branch `codex/frontend-checkpoint2-handoff` từ `0329574`, giữ CP1 nguyên vẹn. Commit 1 `5d96f21` (18 paths, Git nhận diện một rename nên 17 file changes); commit 2 `7f97f56` (12 paths); 6 docs được đóng gói trong commit `docs(ui): hand off frontend checkpoints and integration backlog` tiếp theo. Chưa push/merge/tạo PR hoặc set remote upstream. Các phần audit/proposal phía dưới là snapshot trước commit; xem `git log -4 --oneline` cho history cuối.
>
> Hai HOLD scripts **đã được owner chốt giữ local, không commit/xóa**. Cleanup 435 temporary artifacts được tách PR riêng, cần sensitive-data review trước chia sẻ repo. Baseline backend failures/dev advisories và Governance giữ nguyên. Final tests/build chạy sau ba commits, kết quả được báo trong handoff report của lần thực hiện; không biến số lịch sử phía dưới thành số kiểm thử mới.

Ngày kiểm tra: **11/10/2026**. Branch `main`, HEAD `03295747b7dafbe96f8eb9f6675683fe4bdc08c3`. Đã fetch origin và chạy kiểm tra trên working tree CP2. **Chưa tạo branch, stage, commit, push, merge hoặc PR.** Không sửa application/backend/business logic, dependencies, fixtures hoặc scripts; không cleanup file. Chỉ tạo báo cáo này, liên kết từ [handoff 16](16_frontend_handoff_checkpoint2.md) và sửa ba Markdown hard breaks ở 16 thành blockquote paragraphs để không có trailing whitespace.

**Kết luận:** source UI đủ để chuẩn bị bàn giao, tests/build frontend đạt và bundle tái tạo giống bản đang có. Chưa phải toàn repository sạch: có artifacts tạm đã track từ trước, ignore gaps, tool scripts chưa portable và baseline backend failures. Các vấn đề này được tách khỏi phần source CP1/CP2; owner cần chọn cách xử lý trước push, không tự dọn trong audit.

## 1. Git và mức đồng bộ remote sau fetch

| Mục | Quan sát |
|---|---|
| Remote | `origin` → `https://github.com/ltrphung0620/mis_prototype` |
| Current branch / upstream | `main` / `origin/main` |
| HEAD | `03295747b7dafbe96f8eb9f6675683fe4bdc08c3` — `feat(ui): add executive preview and polish checkpoint 1` |
| `origin/main` sau fetch | `707f58a6178a1d2b4179cb1b4b56d68644de4f52` — merge PR #3 |
| Behind / ahead | `git rev-list --left-right --count origin/main...HEAD` = **0 / 1** |
| Local-only commit | Chỉ `0329574`; CP1/polish chưa có trên remote branches đã fetch |
| Remote branch khác | Fetch thêm `origin/feat/ui-polish`, ở `5894881`; không chứa `0329574` |
| Index | Rỗng; không staged files |
| Working tree trước audit | **37 paths: 11 tracked changes + 26 untracked files** |
| Working tree cuối audit | **38 paths: 11 tracked changes + 27 untracked files**; thêm báo cáo 17, cập nhật file 16 vốn untracked |

Fetch chỉ cập nhật remote-tracking refs, không merge hoặc đổi checkout. Build xong vẫn có cùng 37 paths và cùng SHA-256 trước audit. Phần tăng cuối cùng chỉ là tài liệu 17. Trạng thái remote là tại thời điểm fetch; kiểm tra lại trước push thực tế.

### Tránh bỏ sót hoặc commit trùng

`0329574` đã chứa CP1, visual polish, Recharts, shell/hash routes/provider, ba global pages, shared dialog context, docs 07–14, tests/screenshots và bundle CP1: **81 files changed, 6336 insertions, 71 deletions**. Nó là commit local sẵn có, không phải 37 dirty paths cần tạo lại.

CP2 chỉ thêm React Flow/Node types, viewer/topology/scenario fixtures/tests/CSS, lazy loading và route params trong Contracts/models/navigation, docs 15/16 + cập nhật 06/12/style, workflow evidence và regenerated bundle. Không có Python source/tests/workbook diff. Formatter delta ở `models.ts` không phải thay schema backend. 46 browser checks là reports lịch sử CP2, không browser session mới trong Git audit.

**Đề xuất giữ commit CP1 nguyên vẹn**, tạo feature branch từ HEAD đang chứa `0329574`, rồi commit đúng CP2 delta. PR base `main` sẽ mang cả CP1 và CP2. Không cherry-pick lại `0329574`, không reset/rebase/force-push. Không tạo branch từ `origin/main` rồi chỉ mang 37 paths, vì sẽ thiếu source CP1.

## 2. Phân loại đầy đủ 37 paths ban đầu

`YES`: đưa vào handoff commit theo nhóm. `HOLD`: giữ file local, chưa nên commit nguyên trạng; không xóa. `DEL`: ghi nhận deletion có sẵn trong generated bundle replacement, không phải lệnh xóa file mới.

| Nhóm | Số paths | Quyết định |
|---|---:|---|
| Application source + dependency manifests | 8 | YES |
| Frontend tests | 1 | YES |
| Preview fixtures/tooling/evidence reports | 7 | 5 YES, 2 HOLD |
| Documentation | 5 | YES |
| Screenshots cần bàn giao | 8 | YES |
| Generated bundle | 8 | YES, gồm 2 DEL; repo yêu cầu bundle đi cùng UI source |
| **Tổng** | **37** | **35 YES/DEL, 2 HOLD** |

### Application source — 8

| Path | Trạng thái | Quyết định/lý do |
|---|---|---|
| `frontend/package.json` | M | YES — React Flow runtime + Node types dev |
| `frontend/package-lock.json` | M | YES — lockfile của manifests, không commit node_modules |
| `frontend/src/preview/Contracts.tsx` | M | YES — lazy viewer thay placeholder |
| `frontend/src/preview/models.ts` | M | YES — presentation route params |
| `frontend/src/preview/navigation.ts` | M | YES — hash scenario/phase |
| `frontend/src/preview/workflow/WorkflowViewer.tsx` | ?? | YES — read-only viewer/inspector/list |
| `frontend/src/preview/workflow/workflow.css` | ?? | YES — Mercury-scoped presentation |
| `frontend/src/preview/workflow/topology.ts` | ?? | YES — audited typed UI topology, không server API |

### Frontend tests — 1

| Path | Trạng thái | Quyết định |
|---|---|---|
| `frontend/src/preview/workflow/WorkflowViewer.test.tsx` | ?? | YES — 19 topology/scenario/identity/interaction/no-API tests |

### Preview fixtures/tooling/reports — 7

| Path | Trạng thái | Quyết định/lý do |
|---|---|---|
| `frontend/src/preview/workflow/fixtures.ts` | ?? | YES — labelled scenario-specific fixtures cần cho viewer |
| `output/playwright/workflow-final-checks.js` | ?? | YES — CLI callback fragment; không standalone npm E2E runner, không personal output path |
| `output/playwright/workflow-final-check-results.json` | ?? | YES — 12 historical checks, không secret |
| `output/playwright/workflow-interaction-results.json` | ?? | YES — 34 historical checks, requests/errors rỗng |
| `output/playwright/workflow-typography-results.json` | ?? | YES — computed measurements lịch sử |
| `output/playwright/workflow-interactions.js` | ?? | **HOLD** — absolute screenshot output path của máy người bàn giao, dòng 7 |
| `output/playwright/workflow-review.js` | ?? | **HOLD** — absolute output paths, dòng 6/9 |

Hai HOLD scripts không cần để developer chạy app hoặc unit tests; ảnh/JSON vẫn bàn giao được. Chọn một trong hai cách trước push: làm paths/runner portable trong task tooling được duyệt, hoặc bỏ hai scripts khỏi commits CP2 và ghi rõ evidence là historical. Nếu owner muốn commit như archive nguyên trạng, cần ghi rõ giới hạn này, không coi chúng là reproducible E2E harness. Chưa sửa scripts.

CP1 đã có 5 browser scripts chứa personal absolute paths trong commit `0329574`, và docs 13 có log path của máy người bàn giao. Đây là artifact/tooling legacy, không runtime app paths; giữ lịch sử commit CP1, đề xuất follow-up portability riêng. Không âm thầm sửa/squash CP1 trong audit.

### Documentation — 5

| Path | Trạng thái | Quyết định |
|---|---|---|
| `docs/ui-design/06_frontend_handoff.md` | M | YES — connected baseline + CP2/16 links |
| `docs/ui-design/12_revised_implementation_roadmap.md` | M | YES — CP1 approved, CP2 review pending |
| `style.md` | M | YES — viewer/style/governance continuation rules |
| `docs/ui-design/15_workflow_viewer_checkpoint.md` | ?? | YES — topology, scenarios, validation và visual evidence |
| `docs/ui-design/16_frontend_handoff_checkpoint2.md` | ?? | YES — self-contained source map/setup/backlog |

Tài liệu **17 này là path thứ 38**, mới tạo bởi audit; YES, thuộc nhóm docs commit. Inventory 37 paths trong 16 giữ snapshot lịch sử, không tự biến thành 38 path inventory.

### Screenshots — 8

Tất cả ở `output/playwright/`, dữ liệu minh họa; tổng **955.007 bytes**, không cần Git LFS riêng cho bộ ảnh này. Các ảnh CP1/polish đã ở `0329574`, không tạo lại commit ảnh trùng.

| Path | Trạng thái | Quyết định |
|---|---|---|
| `output/playwright/workflow-assessment-1440.png` | ?? | YES |
| `output/playwright/workflow-banking-1920.png` | ?? | YES |
| `output/playwright/workflow-canvas-1920.png` | ?? | YES |
| `output/playwright/workflow-decision-1440.png` | ?? | YES |
| `output/playwright/workflow-inspector-1440.png` | ?? | YES |
| `output/playwright/workflow-mobile-390.png` | ?? | YES |
| `output/playwright/workflow-mobile-inspector-390.png` | ?? | YES |
| `output/playwright/workflow-overview-1920.png` | ?? | YES |

Tên ảnh là viewport review; full-page PNG có thể hẹp hơn 15px do scrollbar, không đổi ảnh để ép đúng tên. Không chụp/regenerate ảnh trong Git audit.

### Generated files — 8, vẫn cần commit

Theo [style.md](../../style.md), Vite build ra `src/opc_mis/api/static/react/`; bundle phải đi cùng source để FastAPI `/dashboard` chạy sau clone. Vì vậy không dùng quy tắc chung “mọi generated file đều bỏ”. Build đã tái tạo giống SHA-256 hiện có.

| Path | Trạng thái | Quyết định |
|---|---|---|
| `src/opc_mis/api/static/react/index.html` | M | YES |
| `src/opc_mis/api/static/react/assets/PreviewApp-VcK1YR3u.js` | D | YES/DEL — bundle CP1 thay bởi bundle CP2 |
| `src/opc_mis/api/static/react/assets/index-BzKmjIYQ.js` | D | YES/DEL — thay entry CP1 |
| `src/opc_mis/api/static/react/assets/PreviewApp-CAM7oVTL.js` | ?? | YES |
| `src/opc_mis/api/static/react/assets/WorkflowViewer-C0ys1lzU.js` | ?? | YES |
| `src/opc_mis/api/static/react/assets/WorkflowViewer-DOzebP57.css` | ?? | YES |
| `src/opc_mis/api/static/react/assets/index-DompW74u.js` | ?? | YES |
| `src/opc_mis/api/static/react/assets/navigation-BPoIaTCC.js` | ?? | YES |

Shared CSS bundles/favicon không đổi so với CP1; không bỏ chúng khỏi checkout. Không edit bundle bằng tay hoặc commit intermediate build output của từng local iteration.

## 3. Ignore, secrets, runtime artifacts và dependencies

### Đã kiểm tra

- `.env`/`.env.local`/`.env.*.local`, `data/runtime/`, `.venv/`, `frontend/node_modules/`, pytest/Ruff/Python caches, frontend coverage và `.playwright-cli/` đã ignore. `.env.example` được track và chỉ có safe defaults/blank credentials; hợp lệ để bàn giao.
- Không có real `.env`/`frontend/.env` hoặc configured runtime `data/runtime/opc_mis.db` trong checkout tại audit. Không có tracked `.log`/`.pem`/`.key`; 37 dirty paths không chứa runtime DB/secret/env/log.
- Scan credential/private-key patterns trên tracked text + dirty text và 263 tracked DB binaries: **không phát hiện credential thật theo các patterns đã dùng**. Matches đã kiểm tra là test rejection string `sk-proj-must-not-be-persisted`, deterministic test HMAC/placeholder docs và CSS variable fragment, không live keys. Không in secrets hoặc đọc personal environment file ngoài repo.
- Đây là heuristic scan working tree/candidates, **không forensic toàn Git history hoặc bảo đảm mọi sensitive business record đã được kiểm duyệt**. Gitleaks không có sẵn; chưa cài tool ngoài scope.
- TeamPack working file khớp Git object tại HEAD; không sửa workbook. Backend Python source/tests không đổi; static UI generated files trong `src/opc_mis/api/` không phải backend logic edits.
- Manifest/lockfile root deps khớp, lockfile v3, `resolved` packages đều npm registry; không file/git/private registry dependency mới. `npm ls --depth=0` không thiếu direct deps, nhưng local node_modules có 2 extraneous packages (`@emnapi/wasi-threads`, `tslib`); không commit node_modules. Fresh receiver phải dùng `npm ci`, không copy môi trường này. Chưa thử clean install ở máy khác trong audit.
- `npm audit --omit=dev --json`: **0 advisories**; full `npm audit --json`: **6 vulnerable packages**, 3 moderate/3 high, nằm trong dev toolchain (`@vitest/mocker`, `vitest`, `nanoid`, `postcss`, `source-map-js`, `undici`). Không gọi chúng là 6 individual CVEs; không chạy audit fix hoặc nâng dependencies.

### Phát hiện ngoài CP1/CP2 delta — chưa xử lý

**435 temporary files đã track ở cả `origin/main` và HEAD, gồm 263 `.db` files**, dưới `.test-temp-*`/`.tmp-*`. CP1 không thêm file nào trong nhóm này; CP2 dirty paths cũng không sửa chúng. Người nhận clone sẽ vẫn nhận các artifacts cũ đó. Không xóa, untrack hoặc chỉnh DB trong audit.

`.gitignore` chưa chặn đầy đủ `.env.production`, `frontend/.env.development`, `frontend/.env.production`, generic `*.log`, test-temp roots và key files. Các path probe này là kiểm tra rules, không có nghĩa những file đó đang tồn tại. Chỉ thêm ignore rules sẽ **không** untrack 435 files đã commit.

Đề xuất maintenance task riêng, sau owner quyết định: audit provenance/sensitive records của temporary artifacts rồi chọn untrack ở commit mới; bổ sung `.env.*` với exception `!.env.example`, `*.log`, `.test-temp*/`, `.tmp-*/` và credential-file rules phù hợp. Không dùng blanket recursive delete, history rewrite/force push hoặc ignore mọi DB nếu repo cần intentional fixtures. Không gộp cleanup vào UI PR mà không review rõ scope.

## 4. Validation chạy lại

| Check | Kết quả |
|---|---|
| `git diff --check` working tree + `git diff --check origin/main..HEAD` | Pass; LF/CRLF normalization warnings không phải whitespace failures |
| Check untracked text bằng `git diff --no-index --check -- NUL <file>` | **19 text files không có whitespace diagnostics** sau đổi ba Markdown hard breaks ở 16 thành paragraphs. No-index trả 1 vì file khác NUL; không coi exit 1 trống diagnostics là lỗi whitespace |
| `npm.cmd test` | **155 passed / 25 files**, 13.45s |
| `npm.cmd run build` | **Pass**, TypeScript + Vite 8.1.5; 774 modules. Generated outputs giống SHA-256 trước/sau audit |
| `ruff check .` | **2 I001**: `domain/case_workflow_models.py`, `governance/evidence_validator.py` |
| `pytest -q` | **481 passed, 4 failed, 1 warning**, 83.45s; cùng failure names baseline |
| Existing browser reports | 46 historical checks ở CP2; không chạy browser/chụp lại trong Git audit |
| Handoff relative links | 16 có **66 links hợp lệ** sau thêm link 17; 17 có 4 relative links hợp lệ; đủ 37 classification rows, không thiếu/trùng path |

Bốn pytest failures giữ nguyên: hai integration final-decision/negotiation tests trong `test_decision_final_workflow.py`; `test_openai_adapter_retries_ungrounded_numeric_free_prose`; `test_external_proposal_rejects_non_accept_route`. Tên đầy đủ và expected/actual ở [16, mục 6](16_frontend_handoff_checkpoint2.md#6-kết-quả-kiểm-tra-và-baseline-failures). Không sửa assertions/source để làm xanh tests. Không trình bày toàn repository checks là pass.

## 5. Branch và nhóm commit đề xuất — chưa thực hiện

Feature branch: **`codex/frontend-checkpoint2-handoff`**, tạo từ HEAD `0329574`, PR base `main`. Tên này chưa tồn tại trong local/fetched remote refs tại audit; kiểm tra lại khi thực hiện. Không đổi current branch trong audit.

| Thứ tự | Commit message | Files |
|---|---|---|
| Giữ nguyên | `0329574 feat(ui): add executive preview and polish checkpoint 1` | CP1 đã commit local; đi cùng feature branch |
| 1 | `feat(ui): add read-only workflow viewer preview` | 8 application paths + 1 frontend test + workflow fixture + 8 bundle paths = **18 paths**, source/test/deps/bundle nhất quán |
| 2 | `test(ui): record checkpoint 2 visual evidence` | 8 screenshots + 3 historical JSON reports + portable `workflow-final-checks.js` = **12 paths** |
| 3 | `docs(ui): hand off frontend checkpoints and integration backlog` | 5 docs ban đầu + báo cáo 17 = **6 paths** |

Theo phương án HOLD, **36 paths được đề xuất commit, 2 scripts giữ local**. Sau khi owner duyệt portability work, có thể bổ sung hai scripts vào commit evidence; cần cập nhật scope/counts. Tránh `git add .` hoặc stage toàn root vì sẽ khó thấy artifacts mới ngoài danh sách. Stage bằng explicit path allowlist và kiểm tra staged diff/deletions trước mỗi commit. Không re-add code/ảnh CP1 đã nằm trong `0329574` để tạo “commit CP1” thứ hai.

## 6. PR title/description dự thảo

**Title:** `feat(ui): add executive preview and read-only workflow viewer`

Nội dung để copy, chỉ dùng sau owner cho phép tạo PR. Adjust validation/scope nếu source hoặc selection thay đổi; không ghi PR như đã tạo.

```markdown
OPC MIS hiện có Contract Decision Workspace connected nhưng chưa có Executive Home hoặc interactive workflow canvas. Thay đổi này thêm preview thống nhất cho Dashboard, Company Overview và Contracts, cùng read-only Workflow Viewer để Founder xem dependencies, parallel assessments và governance gates.

Preview bật bằng `?preview=1`, dùng dữ liệu minh họa và độc lập với business API/mutations. Connected workspace và exact artifact/approval guards được giữ. Viewer có 27 audited nodes/checkpoints, 32 control-flow connections, 9 fixture scenarios, zoom/pan/fit, keyboard inspection và mobile list. Topology dựa trên orchestration hiện hành; đây chưa là canonical graph API hoặc record-level evidence integration.

PR bao gồm commit CP1/polish `0329574` đang chưa có trên main, CP2 source/tests, generated FastAPI UI bundle, screenshots/reports và handoff/style/roadmap. Hai screenshot scripts có personal output paths được giữ ngoài CP2 commits theo readiness audit; legacy CP1 tooling paths và tracked temporary artifacts là follow-up riêng.

Validation Git readiness: 155 frontend tests / 25 files pass; TypeScript/Vite build pass và bundle hashes tái tạo giống bản CP2. Production npm audit 0 advisories; dev toolchain còn 6 vulnerable packages (3 moderate/3 high). Các số này là records audit trước đóng gói; final tests/build được chạy lại sau ba commits. Existing CP2 browser reports có 46 checks pass; không chạy browser lại trong Git handoff preparation.

Known baseline: pytest 481 passed/4 failed/1 warning; Ruff còn 2 I001. Không sửa backend/business logic/API/database/TeamPack. Company/executive aggregates và live workflow graph integration vẫn là backlog cần review riêng. CP2 đang chờ Founder review; không claim production readiness.

Review: chạy `npm ci`, `npm run dev -- --host 127.0.0.1 --port 5173 --strictPort` trong frontend và mở `/dashboard-assets/?preview=1`. Xem docs/ui-design/16_frontend_handoff_checkpoint2.md và 17_git_handoff_readiness_audit.md để nhận source, kiểm thử 9 scenarios và giữ governance boundaries.
```

## 7. Hướng dẫn nhận source và checklist nghiệm thu

[Handoff 16](16_frontend_handoff_checkpoint2.md) đã đủ entry switch, source map, Node/Python requirements, exact launch URLs, safe demo env, screenshots, fixture/live boundaries, APIs/backlog và workflow guard rules. Điểm còn thiếu cho **chuyển giao Git** được bổ sung ở 17: branch chưa được publish, files cần chọn và tooling/repository hygiene caveats. Không cần đọc lịch sử chat để chạy preview.

### Sau khi owner cho phép publish feature branch

Recipe dưới đây dành cho **máy mới**, chưa chạy trong audit. Trước khi publish, clone `main` chỉ có baseline PR #3; không thể tải dirty CP2 từ remote.

```powershell
git clone https://github.com/ltrphung0620/mis_prototype.git
Set-Location mis_prototype
git fetch origin
git switch --track origin/codex/frontend-checkpoint2-handoff
git log --oneline -5
git status --short
Set-Location frontend
npm.cmd ci
npm.cmd test
npm.cmd run build
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Nếu đã có checkout riêng có thay đổi, không paste clone/switch commands để ghi đè; kiểm tra status và dùng checkout sạch. Sau PR merge, người nhận có thể clone main hoặc dùng `git pull --ff-only` trên clean main thay vì feature branch. Trong lúc chưa publish, chỉ chuyển bản working tree qua cách owner chọn; không gửi `.env`, DB runtime, node_modules hoặc browser profiles/cache. Những temporary artifacts đã track từ trước cần quyết định xử lý riêng trước khi gọi whole-repo archive là sạch.

Preview URL: [Executive Home](http://127.0.0.1:5173/dashboard-assets/?preview=1#/dashboard), [Company](http://127.0.0.1:5173/dashboard-assets/?preview=1#/company), [Contracts](http://127.0.0.1:5173/dashboard-assets/?preview=1#/contracts), [Workflow pending Card](http://127.0.0.1:5173/dashboard-assets/?preview=1#/contracts/CON-004?view=workflow&scenario=approval&phase=decision). Không cần backend/keys/DB cho preview. Logs ở terminal, Ctrl+C dừng. Setup backend riêng ở 16; không bỏ `preview=1` khi chỉ cần fixture review.

- [ ] Có branch/SHA published mà owner xác nhận; CP1 `0329574` nằm trong history và CP2 viewer files/lockfile/bundle/docs có đủ.
- [ ] Đọc AGENTS.md, style.md và handoff 16; hiểu global pages/viewer là fixtures, connected App là chế độ khác.
- [ ] Fresh `npm ci`, frontend tests/build đạt; build không thiếu asset/chunk. Node version phù hợp `^20.19.0 || >=22.12.0`.
- [ ] Ba global pages/navigation/back/forward/reload, Company charts/filters/table alternative, Contracts selector/search/workflow status/drill-down hoạt động.
- [ ] 9 scenarios: approval, assessment, banking, document, input, failed, completed, negotiation, release; four phases và full graph; no-run contract không mượn run khác.
- [ ] Zoom/pan/fit, node selection/highlight, inspector connections/artifact refs, Enter/Space/Escape/focus và mobile 390px list hoạt động; review desktop 1440/1920px.
- [ ] Review pending/stale/resolved/NOT_EVALUABLE, shell loading/empty/error; fixtures luôn có nhãn, simulation/external-release copy đúng.
- [ ] Network business `/api/` và protected mutations không phát sinh khi review preview. Source-module asset URL có `/src/api/` không phải API request.
- [ ] Nắm 4 pytest failures/2 Ruff issues và 6 dev-toolchain advisories; không sửa business states/asserts để ép xanh.
- [ ] Founder ghi nhận pass/fail/discrepancies và nghiệm thu CP2 trước mở backend integration. Screen-reader/zoom 200% thật chưa được xem đã audit.
- [ ] Task tiếp theo: read-contract mapping cho một exact run qua existing GET APIs, review topology authority; không tự xây aggregation/graph API chưa duyệt.

## 8. Owner cần xác nhận trước push

1. Nghiệm thu CP2 và cho phép commit/push/PR riêng; branch/base/nhóm commits theo mục 5 phù hợp.
2. Hai HOLD scripts: portable hóa trước bàn giao, bỏ khỏi CP2 commits và giữ historical evidence, hay commit như archive có giới hạn rõ.
3. Legacy 435 temp files/263 DB đã có trên remote: maintenance PR riêng trước hay sau UI handoff? Chưa xóa/untrack; chưa khẳng định dữ liệu bên trong phù hợp public distribution chỉ từ pattern scan.
4. Ignore gaps và 6 dev advisories: giao task riêng hay duyệt maintenance scope trước publish; chưa auto-fix.
5. Ghi nhận baseline failures và status CP2 review pending trong PR; không yêu cầu sửa backend ngoài scope để làm handoff trông sạch.

Cho phép push source handoff không đồng nghĩa cho phép backend integration, auth/RBAC, live approvals hoặc external release. Audit này dừng ở đề xuất/review artifacts.
