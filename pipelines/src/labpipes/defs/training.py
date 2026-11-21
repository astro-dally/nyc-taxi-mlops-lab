"""S2: training_set, trained_model, eval_report, the challenger gate and the challenger asset.

- training_set: UNLOAD a window of staging.trip_features (and the holdout month) to the artifact bucket.
  The zone-pair distance lookup (contracts/features.yaml, est_distance_miles) comes from the window only.
- trained_model: fit tripmodel.LightGBMModel (the given v2), log it to MLflow as a pyfunc with
  tripmodel.model_signature() and the tripmodel package bundled, register a version of the model named
  in contracts/mlflow.yaml, and tag it as that contract says.
- eval_report: tripmodel.evaluate the new version and the champion (or the v1 baseline before there is
  one) on the same holdout; log the metrics.
- A blocking check that guards a `challenger` asset, which sets the alias. The pipeline never moves
  `champion`.
"""

import os
from pathlib import Path

import dagster as dg
import mlflow
import mlflow.pyfunc

import tripmodel
from tripmodel import BaselineModel, LightGBMModel, evaluate, model_signature

from ..contracts import features_contract, mlflow_contract
from ..resources import ArtifactBucket, MlflowTracking, RedshiftData
from .features import trip_features

TRAINING_WINDOW = "2024-01..2024-03"
TRAINING_MONTHS = ["2024-01", "2024-02", "2024-03"]
HOLDOUT_MONTH = "2024-04"
REQUIRED_MARGIN_MIN = 0.05
MAX_P95_LATENCY_MS = 20.0


@dg.asset(
    deps=[trip_features],
    group_name="training",
    kinds={"redshift", "s3"},
    pool="redshift",
    description="UNLOADs training window (2024-01..03) and holdout month (2024-04) from staging.trip_features to S3, plus computes distance lookup.",
)
def training_set(redshift: RedshiftData, artifacts: ArtifactBucket) -> dg.MaterializeResult:
    months_clause = ", ".join(f"''{m}''" for m in TRAINING_MONTHS)
    train_uri = artifacts.uri("training/train/")
    holdout_uri = artifacts.uri("training/holdout/")
    dist_uri = artifacts.uri("training/distances/")

    train_unload = (
        f"unload ('select pickup_zone_id, dropoff_zone_id, pickup_hour, pickup_dow, duration_min "
        f"from staging.trip_features where trip_month in ({months_clause})') "
        f"to '{train_uri}' iam_role default format as parquet cleanpath"
    )
    holdout_unload = (
        f"unload ('select pickup_zone_id, dropoff_zone_id, pickup_hour, pickup_dow, duration_min "
        f"from staging.trip_features where trip_month in (\'\'{HOLDOUT_MONTH}\'\')') "
        f"to '{holdout_uri}' iam_role default format as parquet cleanpath"
    )
    dist_unload = (
        f"unload ('select pickup_zone_id, dropoff_zone_id, median(trip_distance) as est_distance_miles "
        f"from staging.stg_trips where trip_month in ({months_clause}) and trip_distance > 0 and trip_distance < 100 "
        f"and pickup_zone_id between 1 and 263 and dropoff_zone_id between 1 and 263 group by 1, 2') "
        f"to '{dist_uri}' iam_role default format as parquet cleanpath"
    )

    redshift.execute(train_unload, holdout_unload, dist_unload)

    return dg.MaterializeResult(
        metadata={
            "training_window": dg.MetadataValue.text(TRAINING_WINDOW),
            "holdout_month": dg.MetadataValue.text(HOLDOUT_MONTH),
            "train_uri": dg.MetadataValue.text(train_uri),
            "holdout_uri": dg.MetadataValue.text(holdout_uri),
            "distances_uri": dg.MetadataValue.text(dist_uri),
        }
    )


