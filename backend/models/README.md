# Included corrected activity model

`activity_model_corrected.joblib` is the existing trained
`DecisionTreeClassifier`; it is included with the project owner's explicit
redistribution authorization for this repository. That authorization is a
project decision, **not** an independent determination of the Run-or-Walk
dataset's third-party license. The original CSV dataset is excluded pending
separate redistribution permission. The older model artifact is not used by
the backend and is excluded from the publication baseline.

- File size: 1,513 bytes.
- SHA-256: `85200d80466093a98ded077b4c02ea11f3c030eebb935224e0da806472b7d82f`.
- Required metadata: `activity_preprocessing_corrected.json`.
- Verified runtime: Python 3.13, NumPy 2.5.3, scikit-learn 1.9.1, joblib 1.6.0.
- Model contract: 24 ordered features from six axes, using mean, population
  standard deviation, minimum, and maximum over ten samples. Class 0 maps to
  WALKING and class 1 to RUNNING. A separate backend rule detects IDLE first.

The training script is `../ml/train_activity_model_phase2c.py`; its report is
`../ml/training_report_phase2c.md`. Training used the Run-or-Walk dataset,
date-grouped windows, a 10-sample window, stride 5, and validation selection
of a depth-1 six-axis Decision Tree. The dataset has one participant, and its
sensor units and orientation are undocumented. The reported offline score is
diagnostic; walking/running accuracy on the RT-Spark is **not validated**.
No retraining is needed to run the included artifact.

Only load this `.joblib` file from a trusted checkout. Joblib deserialization
can execute code; verify the file hash when obtaining the repository from an
untrusted source. Do not load arbitrary replacement model files.
