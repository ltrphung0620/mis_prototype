// UI-only API fixtures. Never imported by production. No real approvals or LLM calls.
async (page) => {
  const runId = "UI-REVIEW-RUN";
  const caseId = "UI-REVIEW-CASE";
  const contractId = "CON-004";
  const artifact = (id, type, payload) => ({ artifact_id: id, artifact_type: type, version: 1, validation_status: "VALID", evaluation_case_id: caseId, producer: "UI_REVIEW", status: "CREATED", payload });
  const artifacts = [
    artifact("UI-FINANCE", "FINANCE_ASSESSMENT", { assessment_status: "COMPLETE", facts: [
      { fact_id: "F1", metric: "CONTRACT_VALUE", value: 7000000000, unit: "VND", scope: "CASE_SPECIFIC", quality: "VERIFIED" },
      { fact_id: "F2", metric: "CONTRACT_GROSS_MARGIN_SOURCE", value: 0.18, unit: "RATIO", scope: "CASE_SPECIFIC", quality: "VERIFIED" },
    ], narrative: { headline: "Hiệu quả tài chính của hợp đồng", statements: [{ text: "Biên lợi nhuận được đối chiếu trên hợp đồng và đơn hàng liên kết.", fact_ids: ["F1", "F2"] }] }, limitations: [{ detail: "Giao dịch ngân hàng chưa có liên kết trực tiếp tới hợp đồng." }] }),
    artifact("UI-OPERATIONS", "OPERATIONS_ASSESSMENT", { assessment_status: "COMPLETE", facts: [], summary: [{ text: "Lịch triển khai được đối chiếu với các đơn hàng liên kết.", fact_ids: [] }], limitations: [{ detail: "Chưa đủ bằng chứng để kết luận về năng lực nguồn lực thực tế." }] }),
    artifact("UI-RISK", "INITIAL_RISK_ASSESSMENT", { overall_risk_level: "MEDIUM", findings: [], limitations: [] }),
    artifact("UI-FINAL-RISK", "FINAL_RISK_ASSESSMENT", { residual_risk_level: "MEDIUM", findings: [], limitations: [{ detail: "Kết quả precheck là mô phỏng, không ràng buộc." }] }),
    artifact("UI-ANALYSIS", "AI_DECISION_ANALYSIS", { analysis_id: "UI-AI", source: "OPENAI" }),
    artifact("UI-CARD", "DECISION_CARD", { decision_card_id: "UI-DC", contract_id: contractId, ai_analysis_id: "UI-AI", ai_analysis_artifact: { artifact_id: "UI-ANALYSIS", version: 1 }, recommendation: "ACCEPT", confidence: "MEDIUM", executive_summary: "Đề xuất chấp nhận hợp đồng dựa trên hồ sơ đánh giá hiện hành. Founder cần xem lại giới hạn bằng chứng trước khi đưa ra quyết định cuối cùng.", residual_risk_level: "MEDIUM", reasons: [{ title: "Hồ sơ đánh giá đã được tổng hợp", detail: "Các kết quả tài chính, vận hành và rủi ro đã được đối chiếu trong cùng lượt xử lý." }], limitations: [{ code: "SIMULATED_PRECHECK", detail: "Precheck ngân hàng là mô phỏng, không ràng buộc." }, { code: "EVIDENCE_LIMIT", detail: "Quan hệ giao dịch và dữ liệu năng lực thực tế còn giới hạn." }], finance_metrics: [], operations_metrics: [], selected_options: [], calculations: [], conditions: [] }),
  ];
  const task = (id, title, artifactId, status = "COMPLETED") => ({ task_id: id, title_vi: title, owner_id: id.split("_")[0], status, status_label_vi: status === "COMPLETED" ? "Hoàn tất" : "Chờ phê duyệt", applicability: "APPLICABLE", artifact_ids: artifactId ? [artifactId] : [], description: "Kết quả và giới hạn được đối chiếu trong hồ sơ đánh giá." });
  const dashboard = {
    workflow_run_id: runId, evaluation_case_id: caseId, contract_id: contractId,
    execution_status: "WAITING_FOR_APPROVAL", execution_status_label_vi: "Chờ Founder phê duyệt",
    business_status: "WAITING_FOR_FINAL_DECISION", business_status_label_vi: "Chờ duyệt quyết định cuối",
    current_stage: "FINAL_DECISION_APPROVAL", current_stage_label_vi: "Founder xem xét quyết định cuối",
    progress: { resolved_task_count: 5, total_task_count: 6, percent: 83, basis: "CANONICAL_WORKFLOW_TASKS" },
    input: { readiness_status: "READY", readiness_label_vi: "Đủ dữ liệu đánh giá ban đầu", blocking_missing_count: 0, warning_count: 0, linked_order_count: 3, linked_invoice_count: 2, linked_customer_count: 1 },
    metrics: [
      { code: "CONTRACT_VALUE", label_vi: "Giá trị hợp đồng", value: 7000000000, unit: "VND", scope: "CASE_SPECIFIC", quality: "VERIFIED" },
      { code: "CONTRACT_GROSS_MARGIN_SOURCE", label_vi: "Biên lợi nhuận trên hợp đồng", value: 0.18, unit: "RATIO", scope: "CASE_SPECIFIC", quality: "VERIFIED" },
      { code: "ORDER_GROSS_MARGIN", label_vi: "Biên lợi nhuận đơn hàng liên kết", value: 0.16, unit: "RATIO", scope: "CASE_SPECIFIC", quality: "VERIFIED", note_vi: "Chỉ phản ánh các đơn hàng liên kết rõ ràng." },
    ],
    stages: [
      { stage_id: "INITIAL_ASSESSMENT", title_vi: "Đánh giá ban đầu", sequence: 1, status: "COMPLETED", parallel: true, applicability: "APPLICABLE", tasks: [task("FINANCE_ASSESSMENT", "Finance · Tài chính", "UI-FINANCE"), task("OPERATIONS_ASSESSMENT", "Operations · Vận hành", "UI-OPERATIONS"), task("INITIAL_RISK_FINALIZATION", "Risk · Rủi ro ban đầu", "UI-RISK")] },
      { stage_id: "FINAL_RISK_CHECK", title_vi: "Kiểm tra rủi ro cuối", sequence: 2, status: "COMPLETED", applicability: "APPLICABLE", tasks: [task("FINAL_RISK_CHECK", "Risk · Kiểm tra cuối", "UI-FINAL-RISK")] },
      { stage_id: "DECISION", title_vi: "Quyết định", sequence: 3, status: "WAITING_FOR_APPROVAL", applicability: "APPLICABLE", tasks: [task("DECISION_CARD_COMPOSITION", "Lập Decision Card", "UI-CARD"), task("FINAL_DECISION_APPROVAL", "Founder phê duyệt cuối", null, "WAITING_FOR_APPROVAL")] },
    ],
    run_artifacts: artifacts.map(({ artifact_id, artifact_type, version, validation_status }) => ({ artifact_id, artifact_type, version, validation_status })),
    approval_request_ids: ["UI-APPROVAL"], pending_interactions: [{ interaction_type: "APPROVAL", title_vi: "Xem xét quyết định cuối", instruction_vi: "Đối chiếu Decision Card và bằng chứng trước khi phê duyệt.", request_ids: [], approval_request_ids: ["UI-APPROVAL"], protected_action: "CONFIRM_FINAL_CONTRACT_DECISION", subject_artifact_id: "UI-CARD", subject_artifact_version: 1, required_fields: [] }],
    decision_card: { available: true, artifact_id: "UI-CARD", decision_card_id: "UI-DC", recommendation: "ACCEPT", recommendation_label_vi: "Chấp nhận hợp đồng", confidence: "MEDIUM", executive_summary: artifacts.at(-1).payload.executive_summary },
  };
  await page.unrouteAll();
  await page.route((url) => url.pathname.startsWith("/api/"), async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body;
    if (path === "/api/system/capabilities") body = { dataset_id: "UI-REVIEW", openai_enabled: false, openai_model: null };
    else if (path === "/api/contracts") body = { dataset_id: "UI-REVIEW", snapshot_hash: "UI-ONLY", contracts: [{ contract_id: contractId }] };
    else if (path === "/api/cases/run") body = { workflow_run_id: runId, evaluation_case_id: caseId, contract_id: contractId, status: "RUNNING", status_url: `/api/workflows/${runId}` };
    else if (path.endsWith("/dashboard")) body = dashboard;
    else if (path.endsWith("/artifacts")) body = artifacts;
    else if (path.endsWith("/approval-requests")) body = [{ request_id: "UI-APPROVAL", workflow_run_id: runId, evaluation_case_id: caseId, subject_artifact_id: "UI-CARD", subject_artifact_version: 1, command: { action_type: "CONFIRM_FINAL_CONTRACT_DECISION" }, status: "PENDING" }];
    else if (path.endsWith("/events")) body = [{ event_id: "UI-EVENT", workflow_run_id: runId, sequence: 1, event_type: "NODE_COMPLETED", node: "DECISION_CARD_COMPOSITION", created_at: "2026-10-08T08:00:00Z" }];
    else return route.fulfill({ status: 409, json: { detail: "UI fixture does not perform protected mutations." } });
    await route.fulfill({ status: path === "/api/cases/run" ? 202 : 200, json: body });
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("http://127.0.0.1:5173/dashboard-assets/");
  await page.getByRole("button", { name: "Bắt đầu đánh giá" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Đóng", exact: true }).click();
  await page.getByText("Chấp nhận hợp đồng", { exact: true }).waitFor();
  await page.evaluate(() => {
    const label = document.createElement("span"); label.textContent = "Dữ liệu minh họa · kiểm thử UI";
    label.style.cssText = "padding:4px 8px;color:#595d9e;background:#f0f1fc;border-radius:4px;font-size:11px";
    document.querySelector(".system-badges").prepend(label);
  });
  await page.screenshot({ path: "output/playwright/founder-desktop-initial.png", fullPage: true });
}
