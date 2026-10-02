"""A6 cost model (single source of truth for all fee math).

All rates are fractions of traded value. GST applies to exchange + SEBI
charges. DP charge is a flat rupee fee on the sell leg. Slippage is charged
as an extra fraction on both legs. Adding a broker is a matter of editing the
`costs` block in config/protocol_v2.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor


@dataclass(frozen=True)
class CostModel:
    brokerage: float = 0.0
    stt: float = 0.001
    stamp: float = 0.00015
    exch_txn: float = 0.0000297
    sebi: float = 0.000001
    gst: float = 0.18
    dp_charge: float = 15.93
    slippage: float = 0.001

    @classmethod
    def from_config(cls, cfg: dict) -> "CostModel":
        block = cfg.get("costs", {})
        allowed = {f: float(block[f]) for f in cls.__dataclass_fields__ if f in block}
        return cls(**allowed)

    def _gst_on(self, base_rate: float) -> float:
        return self.gst * (self.exch_txn + self.sebi) if base_rate else 0.0

    @property
    def buy_rate(self) -> float:
        """Fractional cost added on top of the buy notional."""
        gst = self.gst * (self.exch_txn + self.sebi)
        return self.brokerage + self.stt + self.stamp + self.exch_txn + self.sebi + gst + self.slippage

    @property
    def sell_rate(self) -> float:
        """Fractional cost deducted from the sell notional (excl. flat DP)."""
        gst = self.gst * (self.exch_txn + self.sebi)
        return self.brokerage + self.stt + self.exch_txn + self.sebi + gst + self.slippage

    def buy_cost(self, price: float, shares: int) -> float:
        value = price * shares
        return value * self.buy_rate

    def sell_net(self, price: float, shares: int) -> float:
        value = price * shares
        return value - value * self.sell_rate - self.dp_charge

    def target_price(self, entry_px: float, shares: int, target_net: float) -> float:
        """Exit price where NET P&L equals `target_net` of the buy outlay."""
        buy_value = entry_px * shares
        invest = buy_value + buy_value * self.buy_rate
        want = invest * (1.0 + target_net) + self.dp_charge
        return want / (shares * (1.0 - self.sell_rate))

    def net_pnl_pct(self, entry_px: float, exit_px: float, shares: int) -> float:
        buy_value = entry_px * shares
        invest = buy_value + buy_value * self.buy_rate
        proceeds = self.sell_net(exit_px, shares)
        return (proceeds - invest) / invest


def shares_affordable(capital: float, price: float, model: CostModel) -> int:
    """Largest share count whose total buy outlay fits inside `capital`."""
    if price <= 0:
        return 0
    return int(floor(capital / (price * (1.0 + model.buy_rate))))
