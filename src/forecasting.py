from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


def _history_to_1d_array(history: np.ndarray) -> np.ndarray:
    values = np.asarray(history, dtype=float).reshape(-1)
    return values[np.isfinite(values)]


class Forecaster(ABC):
    """Common interface for demand forecasters used by cluster policies."""

    @abstractmethod
    def forecast(self, history: np.ndarray) -> float:
        """Predict the next demand value from the available history."""

    def __call__(self, history: np.ndarray) -> float:
        return self.forecast(history)


@dataclass(frozen=True, kw_only=True)
class LastValueForecaster(Forecaster):
    """Uses the most recent observation as the next-step forecast."""

    def forecast(self, history: np.ndarray) -> float:
        values = _history_to_1d_array(history)
        if len(values) == 0:
            return 0.0
        return float(values[-1])


@dataclass(frozen=True, kw_only=True, init=False)
class MovingAverageForecaster(Forecaster):
    """Averages the latest observations to smooth short-term noise."""

    _window: int = field(default=4)

    def __init__(self, *, window: int = 4) -> None:
        if window <= 0:
            raise ValueError("window must be positive")
        object.__setattr__(self, "_window", window)

    def get_window(self) -> int:
        return self._window

    def forecast(self, history: np.ndarray) -> float:
        values = _history_to_1d_array(history)
        if len(values) == 0:
            return 0.0
        tail = values[-self._window:]
        return float(np.mean(tail))


@dataclass(frozen=True, kw_only=True, init=False)
class EwmaForecaster(Forecaster):
    """Exponential smoothing for short-horizon forecasting."""

    _alpha: float = field(default=0.35)

    def __init__(self, *, alpha: float = 0.35) -> None:
        if not (0.0 < alpha <= 1.0):
            raise ValueError("alpha must be between 0 and 1")
        object.__setattr__(self, "_alpha", alpha)

    def get_alpha(self) -> float:
        return self._alpha

    def forecast(self, history: np.ndarray) -> float:
        values = _history_to_1d_array(history)
        if len(values) == 0:
            return 0.0
        x = values[0]
        for value in values[1:]:
            x = self._alpha * value + (1.0 - self._alpha) * x
        return float(x)


@dataclass(frozen=True, kw_only=True, init=False)
class LinearTrendForecaster(Forecaster):
    """Fits a simple line over the latest observations and extrapolates one step."""

    _window: int = field(default=8)

    def __init__(self, *, window: int = 8) -> None:
        if window < 2:
            raise ValueError("window must be at least 2")
        object.__setattr__(self, "_window", window)

    def get_window(self) -> int:
        return self._window

    def forecast(self, history: np.ndarray) -> float:
        values = _history_to_1d_array(history)
        if len(values) == 0:
            return 0.0
        if len(values) == 1:
            return float(values[-1])

        tail = values[-self._window:]
        x = np.arange(len(tail), dtype=float)
        slope, intercept = np.polyfit(x, tail, deg=1)
        forecast = intercept + slope * len(tail)
        return float(max(0.0, forecast))


__all__ = [
    "Forecaster",
    "LastValueForecaster",
    "MovingAverageForecaster",
    "EwmaForecaster",
    "LinearTrendForecaster",
]
