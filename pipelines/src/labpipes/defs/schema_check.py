"""S1: the schema_contract check on trip_files.

Compare the landed file's Parquet footer (the DataBucket resource reads it) with
contracts/trips.schema.yaml, before raw_trips copies anything. contracts/platform.yaml says this check
is blocking.
"""

import dagster as dg

from ..contracts import trips_schema
from ..partitions import trip_months
from ..resources import DataBucket
from .trip_files import trip_files


@dg.asset_check(
    asset=trip_files,
    name="schema_contract",
    partitions_def=trip_months,
    blocking=True,
    description="Parquet footer matches contracts/trips.schema.yaml (column count, types, case-insensitive names in order).",
)
def schema_contract(context: dg.AssetCheckExecutionContext, data_bucket: DataBucket) -> dg.AssetCheckResult:
    month = context.partition_key
    footer = data_bucket.footer(month)
    expected = trips_schema()

    mismatches = []
    if len(footer.columns) != len(expected):
        mismatches.append(f"column count mismatch: expected {len(expected)}, got {len(footer.columns)}")
    else:
        for i, (act, exp) in enumerate(zip(footer.columns, expected, strict=True)):
            if act.name.lower() != exp.name.lower():
                mismatches.append(f"col {i}: name mismatch: expected '{exp.name}', got '{act.name}'")
            if act.type != exp.type:
                mismatches.append(f"col {i} ({exp.name}): type mismatch: expected '{exp.type}', got '{act.type}'")

    passed = len(mismatches) == 0
    return dg.AssetCheckResult(
        passed=passed,
        severity=dg.AssetCheckSeverity.ERROR,
        description="Schema matches contract" if passed else "; ".join(mismatches),
        metadata={
            "expected_columns": dg.MetadataValue.int(len(expected)),
            "actual_columns": dg.MetadataValue.int(len(footer.columns)),
            "mismatches": dg.MetadataValue.json(mismatches),
        },
    )
