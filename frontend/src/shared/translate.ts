const TRANSLATIONS: Record<string, string> = {
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
  "The resolved Founder rejection remains binding for the exact protected-action subject and cannot be reused or bypassed.": "Quyết định từ chối trước đó của Nhà sáng lập luôn có giá trị ràng buộc đối với hành động được bảo vệ tương ứng và không được phép sử dụng lại hay bỏ qua.",
  "The Banking precheck result is simulated and non-binding; it must not be represented as a bank offer or approval.": "Kết quả kiểm tra sơ bộ với ngân hàng chỉ là mô phỏng và không ràng buộc; không được coi đây là văn bản phê duyệt hay cam kết cấp tín dụng của ngân hàng.",
  "The masked Document package is an internal candidate only; a separate evidence-bound proposal and Governance authorization are required before external release.": "Gói tài liệu đã che ẩn thông tin nhạy cảm chỉ là bản dự thảo nội bộ; cần có đề xuất dựa trên bằng chứng và sự phê duyệt của ban Kiểm soát trước khi gửi ra ngoài."
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
    replace: "Cảnh báo gốc $1: $2"
  },
  {
    pattern: /^Please confirm the case context and supporting evidence for alert (.*?); Risk has preserved the source statement without treating its description as structured proof\.$/i,
    replace: "Vui lòng xác nhận ngữ cảnh và bằng chứng đi kèm cho cảnh báo $1; Hệ thống đánh giá Rủi ro đã giữ nguyên phát biểu nguồn mà không tự ý coi phần mô tả đó là chứng cứ cấu trúc."
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
