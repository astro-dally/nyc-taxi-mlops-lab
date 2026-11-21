# 007: What stays in the notebook vs what moves into the pipeline

Stage: S2 · Date: 2026-11-21 · Author: dally · Drafted by agent: yes

## Choice

Keep exploratory data analysis (EDA), error slice visualization, loss curve exploration, and one-off hyperparameter experiments in SageMaker notebooks (`notebooks/explore.ipynb`). Move feature transformations (`staging.trip_features`), automated model training (`LightGBMModel.fit`), holdout evaluation, contract validation, and MLflow model registration/aliasing (`challenger`) into the automated Dagster pipeline.

## Rejected alternative

Allowing data scientists to train, evaluate, and directly register models or set aliases in MLflow from the SageMaker notebook environment.

## Why

Notebooks are interactive and ideal for fast experimentation and visual debugging, but state in notebooks can easily drift (hidden global state, out-of-order execution, uncommitted code). Moving feature generation, model training, evaluation, and promotion gates into Dagster ensures reproducibility, version-controlled execution, automated CI/CD validation, and strict adherence to frozen schema contracts without human error.

## What would show this was wrong

If hyperparameter iteration in the pipeline is too slow to support routine model improvements, or if pipeline runs become so expensive that rapid iteration requires lightweight local training loops before committing to Dagster assets.
