"""Safe deterministic output for optional Banking option advice."""

from opc_mis.domain.banking_models import (
    BankingAdviceComposition,
    BankingAdvisorInput,
    BankingOptionAdviceDraft,
)
from opc_mis.domain.enums import BankingAdviceSource


class DeterministicBankingOptionAdvisor:
    """Return neutral prose without ranking, selection, or downstream action."""

    model_name = "deterministic-template"
    prompt_version = "banking-option-advisor-v1"

    async def compose(
        self,
        payload: BankingAdvisorInput,
        *,
        fallback_reason: str | None = None,
    ) -> BankingAdviceComposition:
        if len(payload.options) < 2:
            return BankingAdviceComposition(
                advice=BankingOptionAdviceDraft(
                    overview=(
                        "Không gọi bộ tư vấn vì chưa có nhiều phương án để so sánh. "
                        "Ma trận deterministic vẫn là nguồn dữ liệu có thẩm quyền."
                    ),
                    suggestions=(),
                ),
                source=BankingAdviceSource.NOT_INVOKED,
                model="not-invoked",
                prompt_version=self.prompt_version,
                fallback_reason=None,
            )

        return BankingAdviceComposition(
            advice=BankingOptionAdviceDraft(
                overview=(
                    "Không thể tạo phần diễn giải tùy chọn lúc này. "
                    "Hãy đọc trực tiếp ma trận deterministic; hệ thống không đưa ra thứ tự ưu tiên."
                ),
                suggestions=(),
            ),
            source=BankingAdviceSource.DETERMINISTIC_FALLBACK,
            model=self.model_name,
            prompt_version=self.prompt_version,
            fallback_reason=fallback_reason,
        )
