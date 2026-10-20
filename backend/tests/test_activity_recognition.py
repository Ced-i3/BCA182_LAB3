from __future__ import annotations

import math
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from activity_recognition import (
    FEATURE_ORDER,
    ActivityRecognizer,
    ActivityWindow,
    ActivityWindowProcessor,
    IdleMetrics,
    IdleThresholds,
    ModelLoadError,
    extract_features,
    idle_metrics,
    is_idle,
)


BASE_TIME = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)

def reading(
    device: str,
    index: int,
    *,
    timestamp: datetime | None = None,
    accel: tuple[float, float, float] = (0.0, 0.0, 9.48),
    gyro: tuple[float, float, float] = (0.01, -0.008, 0.004),
) -> dict[str, object]:
    timestamp = timestamp or BASE_TIME + timedelta(seconds=index * 0.2)
    return {
        "device_id": device,
        "timestamp": timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "accel_m_s2_x": accel[0],
        "accel_m_s2_y": accel[1],
        "accel_m_s2_z": accel[2],
        "gyro_rad_s_x": gyro[0],
        "gyro_rad_s_y": gyro[1],
        "gyro_rad_s_z": gyro[2],
    }


def stationary_samples(device: str = "test-board") -> list[dict[str, object]]:
    rows = []
    for index in range(10):
        phase = index * 0.7
        rows.append(
            reading(
                device,
                index,
                accel=(
                    0.02 * math.sin(phase),
                    0.02 * math.cos(phase),
                    9.48 + 0.025 * math.sin(phase),
                ),
                gyro=(
                    0.01 + 0.002 * math.sin(phase),
                    -0.008 + 0.002 * math.cos(phase),
                    0.004 + 0.001 * math.sin(phase),
                ),
            )
        )
    return rows


class FeatureAndModelTests(unittest.TestCase):
    def test_corrected_model_loads_with_metadata_contract(self) -> None:
        recognizer = ActivityRecognizer.load_corrected()
        self.assertEqual(recognizer.model.n_features_in_, 24)
        self.assertEqual([int(value) for value in recognizer.model.classes_], [0, 1])
        self.assertIn("activity_model_corrected.joblib:sha256:", recognizer.model_version)
        self.assertEqual(len(FEATURE_ORDER), 24)

    def test_population_standard_deviation_and_feature_order(self) -> None:
        samples = []
        for index in range(10):
            samples.append(
                reading(
                    "features",
                    index,
                    accel=(float(index + 1), 2.0, 3.0),
                    gyro=(4.0, 5.0, 6.0),
                )
            )
        features = extract_features(samples)
        self.assertEqual(len(features), 24)
        self.assertEqual(features[:4][0], 5.5)
        self.assertAlmostEqual(features[:4][1], math.sqrt(8.25))
        self.assertEqual(features[:4][2:], (1.0, 10.0))
        self.assertEqual(FEATURE_ORDER[4:8], (
            "acceleration_y_mean",
            "acceleration_y_std",
            "acceleration_y_min",
            "acceleration_y_max",
        ))

    def test_predictions_for_identical_windows_are_deterministic(self) -> None:
        recognizer = ActivityRecognizer.load_corrected()
        samples = [
            reading(
                "deterministic",
                index,
                accel=(2.0 * math.sin(index), 0.6 * math.cos(index), 9.48 + math.sin(index)),
                gyro=(0.3 * math.sin(index), 0.2, -0.1),
            )
            for index in range(10)
        ]
        window = ActivityWindow("deterministic", tuple(samples), samples[0]["timestamp"], samples[-1]["timestamp"])
        self.assertEqual(recognizer.predict(window), recognizer.predict(window))

    def test_hybrid_classifier_has_idle_walking_and_running_paths(self) -> None:
        recognizer = ActivityRecognizer.load_corrected()
        idle_rows = stationary_samples("three-state")
        idle_window = ActivityWindow(
            "three-state", tuple(idle_rows), idle_rows[0]["timestamp"], idle_rows[-1]["timestamp"]
        )
        idle_prediction = recognizer.predict(idle_window)
        self.assertEqual((idle_prediction.activity_label, idle_prediction.detection_method), ("IDLE", "RULE_BASED"))

        def active_window(y_value: float) -> ActivityWindow:
            rows = [
                reading(
                    "three-state",
                    index,
                    accel=(0.5 * math.sin(index), y_value, 9.48 + 0.4 * math.cos(index)),
                    gyro=(0.3, 0.1, -0.08),
                )
                for index in range(10)
            ]
            return ActivityWindow(
                "three-state", tuple(rows), rows[0]["timestamp"], rows[-1]["timestamp"]
            )

        walking = recognizer.predict(active_window(-0.3))
        running = recognizer.predict(active_window(0.3))
        self.assertEqual((walking.activity_label, walking.detection_method), ("WALKING", "DECISION_TREE"))
        self.assertEqual((running.activity_label, running.detection_method), ("RUNNING", "DECISION_TREE"))
        self.assertTrue(all(item.experimental for item in (idle_prediction, walking, running)))

    def test_missing_or_corrupt_corrected_model_fails_visibly(self) -> None:
        missing = Path(__file__).with_name("missing-activity_model_corrected.joblib")
        with self.assertRaises(ModelLoadError):
            ActivityRecognizer.load_corrected(model_path=missing)
        with patch("activity_recognition.joblib.load", side_effect=EOFError("corrupt artifact")):
            with self.assertRaises(ModelLoadError):
                ActivityRecognizer.load_corrected()


