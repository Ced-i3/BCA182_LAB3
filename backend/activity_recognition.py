"""Three-state experimental activity recognition for backend sensor readings."""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import joblib
import numpy as np
from sklearn.tree import DecisionTreeClassifier


MODEL_FILENAME = "activity_model_corrected.joblib"
PREPROCESSING_FILENAME = "activity_preprocessing_corrected.json"
AXES = (
    "acceleration_x",
    "acceleration_y",
    "acceleration_z",
    "gyro_x",
    "gyro_y",
    "gyro_z",
)
STATISTICS = ("mean", "std", "min", "max")
FEATURE_ORDER = tuple(f"{axis}_{stat}" for axis in AXES for stat in STATISTICS)
WINDOW_SAMPLES = 10
WINDOW_STRIDE = 5

ACTIVITY_CODES = {"IDLE": 0, "WALKING": 1, "RUNNING": 2}
MODEL_LABELS = {0: "WALKING", 1: "RUNNING"}


class ModelLoadError(RuntimeError):
    """The required corrected model or its preprocessing contract is invalid."""


@dataclass(frozen=True)
class IdleThresholds:
    """Engineering defaults for the experimental rule-based idle detector."""

    accel_magnitude_std_m_s2: float = 0.15
    accel_magnitude_range_m_s2: float = 0.50
    gyro_magnitude_rms_rad_s: float = 0.12
    gyro_magnitude_std_rad_s: float = 0.05
    accel_direction_spread_deg: float = 3.0

    @classmethod
    def from_environment(cls) -> "IdleThresholds":
        defaults = cls()
        values: dict[str, float] = {}
        for field_name, env_name in (
            ("accel_magnitude_std_m_s2", "ACTIVITY_IDLE_ACCEL_MAG_STD_M_S2"),
            ("accel_magnitude_range_m_s2", "ACTIVITY_IDLE_ACCEL_MAG_RANGE_M_S2"),
            ("gyro_magnitude_rms_rad_s", "ACTIVITY_IDLE_GYRO_RMS_RAD_S"),
            ("gyro_magnitude_std_rad_s", "ACTIVITY_IDLE_GYRO_STD_RAD_S"),
            ("accel_direction_spread_deg", "ACTIVITY_IDLE_DIRECTION_SPREAD_DEG"),
        ):
            default = getattr(defaults, field_name)
            raw = os.environ.get(env_name)
            if raw is None:
                values[field_name] = default
                continue
            try:
                value = float(raw)
            except ValueError as error:
                raise ValueError(f"{env_name} must be a finite non-negative number") from error
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{env_name} must be a finite non-negative number")
            values[field_name] = value
        return cls(**values)


@dataclass(frozen=True)
class IdleMetrics:
    accel_magnitude_std_m_s2: float
    accel_magnitude_range_m_s2: float
    gyro_magnitude_rms_rad_s: float
    gyro_magnitude_std_rad_s: float
    accel_direction_spread_deg: float


@dataclass(frozen=True)
class ActivityWindow:
    device_id: str
    samples: tuple[Mapping[str, Any], ...]
    window_start_timestamp: str
    window_end_timestamp: str


@dataclass(frozen=True)
class ActivityPrediction:
    device_id: str
    activity_label: str
    activity_code: int
    detection_method: str
    model_version: str
    window_start_timestamp: str
    window_end_timestamp: str
    experimental: bool = True


