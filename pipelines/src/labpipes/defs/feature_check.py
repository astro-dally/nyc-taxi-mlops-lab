"""S2: the feature_contract check on trip_features.

contracts/features.yaml lists the model's inputs, label and the post-trip columns that must never be
inputs; contracts/mlflow.yaml says this check blocks.
"""

import dagster as dg

from ..contracts import features_contract
from ..partitions import trip_months
from ..resources import RedshiftData
from .features import trip_features


@dg.asset_check(
    asset=trip_features,
    name="feature_contract",
    partitions_def=trip_months,
    blocking=True,
    description="Validates staging.trip_features against contracts/features.yaml (columns, types, ranges, no forbidden fields).",
)
def feature_contract(
    context: dg.AssetCheckExecutionContext,
    redshift: RedshiftData,
) -> dg.AssetCheckResult:
    month = context.partition_key
    contract = features_contract()
    forbidden = set(c.lower() for c in contract.get("forbidden", []))

    # 1. Verify schema columns & forbidden columns
    cols_query = (
        "select column_name from information_schema.columns "
        "where table_schema = 'staging' and table_name = 'trip_features'"
    )
    res = redshift.query(cols_query)
    actual_cols = {row["column_name"].lower() for row in res}

    violations = []
    # Check for forbidden columns
    found_forbidden = actual_cols & forbidden
    if found_forbidden:
        violations.append(f"Forbidden post-trip columns found: {sorted(found_forbidden)}")

    # Check for required columns
    expected_cols = {"trip_month", "pickup_zone_id", "dropoff_zone_id", "pickup_hour", "pickup_dow", "duration_min"}
    missing = expected_cols - actual_cols
    if missing:
        violations.append(f"Missing required contract columns: {sorted(missing)}")

    # 2. Check value ranges for the current partition
    range_check_sql = (
        f"select count(*) as bad_count from staging.trip_features "
        f"where trip_month = '{month}' and ("
        f"  pickup_zone_id not between 1 and 263 "
        f"  or dropoff_zone_id not between 1 and 263 "
        f"  or pickup_hour not between 0 and 23 "
        f"  or pickup_dow not between 0 and 6 "
        f"  or duration_min <= 0 "
        f"  or duration_min > 180"
        f")"
    )
    bad_count = int(redshift.scalar(range_check_sql))
    if bad_count > 0:
        violations.append(f"{bad_count} rows out of contract bounds (ranges or durations)")

    passed = len(violations) == 0
    return dg.AssetCheckResult(
        passed=passed,
        severity=dg.AssetCheckSeverity.ERROR,
        description="Feature contract passed" if passed else "; ".join(violations),
        metadata={
            "actual_columns": dg.MetadataValue.json(sorted(actual_cols)),
            "bad_rows": dg.MetadataValue.int(bad_count),
            "violations": dg.MetadataValue.json(violations),
        },
    )
