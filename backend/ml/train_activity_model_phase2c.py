"""Corrected, label-independent window evaluation for Phase 2C."""

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
    precision_recall_fscore_support,
)
from sklearn.tree import DecisionTreeClassifier


BACKEND_DIR = Path(__file__).resolve().parents[1]
DATASET_PATH = BACKEND_DIR / "data" / "archive" / "dataset.csv"
MODEL_PATH = BACKEND_DIR / "models" / "activity_model_corrected.joblib"
CONFIG_PATH = BACKEND_DIR / "models" / "activity_preprocessing_corrected.json"
REPORT_PATH = Path(__file__).resolve().parent / "training_report_phase2c.md"

AXES = [
    "acceleration_x",
    "acceleration_y",
    "acceleration_z",
    "gyro_x",
    "gyro_y",
    "gyro_z",
]
STATISTICS = ["mean", "std", "min", "max"]
SIX_AXIS_FEATURES = [f"{axis}_{stat}" for axis in AXES for stat in STATISTICS]
MAGNITUDE_FEATURES = [f"{axis}_{stat}" for axis in ("acceleration_magnitude", "gyro_magnitude") for stat in STATISTICS]

# Keep the Phase 2B date groups unchanged. Dates remain the unit of separation.
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
NOMINAL_RATE_HZ = 5.0
MAX_GAP_SECONDS = 0.6
RANDOM_STATE = 42
DEPTH_CANDIDATES = (1, 2, 3, 4, 5, 6, 8, 10)


def statistics(values: np.ndarray) -> np.ndarray:
    """Four simple statistics, ordered mean/std/min/max."""
    return np.stack(
        (
            values.mean(axis=0),
            values.std(axis=0, ddof=0),
            values.min(axis=0),
            values.max(axis=0),
        ),
        axis=1,
    ).reshape(-1)