def _utc_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamp must be a valid ISO 8601 string") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _utc_iso(value: Any) -> str:
    return _utc_datetime(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sample_axes(sample: Mapping[str, Any]) -> tuple[float, ...]:
    keys = (
        "accel_m_s2_x",
        "accel_m_s2_y",
        "accel_m_s2_z",
        "gyro_rad_s_x",
        "gyro_rad_s_y",
        "gyro_rad_s_z",
    )
    values: list[float] = []
    for key in keys:
        value = sample.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be numeric")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f"{key} must be finite")
        values.append(numeric)
    return tuple(values)


def _population_statistics(values: Sequence[float]) -> tuple[float, float, float, float]:
    if not values:
        raise ValueError("statistics require at least one sample")
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return mean, math.sqrt(variance), min(values), max(values)


def extract_features(samples: Sequence[Mapping[str, Any]]) -> tuple[float, ...]:
    """Return the corrected 24-feature vector in metadata order using ddof=0."""
    if len(samples) != WINDOW_SAMPLES:
        raise ValueError(f"exactly {WINDOW_SAMPLES} samples are required")
    axes_by_index = list(zip(*(_sample_axes(sample) for sample in samples)))
    return tuple(
        feature
        for axis_values in axes_by_index
        for feature in _population_statistics(axis_values)
    )


def idle_metrics(
    samples: Sequence[Mapping[str, Any]],
) -> IdleMetrics:
    """Measure motion without relying on a single axis or zero acceleration."""
    if len(samples) != WINDOW_SAMPLES:
        raise ValueError(f"exactly {WINDOW_SAMPLES} samples are required")

    accel_vectors: list[tuple[float, float, float]] = []
    accel_magnitudes: list[float] = []
    gyro_magnitudes: list[float] = []
    for sample in samples:
        axes = _sample_axes(sample)
        accel = axes[:3]
        gyro = axes[3:]
        accel_vectors.append((accel[0], accel[1], accel[2]))
        accel_magnitudes.append(math.sqrt(sum(value * value for value in accel)))
        gyro_magnitudes.append(math.sqrt(sum(value * value for value in gyro)))

    accel_mean = sum(accel_magnitudes) / WINDOW_SAMPLES
    accel_std = math.sqrt(
        sum((value - accel_mean) ** 2 for value in accel_magnitudes) / WINDOW_SAMPLES
    )
    accel_range = max(accel_magnitudes) - min(accel_magnitudes)
    gyro_rms = math.sqrt(
        sum(value * value for value in gyro_magnitudes) / WINDOW_SAMPLES
    )
    gyro_mean = sum(gyro_magnitudes) / WINDOW_SAMPLES
    gyro_std = math.sqrt(
        sum((value - gyro_mean) ** 2 for value in gyro_magnitudes) / WINDOW_SAMPLES
    )

    directions: list[tuple[float, float, float]] = []
    for vector, magnitude in zip(accel_vectors, accel_magnitudes):
        if magnitude <= 1e-9:
            directions = []
            break
        directions.append(tuple(component / magnitude for component in vector))
    if len(directions) != WINDOW_SAMPLES:
        direction_spread = 180.0
    else:
        mean_direction = tuple(
            sum(direction[axis] for direction in directions) / WINDOW_SAMPLES
            for axis in range(3)
        )
        mean_norm = math.sqrt(sum(component * component for component in mean_direction))
        if mean_norm <= 1e-9:
            direction_spread = 180.0
        else:
            mean_direction = tuple(component / mean_norm for component in mean_direction)
            direction_spread = max(
                math.degrees(
                    math.acos(
                        max(
                            -1.0,
                            min(
                                1.0,
                                sum(a * b for a, b in zip(direction, mean_direction)),
                            ),
                        )
                    )
                )
                for direction in directions
            )

    return IdleMetrics(
        accel_magnitude_std_m_s2=accel_std,
        accel_magnitude_range_m_s2=accel_range,
        gyro_magnitude_rms_rad_s=gyro_rms,
        gyro_magnitude_std_rad_s=gyro_std,
        accel_direction_spread_deg=direction_spread,
    )


def is_idle(metrics: IdleMetrics, thresholds: IdleThresholds) -> bool:
    return (
        metrics.accel_magnitude_std_m_s2 <= thresholds.accel_magnitude_std_m_s2
        and metrics.accel_magnitude_range_m_s2 <= thresholds.accel_magnitude_range_m_s2
        and metrics.gyro_magnitude_rms_rad_s <= thresholds.gyro_magnitude_rms_rad_s
        and metrics.gyro_magnitude_std_rad_s <= thresholds.gyro_magnitude_std_rad_s
        and metrics.accel_direction_spread_deg <= thresholds.accel_direction_spread_deg
    )


class ActivityRecognizer:
    """Loaded corrected tree plus the three-state hybrid classification rule."""

    def __init__(
        self,
        model: DecisionTreeClassifier,
        model_version: str,
        thresholds: IdleThresholds | None = None,
    ) -> None:
        self.model = model
        self.model_version = model_version
        self.thresholds = thresholds or IdleThresholds()

    @classmethod
    def load_corrected(
        cls,
        model_path: Path | None = None,
        metadata_path: Path | None = None,
        thresholds: IdleThresholds | None = None,
    ) -> "ActivityRecognizer":
        model_dir = Path(__file__).resolve().parent / "models"
        model_path = model_path or (model_dir / MODEL_FILENAME)
        metadata_path = metadata_path or (model_dir / PREPROCESSING_FILENAME)
        try:
            metadata_bytes = metadata_path.read_bytes()
            metadata = json.loads(metadata_bytes.decode("utf-8"))
            if metadata.get("model_type") != "sklearn.tree.DecisionTreeClassifier":
                raise ValueError("unexpected model_type")
            if metadata.get("model_file") != MODEL_FILENAME:
                raise ValueError("preprocessing metadata does not select the corrected model")
            if metadata.get("selected_approach") != "six_axis":
                raise ValueError("corrected model must use the six-axis feature approach")
            if tuple(metadata.get("feature_order", ())) != FEATURE_ORDER:
                raise ValueError("preprocessing feature order does not match the corrected contract")
            if tuple(metadata.get("statistics", ())) != STATISTICS:
                raise ValueError("preprocessing statistics do not match the corrected contract")
            if metadata.get("standard_deviation") != "population (ddof=0)":
                raise ValueError("preprocessing standard deviation must use population ddof=0")
            window = metadata.get("window", {})
            if window.get("samples") != WINDOW_SAMPLES or window.get("stride_samples") != WINDOW_STRIDE:
                raise ValueError("preprocessing window size or stride is incompatible")
            if metadata.get("label_mapping") != {"0": "walking", "1": "running"}:
                raise ValueError("preprocessing class mapping is incompatible")
            model_bytes = model_path.read_bytes()
            model = joblib.load(model_path)
            if not isinstance(model, DecisionTreeClassifier):
                raise ValueError("corrected artifact is not a DecisionTreeClassifier")
            if int(model.n_features_in_) != len(FEATURE_ORDER):
                raise ValueError("loaded model feature count does not match metadata")
            if [int(value) for value in model.classes_] != [0, 1]:
                raise ValueError("loaded model classes do not match walking/running mapping")
            feature_names = getattr(model, "feature_names_in_", None)
            if feature_names is not None and tuple(feature_names) != FEATURE_ORDER:
                raise ValueError("loaded model feature names do not match metadata")
        except Exception as error:
            raise ModelLoadError(
                f"could not load required corrected activity model: {error}"
            ) from error

        effective_thresholds = thresholds or IdleThresholds()
        version_inputs = (
            model_bytes
            + b"\0"
            + metadata_bytes
            + b"\0"
            + json.dumps(
                effective_thresholds.__dict__, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        )
        version = f"{MODEL_FILENAME}:sha256:{hashlib.sha256(version_inputs).hexdigest()}"
        return cls(model=model, model_version=version, thresholds=effective_thresholds)

    def predict(self, window: ActivityWindow) -> ActivityPrediction:
        if len(window.samples) != WINDOW_SAMPLES:
            raise ValueError(f"exactly {WINDOW_SAMPLES} samples are required")

        metrics = idle_metrics(window.samples)
        if is_idle(metrics, self.thresholds):
            label = "IDLE"
            method = "RULE_BASED"
        else:
            feature_vector = extract_features(window.samples)
            class_id = int(self.model.predict(np.asarray([feature_vector], dtype=np.float64))[0])
            try:
                label = MODEL_LABELS[class_id]
            except KeyError as error:
                raise ValueError(f"model returned unsupported class {class_id}") from error
            method = "DECISION_TREE"

        return ActivityPrediction(
            device_id=window.device_id,
            activity_label=label,
            activity_code=ACTIVITY_CODES[label],
            detection_method=method,
            model_version=self.model_version,
            window_start_timestamp=_utc_iso(window.window_start_timestamp),
            window_end_timestamp=_utc_iso(window.window_end_timestamp),
            experimental=True,
        )


@dataclass
class _DeviceState:
    samples: deque[Mapping[str, Any]] = field(default_factory=deque)
    last_timestamp: datetime | None = None


class ActivityWindowProcessor:
    """Bounded per-device timestamp-aware 10-sample/5-sample-stride windows."""

    def __init__(
        self,
        max_gap_seconds: float = 0.6,
        max_devices: int = 64,
    ) -> None:
        if not math.isfinite(max_gap_seconds) or max_gap_seconds <= 0:
            raise ValueError("max_gap_seconds must be positive and finite")
        if max_devices < 1:
            raise ValueError("max_devices must be at least 1")
        self.max_gap_seconds = max_gap_seconds
        self.max_devices = max_devices
        self._lock = threading.RLock()
        self._devices: OrderedDict[str, _DeviceState] = OrderedDict()
        self._stats = {
            "duplicate_samples": 0,
            "out_of_order_samples": 0,
            "invalid_samples": 0,
            "timestamp_gap_resets": 0,
            "device_evictions": 0,
            "queue_discontinuity_resets": 0,
        }

    def reset_all(self) -> None:
        with self._lock:
            self._devices.clear()
            self._stats["queue_discontinuity_resets"] += 1

    def add(self, reading: Mapping[str, Any]) -> ActivityWindow | None:
        with self._lock:
            return self._add_locked(reading)

    def _add_locked(self, reading: Mapping[str, Any]) -> ActivityWindow | None:
        device_id = reading.get("device_id")
        if not isinstance(device_id, str) or not device_id.strip():
            self._stats["invalid_samples"] += 1
            return None
        device_id = device_id.strip()
        try:
            timestamp = _utc_datetime(reading.get("timestamp"))
            _sample_axes(reading)
        except (TypeError, ValueError):
            self._stats["invalid_samples"] += 1
            self._devices.pop(device_id, None)
            return None

        state = self._devices.get(device_id)
        if state is not None and state.last_timestamp is not None:
            delta = (timestamp - state.last_timestamp).total_seconds()
            if delta == 0:
                self._stats["duplicate_samples"] += 1
                return None
            if delta < 0:
                self._stats["out_of_order_samples"] += 1
                return None
            if delta > self.max_gap_seconds:
                state.samples.clear()
                self._stats["timestamp_gap_resets"] += 1
            self._devices.move_to_end(device_id)
        else:
            if len(self._devices) >= self.max_devices:
                self._devices.popitem(last=False)
                self._stats["device_evictions"] += 1
            state = _DeviceState(samples=deque())
            self._devices[device_id] = state

        state.last_timestamp = timestamp
        normalized = dict(reading)
        normalized["device_id"] = device_id
        normalized["timestamp"] = _utc_iso(timestamp.isoformat())
        state.samples.append(normalized)
        if len(state.samples) < WINDOW_SAMPLES:
            return None

        window_samples = tuple(state.samples)
        window = ActivityWindow(
            device_id=device_id,
            samples=window_samples,
            window_start_timestamp=str(window_samples[0]["timestamp"]),
            window_end_timestamp=str(window_samples[-1]["timestamp"]),
        )
        for _ in range(WINDOW_STRIDE):
            state.samples.popleft()
        return window

    def status(self) -> dict[str, int]:
        with self._lock:
            return {
                **self._stats,
                "buffered_devices": len(self._devices),
                "buffered_samples": sum(len(state.samples) for state in self._devices.values()),
            }

