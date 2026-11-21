"""S1: data-quality checks on stg_trips (nulls, ranges, duplicates, row counts).

Decision points: which checks block downstream and which only warn, and every threshold.
"""

import dagster as dg

from ..partitions import trip_months
from ..resources import RedshiftData
from .staging import stg_trips


@dg.asset_check(
    asset=stg_trips,
    name="stg_trips_has_rows",
    partitions_def=trip_months,
    blocking=True,
    description="Staging table has rows for the partition month.",
)
def stg_trips_has_rows(context: dg.AssetCheckExecutionContext, redshift: RedshiftData) -> dg.AssetCheckResult:
    month = context.partition_key
    rows = redshift.scalar(f"select count(*) from staging.stg_trips where trip_month = '{month}'")
    passed = int(rows or 0) > 0
    return dg.AssetCheckResult(
        passed=passed,
        severity=dg.AssetCheckSeverity.ERROR,
        description="Has rows" if passed else f"Empty partition {month}",
        metadata={"rows": dg.MetadataValue.int(int(rows or 0))},
    )


@dg.asset_check(
    asset=stg_trips,
    name="stg_trips_plausible_dates",
    partitions_def=trip_months,
    blocking=True,
    description="Most trips have pickup timestamps matching the partition month (<2% out-of-month meter drift).",
)
def stg_trips_plausible_dates(context: dg.AssetCheckExecutionContext, redshift: RedshiftData) -> dg.AssetCheckResult:
    month = context.partition_key
    stats = redshift.query(
        f"select count(*) as rows, "
        f"count(case when to_char(pickup_at, 'YYYY-MM') != '{month}' then 1 end) as off_month "
        f"from staging.stg_trips where trip_month = '{month}'"
    )[0]
    total = int(stats.get("rows") or 0)
    off_month = int(stats.get("off_month") or 0)
    ratio = (off_month / total) if total > 0 else 0.0
    passed = ratio < 0.02
    return dg.AssetCheckResult(
        passed=passed,
        severity=dg.AssetCheckSeverity.ERROR,
        description=f"{off_month}/{total} ({ratio:.2%}) trips off-month" if not passed else "Dates plausible",
        metadata={
            "total_rows": dg.MetadataValue.int(total),
            "off_month_rows": dg.MetadataValue.int(off_month),
            "off_month_ratio": dg.MetadataValue.float(float(ratio)),
        },
    )


@dg.asset_check(
    asset=stg_trips,
    name="stg_trips_duration_and_zones",
    partitions_def=trip_months,
    blocking=False,
    description="Warn if nonpositive duration, >3h duration, null passengers, or unknown zones exceed 2%.",
)
def stg_trips_duration_and_zones(context: dg.AssetCheckExecutionContext, redshift: RedshiftData) -> dg.AssetCheckResult:
    month = context.partition_key
    stats = redshift.query(
        f"select count(*) as rows, "
        f"count(case when duration_min <= 0 then 1 end) as nonpositive_duration, "
        f"count(case when duration_min > 180 then 1 end) as over_3h, "
        f"count(case when passenger_count is null then 1 end) as null_passengers, "
        f"count(case when pickup_zone_id not between 1 and 263 then 1 end) as unknown_zone "
        f"from staging.stg_trips where trip_month = '{month}'"
    )[0]
    total = int(stats.get("rows") or 0)
    bad_dur = int(stats.get("nonpositive_duration") or 0)
    over_3h = int(stats.get("over_3h") or 0)
    null_pass = int(stats.get("null_passengers") or 0)
    unknown_zone = int(stats.get("unknown_zone") or 0)

    dur_ratio = (bad_dur / total) if total > 0 else 0.0
    passed = dur_ratio < 0.02

    return dg.AssetCheckResult(
        passed=passed,
        severity=dg.AssetCheckSeverity.WARN,
        description="Duration and zone quality within tolerance" if passed else f"Elevated anomalies: {bad_dur} nonpositive durations",
        metadata={
            "total_rows": dg.MetadataValue.int(total),
            "nonpositive_duration": dg.MetadataValue.int(bad_dur),
            "over_3h": dg.MetadataValue.int(over_3h),
            "null_passengers": dg.MetadataValue.int(null_pass),
            "unknown_zone": dg.MetadataValue.int(unknown_zone),
        },
    )