def build_windows(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Make windows without consulting activity labels for boundaries."""
    frame = frame.sort_values(["date", "wrist", "timestamp"], kind="stable").copy()
    frame["_interval"] = frame.groupby(["date", "wrist"], sort=False)[
        "timestamp"
    ].diff().dt.total_seconds()

    # Only timestamp continuity and known recording metadata define segments.
    starts_segment = (
        frame["_interval"].isna()
        | (frame["_interval"] <= 0)
        | (frame["_interval"] > MAX_GAP_SECONDS)
        | frame["date"].ne(frame["date"].shift())
        | frame["wrist"].ne(frame["wrist"].shift())
    )
    frame["_segment"] = starts_segment.cumsum()

    rows: list[dict[str, object]] = []
    segment_count = 0
    for _, segment in frame.groupby("_segment", sort=False):
        segment_count += 1
        values = segment[AXES].to_numpy(dtype=np.float64)
        labels = segment["activity"].to_numpy(dtype=np.int64)
        timestamps = segment["timestamp"].to_numpy()
        if len(values) < WINDOW_SAMPLES:
            continue

        for start in range(0, len(values) - WINDOW_SAMPLES + 1, WINDOW_STRIDE):
            stop = start + WINDOW_SAMPLES
            window_labels = labels[start:stop]
            counts = np.bincount(window_labels, minlength=2)
            mixed = bool(counts[0] and counts[1])
            tied = bool(counts[0] == counts[1])
            if tied:
                # Deterministic tie rule: label at the sixth (center-right) sample.
                label = int(window_labels[WINDOW_SAMPLES // 2])
            else:
                label = int(np.argmax(counts))

            window_values = values[start:stop]
            accel_magnitude = np.linalg.norm(window_values[:, :3], axis=1)
            gyro_magnitude = np.linalg.norm(window_values[:, 3:], axis=1)
            feature_values = statistics(window_values)
            magnitude_values = statistics(
                np.column_stack((accel_magnitude, gyro_magnitude))
            )

            row: dict[str, object] = {
                "date": str(segment["date"].iloc[0]),
                "wrist": int(segment["wrist"].iloc[0]),
                "label": label,
                "mixed_activity": mixed,
                "tie": tied,
                "walking_samples": int(counts[0]),
                "running_samples": int(counts[1]),
                "start_time": str(timestamps[start]),
                "end_time": str(timestamps[stop - 1]),
                "elapsed_seconds": float(
                    (timestamps[stop - 1] - timestamps[start])
                    / np.timedelta64(1, "s")
                ),
            }
            row.update(dict(zip(SIX_AXIS_FEATURES, feature_values)))
            row.update(dict(zip(MAGNITUDE_FEATURES, magnitude_values)))
            rows.append(row)

    windows = pd.DataFrame.from_records(rows)
    if windows.empty:
        raise ValueError("No windows were produced.")
    return windows, segment_count


def evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, object]:
    if len(y_true) == 0:
        empty_class = {"precision": None, "recall": None, "f1": None, "support": 0}
        return {
            "accuracy": None,
            "macro_f1": None,
            "confusion_matrix": [[0, 0], [0, 0]],
            "per_class": {"walking": empty_class.copy(), "running": empty_class.copy()},
        }
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=[0, 1], zero_division=0
    )
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(
            f1_score(y_true, y_pred, labels=[0, 1], average="macro", zero_division=0)
        ),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
        "per_class": {
            "walking": {
                "precision": float(precision[0]),
                "recall": float(recall[0]),
                "f1": float(f1[0]),
                "support": int(support[0]),
            },
            "running": {
                "precision": float(precision[1]),
                "recall": float(recall[1]),
                "f1": float(f1[1]),
                "support": int(support[1]),
            },
        },
    }


def select_tree(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_validation: np.ndarray,
    y_validation: np.ndarray,
) -> tuple[DecisionTreeClassifier, list[tuple[int, float]]]:
    scores: list[tuple[int, float]] = []
    for depth in DEPTH_CANDIDATES:
        candidate = DecisionTreeClassifier(max_depth=depth, random_state=RANDOM_STATE)
        candidate.fit(x_train, y_train)
        score = float(
            f1_score(y_validation, candidate.predict(x_validation), average="macro")
        )
        scores.append((depth, score))
    best_depth, _ = max(scores, key=lambda item: (item[1], -item[0]))
    selected = DecisionTreeClassifier(max_depth=best_depth, random_state=RANDOM_STATE)
    selected.fit(x_train, y_train)
    return selected, scores


def fmt_metric(metrics: dict[str, object]) -> str:
    if metrics["accuracy"] is None:
        return "N/A (no windows in this subset)"
    return (
        f"accuracy={metrics['accuracy']:.4f}, macro-F1={metrics['macro_f1']:.4f}, "
        f"confusion=[[TN, FP], [FN, TP]]={metrics['confusion_matrix']}"
    )


def main() -> None:
    frame = pd.read_csv(DATASET_PATH)
    needed = {"date", "time", "wrist", "activity", *AXES}
    missing = sorted(needed - set(frame.columns))
    if missing:
        raise ValueError(f"Missing CSV columns: {missing}")
    if frame[list(needed)].isna().any().any():
        raise ValueError("Required columns contain missing values.")
    if set(frame["activity"].unique()) != {0, 1}:
        raise ValueError("Expected labels 0=walking and 1=running.")
    if not np.isfinite(frame[AXES].to_numpy(dtype=np.float64)).all():
        raise ValueError("Sensor axes contain non-finite values.")

    frame["timestamp"] = pd.to_datetime(
        frame["date"] + " " + frame["time"],
        format="%Y-%m-%d %H:%M:%S:%f",
        errors="raise",
    )
    transition_frame = frame.sort_values(
        ["date", "wrist", "timestamp"], kind="stable"
    ).copy()
    transition_frame["_interval"] = transition_frame.groupby(
        ["date", "wrist"], sort=False
    )["timestamp"].diff().dt.total_seconds()
    label_changed = transition_frame["activity"].ne(
        transition_frame.groupby(["date", "wrist"], sort=False)["activity"].shift()
    ) & transition_frame["_interval"].notna()
    label_transition_gaps = transition_frame.loc[label_changed, "_interval"]
    transition_summary = {
        "count": int(len(label_transition_gaps)),
        "within_segment_threshold": int(
            ((label_transition_gaps > 0) & (label_transition_gaps <= MAX_GAP_SECONDS)).sum()
        ),
        "over_segment_threshold": int(
            (label_transition_gaps > MAX_GAP_SECONDS).sum()
        ),
        "minimum_gap_seconds": float(label_transition_gaps.min())
        if len(label_transition_gaps)
        else None,
    }
    date_label_counts = frame.groupby("date")["activity"].nunique()
    single_class_dates = sorted(date_label_counts[date_label_counts == 1].index.tolist())
    all_dates = set(frame["date"].unique())
    assigned = [date for dates in DATE_SPLITS.values() for date in dates]
    if len(set(assigned)) != len(assigned) or set(assigned) != all_dates:
        raise ValueError("Date groups overlap or do not cover the dataset exactly.")

    windows, segment_count = build_windows(frame)
    split_data = {
        split: windows[windows.date.isin(dates)].reset_index(drop=True)
        for split, dates in DATE_SPLITS.items()
    }
    for split, data in split_data.items():
        if data.empty or set(data.label.unique()) != {0, 1}:
            raise ValueError(f"{split} must contain both majority-window labels.")

    y_train = split_data["train"].label.to_numpy(dtype=np.int64)
    y_validation = split_data["validation"].label.to_numpy(dtype=np.int64)
    y_test = split_data["test"].label.to_numpy(dtype=np.int64)
    train_counts = Counter(y_train.tolist())
    majority_label = min((0, 1), key=lambda label: (-train_counts[label], label))

    candidates = {}
    validation_tables = {}
    for name, feature_names in (
        ("six_axis", SIX_AXIS_FEATURES),
        ("magnitude", MAGNITUDE_FEATURES),
    ):
        x_train = split_data["train"][feature_names].to_numpy(dtype=np.float64)
        x_validation = split_data["validation"][feature_names].to_numpy(dtype=np.float64)
        model, validation_scores = select_tree(
            x_train, y_train, x_validation, y_validation
        )
        candidates[name] = {"model": model, "features": feature_names}
        validation_tables[name] = validation_scores

    # Choose the approach by validation macro F1 only; exact ties favor magnitudes.
    best_validation = {
        name: max(score for _, score in validation_tables[name])
        for name in candidates
    }
    if best_validation["magnitude"] >= best_validation["six_axis"]:
        preferred_name = "magnitude"
    else:
        preferred_name = "six_axis"
    preferred = candidates[preferred_name]

    split_counts: dict[str, dict[str, object]] = {}
    for split, data in split_data.items():
        split_counts[split] = {
            "dates": DATE_SPLITS[split],
            "total": int(len(data)),
            "walking": int((data.label == 0).sum()),
            "running": int((data.label == 1).sum()),
            "mixed": int(data.mixed_activity.sum()),
            "ties": int(data.tie.sum()),
        }

    # The original test dates are diagnostic only: Phase 2B reported their results.
    test_data = split_data["test"]
    subgroup_results = {}
    for group_name, group_column in (("date", "date"), ("wrist", "wrist")):
        subgroup_results[group_name] = {}
        for value, subset in test_data.groupby(group_column, sort=True):
            subgroup_results[group_name][str(value)] = {
                "windows": int(len(subset)),
                "walking": int((subset.label == 0).sum()),
                "running": int((subset.label == 1).sum()),
                "mixed": int(subset.mixed_activity.sum()),
            }

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(preferred["model"], MODEL_PATH)

    positive_intervals = (
        frame.sort_values(["date", "wrist", "timestamp"], kind="stable")
        .groupby(["date", "wrist"], sort=False)["timestamp"]
        .diff()
        .dt.total_seconds()
    )
    median_interval = float(positive_intervals[positive_intervals > 0].median())
    config = {
        "model_type": "sklearn.tree.DecisionTreeClassifier",
        "model_file": MODEL_PATH.name,
        "selected_approach": preferred_name,
        "feature_order": preferred["features"],
        "all_candidate_feature_sets": {
            "six_axis": SIX_AXIS_FEATURES,
            "magnitude": MAGNITUDE_FEATURES,
        },
        "statistics": STATISTICS,
        "standard_deviation": "population (ddof=0)",
        "label_mapping": {"0": "walking", "1": "running"},
        "window": {
            "samples": WINDOW_SAMPLES,
            "stride_samples": WINDOW_STRIDE,
            "nominal_rate_hz": NOMINAL_RATE_HZ,
            "nominal_duration_seconds": WINDOW_SAMPLES / NOMINAL_RATE_HZ,
            "observed_median_interval_seconds": median_interval,
            "max_gap_seconds": MAX_GAP_SECONDS,
            "overlap": "50 percent",
        },
        "segmentation": {
            "uses_activity_labels": False,
            "new_segment_on": [
                "date change",
                "wrist change",
                "non-positive timestamp interval",
                f"timestamp gap > {MAX_GAP_SECONDS} seconds",
            ],
            "window_target": "majority activity label among samples",
            "tie_break": "label at sixth sample (center-right sample)",
            "mixed_windows_included": True,
            "observed_activity_transition_gaps": transition_summary,
        },
        "date_splits": DATE_SPLITS,
        "model_selection": {
            "depth_candidates": list(DEPTH_CANDIDATES),
            "within_approach_metric": "validation macro F1; ties choose shallower depth",
            "approach_selection_metric": "validation macro F1; ties favor magnitude features",
            "validation_best_macro_f1": best_validation,
            "selected_max_depth": int(preferred["model"].get_depth()),
            "random_state": RANDOM_STATE,
        },
        "test_status": "diagnostic only; original test dates were examined in Phase 2B",
        "unit_assumptions": {
            "acceleration": "unverified raw dataset units; no conversion applied",
            "gyroscope": "unverified raw dataset units; no conversion applied",
        },
        "dataset": {
            "relative_path": "data/archive/dataset.csv",
            "rows": int(len(frame)),
            "dates": int(frame.date.nunique()),
            "participants": int(frame.username.nunique()) if "username" in frame else None,
        },
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    # Reload, verify feature dimensions, and run a real test-window inference.
    loaded_model = joblib.load(MODEL_PATH)
    test_metrics: dict[str, dict[str, object]] = {}
    mixed_metrics: dict[str, dict[str, object]] = {}
    pure_metrics: dict[str, dict[str, object]] = {}
    subgroup_metrics: dict[str, dict[str, dict[str, object]]] = {"date": {}, "wrist": {}}
    baseline_metrics: dict[str, object] = {}
    for name, candidate in candidates.items():
        test_x = test_data[candidate["features"]].to_numpy(dtype=np.float64)
        prediction = (
            loaded_model.predict(test_x)
            if name == preferred_name
            else candidate["model"].predict(test_x)
        )
        test_metrics[name] = evaluate(y_test, prediction)
        mixed_mask = test_data.mixed_activity.to_numpy(dtype=bool)
        pure_mask = ~mixed_mask
        mixed_metrics[name] = evaluate(y_test[mixed_mask], prediction[mixed_mask])
        pure_metrics[name] = evaluate(y_test[pure_mask], prediction[pure_mask])
        subgroup_metrics["date"][name] = {}
        subgroup_metrics["wrist"][name] = {}
        for group_name, group_column in (("date", "date"), ("wrist", "wrist")):
            for value, subset in test_data.groupby(group_column, sort=True):
                indices = subset.index.to_numpy()
                mask = test_data.index.isin(indices)
                subgroup_metrics[group_name][name][str(value)] = evaluate(
                    y_test[mask], prediction[mask]
                )
        if name == preferred_name:
            expected = candidates[preferred_name]["model"].predict(test_x)
            if not np.array_equal(prediction, expected):
                raise RuntimeError("Saved model predictions differ from the selected model.")
            if loaded_model.n_features_in_ != len(preferred["features"]):
                raise RuntimeError("Saved model feature count does not match its config.")

    baseline_predictions = np.full_like(y_test, majority_label)
    baseline_metrics["all"] = evaluate(y_test, baseline_predictions)
    mixed_mask = test_data.mixed_activity.to_numpy(dtype=bool)
    pure_mask = ~mixed_mask
    baseline_metrics["mixed"] = evaluate(y_test[mixed_mask], baseline_predictions[mixed_mask])
    baseline_metrics["pure"] = evaluate(y_test[pure_mask], baseline_predictions[pure_mask])

    # Build a compact report with overall, mixed, per-class, per-date, and per-wrist results.
    split_rows = []
    for split, summary in split_counts.items():
        split_rows.append(
            f"| {split} | {', '.join(summary['dates'])} | {summary['total']} | "
            f"{summary['walking']} | {summary['running']} | {summary['mixed']} | {summary['ties']} |"
        )
    depth_rows = []
    for name in candidates:
        for depth, score in validation_tables[name]:
            depth_rows.append(f"| {name} | {depth} | {score:.4f} |")

    def per_class_text(metrics: dict[str, object]) -> str:
        p = metrics["per_class"]
        if p["walking"]["support"] == 0 and p["running"]["support"] == 0:
            return "N/A (no windows in this subset)"
        return (
            f"walking P/R/F1={p['walking']['precision']:.3f}/"
            f"{p['walking']['recall']:.3f}/{p['walking']['f1']:.3f} "
            f"(n={p['walking']['support']}), running P/R/F1="
            f"{p['running']['precision']:.3f}/{p['running']['recall']:.3f}/"
            f"{p['running']['f1']:.3f} (n={p['running']['support']})"
        )

    results_rows = []
    for name in (*candidates.keys(), "majority_baseline"):
        metrics = baseline_metrics["all"] if name == "majority_baseline" else test_metrics[name]
        results_rows.append(
            f"| {name} | {fmt_metric(metrics)} | {per_class_text(metrics)} |"
        )

    mixed_rows = []
    for name in (*candidates.keys(), "majority_baseline"):
        metrics = baseline_metrics["mixed"] if name == "majority_baseline" else mixed_metrics[name]
        mixed_rows.append(
            f"| {name} | {fmt_metric(metrics)} | {per_class_text(metrics)} |"
        )

    subgroup_lines = []
    for group_name in ("date", "wrist"):
        for group_value, summary in subgroup_results[group_name].items():
            for name in candidates:
                metrics = subgroup_metrics[group_name][name][group_value]
                subgroup_lines.append(
                    f"| {group_name} {group_value} | {name} | {summary['windows']} | "
                    f"{summary['walking']} | {summary['running']} | {summary['mixed']} | "
                    f"{metrics['accuracy']:.4f} | {metrics['macro_f1']:.4f} |"
                )

    selected_validation = best_validation[preferred_name]
    reload_prediction = loaded_model.predict(
        test_data[preferred["features"]].iloc[:1].to_numpy(dtype=np.float64)
    )[0]
    report = f"""# Phase 2C Corrected Evaluation Report

## Corrected window construction

Windows use 10 consecutive samples, stride 5 (50% overlap), nominally 2 seconds at 5 Hz. Segments break only at date changes, wrist changes, non-positive timestamp intervals, or gaps over {MAX_GAP_SECONDS:.1f} seconds. Activity labels are not read by the segmentation logic. Each window is labeled by the majority of its ten row labels; an exact tie uses the sixth sample's label. Mixed windows remain included and are also evaluated separately.

Total data rows: {len(frame):,}; inferred continuity segments: {segment_count:,}; median positive sample interval: {median_interval:.4f} seconds. Units remain unverified and no conversion was applied.

The source labels are clustered by recording conditions: {len(single_class_dates)} dates contain only one activity ({', '.join(single_class_dates)}). On 2017-7-17, walking occurs only at wrist value 0 and running only at wrist value 1. There are {transition_summary['count']} within-date/wrist label changes; {transition_summary['within_segment_threshold']} occur at or below the {MAX_GAP_SECONDS:.1f}s continuity threshold and {transition_summary['over_segment_threshold']} occur after a larger gap. Thus the current dataset produced no mixed windows; transition performance is unavailable, not omitted.

## Date-grouped windows

The Phase 2B date assignment was retained unchanged. The test dates were previously examined in Phase 2B, so all test results below are diagnostic and are not independent final generalization evidence.

| Split | Dates | Total windows | Walking target | Running target | Mixed windows | Ties |
|---|---|---:|---:|---:|---:|---:|
{chr(10).join(split_rows)}

No date appears in more than one split. Candidate tree depths were selected using validation macro F1 only. The preferred approach was selected using validation macro F1 only; test results did not affect that choice.

| Feature approach | Depth | Validation macro F1 |
|---|---:|---:|
{chr(10).join(depth_rows)}

Selected approach: **{preferred_name}**, depth **{loaded_model.get_depth()}**, validation macro F1 **{selected_validation:.4f}**. The magnitude approach computes acceleration norm and gyroscope norm per sample, then extracts mean/std/min/max (8 features). The six-axis approach uses the original six axes and the same statistics (24 features).

## Diagnostic test results

Confusion matrices use rows actual `[walking, running]` and columns predicted `[walking, running]`.

| Approach | Accuracy, macro F1, confusion matrix | Per-class precision/recall/F1 and support |
|---|---|---|
{chr(10).join(results_rows)}

Majority baseline always predicts the majority training-window label ({'walking' if majority_label == 0 else 'running'}).

### Mixed-activity test windows

Mixed windows are included in the overall results above. This separate view shows how they performed. Counts and targets use the majority/tie rule stated above.

| Approach | Accuracy, macro F1, confusion matrix | Per-class precision/recall/F1 and support |
|---|---|---|
{chr(10).join(mixed_rows)}

Pure-window metrics (reported for context):

{chr(10).join(f'- {name}: {fmt_metric(pure_metrics[name])}' for name in candidates)}

### Test differences by date and wrist

Subgroups may contain only one class; their macro F1 should be interpreted with the displayed class counts.

| Group | Approach | Windows | Walking | Running | Mixed | Accuracy | Macro F1 |
|---|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(subgroup_lines)}

