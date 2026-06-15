from __future__ import annotations

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split


def logistic_regression_baseline(
    frame: pd.DataFrame,
    *,
    feature_columns: list[str],
    label_column: str,
) -> tuple[pd.DataFrame, dict[str, float]]:
    if label_column not in frame.columns:
        raise ValueError("classification requires a label column")
    features = [column for column in feature_columns if column in frame.columns]
    if not features:
        raise ValueError("classification requires feature columns")

    data = frame[[*features, label_column]].dropna().copy()
    if data.empty:
        raise ValueError("classification requires non-empty training rows")
    x = data[features].astype(float)
    y = data[label_column]
    result = frame.copy()
    if y.nunique(dropna=True) < 2:
        label = y.iloc[0]
        result["predicted_label"] = label
        result["predicted_probability"] = 1.0
        return result, {
            "classification_accuracy": 1.0,
            "classification_f1": 1.0,
            "classification_train_rows": float(len(data)),
        }

    stratify = y if y.value_counts().min() >= 2 and len(data) >= 6 else None
    if len(data) >= 4:
        x_train, x_test, y_train, y_test = train_test_split(
            x,
            y,
            test_size=0.33,
            random_state=42,
            stratify=stratify,
        )
    else:
        x_train, x_test, y_train, y_test = x, x, y, y
    model = LogisticRegression(max_iter=1000)
    model.fit(x_train, y_train)
    test_prediction = model.predict(x_test)
    all_prediction = model.predict(frame[features].fillna(0).astype(float))
    result["predicted_label"] = all_prediction
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(frame[features].fillna(0).astype(float))
        result["predicted_probability"] = probabilities.max(axis=1)
    else:
        result["predicted_probability"] = 1.0

    average = "binary" if y.nunique(dropna=True) == 2 else "weighted"
    return result, {
        "classification_accuracy": float(accuracy_score(y_test, test_prediction)),
        "classification_f1": float(f1_score(y_test, test_prediction, average=average)),
        "classification_train_rows": float(len(x_train)),
    }