@dg.asset(
    deps=[training_set],
    group_name="training",
    kinds={"mlflow"},
    description="Fits LightGBM v2 model on the training window and registers it in MLflow with required tags.",
)
def trained_model(artifacts: ArtifactBucket, tracking: MlflowTracking) -> dg.MaterializeResult:
    train = artifacts.read_parquet("training/train")
    distances = artifacts.read_parquet("training/distances")

    # Fit LightGBM model
    model = LightGBMModel().fit(train, distances, num_rounds=300)

    client = tracking.client()
    contract = mlflow_contract()
    exp_name = contract["experiment"]
    model_name = contract["registered_model"]
    git_sha = os.environ.get("GIT_SHA", "unknown")
    features_ver = str(features_contract().get("version", 1))

    mlflow.set_tracking_uri(tracking.tracking_uri)
    mlflow.set_experiment(exp_name)

    with mlflow.start_run(run_name="train_model") as run:
        mlflow.log_params({
            "num_rounds": 300,
            "training_window": TRAINING_WINDOW,
            "holdout_month": HOLDOUT_MONTH,
            "features_version": features_ver,
        })
        info = mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=model,
            signature=model_signature(),
            code_paths=[str(Path(tripmodel.__file__).parent)],
            registered_model_name=model_name,
        )
        run_id = run.info.run_id

    version = str(info.registered_model_version)

    # Apply version tags required by contracts/mlflow.yaml
    for tag, val in [
        ("training_window", TRAINING_WINDOW),
        ("holdout_month", HOLDOUT_MONTH),
        ("features_version", features_ver),
        ("git_sha", git_sha),
    ]:
        client.set_model_version_tag(model_name, version, tag, str(val))

    artifacts.write_json("training/latest_version.json", {"version": version, "run_id": run_id})

    return dg.MaterializeResult(
        metadata={
            "registered_model": dg.MetadataValue.text(model_name),
            "model_version": dg.MetadataValue.text(version),
            "run_id": dg.MetadataValue.text(run_id),
        }
    )


@dg.asset(
    deps=[trained_model],
    group_name="training",
    kinds={"mlflow"},
    description="Evaluates candidate model against champion/baseline on holdout data and records metrics.",
)
def eval_report(artifacts: ArtifactBucket, tracking: MlflowTracking, redshift: RedshiftData) -> dg.MaterializeResult:
    holdout = artifacts.read_parquet("training/holdout")
    train = artifacts.read_parquet("training/train")
    distances = artifacts.read_parquet("training/distances")
    zones_data = redshift.query("select location_id, borough from ingest.taxi_zones")
    boroughs = {row["location_id"]: row["borough"] for row in zones_data}

    ver_info = artifacts.read_json("training/latest_version.json")
    version = ver_info["version"]
    run_id = ver_info["run_id"]

    client = tracking.client()
    contract = mlflow_contract()
    model_name = contract["registered_model"]
    exp_name = contract["experiment"]

    mlflow.set_tracking_uri(tracking.tracking_uri)
    mlflow.set_experiment(exp_name)

    # 1. Evaluate candidate
    cand_uri = f"models:/{model_name}/{version}"
    candidate = mlflow.pyfunc.load_model(cand_uri)
    cand_metrics = evaluate(candidate.predict, holdout, boroughs)

    # 2. Evaluate champion (or v1 baseline if no champion exists)
    try:
        champ = mlflow.pyfunc.load_model(f"models:/{model_name}@champion")
        champ_metrics = evaluate(champ.predict, holdout, boroughs)
        champion_mae = champ_metrics["mae_min"]
        baseline_name = "champion"
    except Exception:
        baseline = BaselineModel().fit(train, distances)
        base_metrics = evaluate(lambda df: baseline.predict(None, df), holdout, boroughs)
        champion_mae = base_metrics["mae_min"]
        baseline_name = "baseline_v1"

    # 3. Log metrics to the training run in MLflow
    with mlflow.start_run(run_id=run_id):
        mlflow.log_metric("mae_min", cand_metrics["mae_min"])
        mlflow.log_metric("p95_latency_ms", cand_metrics["p95_latency_ms"])
        mlflow.log_metric("champion_mae_min", champion_mae)
        for k in ("airport", "manhattan", "outer", "night"):
            if f"mae_min.{k}" in cand_metrics:
                mlflow.log_metric(f"mae_min.{k}", cand_metrics[f"mae_min.{k}"])

    # 4. Copy metrics to model version tags as required by contracts/mlflow.yaml
    client.set_model_version_tag(model_name, version, "mae_min", f"{cand_metrics['mae_min']:.4f}")
    client.set_model_version_tag(model_name, version, "p95_latency_ms", f"{cand_metrics['p95_latency_ms']:.2f}")
    client.set_model_version_tag(model_name, version, "champion_mae_min", f"{champion_mae:.4f}")

    report = {
        "version": version,
        "run_id": run_id,
        "mae_min": cand_metrics["mae_min"],
        "champion_mae_min": champion_mae,
        "p95_latency_ms": cand_metrics["p95_latency_ms"],
        "comparison_baseline": baseline_name,
    }
    artifacts.write_json("training/eval_report.json", report)

    return dg.MaterializeResult(
        metadata={
            "version": dg.MetadataValue.text(version),
            "mae_min": dg.MetadataValue.float(cand_metrics["mae_min"]),
            "champion_mae_min": dg.MetadataValue.float(champion_mae),
            "p95_latency_ms": dg.MetadataValue.float(cand_metrics["p95_latency_ms"]),
            "comparison": dg.MetadataValue.text(baseline_name),
        }
    )


