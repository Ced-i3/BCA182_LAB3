"""Bounded, single-worker activity inference service."""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import asdict
from typing import Any, Callable, Mapping

from activity_recognition import ActivityRecognizer, ActivityWindowProcessor


LOGGER = logging.getLogger("lab3.inference")


class InferenceService:
    """Offer validated readings without waiting for feature extraction or inference."""

    def __init__(
        self,
        recognizer_loader: Callable[[], ActivityRecognizer],
        prediction_store: Callable[[Mapping[str, Any]], bool],
        queue_capacity: int = 100,
        max_devices: int = 64,
        max_gap_seconds: float = 0.6,
    ) -> None:
        if queue_capacity < 1:
            raise ValueError("queue_capacity must be at least 1")
        self._recognizer_loader = recognizer_loader
        self._prediction_store = prediction_store
        self._queue: queue.Queue[tuple[dict[str, Any], int]] = queue.Queue(queue_capacity)
        self._max_devices = max_devices
        self._max_gap_seconds = max_gap_seconds
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._recognizer: ActivityRecognizer | None = None
        self._processor: ActivityWindowProcessor | None = None
        self._status = "stopped"
        self._last_error: str | None = None
        self._generation = 0
        self._lifecycle_generation = 0
        self._counters = {
            "accepted_samples": 0,
            "processed_samples": 0,
            "dropped_samples": 0,
            "queue_drops": 0,
            "unavailable_drops": 0,
            "inference_errors": 0,
            "windows_classified": 0,
            "predictions_stored": 0,
            "duplicate_predictions": 0,
            "worker_starts": 0,
            "source_discontinuities": 0,
        }

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            if self._status in {"loading", "stopping"}:
                return False
            self._status = "loading"
            self._lifecycle_generation += 1
            lifecycle_generation = self._lifecycle_generation

        try:
            recognizer = self._recognizer_loader()
        except Exception as error:
            with self._lock:
                if self._lifecycle_generation == lifecycle_generation:
                    self._status = "unavailable"
                    self._last_error = f"model load failed: {error}"[:500]
            LOGGER.exception("Activity inference model could not be loaded")
            return False

        with self._lock:
            if self._lifecycle_generation != lifecycle_generation or self._status != "loading":
                return False
            self._recognizer = recognizer
            self._processor = ActivityWindowProcessor(
                max_gap_seconds=self._max_gap_seconds,
                max_devices=self._max_devices,
            )
            self._generation += 1
            self._stop_event.clear()
            self._status = "running"
            self._last_error = None
            self._thread = threading.Thread(
                target=self._run,
                name="activity-inference",
                daemon=True,
            )
            self._counters["worker_starts"] += 1
            self._thread.start()
            LOGGER.info(
                "Started experimental activity inference model=%s thresholds=%s",
                recognizer.model_version,
                getattr(recognizer, "thresholds", None),
            )
            return True

    def offer(self, reading: Mapping[str, Any]) -> bool:
        """Enqueue one validated reading using a nonblocking bounded put."""
        with self._lock:
            if self._status != "running":
                self._counters["dropped_samples"] += 1
                self._counters["unavailable_drops"] += 1
                return False
            item = (dict(reading), self._generation)
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                self._generation += 1
                self._counters["dropped_samples"] += 1
                self._counters["queue_drops"] += 1
                self._last_error = "inference queue full; partial windows will reset"
                return False
            self._counters["accepted_samples"] += 1
            return True

    def mark_discontinuity(self) -> None:
        """Break every partial window after a received but unusable MQTT item."""
        with self._lock:
            self._generation += 1
            self._counters["source_discontinuities"] += 1

    def _run(self) -> None:
        worker_generation = -1
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                reading, generation = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                processor = self._processor
                recognizer = self._recognizer
                if processor is None or recognizer is None:
                    raise RuntimeError("inference worker was not initialized")
                if generation != worker_generation:
                    if worker_generation >= 0:
                        processor.reset_all()
                    worker_generation = generation

                window = processor.add(reading)
                with self._lock:
                    self._counters["processed_samples"] += 1
                if window is not None:
                    prediction = recognizer.predict(window)
                    with self._lock:
                        self._counters["windows_classified"] += 1
                    inserted = self._prediction_store(asdict(prediction))
                    with self._lock:
                        if inserted:
                            self._counters["predictions_stored"] += 1
                        else:
                            self._counters["duplicate_predictions"] += 1
            except Exception as error:
                with self._lock:
                    self._counters["inference_errors"] += 1
                    self._last_error = f"inference processing failed: {error}"[:500]
                LOGGER.exception("Activity inference failed; raw sensor ingestion continues")
            finally:
                self._queue.task_done()

        with self._lock:
            if self._status != "unavailable":
                self._status = "stopped"

    def stop(self, timeout_seconds: float = 5.0) -> bool:
        with self._lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                self._lifecycle_generation += 1
                if self._status != "unavailable":
                    self._status = "stopped"
                return True
            self._status = "stopping"
            self._stop_event.set()

        thread.join(timeout_seconds)
        stopped = not thread.is_alive()
        with self._lock:
            if stopped:
                self._thread = None
                self._status = "stopped"
            else:
                self._last_error = "worker did not stop before timeout"
        return stopped

    def status(self) -> dict[str, Any]:
        with self._lock:
            processor_status = self._processor.status() if self._processor else {}
            recognizer = self._recognizer
            return {
                "status": self._status,
                "model_loaded": recognizer is not None,
                "model_version": recognizer.model_version if recognizer else None,
                "queue_depth": self._queue.qsize(),
                "queue_capacity": self._queue.maxsize,
                **self._counters,
                **processor_status,
                "last_error": self._last_error,
            }

