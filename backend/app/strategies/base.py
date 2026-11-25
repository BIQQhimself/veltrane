from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.providers.base import Candle

Action = Literal["buy", "sell", "exit", "hold"]


@dataclass(frozen=True)
class PositionState:
    side: str
    quantity: float
    entry_price: float
    bars_held: int = 0


@dataclass(frozen=True)
class Signal:
    action: Action
    reason: str
    stop_loss: float | None = None
    take_profit: float | None = None
    strength: float = 0.0
    meta: dict = field(default_factory=dict)


class Strategy:
    """Strategy contract.

    Implementations must be deterministic functions of the supplied candles. They may
    not perform I/O, read secrets or call the execution layer. The risk engine has the
    final say on every order, so a strategy can never bypass safeguards.
    """

    code: str = ""
    name: str = ""
    category: str = "technical"
    summary: str = ""
    version: int = 1
    supported_markets: list[str] = []
    timeframes: list[str] = []
    entry_rules: str = ""
    exit_rules: str = ""
    data_requirements: str = ""
    backtest_methodology: str = ""
    known_limitations: str = ""
    params_schema: dict = {}
    default_params: dict = {}
    risk_params: dict = {}
    min_bars: int = 50

    def generate(self, candles: list[Candle], params: dict, position: PositionState | None) -> Signal:
        raise NotImplementedError

    def warmup_bars(self, params: dict) -> int:
        return self.min_bars

    def describe(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "category": self.category,
            "summary": self.summary,
            "version": self.version,
            "supported_markets": self.supported_markets,
            "timeframes": self.timeframes,
            "entry_rules": self.entry_rules,
            "exit_rules": self.exit_rules,
            "data_requirements": self.data_requirements,
            "backtest_methodology": self.backtest_methodology,
            "known_limitations": self.known_limitations,
            "params_schema": self.params_schema,
            "default_params": self.default_params,
            "risk_params": self.risk_params,
        }
