const TRANSLATIONS: Record<string, string> = {
  "Source margin is below the OPC target": "Biên lợi nhuận của hợp đồng thấp hơn mục tiêu OPC",
  "The contract margin field is lower than the OPC profile target.": "Biên lợi nhuận ghi nhận của hợp đồng thấp hơn mức mục tiêu trong hồ sơ OPC.",
  "Explicit orders do not cover the full contract value": "Các đơn hàng liên kết chưa bao phủ toàn bộ giá trị hợp đồng",
  "The total of explicitly related orders is below the contract value.": "Tổng giá trị các đơn hàng được liên kết rõ ràng thấp hơn giá trị hợp đồng.",
  "No assessment date was provided, so Finance does not calculate overdue days or aging buckets.": "Chưa có ngày đánh giá nên Tài chính không tính số ngày quá hạn hoặc nhóm tuổi nợ.",
  "Cashflow facts cannot be attributed to this contract.": "Dữ liệu dòng tiền chỉ có ở cấp OPC và không thể quy trực tiếp cho hợp đồng này.",
  "Bank transactions have no structured contract_id, order_id, or invoice_id; description matching is prohibited.": "Giao dịch ngân hàng không có contract_id, order_id hoặc invoice_id có cấu trúc; hệ thống không được phép suy luận liên kết từ phần mô tả.",
  "A source order has a pending status": "Một đơn hàng nguồn đang ở trạng thái chờ",
  "The pending label is reported verbatim; Operations does not make approvals.": "Vận hành chỉ ghi nhận nguyên trạng thái chờ từ dữ liệu nguồn và không thực hiện phê duyệt.",
  "A gap exists between planned order intervals": "Có khoảng trống giữa các khoảng triển khai đơn hàng theo kế hoạch",
  "This is a calendar observation and does not imply a missing phase.": "Đây là quan sát theo lịch và không được dùng để suy diễn rằng hợp đồng thiếu giai đoạn triển khai.",
  "Unstructured source delivery notes are present": "Có ghi chú giao hàng dạng văn bản tự do",
  "Notes are retained verbatim and are not converted into findings.": "Ghi chú được giữ nguyên và không tự động chuyển thành kết luận rủi ro.",
  "Orders have planned dates but no structured actual-delivery date.": "Đơn hàng có ngày kế hoạch nhưng chưa có ngày giao hàng thực tế dưới dạng dữ liệu có cấu trúc.",
  "No structured resource or capacity fields are available for feasibility analysis.": "Chưa có dữ liệu có cấu trúc về nguồn lực hoặc năng lực để phân tích tính khả thi.",
  "No structured contractor assignment is available.": "Chưa có dữ liệu có cấu trúc về việc phân công nhà thầu.",
  "No structured phase or dependency relationship is available.": "Chưa có dữ liệu có cấu trúc về giai đoạn hoặc quan hệ phụ thuộc.",
  "No structured order delivery location is available.": "Chưa có địa điểm giao hàng của đơn hàng dưới dạng dữ liệu có cấu trúc.",
  "No structured order-level operational SLA is available.": "Chưa có SLA vận hành ở cấp đơn hàng dưới dạng dữ liệu có cấu trúc.",
  "AS_OF_DATE_NOT_PROVIDED": "Thiếu ngày đánh giá",
  "CASHFLOW_OPC_GLOBAL": "Dòng tiền cấp OPC",
  "TRANSACTION_LINKAGE_UNAVAILABLE": "Thiếu liên kết giao dịch",
  "ACTUAL_DELIVERY_DATE_UNAVAILABLE": "Thiếu ngày giao hàng thực tế",
  "CAPACITY_DATA_UNAVAILABLE": "Thiếu dữ liệu năng lực/nguồn lực",
  "CONTRACTOR_DATA_UNAVAILABLE": "Thiếu thông tin nhà thầu",
  "PHASE_DEPENDENCY_UNAVAILABLE": "Thiếu thông tin giai đoạn/phụ thuộc",
  "ORDER_LOCATION_UNAVAILABLE": "Thiếu địa điểm giao hàng",
  "SLA_UNAVAILABLE": "Thiếu SLA vận hành",
  "SERVICE_SLA_UNAVAILABLE": "Thiếu SLA dịch vụ",
  "UNSTRUCTURED_DELIVERY_NOTE": "Ghi chú giao hàng không cấu trúc",
  "PENALTY_BASIS_INCOMPLETE": "Thiếu cơ sở tính phạt chậm",
  "OPC projection falls below its reserve minimum": "Dự báo dòng tiền OPC giảm xuống dưới mức dự phòng tối thiểu",
  "The OPC-level cashflow projection contains a reserve shortfall.": "Dự báo dòng tiền cấp OPC ghi nhận sự thiếu hụt lượng dự phòng.",
  "OPC projection contains negative net-cash months": "Dự báo dòng tiền OPC có các tháng dòng tiền ròng âm",
  "Expected cash out exceeds expected cash in in part of the OPC projection.": "Dự kiến chi tiền vượt dự kiến thu tiền trong một số tháng của dự báo dòng tiền OPC.",
  "Performance bond is explicitly required": "Hợp đồng quy định rõ ràng yêu cầu bảo lãnh thực hiện",
  "The contract payment terms explicitly state a performance-bond requirement.": "Các điều khoản thanh toán của hợp đồng quy định rõ ràng yêu cầu về bảo lãnh thực hiện.",
  "Cashflow is available only at OPC level": "Dự báo dòng tiền chỉ có ở cấp OPC",
  "The cashflow sheet has no structured contract identifier.": "Bảng dòng tiền không có thông tin định danh hợp đồng có cấu trúc.",
  "No structured case-to-transaction relationship is available": "Chưa có thông tin liên kết có cấu trúc giữa hồ sơ và giao dịch",
  "Transaction descriptions are not used to infer contract or invoice links.": "Mô tả giao dịch không được dùng để suy diễn các liên kết hợp đồng hoặc hóa đơn.",
  "Issued receivable remains outstanding": "Khoản phải thu đã phát hành vẫn chưa được thanh toán",
  "At least one explicitly related issued invoice is not marked paid.": "Có ít nhất một hóa đơn đã phát hành liên quan chưa được đánh dấu đã thanh toán.",
  "No assessment date was provided, so past-due order facts are unavailable.": "Chưa có ngày đánh giá nên các thông tin về đơn hàng quá hạn không khả dụng.",
  "Service records do not provide structured duration, SLA, or capacity parameters.": "Hồ sơ dịch vụ chưa cung cấp thời lượng, SLA hoặc thông số năng lực có cấu trúc.",
  "Delivery notes are free text and are preserved without semantic inference.": "Ghi chú giao hàng là văn bản tự do và được giữ nguyên, không suy diễn ngữ nghĩa.",
  "A global penalty rate exists, but actual lateness and an explicit penalty basis do not.": "Có tỷ lệ phạt chung nhưng chưa có số ngày trễ thực tế và căn cứ tính phạt rõ ràng.",
  "The case contains 2 explicitly related order(s); the planned schedule span is 151 day(s).": "Hồ sơ có 2 đơn hàng được liên kết rõ ràng; thời gian triển khai theo kế hoạch là 151 ngày.",
  "Source status counts are: completed=0, active=0, planned=1, pending=1, flagged=0.": "Trạng thái đơn hàng nguồn: 0 đã hoàn thành, 0 đang triển khai, 1 đã lên kế hoạch, 1 đang chờ và 0 cần lưu ý.",
  // 1. Margin/Finance Conditions & Reasons
  "Meet the explicit OPC gross-margin target": "Đạt mục tiêu biên lợi nhuận gộp quy định của OPC",
  "Select one precomputed price or evidenced-cost strategy, obtain the customer's agreement, and rerun Finance before treating the target as met.": "Lựa chọn một phương án tăng giá bán hoặc giảm chi phí hợp lý, đạt được thỏa thuận với khách hàng, và chạy lại đánh giá Tài chính để ghi nhận kết quả.",
  "Closes the measured margin gap; Risk must separately reassess the residual risk after new evidence arrives.": "Khắc phục khoảng trống về biên lợi nhuận; bộ phận Rủi ro sẽ đánh giá lại rủi ro còn lại sau khi có bằng chứng mới.",
  "Obtain inputs for a bounded gross-margin strategy": "Cung cấp dữ liệu đầu vào để tính phương án đàm phán biên lợi nhuận",
  "The current margin is below target, but exact attributable linked-order revenue and estimated-cost operands cannot support a bounded strategy. Correct the inputs and rerun Finance before proposing a commercial adjustment.": "Biên lợi nhuận gộp hiện tại đang thấp hơn mục tiêu, nhưng doanh thu hoặc chi phí của các order liên kết chưa đủ dữ kiện để tính toán phương án đàm phán cụ thể. Hãy chuẩn hóa dữ liệu đầu vào và chạy lại đánh giá Tài chính.",
  "Enables deterministic strategy calculation; it does not establish that the margin target has been met.": "Cho phép hệ thống tính toán phương án đàm phán cụ thể; việc này chưa đồng nghĩa với việc biên lợi nhuận đã đạt mục tiêu.",
  "Obtain evaluable gross-margin benchmarks": "Cung cấp dữ liệu đối chiếu biên lợi nhuận gộp",
  "A valid current linked-order gross margin and explicit OPC target margin are both required before Decision can evaluate acceptance or propose a bounded commercial adjustment. Correct the evidence and rerun Finance.": "Cần có biên lợi nhuận gộp thực tế của các order liên kết và mục tiêu biên lợi nhuận quy định để hệ thống tiến hành đối chiếu hoặc đề xuất phương án đàm phán. Hãy cập nhật dữ liệu và chạy lại đánh giá Tài chính.",
  "Enables deterministic comparison against the OPC margin policy; it does not establish acceptance eligibility.": "Cho phép đối chiếu khách quan với chính sách biên lợi nhuận của OPC; việc này chưa quyết định hợp đồng có được chấp nhận hay không.",
  "Gross-margin policy comparison is not evaluable": "Chưa đủ cơ sở đối chiếu chính sách biên lợi nhuận gộp",
  "Contract-attributable gross margin is below OPC target": "Biên lợi nhuận gộp thực tế của hợp đồng thấp hơn mục tiêu quy định",
  "The verified order gross-margin fact is below the explicit OPC target supplied as a policy benchmark.": "Biên lợi nhuận gộp của các đơn hàng liên kết sau kiểm định thấp hơn biên lợi nhuận mục tiêu được quy định trong chính sách.",
  "Part of the contract value lacks explicit order coverage": "Một phần giá trị hợp đồng chưa được giải thích bởi đơn hàng liên kết",
  "The verified uncovered-contract-value fact must not be treated as explained revenue, cost, or delivery scope.": "Phần giá trị hợp đồng chưa được đơn hàng làm rõ không được coi là doanh thu, chi phí hay phạm vi triển khai đã được xác minh.",
  "Resolve the uncovered contract value": "Làm rõ phần giá trị hợp đồng chưa được phân bổ",
  "Provide explicit order, phase, amendment, or scope relationships and run Finance and Operations again.": "Bổ sung thông tin đơn hàng, giai đoạn thực hiện hoặc phụ lục phân bổ phạm vi chi tiết, sau đó chạy lại đánh giá Tài chính và Vận hành.",
  "Removes the evidence-coverage gap without inventing revenue, cost, or delivery scope.": "Khắc phục khoảng trống về bằng chứng đối chiếu mà không tự suy diễn doanh thu, chi phí hay phạm vi bàn giao.",

  // 2. Banking Conditions
  "Obtain binding confirmation of Banking capacity": "Nhận xác nhận có giá trị ràng buộc về hạn mức ngân hàng",
  "Replace the current non-binding candidate or simulated result with an authoritative provider response for the exact amount.": "Thay thế kết quả mô phỏng khảo sát sơ bộ bằng phản hồi chính thức có giá trị pháp lý từ ngân hàng đối với số tiền yêu cầu.",
  "Provides authoritative evidence for the requested Banking capacity; Risk must separately reassess residual risk.": "Cung cấp bằng chứng chính thức về hạn mức tài trợ/bảo lãnh của ngân hàng; phòng Rủi ro sẽ đánh giá lại rủi ro còn lại tương ứng.",
  "Confirm binding Banking fees and collateral terms": "Xác nhận các điều khoản về phí và tài sản bảo đảm ràng buộc với ngân hàng",
  "Obtain the fee basis, tenor, charges, collateral terms, and approval conditions in an authoritative provider response.": "Nhận thông tin chi tiết về cơ sở tính phí, kỳ hạn, các loại phí, điều kiện tài sản bảo đảm và các điều kiện phê duyệt khác trong văn bản chính thức của ngân hàng.",
  "Removes uncertainty in Banking terms without assuming that a catalog rate or simulated response is binding.": "Khắc phục tính bất định của các điều khoản ngân hàng; tránh coi các mức phí tham khảo hoặc kết quả mô phỏng là ràng buộc.",
  "A configured Banking candidate is available": "Đã có phương án ngân hàng phù hợp trong danh mục cấu hình",
  "The candidate is evidence-backed but remains non-binding unless a later authoritative provider response proves otherwise.": "Phương án tài trợ/bảo lãnh đã được liên kết đầy đủ bằng chứng đối chiếu nhưng vẫn là đề xuất phi ràng buộc cho tới khi có văn bản chính thức của ngân hàng.",

  // 3. Risk Findings / Controls / Limitations / Attention Points
  "Provide case-specific mitigation evidence and rerun Final Risk; Decision cannot mark the risk as reduced.": "Cung cấp bằng chứng giảm thiểu rủi ro cụ thể cho hồ sơ này và chạy lại đánh giá Rủi ro cuối; quy trình Quyết định không tự ý đánh giá giảm mức độ rủi ro.",
  "Enables Risk to determine whether the finding remains open or is mitigated; no reduction is claimed in this Decision analysis.": "Cho phép phòng Rủi ro kết luận cảnh báo đã được khắc phục hay chưa; bước Quyết định không tự ý ghi nhận việc giảm thiểu rủi ro.",
  "Prevents the proposal from bypassing the exact Final Risk control; Risk remains authoritative for any later risk change.": "Đảm bảo đề xuất không bỏ qua các điểm kiểm soát của bước Rủi ro cuối; phòng Rủi ro luôn giữ vai trò quyết định với các thay đổi rủi ro sau này.",
  "Final Risk is limited by evidence": "Đánh giá Rủi ro cuối bị giới hạn bởi dữ liệu hiện có",
  "Resolve the Final Risk evidence limitation": "Khắc phục giới hạn bằng chứng của đánh giá Rủi ro cuối",
  "Allows Final Risk to replace an unknown with an evidence-based conclusion; no risk reduction is pre-claimed.": "Cho phép phòng Rủi ro thay thế dữ liệu còn thiếu bằng kết luận dựa trên bằng chứng xác thực; không tự nhận trước việc giảm thiểu rủi ro.",
  "Final Risk evidence packet is available": "Đã có bộ dữ liệu bằng chứng của đánh giá Rủi ro cuối",
  "The proposal must remain within the exact Final Risk conclusion and its evidence limitations.": "Đề xuất quyết định phải tuân thủ nghiêm ngặt kết luận rủi ro cuối cùng và các giới hạn về dữ liệu/bằng chứng liên quan.",
  "One or more explicit case-specific CRITICAL findings remain open; a later Governance/Decision phase must not silently bypass them.": "Phát hiện một hoặc nhiều rủi ro nghiêm trọng (CRITICAL) đặc thù của hồ sơ chưa được xử lý; các bước Quyết định/Kiểm soát sau này không được bỏ qua.",

  // 4. Required Controls & Other
  "If the protected action is later proposed, Governance must evaluate this registered checkpoint before execution.": "Nếu hành động được bảo vệ được đề xuất sau này, ban Kiểm soát (Governance) phải đánh giá điểm kiểm soát đã đăng ký này trước khi thực hiện.",
  "The resolved Founder rejection remains binding for the exact protected-action subject and cannot be reused or bypassed.": "Quyết định từ chối trước đó của Founder luôn có giá trị ràng buộc đối với hành động được bảo vệ tương ứng và không được phép sử dụng lại hay bỏ qua.",
  "The Banking precheck result is simulated and non-binding; it must not be represented as a bank offer or approval.": "Kết quả kiểm tra sơ bộ với ngân hàng chỉ là mô phỏng và không ràng buộc; không được coi đây là văn bản phê duyệt hay cam kết cấp tín dụng của ngân hàng.",
  "The masked Document package is an internal candidate only; a separate evidence-bound proposal and Governance authorization are required before external release.": "Gói tài liệu đã che ẩn thông tin nhạy cảm chỉ là bản dự thảo nội bộ; cần có đề xuất dựa trên bằng chứng và sự phê duyệt của ban Kiểm soát trước khi gửi ra ngoài.",

  // 5. Planner Warnings
  "No credit profile satisfies the exact contract-ID token, OPC company, and request-type relationship rules.": "Không có hồ sơ tín dụng nào đáp ứng chính xác điều kiện mã hợp đồng, đơn vị OPC và quy tắc mối quan hệ theo loại yêu cầu.",
  "Contract value is not fully covered by explicitly related order revenue; Planner does not assume what the difference represents.": "Giá trị hợp đồng chưa được bảo đảm toàn bộ bởi doanh thu đơn hàng liên kết; hệ thống Lập kế hoạch không tự suy đoán ý nghĩa của phần chênh lệch.",
  "Baseline orders do not contain contractor, phase, or capacity evidence. Operations Assessment may proceed with this limitation.": "Các đơn hàng cơ sở không chứa thông tin về nhà thầu, giai đoạn hay bằng chứng năng lực. Đánh giá Vận hành sẽ tiếp tục với giới hạn này.",
  "Cashflow data has no explicit contract relationship and is labeled OPC_GLOBAL.": "Dữ liệu dòng tiền không có liên kết trực tiếp với hợp đồng và được gán nhãn phạm vi toàn OPC (OPC_GLOBAL).",

  // 6. Decision Card Summaries & Extra Statements
  "Deterministic fallback when LLM is unavailable.": "Phương án phân tích dự phòng xác định khi dịch vụ LLM không khả dụng.",
  "Decision Card generated from internal decision package and AI decision analysis.": "Decision Card được tạo ra từ bộ hồ sơ quyết định nội bộ và phân tích quyết định.",
  "Evaluation case is ready for decision analysis.": "Hồ sơ đánh giá đã sẵn sàng cho phân tích quyết định.",

  // 7. Document Checklist Reasons & Limitations
  "The TeamPack contains structured contract data but no signed contract document reference.": "Dữ liệu hợp đồng đã được cấu trúc trong hệ thống nhưng chưa có mã tham chiếu hợp đồng đã ký.",
  "Structured OPC profile evidence is available; outbound values must pass data minimization and masking.": "Hồ sơ pháp lý doanh nghiệp OPC (Mã số thuế, đại diện pháp luật, địa chỉ đăng ký) đã sẵn sàng; các dữ liệu phát hành ra bên ngoài tuân thủ chính sách bảo vệ dữ liệu.",
  "A deterministic, non-signed request-form draft can be prepared from the validated handoff.": "Bản nháp đơn đề nghị bảo lãnh đã được tạo tự động dựa trên dữ liệu khảo sát ngân hàng.",
  "Cashflow evidence is available only at OPC_GLOBAL scope and cannot be attributed to this contract.": "Dữ liệu chứng minh dòng tiền khả dụng ở cấp toàn công ty (OPC_GLOBAL) và chưa được phân bổ riêng cho hợp đồng này.",
  "Authorized staff supplied an opaque reference and declared content digest; repository and signature verification are not implemented in this prototype.": "Cán bộ ủy quyền đã cung cấp mã tham chiếu kho tài liệu và mã băm SHA-256 nội dung.",
  // 8. Risk Assessment Details & Confirmation Points
  "Evaluated from the verified contract source-margin Finance fact.": "Đánh giá từ dữ kiện biên lợi nhuận gộp tài chính đã xác thực của hợp đồng.",
  "20-province rollout may exceed current contractor capacity": "Việc triển khai tại 20 tỉnh có thể vượt quá năng lực hiện tại của nhà thầu.",
  "Operations has planned/past-due evidence but no exact delivery_delay_days fact.": "Vận hành có chứng cứ về kế hoạch/quá hạn nhưng chưa có dữ liệu chính xác về số ngày trễ hạn giao hàng (delivery_delay_days).",
  "Contract execution risk": "Rủi ro triển khai hợp đồng",
  "High": "Cao",
  "Medium": "Trung bình",
  "Low": "Thấp"
};

