from enum import StrEnum


class SourceType(StrEnum):
    MARKET_DATA = "market_data"
    FINANCIAL_NEWS = "financial_news"
    SEC_FILING = "sec_filing"
    FIXTURE = "fixture"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    PERMANENT_FAILURE = "permanent_failure"


class CollectionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class FailureKind(StrEnum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"


class EventType(StrEnum):
    EARNINGS = "earnings"
    GUIDANCE = "guidance"
    DIVIDEND = "dividend"
    MANAGEMENT_CHANGE = "management_change"
    MERGER_ACQUISITION = "merger_acquisition"
    REGULATORY = "regulatory"
    OTHER = "other"


class InferenceStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
