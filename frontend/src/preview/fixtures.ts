/** Synthetic design fixtures only. No workbook data, model call or backend mutation. */
import type { ArtifactEnvelope } from "../features/artifacts";
import type {
  DecisionCardArtifact,
  PendingDecisionApproval,
} from "../features/decision";
import type {
  CashPoint,
  PreviewAction,
  PreviewContract,
  InvoiceRow,
  OrderRow,
  SourceAlert,
  StatusPoint,
} from "./models";

export const snapshot = {
  company: "OPC Technology",
  subtitle: "Giải pháp công nghệ cho doanh nghiệp",
  id: "UI-SNAPSHOT-2026",
  period: "06–11/2026",
  unit: "VND",
  source: "Fixtures giao diện",
  dataAsOf: null,
  kpis: { contracts: 5, contractValue: 23300000000, openInvoices: 2200000000 },
};
export const contracts: readonly PreviewContract[] = [
  {
    id: "CON-004",
    customer: "An Việt",
    title: "Triển khai nền tảng quản trị doanh nghiệp",
    value: 7000000000,
    margin: 18,
    sourceStatus: "Negotiation",
    businessStatus: "WAITING_FOR_FINAL_DECISION",
    statusLabel: "Chờ duyệt quyết định",
    runId: "UI-RUN-CON-004",
    date: "10/10/2026",
    attention: "Decision Card cần Founder xem xét",
  },
  {
    id: "CON-002",
    customer: "Minh Hải",
    title: "Nâng cấp hệ thống vận hành",
    value: 4800000000,
    margin: 22,
    sourceStatus: "Active",
    businessStatus: "WAITING_FOR_INPUT",
    statusLabel: "Chờ bổ sung dữ liệu",
    runId: "UI-RUN-CON-002",
    date: "09/10/2026",
    attention: "Thiếu số tiền yêu cầu precheck",
  },
  {
    id: "CON-001",
    customer: "Bình Minh",
    title: "Tích hợp dữ liệu và báo cáo",
    value: 3100000000,
    margin: 24,
    sourceStatus: "Active",
    businessStatus: "NOT_EVALUABLE",
    statusLabel: "Chưa đủ cơ sở quyết định",
    runId: "UI-RUN-CON-001",
    date: "08/10/2026",
  },
  {
    id: "CON-005",
    customer: "Nam Sơn",
    title: "Dịch vụ hạ tầng và bảo trì",
    value: 6000000000,
    margin: 19,
    sourceStatus: "Negotiation",
    businessStatus: "FAILED_SAFE",
    statusLabel: "Dừng an toàn",
    runId: "UI-RUN-CON-005",
    date: "08/10/2026",
    attention: "Bằng chứng cần được kiểm tra lại",
  },
  {
    id: "CON-003",
    customer: "Tân Phú",
    title: "Mở rộng nền tảng khách hàng",
    value: 2400000000,
    margin: 20,
    sourceStatus: "Pending expansion",
    businessStatus: "",
    statusLabel: "Chưa có lượt đánh giá",
    runId: null,
    date: "—",
  },
];
export const actions: readonly PreviewAction[] = [
  {
    id: "UI-APPROVAL-CON-004",
    kind: "approval",
    title: "Xem xét quyết định hợp đồng",
    description: "Decision Card hiện hành đã sẵn sàng để đối chiếu.",
    contractId: "CON-004",
    label: "Xem xét",
    link: "/contracts/CON-004?view=overview&request=UI-APPROVAL-CON-004",
  },
  {
    id: "UI-INPUT-CON-002",
    kind: "input",
    title: "Bổ sung số tiền yêu cầu precheck",
    description: "Quy trình đang chờ thông tin do Founder cung cấp.",
    contractId: "CON-002",
    label: "Bổ sung",
    link: "/contracts/CON-002?view=overview&request=UI-INPUT-CON-002",
  },
  {
    id: "UI-FAIL-CON-005",
    kind: "failure",
    title: "Kiểm tra giới hạn bằng chứng",
    description: "Lượt xử lý dừng an toàn; chưa tạo đề xuất có thể duyệt.",
    contractId: "CON-005",
    label: "Xem quy trình",
    link: "/contracts/CON-005?view=workflow",
  },
];
export const cashflow: readonly CashPoint[] = [
  {
    month: "2026-06",
    label: "Thg 6",
    cashIn: 1700000000,
    cashOut: 1450000000,
    closing: 950000000,
    reserve: 800000000,
  },
  {
    month: "2026-07",
    label: "Thg 7",
    cashIn: 2250000000,
    cashOut: 1800000000,
    closing: 1400000000,
    reserve: 800000000,
  },
  {
    month: "2026-08",
    label: "Thg 8",
    cashIn: 1900000000,
    cashOut: 2200000000,
    closing: 1100000000,
    reserve: 800000000,
  },
  {
    month: "2026-09",
    label: "Thg 9",
    cashIn: 2100000000,
    cashOut: 2450000000,
    closing: 750000000,
    reserve: 800000000,
  },
  {
    month: "2026-10",
    label: "Thg 10",
    cashIn: 2650000000,
    cashOut: 2000000000,
    closing: 1400000000,
    reserve: 800000000,
  },
  {
    month: "2026-11",
    label: "Thg 11",
    cashIn: 3200000000,
    cashOut: 2400000000,
    closing: 2200000000,
    reserve: 800000000,
  },
];
export const invoices: readonly InvoiceRow[] = [
  {
    id: "INV-001",
    order: "ORD-001",
    contract: "CON-001",
    customer: "Bình Minh",
    amount: 1200000000,
    status: "Paid",
    date: "14/06/2026",
  },
  {
    id: "INV-002",
    order: "ORD-002",
    contract: "CON-002",
    customer: "Minh Hải",
    amount: 800000000,
    status: "Open",
    date: "20/07/2026",
  },
  {
    id: "INV-003",
    order: "ORD-003",
    contract: "CON-004",
    customer: "An Việt",
    amount: 1400000000,
    status: "Open",
    date: "12/09/2026",
  },
  {
    id: "INV-004",
    order: "ORD-004",
    contract: "CON-005",
    customer: "Nam Sơn",
    amount: 900000000,
    status: "Paid",
    date: "04/08/2026",
  },
  {
    id: "INV-005",
    order: "ORD-005",
    contract: "CON-004",
    customer: "An Việt",
    amount: 1600000000,
    status: "Paid",
    date: "22/08/2026",
  },
  {
    id: "INV-006",
    order: "ORD-006",
    contract: "CON-003",
    customer: "Tân Phú",
    amount: 600000000,
    status: "Not issued",
    date: null,
  },
  {
    id: "INV-007",
    order: "ORD-007",
    contract: "CON-002",
    customer: "Minh Hải",
    amount: 1100000000,
    status: "Not issued",
    date: null,
  },
];
// Already-composed fixture read models. Components only format/filter; no financial aggregation.
export const invoiceDistribution: readonly StatusPoint[] = [
  { label: "Ghi nguồn Paid", value: 3700000000, status: "Paid" },
  { label: "Ghi nguồn Open", value: 2200000000, status: "Open" },
  { label: "Chưa phát hành", value: 1700000000, status: "Not issued" },
];
export const orders: readonly OrderRow[] = [
  {
    id: "ORD-001",
    contract: "CON-001",
    service: "Tích hợp dữ liệu",
    status: "Delivered",
    due: "30/06/2026",
  },
  {
    id: "ORD-002",
    contract: "CON-002",
    service: "Tư vấn triển khai",
    status: "In progress",
    due: "31/10/2026",
  },
  {
    id: "ORD-003",
    contract: "CON-004",
    service: "Nền tảng quản trị",
    status: "Planned",
    due: "30/11/2026",
  },
  {
    id: "ORD-004",
    contract: "CON-005",
    service: "Bảo trì hạ tầng",
    status: "At risk",
    due: "15/10/2026",
  },
  {
    id: "ORD-005",
    contract: "CON-004",
    service: "Tích hợp hệ thống",
    status: "In progress",
    due: "10/11/2026",
  },
  {
    id: "ORD-006",
    contract: "CON-003",
    service: "Nâng cấp nền tảng",
    status: "Pending approval",
    due: "30/11/2026",
  },
  {
    id: "ORD-007",
    contract: "CON-002",
    service: "Đào tạo vận hành",
    status: "Planned",
    due: "15/11/2026",
  },
];
export const orderDistribution: readonly StatusPoint[] = [
  { label: "Đang triển khai", value: 2, status: "In progress" },
  { label: "Đã bàn giao", value: 1, status: "Delivered" },
  { label: "Dự kiến", value: 2, status: "Planned" },
  { label: "Cần chú ý", value: 1, status: "At risk" },
  { label: "Chờ xác nhận", value: 1, status: "Pending approval" },
];
export const alerts: readonly SourceAlert[] = [
  {
    id: "UI-ALERT-001",
    title: "Dự trữ dự kiến dưới ngưỡng nguồn",
    detail:
      "Tháng 9 trong kịch bản minh họa có projected closing cash thấp hơn minimum reserve. Đây là dự kiến, không phải số dư ngân hàng.",
    severity: "High",
  },
  {
    id: "UI-ALERT-002",
    title: "Giới hạn liên kết giao dịch",
    detail:
      "Chưa có quan hệ trực tiếp để phân bổ giao dịch ngân hàng vào từng hợp đồng.",
    severity: "Medium",
  },
  {
    id: "UI-ALERT-003",
    title: "Bằng chứng chưa đủ cho quyết định",
    detail: "Lượt xử lý cần kiểm tra lại bằng chứng trước khi tiếp tục.",
    severity: "High",
    contract: "CON-005",
  },
];
export function contractArtifacts(
  contract: PreviewContract,
): ArtifactEnvelope[] {
  const financeId = `UI-FINANCE-${contract.id}`;
  return [
    {
      artifact_id: financeId,
      artifact_type: "FINANCE_ASSESSMENT",
      version: 1,
      validation_status: "VALID",
      payload: {
        assessment_status: "COMPLETE",
        facts: [
          {
            fact_id: "UI-F1",
            metric: "CONTRACT_VALUE",
            value: contract.value,
            unit: "VND",
            scope: "CASE_SPECIFIC",
            quality: "VERIFIED",
          },
          {
            fact_id: "UI-F2",
            metric: "CONTRACT_GROSS_MARGIN_SOURCE",
            value: contract.margin / 100,
            unit: "RATIO",
            scope: "CASE_SPECIFIC",
            quality: "VERIFIED",
          },
        ],
        narrative: {
          headline: "Các chỉ số nguồn được đối chiếu trong cùng lượt xử lý.",
          statements: [
            {
              text: "Giá trị và biên lợi nhuận là dữ liệu minh họa cho hợp đồng đang chọn.",
              fact_ids: ["UI-F1", "UI-F2"],
            },
          ],
        },
        limitations: [
          { detail: "Chưa đối soát với giao dịch ngân hàng thực tế." },
        ],
      },
    },
    {
      artifact_id: `UI-OPERATIONS-${contract.id}`,
      artifact_type: "OPERATIONS_ASSESSMENT",
      version: 1,
      validation_status: "VALID",
      payload: {
        assessment_status: "COMPLETE",
        facts: [],
        summary: [
          {
            text: "Lịch triển khai chỉ phản ánh các đơn hàng có liên kết rõ ràng.",
          },
        ],
        limitations: [{ detail: "Chưa có dữ liệu năng lực nhân sự thực tế." }],
      },
    },
    {
      artifact_id: `UI-RISK-${contract.id}`,
      artifact_type: "FINAL_RISK_ASSESSMENT",
      version: 1,
      validation_status: "VALID",
      input_artifact_ids: [financeId, `UI-OPERATIONS-${contract.id}`],
      payload: {
        residual_risk_level: "MEDIUM",
        findings: [
          {
            title: "Giới hạn bằng chứng",
            detail: "Kết quả cần được Founder đối chiếu trước khi quyết định.",
            severity: "MEDIUM",
          },
        ],
        limitations: [{ detail: "Precheck là mô phỏng, không ràng buộc." }],
      },
    },
  ];
}
export function fixtureCard(contract: PreviewContract): DecisionCardArtifact {
  const evaluable = contract.id === "CON-004";
  return {
    artifact_id: `UI-CARD-${contract.id}`,
    version: 1,
    payload: {
      decision_card_id: `UI-DC-${contract.id}`,
      contract_id: contract.id,
      analysis_source: evaluable ? "OPENAI" : "DETERMINISTIC_FALLBACK",
      recommendation: evaluable ? "ACCEPT" : "NOT_EVALUABLE",
      confidence: evaluable ? "MEDIUM" : "NOT_EVALUABLE",
      executive_summary: evaluable
        ? "Đề xuất chấp nhận dựa trên hồ sơ đánh giá hiện hành. Founder cần xem lại các giới hạn bằng chứng trước khi quyết định."
        : "Chưa đủ cơ sở để đưa ra đề xuất có thể phê duyệt.",
      reasons: [
        {
          title: "Đối chiếu cùng lượt đánh giá",
          detail:
            "Finance, Operations và Risk được trình bày cùng identity của lượt xử lý minh họa.",
        },
      ],
      residual_risk_level: "MEDIUM",
      conditions: [],
      limitations: [
        {
          code: "UI_FIXTURE",
          detail:
            "Toàn bộ phân tích, kể cả nhãn nguồn OpenAI, là fixture; không có lần gọi model thật.",
        },
        {
          code: "SIMULATED_PRECHECK",
          detail: "Precheck ngân hàng là mô phỏng, không ràng buộc.",
        },
        {
          code: "SEPARATE_RELEASE",
          detail: "Phê duyệt quyết định không đồng nghĩa cho phép gửi hồ sơ.",
        },
      ],
      finance_metrics: [],
      operations_metrics: [],
      calculations: [],
    },
  };
}
export const pendingApproval: PendingDecisionApproval = {
  request_id: "UI-APPROVAL-CON-004",
  status: "PENDING",
  subject_artifact_id: "UI-CARD-CON-004",
  subject_artifact_version: 1,
  protected_action: "CONFIRM_FINAL_CONTRACT_DECISION",
};
