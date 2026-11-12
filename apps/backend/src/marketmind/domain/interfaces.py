from collections.abc import Sequence
from typing import Protocol

from marketmind.domain.entities import InferenceRequest, InferenceResult, RawRecordInput


class MarketDataCollector(Protocol):
    def collect(self, symbols: Sequence[str]) -> Sequence[RawRecordInput]: ...


class FinancialNewsCollector(Protocol):
    def collect(self, symbols: Sequence[str]) -> Sequence[RawRecordInput]: ...


class SecFilingCollector(Protocol):
    def collect(self, ciks: Sequence[str]) -> Sequence[RawRecordInput]: ...


class InferenceGateway(Protocol):
    """Replaceable boundary; M0A deliberately provides no implementation."""

    def infer(self, request: InferenceRequest) -> InferenceResult: ...
