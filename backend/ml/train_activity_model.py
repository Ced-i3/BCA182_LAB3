"""Train a small walking/running Decision Tree from Run-or-Walk CSV data."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.tree import DecisionTreeClassifier


ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "archive" / "dataset.csv"
MODEL_DIR = ROOT / "models"
MODEL_PATH = MODEL_DIR / "activity_decision_tree.joblib"
CONFIG_PATH = MODEL_DIR / "activity_preprocessing.json"
REPORT_PATH = Path(__file__).resolve().parent / "training_report.md"

AXES = (
    "acceleration_x",
    "acceleration_y",
    "acceleration_z",
    "gyro_x",
    "gyro_y",
    "gyro_z",
)
STATISTICS = ("mean", "std", "min", "max")
FEATURE_NAMES = [f"{axis}_{stat}" for axis in AXES for stat in STATISTICS]

# Fixed before model selection; each date belongs to exactly one split.
DATE_SPLITS = {
    "train": [
        "2017-6-30",
        "2017-7-2",
        "2017-7-4",
        "2017-7-6",
        "2017-7-7",
        "2017-7-9",
        "2017-7-10",
        "2017-7-11",
    ],
    "validation": ["2017-7-15", "2017-7-16"],
    "test": ["2017-7-1", "2017-7-17"],
}

WINDOW_SAMPLES = 10
WINDOW_STRIDE = 5
EXPECTED_SAMPLE_RATE_HZ = 5.0
MAX_GAP_SECONDS = 0.6
RANDOM_STATE = 42
CANDIDATE_DEPTHS = (2, 3, 4, 5, 6, 8, 10)


def make_feature_row(values: np.ndarray) -> np.ndarray:
    """Return mean, population std, min and max for each axis in fixed order."""
    per_axis = np.stack(
        (
            values.mean(axis=0),
            values.std(axis=0, ddof=0),
            values.min(axis=0),
            values.max(axis=0),
        ),
        axis=1,
    )
    return per_axis.reshape(-1)


def build_windows(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Segment on date/wrist/activity/gaps, then make overlapping sample windows."""
    frame = frame.sort_values(["date", "wrist", "timestamp"], kind="stable").copy()
    frame["_interval"] = frame.groupby(["date", "wrist"], sort=False)[
        "timestamp"
    ].diff().dt.total_seconds()

    starts_new_segment = (
        frame["_interval"].isna()
        | (frame["_interval"] <= 0)
        | (frame["_interval"] > MAX_GAP_SECONDS)
        | frame["date"].ne(frame["date"].shift())
        | frame["wrist"].ne(frame["wrist"].shift())
        | frame["activity"].ne(frame["activity"].shift())
    )
    frame["_segment"] = starts_new_segment.cumsum()

    records: list[dict[str, object]] = []
    segment_count = 0
    for _, segment in frame.groupby("_segment", sort=False):
        segment_count += 1
        sensor_values = segment.loc[:, AXES].to_numpy(dtype=np.float64)
        if len(sensor_values) < WINDOW_SAMPLES:
            continue

        label = int(segment["activity"].iloc[0])
        date = str(segment["date"].iloc[0])
        wrist = int(segment["wrist"].iloc[0])
        timestamps = segment["timestamp"].to_numpy()
        for start in range(0, len(segment) - WINDOW_SAMPLES + 1, WINDOW_STRIDE):
            stop = start + WINDOW_SAMPLES
            row: dict[str, object] = {
                "date": date,
                "wrist": wrist,
                "label": label,
                "start_time": str(timestamps[start]),
                "end_time": str(timestamps[stop - 1]),
                "elapsed_seconds": float(
                    (timestamps[stop - 1] - timestamps[start])
                    / np.timedelta64(1, "s")
                ),
            }
            row.update(dict(zip(FEATURE_NAMES, make_feature_row(sensor_values[start:stop]))))
            records.append(row)

    windows = pd.DataFrame.from_records(records)
    if windows.empty:
        raise ValueError("No windows were produced; check the data and window settings.")
    return windows, segment_count


