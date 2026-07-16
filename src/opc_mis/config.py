"""Environment-backed runtime configuration."""

from dataclasses import dataclass
from os import getenv
from pathlib import Path

DEFAULT_DATASET_ID = "MISTalent2026_OPC_AgenticAI_TeamPack_v3"
DEFAULT_WORKBOOK_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "input"
    / "MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx"
)


@dataclass(frozen=True)
class AppSettings:
    """Configuration resolved by the interface composition root."""

    team_pack_path: Path
    dataset_id: str
    openai_enabled: bool
    openai_api_key: str | None
    openai_model: str
    openai_timeout_seconds: float
    openai_max_retries: int
    finance_prompt_version: str
    finance_prompt_path: Path

    @classmethod
    def from_environment(cls) -> "AppSettings":
        """Build settings without exposing file paths in the public API."""
        return cls(
            team_pack_path=Path(getenv("OPC_MIS_TEAM_PACK_PATH", str(DEFAULT_WORKBOOK_PATH))),
            dataset_id=getenv("OPC_MIS_DATASET_ID", DEFAULT_DATASET_ID),
            openai_enabled=getenv("OPENAI_ENABLED", "false").strip().casefold()
            in {"1", "true", "yes", "on"},
            openai_api_key=getenv("OPENAI_API_KEY") or None,
            openai_model=getenv("OPENAI_MODEL", "gpt-5.6-terra"),
            openai_timeout_seconds=float(getenv("OPENAI_TIMEOUT_SECONDS", "12")),
            openai_max_retries=int(getenv("OPENAI_MAX_RETRIES", "1")),
            finance_prompt_version=getenv("FINANCE_PROMPT_VERSION", "finance-narrative-v1"),
            finance_prompt_path=Path(
                getenv(
                    "FINANCE_PROMPT_PATH",
                    str(
                        Path(__file__).resolve().parents[2]
                        / "config"
                        / "prompts"
                        / "finance_narrative.md"
                    ),
                )
            ),
        )
