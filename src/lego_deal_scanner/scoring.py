"""Turn a candidate listing + reference value into a profit verdict."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Optional

from .valuation import Reference, resale_value


@dataclass
class ScoreConfig:
    marketplace_fee_pct: float = 0.11
    payment_fee_pct: float = 0.0
    payment_fee_fixed: float = 0.0
    packaging_eur: float = 1.20
    resale_haircut_pct: float = 0.08
    assumed_shipping_in_eur: float = 5.49
    default_shipping_out_eur: float = 6.99
    shipping_out_by_weight: dict = field(default_factory=dict)
    refurb_cost_used_eur: float = 0.0
    min_profit_eur: float = 20.0
    min_roi: float = 0.30
    watch_roi: float = 0.15

    @classmethod
    def from_dict(cls, d: dict | None) -> "ScoreConfig":
        d = dict(d or {})
        allowed = {f.name for f in fields(cls)}
        kw = {k: v for k, v in d.items() if k in allowed}
        raw = kw.get("shipping_out_by_weight") or {}
        kw["shipping_out_by_weight"] = {int(k): float(v) for k, v in raw.items()}
        return cls(**kw)


@dataclass
class Deal:
    set_num: str
    name: str
    condition: str
    asking_eur: float
    shipping_in_eur: float
    resale_ref_eur: float
    expected_sale_eur: float
    selling_costs_eur: float
    acquisition_eur: float
    net_profit_eur: float
    roi: float
    margin: float
    verdict: str  # DEAL | WATCH | SKIP
    notes: list[str] = field(default_factory=list)


def _shipping_out(cfg: ScoreConfig, weight_g: Optional[int]) -> float:
    if weight_g and cfg.shipping_out_by_weight:
        for tier in sorted(cfg.shipping_out_by_weight):
            if weight_g <= tier:
                return float(cfg.shipping_out_by_weight[tier])
    return cfg.default_shipping_out_eur


def score(
    ref: Reference,
    condition: str,
    asking_eur: float,
    shipping_in_eur: float,
    cfg: ScoreConfig,
    prefer: str = "market",
    extra_notes: Optional[list[str]] = None,
) -> Optional[Deal]:
    """None when the set can't be valued; otherwise a Deal with a verdict."""
    ref_val = resale_value(ref, condition, prefer)
    if not ref_val or asking_eur is None or asking_eur <= 0:
        return None

    expected = ref_val * (1.0 - cfg.resale_haircut_pct)
    ship_out = _shipping_out(cfg, ref.weight_g)
    selling_costs = (
        expected * (cfg.marketplace_fee_pct + cfg.payment_fee_pct)
        + cfg.payment_fee_fixed
        + ship_out
        + cfg.packaging_eur
    )
    refurb = cfg.refurb_cost_used_eur if condition.startswith("used") else 0.0
    acquisition = asking_eur + shipping_in_eur + refurb
    net = expected - selling_costs - acquisition
    roi = net / acquisition if acquisition else 0.0
    margin = net / expected if expected else 0.0

    if net >= cfg.min_profit_eur and roi >= cfg.min_roi:
        verdict = "DEAL"
    elif net > 0 and roi >= cfg.watch_roi:
        verdict = "WATCH"
    else:
        verdict = "SKIP"

    notes = list(extra_notes or [])
    if condition == "unknown":
        notes.append("condition unknown - valued as used")
    if ref.weight_g is None:
        notes.append("weight unknown - default outbound shipping used")
    if ref.mv_new_eur is None and ref.mv_used_eur is None:
        notes.append("no market value in reference - RRP-derived estimate")

    return Deal(
        set_num=ref.set_num,
        name=ref.name,
        condition=condition,
        asking_eur=round(asking_eur, 2),
        shipping_in_eur=round(shipping_in_eur, 2),
        resale_ref_eur=round(ref_val, 2),
        expected_sale_eur=round(expected, 2),
        selling_costs_eur=round(selling_costs, 2),
        acquisition_eur=round(acquisition, 2),
        net_profit_eur=round(net, 2),
        roi=round(roi, 4),
        margin=round(margin, 4),
        verdict=verdict,
        notes=notes,
    )
