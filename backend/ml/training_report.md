# Phase 2B Training Report

## Dataset and windows

- Source: `data/archive/dataset.csv`; 88,588 rows, 12 dates, one participant.
- Labels: 0 = walking, 1 = running. Raw row totals: 44,223 walking and 44,365 running.
- Missing values in required columns: 0. Sensor values are retained as recorded; acceleration and gyroscope units could not be verified from available provenance, so no unit conversion was applied.
- Observed median positive sample interval: 0.2000 s (about 5.00 Hz). Window: 10 readings (nominal 2.0 s at 5.0 Hz), stride 5 readings (50% overlap).
- A segment ends at a date, wrist, or activity change; a non-positive timestamp interval; or a gap over 0.6 s. Windows are formed only inside segments.
- Total contiguous segments: 499. Feature vector: 24 values (mean, population standard deviation, minimum, maximum for each of six axes).

## Date-grouped split

No date occurs in more than one split. The date lists were fixed before depth selection.

| Split | Dates | Windows | Walking | Running |
|---|---|---:|---:|---:|
| train | 2017-6-30, 2017-7-2, 2017-7-4, 2017-7-6, 2017-7-7, 2017-7-9, 2017-7-10, 2017-7-11 | 8389 | 3000 | 5389 |
| validation | 2017-7-15, 2017-7-16 | 5572 | 4148 | 1424 |
| test | 2017-7-1, 2017-7-17 | 2965 | 1400 | 1565 |

## Model selection and test results

Decision Tree with fixed `random_state=42`. Maximum depth was selected using validation macro F1; the test set was not used for selection. Validation scores:

| Maximum depth | Validation macro F1 |
|---:|---:|
| 2 | 0.9998 |
| 3 | 0.9998 |
| 4 | 0.9998 |
| 5 | 0.9998 |
| 6 | 0.9998 |
| 8 | 0.9998 |
| 10 | 0.9998 |

Selected maximum depth: **2** (validation macro F1 0.9998). The test-set majority baseline predicts **running**, based on training windows.

- Decision Tree: Accuracy 0.9997; precision (running) 1.0000; recall (running) 0.9994; F1 (running) 0.9997; confusion matrix [[TN, FP], [FN, TP]] = [[1400, 0], [1, 1564]]
- Majority baseline: Accuracy 0.5278; precision (running) 0.5278; recall (running) 1.0000; F1 (running) 0.6909; confusion matrix [[TN, FP], [FN, TP]] = [[0, 1400], [0, 1565]]
- Confusion matrix rows are actual `[walking, running]`; columns are predicted `[walking, running]`.
- Saved-model reload/inference check: **passed**; loaded model predictions matched the trained model on all 2,965 test windows.

## Limitations

- The dataset contains one participant. Date grouping helps prevent overlapping-window leakage across recording dates, but does not establish generalization to new people or RT-Spark hardware.
- Date is the only reliable recording-group metadata; separate sessions within a date are inferred from timestamps and metadata transitions.
- Sensor units and the exact original phone/sensor configuration are unverified. The saved model expects features in the same raw scale and axis orientation as this dataset. Before hardware integration, confirm the source units and calibrate/convert RT-Spark readings accordingly.
- Windows are sample-count based. The 2-second duration is nominal because sampling intervals vary; windows never bridge a gap over 0.6 s.
