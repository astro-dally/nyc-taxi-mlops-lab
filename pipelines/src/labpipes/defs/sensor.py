"""S1: the S3 sensor (and the job it starts).

Watch trips/ in the data bucket (DataBucket.trip_files). When a month's file appears or changes, add
the month to the trip_months partitions and request a run that goes from trip_files to zone_hour_stats.
"""

import json

import dagster as dg

from ..partitions import trip_months
from ..resources import DataBucket
from .features import trip_features
from .marts import zone_hour_stats
from .raw_trips import raw_trips
from .staging import stg_trips
from .trip_files import trip_files

ingest_month = dg.define_asset_job(
    "ingest_month",
    selection=dg.AssetSelection.assets(trip_files, raw_trips, stg_trips, zone_hour_stats, trip_features),
    description="Ingest one month of trip data: trip_files -> raw_trips -> stg_trips -> zone_hour_stats, trip_features.",
)


@dg.sensor(
    job=ingest_month,
    name="trip_files_sensor",
    minimum_interval_seconds=60,
    description="Watches trips/ in the data bucket and launches ingest_month when a file lands or updates.",
)
def trip_files_sensor(context: dg.SensorEvaluationContext, data_bucket: DataBucket):
    cursor: dict[str, str] = json.loads(context.cursor or "{}")
    files = data_bucket.trip_files()

    new_or_changed = []
    new_partitions = []
    for f in files:
        if f.month not in cursor:
            new_partitions.append(f.month)
            new_or_changed.append(f)
        elif cursor[f.month] != f.etag:
            new_or_changed.append(f)

    if not new_or_changed:
        return dg.SkipReason("No new or changed trip files")

    new_cursor = {**cursor, **{f.month: f.etag for f in new_or_changed}}

    return dg.SensorResult(
        run_requests=[dg.RunRequest(partition_key=f.month, run_key=f"{f.month}:{f.etag}") for f in new_or_changed],
        dynamic_partitions_requests=[trip_months.build_add_request(new_partitions)] if new_partitions else [],
        cursor=json.dumps(new_cursor),
    )