@dg.asset_check(
    asset=eval_report,
    name="beats_champion",
    blocking=True,
    description="Blocking check: candidate MAE must beat champion/baseline by margin, and p95 latency must be under SLA.",
)
def beats_champion(artifacts: ArtifactBucket) -> dg.AssetCheckResult:
    report = artifacts.read_json("training/eval_report.json")
    mae = float(report["mae_min"])
    champ_mae = float(report["champion_mae_min"])
    latency = float(report["p95_latency_ms"])

    improved = (mae <= (champ_mae - REQUIRED_MARGIN_MIN))
    latency_ok = (latency <= MAX_P95_LATENCY_MS)
    passed = improved and latency_ok

    desc = (
        f"Passed: MAE {mae:.4f} <= {champ_mae:.4f} - {REQUIRED_MARGIN_MIN:.2f}, "
        f"latency {latency:.1f}ms <= {MAX_P95_LATENCY_MS:.1f}ms"
        if passed
        else f"Failed: MAE {mae:.4f} vs champion {champ_mae:.4f} (margin {REQUIRED_MARGIN_MIN}), latency {latency:.1f}ms"
    )

    return dg.AssetCheckResult(
        passed=passed,
        severity=dg.AssetCheckSeverity.ERROR,
        description=desc,
        metadata={
            "mae_min": dg.MetadataValue.float(mae),
            "champion_mae_min": dg.MetadataValue.float(champ_mae),
            "margin_min": dg.MetadataValue.float(REQUIRED_MARGIN_MIN),
            "p95_latency_ms": dg.MetadataValue.float(latency),
            "latency_sla_ms": dg.MetadataValue.float(MAX_P95_LATENCY_MS),
        },
    )


@dg.asset(
    deps=[eval_report],
    group_name="training",
    kinds={"mlflow"},
    description="Promotes candidate version to challenger alias in MLflow when beats_champion passes.",
)
def challenger(artifacts: ArtifactBucket, tracking: MlflowTracking) -> dg.MaterializeResult:
    report = artifacts.read_json("training/eval_report.json")
    version = report["version"]
    client = tracking.client()
    contract = mlflow_contract()
    model_name = contract["registered_model"]

    client.set_registered_model_alias(model_name, "challenger", version)

    return dg.MaterializeResult(
        metadata={
            "registered_model": dg.MetadataValue.text(model_name),
            "alias": dg.MetadataValue.text("challenger"),
            "version": dg.MetadataValue.text(version),
        }
    )


train_model = dg.define_asset_job(
    "train_model",
    selection=dg.AssetSelection.assets(training_set, trained_model, eval_report, challenger),
    description="Train model: training_set -> trained_model -> eval_report (beats_champion gate) -> challenger.",
)
