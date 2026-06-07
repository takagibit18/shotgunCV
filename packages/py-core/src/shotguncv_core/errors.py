from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ErrorClassification:
    status_kind: str
    error_code: str


class ModelProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        category: str = "model_error",
        provider: str = "",
        model: str = "",
        status_code: int | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.category = category
        self.provider = provider
        self.model = model
        self.status_code = status_code


class ParseInputError(ValueError):
    code = "PARSE_INPUT_INVALID"
    category = "parse_error"


class StructuredAnalysisError(ValueError):
    code = "STRUCTURED_ANALYSIS_INVALID"
    category = "model_error"


def classify_error(error: Exception) -> ErrorClassification:
    code = str(getattr(error, "code", "") or error.__class__.__name__)
    category = str(getattr(error, "category", "") or "")
    if category in {"config_error", "model_error", "parse_error"}:
        return ErrorClassification(status_kind=category, error_code=code)
    if isinstance(error, (ParseInputError,)):
        return ErrorClassification(status_kind="parse_error", error_code=code)
    if isinstance(error, StructuredAnalysisError):
        return ErrorClassification(status_kind="model_error", error_code=code)
    return ErrorClassification(status_kind="failed", error_code=code)