def metric_values(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, object]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_running": float(
            precision_score(y_true, y_pred, pos_label=1, zero_division=0)
        ),
        "recall_running": float(recall_score(y_true, y_pred, pos_label=1, zero_division=0)),
        "f1_running": float(f1_score(y_true, y_pred, pos_label=1, zero_division=0)),
        "confusion_matrix_walk_run": confusion_matrix(
            y_true, y_pred, labels=[0, 1]
        ).tolist(),
    }


def format_metrics(metrics: dict[str, object]) -> str:
    matrix = metrics["confusion_matrix_walk_run"]
    return (
        f"Accuracy {metrics['accuracy']:.4f}; "
        f"precision (running) {metrics['precision_running']:.4f}; "
        f"recall (running) {metrics['recall_running']:.4f}; "
        f"F1 (running) {metrics['f1_running']:.4f}; "
        f"confusion matrix [[TN, FP], [FN, TP]] = {matrix}"
    )


def main() -> None:
    if not DATASET_PATH.is_file():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    frame = pd.read_csv(DATASET_PATH)
    required = {"date", "time", "wrist", "activity", *AXES}
    missing_columns = sorted(required - set(frame.columns))
    if missing_columns:
        raise ValueError(f"Dataset is missing required columns: {missing_columns}")
    if frame[list(required)].isna().any().any():
        raise ValueError("Required dataset columns contain missing values.")
    if set(frame["activity"].unique()) != {0, 1}:
        raise ValueError("Expected activity labels 0 (walking) and 1 (running).")
    if not np.isfinite(frame.loc[:, AXES].to_numpy(dtype=np.float64)).all():
        raise ValueError("Sensor columns contain non-finite values.")

    frame["timestamp"] = pd.to_datetime(
        frame["date"] + " " + frame["time"],
        format="%Y-%m-%d %H:%M:%S:%f",
        errors="raise",
    )
    available_dates = set(frame["date"].unique())
    assigned_dates = [date for dates in DATE_SPLITS.values() for date in dates]
    if len(assigned_dates) != len(set(assigned_dates)):
        raise ValueError("A recording date appears in more than one split.")
    if set(assigned_dates) != available_dates:
        raise ValueError("Date split does not cover the dataset exactly.")

    windows, segment_count = build_windows(frame)
    split_frames = {
        name: windows[windows["date"].isin(dates)].reset_index(drop=True)
        for name, dates in DATE_SPLITS.items()
    }
    for name, split_frame in split_frames.items():
        if split_frame.empty or set(split_frame["label"].unique()) != {0, 1}:
            raise ValueError(f"The {name} split must contain windows from both classes.")

    x_train = split_frames["train"].loc[:, FEATURE_NAMES].to_numpy(dtype=np.float64)
    y_train = split_frames["train"]["label"].to_numpy(dtype=np.int64)
    x_validation = split_frames["validation"].loc[:, FEATURE_NAMES].to_numpy(
        dtype=np.float64
    )
    y_validation = split_frames["validation"]["label"].to_numpy(dtype=np.int64)

    # Validation alone selects depth. A tied score selects the shallower tree.
    validation_scores: list[tuple[float, int]] = []
    for depth in CANDIDATE_DEPTHS:
        candidate = DecisionTreeClassifier(max_depth=depth, random_state=RANDOM_STATE)
        candidate.fit(x_train, y_train)
        prediction = candidate.predict(x_validation)
        validation_scores.append(
            (float(f1_score(y_validation, prediction, average="macro")), depth)
        )
    best_validation_f1, best_depth = max(
        validation_scores, key=lambda item: (item[0], -item[1])
    )

    model = DecisionTreeClassifier(max_depth=best_depth, random_state=RANDOM_STATE)
    model.fit(x_train, y_train)

    train_counts = Counter(int(x) for x in y_train)
    # In a tie, choose walking (0) deterministically.
    majority_label = min((0, 1), key=lambda label: (-train_counts[label], label))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)

    observed_dt = frame.sort_values(["date", "wrist", "timestamp"], kind="stable")
    intervals = observed_dt.groupby(["date", "wrist"], sort=False)[
        "timestamp"
    ].diff().dt.total_seconds()
    positive_intervals = intervals[intervals > 0]
    median_interval = float(positive_intervals.median())

    config = {
        "model_type": "sklearn.tree.DecisionTreeClassifier",
        "model_file": MODEL_PATH.name,
        "feature_order": FEATURE_NAMES,
        "sensor_axes": list(AXES),
        "statistics": list(STATISTICS),
        "standard_deviation": "population (ddof=0)",
        "label_mapping": {"0": "walking", "1": "running"},
        "window": {
            "samples": WINDOW_SAMPLES,
            "stride_samples": WINDOW_STRIDE,
            "nominal_sample_rate_hz": EXPECTED_SAMPLE_RATE_HZ,
            "nominal_duration_seconds": WINDOW_SAMPLES / EXPECTED_SAMPLE_RATE_HZ,
            "observed_median_interval_seconds": median_interval,
            "max_within_segment_gap_seconds": MAX_GAP_SECONDS,
        },
        "preprocessing": {
            "timestamp_format": "%Y-%m-%d %H:%M:%S:%f",
            "sort_order": ["date", "wrist", "timestamp"],
            "start_new_segment_on": [
                "date change",
                "wrist change",
                "activity change",
                "non-positive timestamp interval",
                f"timestamp gap > {MAX_GAP_SECONDS} seconds",
            ],
            "overlap": "50 percent",
            "acceleration_unit": "unverified raw dataset values; no conversion applied",
            "gyroscope_unit": "unverified raw dataset values; no conversion applied",
        },
        "date_splits": DATE_SPLITS,
        "training": {
            "max_depth_candidates": list(CANDIDATE_DEPTHS),
            "selection_metric": "validation macro F1; ties choose shallower depth",
            "selected_max_depth": best_depth,
            "random_state": RANDOM_STATE,
        },
        "dataset": {
            "relative_path": "data/archive/dataset.csv",
            "rows": int(len(frame)),
            "date_count": int(frame["date"].nunique()),
            "participant_count": int(frame["username"].nunique())
            if "username" in frame.columns
            else None,
        },
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    # Reload from disk and use this loaded artifact for the untouched test set.
    loaded_model = joblib.load(MODEL_PATH)
    x_test = split_frames["test"].loc[:, FEATURE_NAMES].to_numpy(dtype=np.float64)
    y_test = split_frames["test"]["label"].to_numpy(dtype=np.int64)
    test_predictions = loaded_model.predict(x_test)
    reload_predictions_match = np.array_equal(test_predictions, model.predict(x_test))
    if not reload_predictions_match:
        raise RuntimeError("Reloaded model predictions differ from the trained model.")

    baseline_predictions = np.full_like(y_test, majority_label)
    model_metrics = metric_values(y_test, test_predictions)
    baseline_metrics = metric_values(y_test, baseline_predictions)

    split_summaries = {}
    for name, split_frame in split_frames.items():
        counts = split_frame["label"].value_counts().to_dict()
        split_summaries[name] = {
            "dates": DATE_SPLITS[name],
            "windows": len(split_frame),
            "walking": int(counts.get(0, 0)),
            "running": int(counts.get(1, 0)),
        }

    validation_lines = [
        f"| {depth} | {score:.4f} |" for score, depth in sorted(validation_scores, key=lambda x: x[1])
    ]
    split_lines = [
        f"| {name} | {', '.join(summary['dates'])} | {summary['windows']} | "
        f"{summary['walking']} | {summary['running']} |"
        for name, summary in split_summaries.items()
    ]
    report = f"""# Phase 2B Training Report

## Dataset and windows

- Source: `data/archive/dataset.csv`; {len(frame):,} rows, {frame['date'].nunique()} dates, one participant.
- Labels: 0 = walking, 1 = running. Raw row totals: {int((frame['activity'] == 0).sum()):,} walking and {int((frame['activity'] == 1).sum()):,} running.
- Missing values in required columns: 0. Sensor values are retained as recorded; acceleration and gyroscope units could not be verified from available provenance, so no unit conversion was applied.
- Observed median positive sample interval: {median_interval:.4f} s (about {1 / median_interval:.2f} Hz). Window: {WINDOW_SAMPLES} readings (nominal {WINDOW_SAMPLES / EXPECTED_SAMPLE_RATE_HZ:.1f} s at {EXPECTED_SAMPLE_RATE_HZ:.1f} Hz), stride {WINDOW_STRIDE} readings (50% overlap).
- A segment ends at a date, wrist, or activity change; a non-positive timestamp interval; or a gap over {MAX_GAP_SECONDS:.1f} s. Windows are formed only inside segments.
- Total contiguous segments: {segment_count:,}. Feature vector: 24 values (mean, population standard deviation, minimum, maximum for each of six axes).

## Date-grouped split

No date occurs in more than one split. The date lists were fixed before depth selection.

| Split | Dates | Windows | Walking | Running |
|---|---|---:|---:|---:|
{chr(10).join(split_lines)}

## Model selection and test results

Decision Tree with fixed `random_state={RANDOM_STATE}`. Maximum depth was selected using validation macro F1; the test set was not used for selection. Validation scores:

| Maximum depth | Validation macro F1 |
|---:|---:|
{chr(10).join(validation_lines)}

Selected maximum depth: **{best_depth}** (validation macro F1 {best_validation_f1:.4f}). The test-set majority baseline predicts **{'walking' if majority_label == 0 else 'running'}**, based on training windows.

- Decision Tree: {format_metrics(model_metrics)}
- Majority baseline: {format_metrics(baseline_metrics)}
- Confusion matrix rows are actual `[walking, running]`; columns are predicted `[walking, running]`.
- Saved-model reload/inference check: **{'passed' if reload_predictions_match else 'failed'}**; loaded model predictions matched the trained model on all {len(y_test):,} test windows.

## Limitations

- The dataset contains one participant. Date grouping helps prevent overlapping-window leakage across recording dates, but does not establish generalization to new people or RT-Spark hardware.
- Date is the only reliable recording-group metadata; separate sessions within a date are inferred from timestamps and metadata transitions.
- Sensor units and the exact original phone/sensor configuration are unverified. The saved model expects features in the same raw scale and axis orientation as this dataset. Before hardware integration, confirm the source units and calibrate/convert RT-Spark readings accordingly.
- Windows are sample-count based. The 2-second duration is nominal because sampling intervals vary; windows never bridge a gap over {MAX_GAP_SECONDS:.1f} s.
"""
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(f"Python packages: numpy={np.__version__}, pandas={pd.__version__}, scikit-learn={sklearn.__version__}, joblib={joblib.__version__}")
    print(f"Dataset rows: {len(frame)}; dates: {frame['date'].nunique()}; segments: {segment_count}")
    print(f"Median positive sample interval: {median_interval:.6f} s")
    for name, summary in split_summaries.items():
        print(
            f"{name}: windows={summary['windows']}, walking={summary['walking']}, "
            f"running={summary['running']}, dates={summary['dates']}"
        )
    print(f"Selected max_depth={best_depth}; validation macro F1={best_validation_f1:.4f}")
    print(f"Test Decision Tree: {format_metrics(model_metrics)}")
    print(f"Test majority baseline: {format_metrics(baseline_metrics)}")
    print(f"Reload/inference check: PASS ({len(y_test)} predictions match)")
    print(f"Model: {MODEL_PATH}")
    print(f"Configuration: {CONFIG_PATH}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
