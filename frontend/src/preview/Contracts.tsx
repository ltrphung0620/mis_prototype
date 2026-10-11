import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  ArtifactDetailDialog,
  type ArtifactEnvelope,
} from "../features/artifacts";
import { DecisionCardModal } from "../features/decision";
import { useDialogFocus } from "../shared/useDialogFocus";
import { usePreviewData } from "./data";
import {
  Badge,
  Icon,
  Link,
  money,
  PageHeading,
  SearchField,
  Section,
  SourceNote,
  sourceStatusLabel,
  Tabs,
} from "./components";
import type { PreviewRoute } from "./models";
import { navigatePreview } from "./navigation";

const WorkflowViewer = lazy(() => import("./workflow/WorkflowViewer"));

const views = [
  { key: "overview", label: "Tổng quan" },
  { key: "assessments", label: "Đánh giá" },
  { key: "workflow", label: "Workflow" },
  { key: "evidence", label: "Bằng chứng" },
  { key: "history", label: "Lịch sử" },
];
const assessments = [
  {
    name: "Finance",
    icon: "finance",
    text: "Giá trị nguồn và biên lợi nhuận của hợp đồng được trình bày riêng với dòng tiền công ty.",
  },
  {
    name: "Operations",
    icon: "operations",
    text: "Lịch triển khai chỉ phản ánh đơn hàng có liên kết rõ ràng. Chưa có dữ liệu năng lực nhân sự.",
  },
  {
    name: "Risk",
    icon: "risk",
    text: "Rủi ro còn lại: Trung bình. Cần đối chiếu các giới hạn bằng chứng trước khi quyết định.",
  },
];
const assessmentLabels: Record<string, string> = {
  FINANCE_ASSESSMENT: "Finance",
  OPERATIONS_ASSESSMENT: "Operations",
  FINAL_RISK_ASSESSMENT: "Risk",
};

