from __future__ import annotations

import threading
import time
import unittest
from typing import Any

from activity_recognition import ActivityPrediction
from inference_service import InferenceService
from test_activity_recognition import reading


class FakeRecognizer:
    model_version = "test-model"

    def __init__(self, block_first: bool = False, fail: bool = False) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        if not block_first:
            self.release.set()
        self.fail = fail
        self.windows: list[tuple[str, str]] = []

    def predict(self, window: Any) -> ActivityPrediction:
        self.started.set()
        self.release.wait(3)
        if self.fail:
            raise RuntimeError("controlled prediction failure")
        self.windows.append((window.window_start_timestamp, window.window_end_timestamp))
        return ActivityPrediction(
            device_id=window.device_id,
            activity_label="IDLE",
            activity_code=0,
            detection_method="RULE_BASED",
            model_version=self.model_version,
            window_start_timestamp=window.window_start_timestamp,
            window_end_timestamp=window.window_end_timestamp,
        )


def wait_until(predicate, timeout: float = 4.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class InferenceServiceTests(unittest.TestCase):
    def test_worker_is_single_instance_and_stops_cleanly(self) -> None:
        recognizer = FakeRecognizer()
        service = InferenceService(lambda: recognizer, lambda _prediction: True)
        self.assertTrue(service.start())
        self.assertFalse(service.start())
        self.assertEqual(service.status()["worker_starts"], 1)
        self.assertTrue(service.stop())
        self.assertEqual(service.status()["status"], "stopped")

    def test_missing_model_is_visible_and_does_not_accept_for_inference(self) -> None:
        service = InferenceService(
            lambda: (_ for _ in ()).throw(FileNotFoundError("missing corrected model")),
            lambda _prediction: True,
        )
        with self.assertLogs("lab3.inference", level="ERROR"):
            self.assertFalse(service.start())
        self.assertEqual(service.status()["status"], "unavailable")
        self.assertFalse(service.offer(reading("missing-model", 0)))
        self.assertEqual(service.status()["unavailable_drops"], 1)
        self.assertIn("model load failed", service.status()["last_error"])

    def test_queue_overflow_is_nonblocking_and_resets_partial_window(self) -> None:
        recognizer = FakeRecognizer(block_first=True)
        stored: list[dict[str, Any]] = []
        service = InferenceService(
            lambda: recognizer,
            lambda prediction: stored.append(dict(prediction)) is None,
            queue_capacity=1,
        )
        self.assertTrue(service.start())
        for index in range(10):
            self.assertTrue(service.offer(reading("overflow", index)))
            if index < 9:
                self.assertTrue(wait_until(lambda expected=index + 1: service.status()["processed_samples"] >= expected))
        self.assertTrue(recognizer.started.wait(2))
        self.assertTrue(service.offer(reading("overflow", 10)))
        self.assertFalse(service.offer(reading("overflow", 11)))
        self.assertEqual(service.status()["queue_drops"], 1)
        recognizer.release.set()
        self.assertTrue(wait_until(lambda: service.status()["processed_samples"] >= 11))

        self.assertTrue(service.offer(reading("overflow", 12)))
        self.assertTrue(wait_until(lambda: service.status()["processed_samples"] >= 12))
        expected_processed = 12
        for index in range(13, 22):
            self.assertTrue(service.offer(reading("overflow", index)))
            expected_processed += 1
            self.assertTrue(
                wait_until(
                    lambda expected=expected_processed: service.status()["processed_samples"] >= expected
                )
            )
        self.assertTrue(wait_until(lambda: service.status()["windows_classified"] >= 2))
        self.assertEqual(service.status()["queue_discontinuity_resets"], 1)
        self.assertEqual(len(recognizer.windows), 2)
        self.assertEqual(recognizer.windows[1][0], reading("overflow", 12)["timestamp"])
        self.assertTrue(service.stop())

    def test_inference_exception_is_counted_and_worker_survives(self) -> None:
        recognizer = FakeRecognizer(fail=True)
        service = InferenceService(lambda: recognizer, lambda _prediction: True)
        self.assertTrue(service.start())
        with self.assertLogs("lab3.inference", level="ERROR"):
            for index in range(10):
                self.assertTrue(service.offer(reading("inference-error", index)))
            self.assertTrue(wait_until(lambda: service.status()["inference_errors"] == 1))
        self.assertEqual(service.status()["status"], "running")
        self.assertTrue(service.stop())

    def test_source_discontinuity_resets_partial_window(self) -> None:
        recognizer = FakeRecognizer()
        service = InferenceService(lambda: recognizer, lambda _prediction: True)
        self.assertTrue(service.start())
        for index in range(5):
            self.assertTrue(service.offer(reading("source-gap", index)))
            self.assertTrue(
                wait_until(lambda expected=index + 1: service.status()["processed_samples"] >= expected)
            )
        service.mark_discontinuity()
        expected_processed = 5
        for index in range(5, 15):
            self.assertTrue(service.offer(reading("source-gap", index)))
            expected_processed += 1
            self.assertTrue(
                wait_until(
                    lambda expected=expected_processed: service.status()["processed_samples"] >= expected
                )
            )
        self.assertTrue(wait_until(lambda: service.status()["windows_classified"] == 1))
        self.assertEqual(recognizer.windows[0][0], reading("source-gap", 5)["timestamp"])
        self.assertEqual(service.status()["source_discontinuities"], 1)
        self.assertEqual(service.status()["queue_discontinuity_resets"], 1)
        self.assertTrue(service.stop())


if __name__ == "__main__":
    unittest.main()
