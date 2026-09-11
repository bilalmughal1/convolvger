from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RawSource(BaseModel):
    """Unparsed provider snapshot, before canonicalization."""

    model_config = ConfigDict(extra="forbid")

    url: str
    content: str
    content_type: str | None = None
    fetched_at: datetime | None = None
