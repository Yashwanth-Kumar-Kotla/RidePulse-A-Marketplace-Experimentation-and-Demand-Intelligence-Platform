from ridepulse.ingestion.tlc import ValidationResult


def make_result(**overrides) -> ValidationResult:
    defaults = {
        "month": "2024-01",
        "row_count": 1000,
        "schema_ok": True,
        "schema_diff": {},
        "null_violations": {},
        "timestamp_order_violations": 0,
        "duplicate_rows": 0,
    }
    defaults.update(overrides)
    return ValidationResult(**defaults)


def test_clean_file_is_ok():
    assert make_result().ok


def test_schema_drift_fails():
    assert not make_result(schema_ok=False, schema_diff={"trip_miles": {"expected": "DOUBLE", "got": "VARCHAR"}}).ok


def test_required_field_nulls_fail():
    assert not make_result(null_violations={"pickup_datetime": 5}).ok


def test_timestamp_violations_below_threshold_pass():
    # 0.95% observed in real pilot data; threshold is 2%.
    assert make_result(timestamp_order_violations=9).ok  # 0.9% of 1000


def test_timestamp_violations_above_threshold_fail():
    assert not make_result(timestamp_order_violations=30).ok  # 3% of 1000


def test_duplicate_rate_above_threshold_fails():
    assert not make_result(duplicate_rows=5).ok  # 0.5% of 1000, threshold is 0.1%


def test_empty_file_fails():
    assert not make_result(row_count=0).ok
