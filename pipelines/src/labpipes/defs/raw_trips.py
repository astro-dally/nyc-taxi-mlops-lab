"""S1: the raw_trips asset.

One partition per month (partitions.trip_months), depending on trip_files. COPY the month's file into
Redshift with the LabRole attached to the cluster (`iam_role default`), so that re-running a month never
duplicates its rows. The landing columns come from contracts/trips.schema.yaml
(contracts.redshift_columns).
"""

import dagster as dg

from ..contracts import redshift_columns, trips_schema
from ..partitions import source_file, trip_months
from ..resources import DataBucket, RedshiftData
from .trip_files import trip_files


@dg.asset(
    partitions_def=trip_months,
    deps=[trip_files],
    group_name="ingest",
    kinds={"redshift"},
    pool="redshift",
)
def raw_trips(context: dg.AssetExecutionContext, redshift: RedshiftData, data_bucket: DataBucket) -> dg.MaterializeResult:
    month = context.partition_key
    file = source_file(month)
    s3_uri = data_bucket.trip_uri(month)
    cols_ddl = redshift_columns(trips_schema())

    # Load via temporary staging table so Parquet positional mapping is clean,
    # then atomically swap into ingest.raw_trips with source_file populated.
    redshift.execute(
        "create schema if not exists ingest",
        f"create table if not exists ingest.raw_trips (source_file varchar(64) not null, {cols_ddl}) "
        "sortkey (tpep_pickup_datetime)",
        f"create temp table raw_stage ({cols_ddl})",
        f"copy raw_stage from '{s3_uri}' iam_role default format as parquet",
        f"delete from ingest.raw_trips where source_file = '{file}'",
        f"insert into ingest.raw_trips select '{file}', * from raw_stage",
    )

    rows = redshift.scalar(f"select count(*) from ingest.raw_trips where source_file = '{file}'")
    return dg.MaterializeResult(
        metadata={
            "source_file": file,
            "rows": dg.MetadataValue.int(int(rows)),
            "s3_uri": s3_uri,
        }
    )