## Saved model check

Selected artifact was saved, reloaded with joblib, and used to predict a test-date window. Reload prediction: label **{int(reload_prediction)}**; feature count **{loaded_model.n_features_in_}**. The selected approach configuration records the matching feature order.

## Limitations

- The original test dates have already been evaluated in Phase 2B and are reused only for diagnosis. Do not describe these revised scores as an untouched final test.
- There is one participant and no validation on the RT-Spark/ICM-20608-G hardware. Generalization to new people, placements, devices, and firmware sampling behavior remains unknown.
- Acceleration and gyroscope units and original sensor placement/orientation are not verified. Magnitudes reduce dependence on axis orientation, but do not resolve scale, gravity handling, sensor calibration, or device differences.
- Magnitude features can discard useful directional information. Validation performance guides the selection, but dates are few and the labels are correlated with date/wrist conditions.
- Fixed sample-count windows are nominally 2 seconds; actual duration varies with timestamps. Label-majority windows near transitions are inherently ambiguous.
"""
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(f"Imports OK: numpy={np.__version__}, pandas={pd.__version__}, scikit-learn={sklearn.__version__}, joblib={joblib.__version__}")
    print(f"Rows={len(frame)} segments={segment_count} median_interval={median_interval:.6f}s")
    for split, summary in split_counts.items():
        print(f"{split}: {summary}")
    print("Validation best macro F1:", best_validation)
    print("Selected by validation only:", preferred_name, "depth", loaded_model.get_depth())
    for name, metrics in test_metrics.items():
        print(f"Test {name}: {fmt_metric(metrics)}")
    print(f"Test majority baseline: {fmt_metric(baseline_metrics['all'])}")
    for name, metrics in mixed_metrics.items():
        print(f"Mixed test {name}: {fmt_metric(metrics)}")
    print(f"Saved-model load/inference: PASS; test sample prediction={int(reload_prediction)}")
    print(f"Model: {MODEL_PATH}")
    print(f"Configuration: {CONFIG_PATH}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
