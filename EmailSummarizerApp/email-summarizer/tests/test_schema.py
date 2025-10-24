from libs.schema.email_summary_v1 import EmailSummaryV1, example
import pytest

def test_example_validates():
    m = example()
    assert m.schema_version == "email_summary.v1"
    assert 0.0 <= m.confidence <= 1.0
    # round-trip
    data = m.model_dump()
    EmailSummaryV1(**data)

def test_invalid_date_rejected():
    bad = example().model_dump()
    bad["dates"] = ["not-a-date"]
    with pytest.raises(Exception):
        EmailSummaryV1(**bad)
