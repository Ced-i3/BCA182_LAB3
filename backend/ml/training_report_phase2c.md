# Phase 2C Corrected Evaluation Report

## Corrected window construction

Windows use 10 consecutive samples, stride 5 (50% overlap), nominally 2 seconds at 5 Hz. Segments break only at date changes, wrist changes, non-positive timestamp intervals, or gaps over 0.6 seconds. Activity labels are not read by the segmentation logic. Each window is labeled by the majority of its ten row labels; an exact tie uses the sixth sample's label. Mixed windows remain included and are also evaluated separately.

Total data rows: 88,588; inferred continuity segments: 499; median positive sample interval: 0.2000 seconds. Units remain unverified and no conversion was applied.

The source labels are clustered by recording conditions: 4 dates contain only one activity (2017-7-10, 2017-7-11, 2017-7-16, 2017-7-7). On 2017-7-17, walking occurs only at wrist value 0 and running only at wrist value 1. There are 10 within-date/wrist label changes; 0 occur at or below the 0.6s continuity threshold and 10 occur after a larger gap. Thus the current dataset produced no mixed windows; transition performance is unavailable, not omitted.

## Date-grouped windows

The Phase 2B date assignment was retained unchanged. The test dates were previously examined in Phase 2B, so all test results below are diagnostic and are not independent final generalization evidence.

| Split | Dates | Total windows | Walking target | Running target | Mixed windows | Ties |
|---|---|---:|---:|---:|---:|---:|
| train | 2017-6-30, 2017-7-2, 2017-7-4, 2017-7-6, 2017-7-7, 2017-7-9, 2017-7-10, 2017-7-11 | 8389 | 3000 | 5389 | 0 | 0 |
| validation | 2017-7-15, 2017-7-16 | 5572 | 4148 | 1424 | 0 | 0 |
| test | 2017-7-1, 2017-7-17 | 2965 | 1400 | 1565 | 0 | 0 |

No date appears in more than one split. Candidate tree depths were selected using validation macro F1 only. The preferred approach was selected using validation macro F1 only; test results did not affect that choice.

| Feature approach | Depth | Validation macro F1 |
|---|---:|---:|
| six_axis | 1 | 0.9998 |
| six_axis | 2 | 0.9998 |
| six_axis | 3 | 0.9998 |
| six_axis | 4 | 0.9998 |
| six_axis | 5 | 0.9998 |
| six_axis | 6 | 0.9998 |
| six_axis | 8 | 0.9998 |
| six_axis | 10 | 0.9998 |
| magnitude | 1 | 0.9360 |
| magnitude | 2 | 0.9193 |
| magnitude | 3 | 0.9335 |
| magnitude | 4 | 0.9480 |
| magnitude | 5 | 0.9342 |
| magnitude | 6 | 0.9339 |
| magnitude | 8 | 0.9375 |
| magnitude | 10 | 0.9222 |

Selected approach: **six_axis**, depth **1**, validation macro F1 **0.9998**. The magnitude approach computes acceleration norm and gyroscope norm per sample, then extracts mean/std/min/max (8 features). The six-axis approach uses the original six axes and the same statistics (24 features).

## Diagnostic test results

Confusion matrices use rows actual `[walking, running]` and columns predicted `[walking, running]`.

| Approach | Accuracy, macro F1, confusion matrix | Per-class precision/recall/F1 and support |
|---|---|---|
| six_axis | accuracy=0.9997, macro-F1=0.9997, confusion=[[TN, FP], [FN, TP]]=[[1400, 0], [1, 1564]] | walking P/R/F1=0.999/1.000/1.000 (n=1400), running P/R/F1=1.000/0.999/1.000 (n=1565) |
| magnitude | accuracy=0.9700, macro-F1=0.9698, confusion=[[TN, FP], [FN, TP]]=[[1322, 78], [11, 1554]] | walking P/R/F1=0.992/0.944/0.967 (n=1400), running P/R/F1=0.952/0.993/0.972 (n=1565) |
| majority_baseline | accuracy=0.5278, macro-F1=0.3455, confusion=[[TN, FP], [FN, TP]]=[[0, 1400], [0, 1565]] | walking P/R/F1=0.000/0.000/0.000 (n=1400), running P/R/F1=0.528/1.000/0.691 (n=1565) |

Majority baseline always predicts the majority training-window label (running).

### Mixed-activity test windows

Mixed windows are included in the overall results above. This separate view shows how they performed. Counts and targets use the majority/tie rule stated above.

| Approach | Accuracy, macro F1, confusion matrix | Per-class precision/recall/F1 and support |
|---|---|---|
| six_axis | N/A (no windows in this subset) | N/A (no windows in this subset) |
| magnitude | N/A (no windows in this subset) | N/A (no windows in this subset) |
| majority_baseline | N/A (no windows in this subset) | N/A (no windows in this subset) |

Pure-window metrics (reported for context):

- six_axis: accuracy=0.9997, macro-F1=0.9997, confusion=[[TN, FP], [FN, TP]]=[[1400, 0], [1, 1564]]
- magnitude: accuracy=0.9700, macro-F1=0.9698, confusion=[[TN, FP], [FN, TP]]=[[1322, 78], [11, 1554]]

### Test differences by date and wrist

Subgroups may contain only one class; their macro F1 should be interpreted with the displayed class counts.

| Group | Approach | Windows | Walking | Running | Mixed | Accuracy | Macro F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| date 2017-7-1 | six_axis | 701 | 495 | 206 | 0 | 0.9986 | 0.9983 |
| date 2017-7-1 | magnitude | 701 | 495 | 206 | 0 | 0.9957 | 0.9949 |
| date 2017-7-17 | six_axis | 2264 | 905 | 1359 | 0 | 1.0000 | 1.0000 |
| date 2017-7-17 | magnitude | 2264 | 905 | 1359 | 0 | 0.9620 | 0.9599 |
| wrist 0 | six_axis | 1606 | 1400 | 206 | 0 | 0.9994 | 0.9986 |
| wrist 0 | magnitude | 1606 | 1400 | 206 | 0 | 0.9508 | 0.9047 |
| wrist 1 | six_axis | 1359 | 0 | 1359 | 0 | 1.0000 | 0.5000 |
| wrist 1 | magnitude | 1359 | 0 | 1359 | 0 | 0.9926 | 0.4982 |

## Saved model check

Selected artifact was saved, reloaded with joblib, and used to predict a test-date window. Reload prediction: label **0**; feature count **24**. The selected approach configuration records the matching feature order.

## Limitations

- The original test dates have already been evaluated in Phase 2B and are reused only for diagnosis. Do not describe these revised scores as an untouched final test.
- There is one participant and no validation on the RT-Spark/ICM-20608-G hardware. Generalization to new people, placements, devices, and firmware sampling behavior remains unknown.
- Acceleration and gyroscope units and original sensor placement/orientation are not verified. Magnitudes reduce dependence on axis orientation, but do not resolve scale, gravity handling, sensor calibration, or device differences.
- Magnitude features can discard useful directional information. Validation performance guides the selection, but dates are few and the labels are correlated with date/wrist conditions.
- Fixed sample-count windows are nominally 2 seconds; actual duration varies with timestamps. Label-majority windows near transitions are inherently ambiguous.