class IdleDetectorTests(unittest.TestCase):
    def test_idle_thresholds_are_environment_configurable_and_validated(self) -> None:
        with patch.dict(os.environ, {"ACTIVITY_IDLE_GYRO_RMS_RAD_S": "0.2"}, clear=True):
            thresholds = IdleThresholds.from_environment()
        self.assertEqual(thresholds.gyro_magnitude_rms_rad_s, 0.2)
        with patch.dict(os.environ, {"ACTIVITY_IDLE_GYRO_RMS_RAD_S": "-1"}, clear=True):
            with self.assertRaises(ValueError):
                IdleThresholds.from_environment()

    def test_stationary_gravity_and_small_noise_are_idle(self) -> None:
        metrics = idle_metrics(stationary_samples())
        self.assertGreater(metrics.accel_magnitude_std_m_s2, 0.0)
        self.assertGreater(metrics.gyro_magnitude_rms_rad_s, 0.0)
        self.assertTrue(is_idle(metrics, IdleThresholds()))

    def test_rotation_is_not_idle_even_when_acceleration_magnitude_stays_near_gravity(self) -> None:
        rows = []
        gravity = 9.48
        angular_speed = 0.16
        for index in range(10):
            angle = angular_speed * index * 0.2
            rows.append(
                reading(
                    "rotating",
                    index,
                    accel=(gravity * math.sin(angle), 0.0, gravity * math.cos(angle)),
                    gyro=(0.0, angular_speed, 0.0),
                )
            )
        self.assertFalse(is_idle(idle_metrics(rows), IdleThresholds()))

    def test_active_motion_is_not_idle(self) -> None:
        rows = [
            reading(
                "moving",
                index,
                accel=(3.0 * (-1) ** index, 1.2 * math.sin(index), 9.48 + 2.0 * math.cos(index)),
                gyro=(0.3, 0.2 * math.sin(index), 0.15),
            )
            for index in range(10)
        ]
        self.assertFalse(is_idle(idle_metrics(rows), IdleThresholds()))

    def test_threshold_boundaries_are_inclusive(self) -> None:
        thresholds = IdleThresholds()
        at_boundary = IdleMetrics(
            thresholds.accel_magnitude_std_m_s2,
            thresholds.accel_magnitude_range_m_s2,
            thresholds.gyro_magnitude_rms_rad_s,
            thresholds.gyro_magnitude_std_rad_s,
            thresholds.accel_direction_spread_deg,
        )
        over_boundary = IdleMetrics(
            thresholds.accel_magnitude_std_m_s2 + 1e-9,
            thresholds.accel_magnitude_range_m_s2,
            thresholds.gyro_magnitude_rms_rad_s,
            thresholds.gyro_magnitude_std_rad_s,
            thresholds.accel_direction_spread_deg,
        )
        self.assertTrue(is_idle(at_boundary, thresholds))
        self.assertFalse(is_idle(over_boundary, thresholds))


