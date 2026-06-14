from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error


def linear_trend_forecast(
    frame: pd.DataFrame,
    *,
    time_column: str,
    target_column: str,
    periods: int = 3,
) -> tuple[pd.DataFrame, dict[str, float]]:
    if time_column not in frame.columns or target_column not in frame.columns:
        raise ValueError("forecast requires time and target columns")
    data = frame[[time_column, target_column]].dropna().copy()
    if data.empty:
        raise ValueError("forecast requires non-empty data")

    x_train = data[[time_column]].astype(float)
    y_train = data[target_column].astype(float)
    model = LinearRegression()
    model.fit(x_train, y_train)

    fitted = model.predict(x_train)
    last_period = float(x_train[time_column].max())
    future_periods = np.arange(last_period + 1, last_period + periods + 1, dtype=float)
    future_features = pd.DataFrame({time_column: future_periods})
    future = pd.DataFrame({"forecast_period": future_periods})
    future["forecast_value"] = model.predict(future_features[[time_column]])

    history = pd.DataFrame(
        {
            "forecast_period": x_train[time_column].to_numpy(dtype=float),
            "actual_value": y_train.to_numpy(dtype=float),
            "forecast_value": fitted,
            "is_forecast": False,
        }
    )
    future["actual_value"] = np.nan
    future["is_forecast"] = True
    output = pd.concat([history, future], ignore_index=True)
    output["forecast_value"] = output["forecast_value"].round(10)

    metrics = {
        "forecast_horizon": float(periods),
        "training_mae": float(mean_absolute_error(y_train, fitted)),
        "training_rmse": float(mean_squared_error(y_train, fitted) ** 0.5),
        "trend_slope": float(model.coef_[0]),
        "trend_intercept": float(model.intercept_),
    }
    return output, metrics