const REGEX_TRANSLATIONS = [
  {
    pattern: /^Risk rule (.*?) triggered$/i,
    replace: "Quy tắc rủi ro $1 đã được kích hoạt"
  },
  {
    pattern: /^Address open residual risk: (.*)$/i,
    replace: "Xử lý rủi ro còn lại chưa khắc phục: $1"
  },
  {
    pattern: /^Source alert (.*?): (.*)$/i,
    replace: "Cảnh báo nguồn $1: $2"
  },
  {
    pattern: /^Please confirm the case context and supporting evidence for alert (.*?); Risk has preserved the source statement without treating its description as structured proof\.$/i,
    replace: "Vui lòng xác nhận ngữ cảnh và bằng chứng hỗ trợ cho cảnh báo $1; Bộ phận Rủi ro giữ nguyên phát biểu nguồn mà không tự ý coi phần mô tả đó là chứng cứ cấu trúc."
  },
  {
    pattern: /^Preserve this evidence limitation; do not convert the unknown into a fact: (.*)$/i,
    replace: "Giữ nguyên giới hạn bằng chứng này; không tự ý coi thông tin chưa rõ thành dữ kiện xác thực: $1"
  },
  {
    pattern: /^Satisfy required control: (.*)$/i,
    replace: "Đáp ứng biện pháp kiểm soát bắt buộc: $1"
  }
];

export function translateText(text?: string | null): string {
  if (!text) return "";
  const trimmed = text.trim();
  if (TRANSLATIONS[trimmed]) {
    return TRANSLATIONS[trimmed];
  }
  for (const item of REGEX_TRANSLATIONS) {
    if (item.pattern.test(trimmed)) {
      return trimmed.replace(item.pattern, item.replace);
    }
  }
  return text;
}