export function Contracts({ route }: { route: PreviewRoute }) {
  const { contractArtifacts, contracts, fixtureCard, pendingApproval } =
    usePreviewData();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [artifact, setArtifact] = useState<ArtifactEnvelope | null>(null);
  const [dialog, setDialog] = useState<"decision" | "input" | null>(null);
  const [notice, setNotice] = useState("");
  const [reviewState, setReviewState] = useState("pending");
  const [amount, setAmount] = useState("");
  const [inputError, setInputError] = useState("");
  const close = useCallback(() => {
    setArtifact(null);
    setDialog(null);
    setNotice("");
    if (route.request)
      navigatePreview(
        `/contracts/${route.contractId}?view=${route.view ?? "overview"}`,
      );
  }, [route.request, route.contractId, route.view]);
  useDialogFocus(artifact !== null || dialog !== null, close, {
    fallbackFocusId: "workspace-content",
  });
  useEffect(() => {
    setArtifact(null);
    setDialog(null);
    setSearch("");
    setNotice("");
    setReviewState("pending");
  }, [route.contractId, route.view]);
  useEffect(() => {
    if (
      route.contractId === "CON-004" &&
      route.request === pendingApproval.request_id
    )
      setDialog("decision");
    if (route.contractId === "CON-002" && route.request === "UI-INPUT-CON-002")
      setDialog("input");
  }, [route.contractId, route.request]);
  const contract = contracts.find((c) => c.id === route.contractId);
  const artifacts = useMemo(
    () => (contract ? contractArtifacts(contract) : []),
    [contract],
  );
  const tone = (status: string) =>
    status === "FAILED_SAFE"
      ? "error"
      : status === "WAITING_FOR_FINAL_DECISION"
        ? "lavender"
        : status === "WAITING_FOR_INPUT"
          ? "warning"
          : "neutral";
  if (!route.contractId) {
    const rows = contracts.filter(
      (c) =>
        (filter === "all" || c.businessStatus === filter) &&
        `${c.id} ${c.customer} ${c.title}`
          .toLocaleLowerCase("vi")
          .includes(search.toLocaleLowerCase("vi")),
    );
    return (
      <>
        <PageHeading
          title="Hợp đồng"
          description="Tìm hợp đồng và tiếp tục công việc trong đúng lượt đánh giá."
          action={<Badge>5 hợp đồng minh họa</Badge>}
        />
        <Section
          title="Danh sách hợp đồng"
          action={
            <div className="pv-controls">
              <SearchField
                label="Tìm hợp đồng"
                value={search}
                onChange={setSearch}
                placeholder="Tìm hợp đồng, khách hàng…"
              />
              <select
                aria-label="Lọc trạng thái hợp đồng"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option value="all">Workflow: Tất cả</option>
                {contracts.map((c) => (
                  <option key={c.id} value={c.businessStatus}>
                    {c.statusLabel}
                  </option>
                ))}
              </select>
            </div>
          }
        >
          <div
            className="pv-table-scroll"
            tabIndex={0}
            role="region"
            aria-label="Bảng dữ liệu có thể cuộn ngang"
          >
            <table className="pv-contract-table">
              <caption className="pv-sr-only">
                Hợp đồng minh họa, không phải dữ liệu backend
              </caption>
              <thead>
                <tr>
                  <th>Hợp đồng / khách hàng</th>
                  <th className="pv-numeric">Giá trị (tỷ VND)</th>
                  <th>Trạng thái nguồn</th>
                  <th>Trạng thái workflow</th>
                  <th>Ngày minh họa</th>
                  <th>
                    <span className="pv-sr-only">Mở</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr
                    key={c.id}
                    className="pv-contract-row"
                    onClick={(event) => {
                      // Native links keep keyboard/new-tab semantics; the rest of the row is a pointer shortcut.
                      if (
                        event.button !== 0 ||
                        event.ctrlKey ||
                        event.metaKey ||
                        event.shiftKey ||
                        event.altKey
                      )
                        return;
                      if (
                        (event.target as Element).closest(
                          "a, button, input, select",
                        )
                      )
                        return;
                      if (window.getSelection()?.toString()) return;
                      navigatePreview(`/contracts/${c.id}`);
                    }}
                  >
                    <td>
                      <Link
                        to={`/contracts/${c.id}`}
                        className="pv-contract-link"
                      >
                        <strong>{c.id}</strong>
                        <span>{c.customer}</span>
                        <small>{c.title}</small>
                      </Link>
                    </td>
                    <td className="pv-numeric">{money(c.value)}</td>
                    <td>
                      <span>{sourceStatusLabel(c.sourceStatus)}</span>
                      <small>{c.sourceStatus}</small>
                    </td>
                    <td>
                      <Badge tone={tone(c.businessStatus)}>
                        {c.statusLabel}
                      </Badge>
                    </td>
                    <td>{c.date}</td>
                    <td>
                      <Link
                        to={`/contracts/${c.id}`}
                        className="pv-row-link"
                        aria-label={`Mở hợp đồng ${c.id}`}
                      >
                        <Icon />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!rows.length && (
            <p role="status" className="pv-no-results">
              Không có hợp đồng khớp bộ lọc.{" "}
              <button
                onClick={() => {
                  setSearch("");
                  setFilter("all");
                }}
              >
                Xóa bộ lọc
              </button>
            </p>
          )}
        </Section>
        <div className="pv-inline-note">
          <Icon name="contracts" />
          <p>
            Trạng thái nguồn của hợp đồng và trạng thái xử lý workflow là hai
            thông tin riêng. Chọn một dòng để mở hợp đồng; dùng liên kết mã hợp
            đồng khi thao tác bằng bàn phím.
          </p>
        </div>
      </>
    );
  }
  if (!contract)
    return (
      <>
        <PageHeading
          title="Không tìm thấy hợp đồng"
          description="Định danh này không có trong fixtures của preview."
        />
        <Link to="/contracts" className="pv-button">
          Về danh sách hợp đồng
        </Link>
      </>
    );
  const view = route.view ?? "overview";
  const evaluable = contract.id === "CON-004";
  const card = fixtureCard(contract);
  const evidence = artifacts.filter((a) =>
    `${a.artifact_type} ${a.artifact_id}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  const reviewAction = () => {
    setNotice("");
    navigatePreview(
      `/contracts/${contract.id}?view=${view}&request=${pendingApproval.request_id}`,
    );
  };
  const assessmentRows = (
    <div className="pv-assessment-list">
      {assessments.map((a, i) => (
        <div key={a.name}>
          <span className="pv-assessment-icon">
            <Icon name={a.icon} />
          </span>
          <div>
            <h3>
              {a.name} <Badge>Hoàn tất xử lý</Badge>
            </h3>
            <p>{a.text}</p>
          </div>
          <button onClick={() => setArtifact(artifacts[i])}>
            Xem chi tiết <Icon />
          </button>
        </div>
      ))}
    </div>
  );
  const evidenceTable = (
    <>
      <div
        className="pv-table-scroll"
        tabIndex={0}
        role="region"
        aria-label="Bảng dữ liệu có thể cuộn ngang"
      >
        <table>
          <caption className="pv-sr-only">
            Artifacts minh họa của {contract.id}, cùng lượt xử lý
          </caption>
          <thead>
            <tr>
              <th>Artifact</th>
              <th>Định danh / version</th>
              <th>Kiểm tra nội bộ</th>
              <th>
                <span className="pv-sr-only">Chi tiết</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {evidence.map((a) => (
              <tr key={a.artifact_id}>
                <td>
                  {assessmentLabels[a.artifact_type] ?? a.artifact_type}
                  <small>{a.artifact_type}</small>
                </td>
                <td className="pv-id">
                  {a.artifact_id}
                  <small>
                    v{a.version} · {contract.runId}
                  </small>
                </td>
                <td>
                  <Badge>VALID · Minh họa</Badge>
                </td>
                <td>
                  <button onClick={() => setArtifact(a)}>Xem bằng chứng</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!evidence.length && (
        <p role="status" className="pv-no-results">
          Không có artifact khớp tìm kiếm.
        </p>
      )}
      <SourceNote>
        Validation nội bộ minh họa · Không xác minh pháp lý · Giữ artifact
        ID/version và upstream lineage
      </SourceNote>
    </>
  );
  return (
    <>
      <div className="pv-contract-breadcrumb">
        <Link to="/contracts">Hợp đồng</Link>
        <Icon />
        <span>{contract.id}</span>
        <label>
          <span className="pv-sr-only">Chọn hợp đồng</span>
          <select
            value={contract.id}
            onChange={(e) =>
              navigatePreview(`/contracts/${e.target.value}?view=${view}`)
            }
          >
            {contracts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.id} · {c.customer}
              </option>
            ))}
          </select>
        </label>
      </div>
      <PageHeading
        eyebrow={`${contract.id} · ${contract.customer}`}
        title={contract.title}
        action={
          <Badge tone={tone(contract.businessStatus)}>
            {contract.statusLabel}
          </Badge>
        }
      />
      <Tabs
        current={view}
        label="Workspace hợp đồng"
        items={views.map((v) => ({
          ...v,
          to: `/contracts/${contract.id}?view=${v.key}`,
        }))}
      />
      <div className="pv-snapshot-context">
        <span>
          Lượt minh họa: <strong>{contract.runId ?? "Chưa có"}</strong>
        </span>
        <span>
          Trạng thái nguồn: {sourceStatusLabel(contract.sourceStatus)} (
          {contract.sourceStatus})
        </span>
        <span>Contract scope</span>
      </div>
      {route.request &&
        !(
          (contract.id === "CON-004" &&
            route.request === pendingApproval.request_id) ||
          (contract.id === "CON-002" && route.request === "UI-INPUT-CON-002")
        ) && (
          <p role="alert" className="pv-inline-note">
            Không có yêu cầu tương ứng trong preview; không mở review của
            request khác.
          </p>
        )}
      {view === "overview" && (
        <>
          {evaluable ? (
            <section className="pv-decision-summary">
              <header>
                <div className="pv-eyebrow">
                  Decision Card · v1{" "}
                  <Badge tone="lavender">Chờ Founder xem xét</Badge>
                </div>
                <small className="pv-id">{card.artifact_id}</small>
              </header>
              <div className="pv-decision-body">
                <div>
                  <h2>Đề xuất chấp nhận hợp đồng</h2>
                  <p>{card.payload.executive_summary}</p>
                  <span className="pv-confidence">
                    Độ tin cậy: Trung bình{" "}
                    <span>· Đề xuất chưa được phê duyệt</span>
                  </span>
                </div>
                <button
                  className="pv-button pv-button--primary"
                  onClick={reviewAction}
                >
                  Xem xét quyết định <Icon />
                </button>
              </div>
              <footer>
                <span>Precheck mô phỏng, không ràng buộc.</span>
                <span>Phê duyệt quyết định ≠ cho phép gửi hồ sơ.</span>
              </footer>
            </section>
          ) : (
            <Section
              title={contract.statusLabel}
              description={
                contract.attention ?? "Chưa có đề xuất đủ cơ sở để phê duyệt."
              }
            >
              <p>
                {contract.runId
                  ? "Trạng thái chờ/dừng minh họa; không dùng artifacts hoàn tất của CON-004 để thay thế kết quả hợp đồng này."
                  : "Chưa có run, artifact hoặc Decision Card. Preview không tạo lượt xử lý mới."}
              </p>
              {contract.id === "CON-002" && (
                <button
                  onClick={() => {
                    setNotice("");
                    setDialog("input");
                  }}
                >
                  Xem yêu cầu bổ sung
                </button>
              )}
              {contract.businessStatus === "NOT_EVALUABLE" && (
                <button onClick={() => setDialog("decision")}>
                  Xem giới hạn Decision Card
                </button>
              )}
            </Section>
          )}
          <dl className="pv-kpi-strip">
            <div>
              <dt>Giá trị hợp đồng nguồn</dt>
              <dd>
                {money(contract.value)} <span>VND</span>
              </dd>
              <small>Không phải doanh thu đã thu</small>
            </div>
            <div>
              <dt>Biên lợi nhuận ghi trên hợp đồng</dt>
              <dd>{contract.margin}%</dd>
              <small>Trường nguồn · Không tính lại tại browser</small>
            </div>
            <div>
              <dt>Trạng thái xử lý hiện hành</dt>
              <dd className="pv-kpi-text">{contract.statusLabel}</dd>
              <small>Fixture run · Không suy ra từ animation</small>
            </div>
          </dl>
          {evaluable && (
            <>
              <Section
                title="Kết quả đánh giá"
                description="Cùng lượt xử lý · Hoàn tất không đồng nghĩa an toàn"
                action={
                  <Link to={`/contracts/${contract.id}?view=assessments`}>
                    Mở đánh giá <Icon />
                  </Link>
                }
              >
                {assessmentRows}
              </Section>
              <Section
                title="Bằng chứng hỗ trợ"
                action={
                  <Link to={`/contracts/${contract.id}?view=evidence`}>
                    Tất cả bằng chứng <Icon />
                  </Link>
                }
              >
                {evidenceTable}
              </Section>
            </>
          )}
        </>
      )}
      {view === "assessments" &&
        (evaluable ? (
          <Section
            title="Finance, Operations & Risk"
            description="Kết quả minh họa được tách khỏi nhận định và giới hạn"
          >
            {assessmentRows}
            <div className="pv-inline-note">
              <Icon name="risk" />
              <p>
                Không có Risk Score hoặc confidence phần trăm. Xem chi tiết để
                đối chiếu facts và limitations.
              </p>
            </div>
          </Section>
        ) : (
          <Section title="Chưa có bộ đánh giá hiện hành trong preview">
            <p>
              Fixtures chỉ cung cấp trạng thái chờ/dừng của hợp đồng này. Không
              giả định kết quả đã hoàn tất.
            </p>
          </Section>
        ))}
      {view === "evidence" &&
        (evaluable ? (
          <Section
            title="Bằng chứng của lượt xử lý"
            description="Chỉ các artifacts trong run đang chọn"
            action={
              <SearchField
                label="Tìm bằng chứng"
                value={search}
                onChange={setSearch}
                placeholder="Tìm loại artifact hoặc ID…"
              />
            }
          >
            {evidenceTable}
          </Section>
        ) : (
          <Section title="Chưa có artifact để đối chiếu">
            <p>Không hiển thị artifact của hợp đồng khác.</p>
          </Section>
        ))}
      {view === "workflow" && (
        <Suspense fallback={<p role="status">Đang tải Workflow Viewer…</p>}>
          <WorkflowViewer key={contract.id} contract={contract} route={route} />
        </Suspense>
      )}
      {view === "history" && (
        <Section
          title="Lịch sử của lượt xử lý"
          description="Các sự kiện dưới đây là minh họa; không phải audit log backend"
        >
          {!contract.runId && (
            <p>Chưa có lượt xử lý hoặc nhật ký để hiển thị.</p>
          )}
          <ol className="pv-history">
            {(!contract.runId
              ? []
              : evaluable
                ? [
                    "Bắt đầu đánh giá hợp đồng",
                    "Finance và Operations hoàn tất xử lý",
                    "Kiểm tra bằng chứng nội bộ hoàn tất",
                    "Tạo Decision Card v1",
                    "Tạm dừng để chờ Founder xem xét",
                  ]
                : ["Chọn hợp đồng để đánh giá", contract.statusLabel]
            ).map((event, i) => (
              <li key={event}>
                <span className="pv-history-dot" />
                <div>
                  <h3>{event}</h3>
                  <p>
                    {contract.runId ?? "Chưa có run"} · Sự kiện minh họa {i + 1}
                  </p>
                </div>
              </li>
            ))}
          </ol>
          <SourceNote>
            Không tạo timestamp giả để mô tả audit trail thật.
          </SourceNote>
        </Section>
      )}
      <SourceNote />
      <DecisionCardModal
        open={dialog === "decision"}
        card={card}
        current_decision_card_artifact_id={card.artifact_id}
        pending_approval={
          evaluable
            ? {
                ...pendingApproval,
                status: reviewState === "resolved" ? "APPROVED" : "PENDING",
                subject_artifact_version: reviewState === "stale" ? 2 : 1,
              }
            : null
        }
        submitting={Boolean(notice)}
        context={
          <>
            <div className="pv-modal-demo-note" role="status">
              <strong>Dữ liệu minh họa</strong> · Tất cả dữ liệu, kể cả nhãn
              OpenAI, là fixture. Không có model, validation hoặc request
              backend thật.{notice && <p>{notice}</p>}
            </div>
            <div className="pv-review-scenario">
              <label>
                Trạng thái review minh họa{" "}
                <select
                  aria-label="Trạng thái review minh họa"
                  value={reviewState}
                  onChange={(e) => {
                    setReviewState(e.target.value);
                    setNotice("");
                  }}
                >
                  <option value="pending">Pending · Đúng ID/version</option>
                  <option value="stale">Stale · Version không khớp</option>
                  <option value="resolved">Resolved · Request đã đóng</option>
                </select>
              </label>
            </div>
          </>
        }
        onClose={close}
        onApprove={() =>
          setNotice(
            "Đã thử thao tác phê duyệt trong preview. Không gửi request và không thay đổi quyết định backend.",
          )
        }
        onReject={() =>
          setNotice(
            "Đã thử thao tác từ chối trong preview. Không gửi request và không thay đổi quyết định backend.",
          )
        }
      />
      {artifact && (
        <ArtifactDetailDialog
          artifact={artifact}
          runArtifacts={artifacts}
          context={
            <div className="pv-modal-demo-note">
              Dữ liệu minh họa · Artifact và validation là fixture, không phải
              kết quả backend.
            </div>
          }
          onClose={close}
        />
      )}
      {dialog === "input" && (
        <div className="decision-card-modal">
          <article
            role="dialog"
            aria-modal="true"
            aria-labelledby="pv-input-title"
          >
            <header>
              <Badge tone="lavender">Dữ liệu minh họa</Badge>
              <h2 id="pv-input-title">Bổ sung số tiền yêu cầu precheck</h2>
              <p>Thử tương tác form. Không lưu vào backend hoặc dataset.</p>
            </header>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (
                  !amount ||
                  !Number.isFinite(Number(amount)) ||
                  Number(amount) <= 0
                ) {
                  setInputError("Nhập số tiền lớn hơn 0.");
                  return;
                }
                setInputError("");
                setNotice(
                  "Form hợp lệ trong preview. Không tạo patch, không resume workflow và không gọi ngân hàng.",
                );
              }}
            >
              <label className="pv-form-field">
                Số tiền yêu cầu (VND)
                <input
                  type="number"
                  step="1"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  aria-invalid={Boolean(inputError)}
                  aria-describedby={inputError ? "pv-input-error" : undefined}
                />
              </label>
              {inputError && (
                <p id="pv-input-error" role="alert">
                  {inputError}
                </p>
              )}
              {notice && (
                <p role="status" className="pv-modal-demo-note">
                  {notice}
                </p>
              )}
              <footer>
                <button type="button" onClick={close}>
                  Đóng
                </button>
                <button
                  className="pv-button--primary"
                  disabled={Boolean(notice)}
                >
                  Kiểm tra form minh họa
                </button>
              </footer>
            </form>
          </article>
        </div>
      )}
    </>
  );
}
