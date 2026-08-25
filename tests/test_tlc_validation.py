import duckdb

from ridepulse.ingestion.tlc import EXPECTED_SCHEMA, ValidationResult, validate_file


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


def _write_minimal_fixture(tmp_path, pu_location_type: str):
    """A one-row file with every EXPECTED_SCHEMA column, PULocationID/
    DOLocationID cast to the given type -- lets the BIGINT-widening test
    exercise validate_file() against a real file, not a hand-built dataclass."""
    con = duckdb.connect()
    select_cols = []
    for col, dtype in EXPECTED_SCHEMA.items():
        if col in ("PULocationID", "DOLocationID"):
            select_cols.append(f"CAST(1 AS {pu_location_type}) AS \"{col}\"")
        elif dtype == "VARCHAR":
            select_cols.append(f"'x' AS \"{col}\"")
        elif dtype == "TIMESTAMP":
            select_cols.append(f"TIMESTAMP '2024-01-01 00:00:00' AS \"{col}\"")
        else:
            select_cols.append(f"CAST(1 AS {dtype}) AS \"{col}\"")
    path = tmp_path / "fixture.parquet"
    con.execute(f"COPY (SELECT {', '.join(select_cols)}) TO '{path}' (FORMAT PARQUET)")
    return path


def test_bigint_location_id_is_accepted_as_a_compatible_widening(tmp_path):
    # Found in the wild: 2023-01's real file has PULocationID/DOLocationID as
    # BIGINT while every other month checked has INTEGER. DuckDB itself
    # promotes across a glob spanning both without loss, so this must not
    # be treated as a schema failure.
    path = _write_minimal_fixture(tmp_path, "BIGINT")
    result = validate_file(path, month="2023-01")
    assert result.schema_ok
    assert result.schema_diff == {}


def test_a_genuinely_incompatible_type_still_fails(tmp_path):
    # sanity check that the widening allowance doesn't turn into a blanket
    # "ignore schema drift" -- an unrelated wrong type must still fail.
    good_path = _write_minimal_fixture(tmp_path, "INTEGER")
    bad_path = tmp_path / "bad_fixture.parquet"
    con = duckdb.connect()
    con.execute(f"""
        COPY (SELECT * REPLACE ('9.9' AS trip_miles) FROM read_parquet('{good_path}'))
        TO '{bad_path}' (FORMAT PARQUET)
    """)
    result = validate_file(bad_path, month="2024-01")
    assert not result.schema_ok
    assert "trip_miles" in result.schema_diff