class WindowProcessorTests(unittest.TestCase):
    def test_ten_sample_window_then_stride_of_five(self) -> None:
        processor = ActivityWindowProcessor()
        outputs = [processor.add(reading("one", index)) for index in range(15)]
        windows = [window for window in outputs if window is not None]
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0].window_start_timestamp, reading("one", 0)["timestamp"])
        self.assertEqual(windows[0].window_end_timestamp, reading("one", 9)["timestamp"])
        self.assertEqual(windows[1].window_start_timestamp, reading("one", 5)["timestamp"])
        self.assertEqual(windows[1].window_end_timestamp, reading("one", 14)["timestamp"])

    def test_devices_have_independent_windows(self) -> None:
        processor = ActivityWindowProcessor()
        for index in range(5):
            self.assertIsNone(processor.add(reading("device-a", index)))
            self.assertIsNone(processor.add(reading("device-b", index)))
        a_window = None
        b_window = None
        for index in range(5, 10):
            a_window = processor.add(reading("device-a", index)) or a_window
            b_window = processor.add(reading("device-b", index)) or b_window
        self.assertIsNotNone(a_window)
        self.assertIsNotNone(b_window)
        self.assertEqual(a_window.device_id, "device-a")
        self.assertEqual(b_window.device_id, "device-b")

    def test_duplicate_out_of_order_and_gap_handling(self) -> None:
        processor = ActivityWindowProcessor(max_gap_seconds=0.6)
        self.assertIsNone(processor.add(reading("sequence", 0)))
        self.assertIsNone(processor.add(reading("sequence", 0)))
        self.assertIsNone(processor.add(reading("sequence", -1)))
        for index in range(1, 10):
            window = processor.add(reading("sequence", index))
        self.assertIsNotNone(window)
        self.assertEqual(processor.status()["duplicate_samples"], 1)
        self.assertEqual(processor.status()["out_of_order_samples"], 1)

        reset_processor = ActivityWindowProcessor(max_gap_seconds=0.6)
        for index in range(5):
            reset_processor.add(reading("gap", index))
        gap_time = BASE_TIME + timedelta(seconds=2.0)
        self.assertIsNone(reset_processor.add(reading("gap", 10, timestamp=gap_time)))
        for index in range(1, 10):
            window = reset_processor.add(
                reading("gap", 10 + index, timestamp=gap_time + timedelta(seconds=index * 0.2))
            )
        self.assertIsNotNone(window)
        self.assertEqual(window.window_start_timestamp, gap_time.isoformat(timespec="milliseconds").replace("+00:00", "Z"))
        self.assertEqual(reset_processor.status()["timestamp_gap_resets"], 1)

    def test_invalid_timestamp_resets_partial_window_and_incomplete_is_pending(self) -> None:
        processor = ActivityWindowProcessor()
        for index in range(9):
            self.assertIsNone(processor.add(reading("pending", index)))
        invalid = reading("pending", 9)
        invalid["timestamp"] = "not-a-time"
        self.assertIsNone(processor.add(invalid))
        self.assertEqual(processor.status()["invalid_samples"], 1)
        self.assertEqual(processor.status()["buffered_samples"], 0)

    def test_device_buffer_count_is_bounded(self) -> None:
        processor = ActivityWindowProcessor(max_devices=2)
        processor.add(reading("a", 0))
        processor.add(reading("b", 0))
        processor.add(reading("c", 0))
        self.assertEqual(processor.status()["buffered_devices"], 2)
        self.assertEqual(processor.status()["device_evictions"], 1)


if __name__ == "__main__":
    unittest.main()
