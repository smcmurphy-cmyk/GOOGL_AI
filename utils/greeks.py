from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple
from models.market_data import OptionsChain

@dataclass
class StrikeGEX:
    strike: float
    net_gex: float
    call_gex: float
    put_gex: float
    total_oi: int
    contracts: int

@dataclass
class GEXProfile:
    by_strike: Dict[float, StrikeGEX]
    sorted_strikes: List[StrikeGEX]
    net_gex: float
    primary_pin_strike: Optional[float]
    volatility_wall_strike: Optional[float]
    call_wall: Optional[float]
    put_wall: Optional[float]
    gamma_flip: Optional[float]

def calculate_gex_profile(
    chain: OptionsChain,
    max_dte: Optional[int] = 45,
    min_oi: int = 10,
) -> GEXProfile:
   # FIX: Use dot notation to access the Pydantic object's attributes
    spot = chain.underlying.price
    timestamp_str = chain.underlying.timestamp
    today = date.fromisoformat(timestamp_str.split('T')[0]) if timestamp_str else date.today()

    if not spot or spot <= 0:
        return GEXProfile({}, [], 0.0, None, None, None, None, None)

    buckets: Dict[float, dict] = defaultdict(lambda: {
        "call_gex": 0.0, "put_gex": 0.0, "oi": 0, "n": 0
    })

    for c in chain.contracts:
        if c.gamma is None or c.gamma <= 0:
            continue
        oi = c.open_interest or 0
        if oi < min_oi:
            continue
        dte = (c.expiration - today).days
        if dte < 0 or (max_dte is not None and dte > max_dte):
            continue

        # The improved 1% move formula
        gex = c.gamma * oi * 100 * (spot ** 2) * 0.01

        if c.option_type == "call":
            buckets[c.strike]["call_gex"] += gex
        else:
            buckets[c.strike]["put_gex"] -= gex 

        buckets[c.strike]["oi"] += oi
        buckets[c.strike]["n"] += 1

    by_strike: Dict[float, StrikeGEX] = {}
    for k, v in buckets.items():
        net = v["call_gex"] + v["put_gex"]
        by_strike[k] = StrikeGEX(
            strike=k, net_gex=net, call_gex=v["call_gex"],
            put_gex=v["put_gex"], total_oi=v["oi"], contracts=v["n"]
        )

    sorted_strikes = sorted(by_strike.values(), key=lambda x: x.strike)
    net_gex = sum(s.net_gex for s in sorted_strikes)

    # Calculate levels
    primary_pin = max(sorted_strikes, key=lambda x: x.net_gex).strike if sorted_strikes else None
    vol_wall = min(sorted_strikes, key=lambda x: x.net_gex).strike if sorted_strikes else None
    call_wall = max(sorted_strikes, key=lambda x: x.call_gex).strike if sorted_strikes else None
    put_wall = min(sorted_strikes, key=lambda x: x.put_gex).strike if sorted_strikes else None

    # Calculate Gamma Flip
    gamma_flip = None
    cumul = 0.0
    for s in sorted_strikes:
        prev = cumul
        cumul += s.net_gex
        if prev < 0 <= cumul or prev > 0 >= cumul:
            gamma_flip = s.strike
            break

    return GEXProfile(
        by_strike=by_strike, sorted_strikes=sorted_strikes, net_gex=net_gex,
        primary_pin_strike=primary_pin, volatility_wall_strike=vol_wall,
        call_wall=call_wall, put_wall=put_wall, gamma_flip=gamma_flip
    )

def calculate_iv_rank(
    current_iv: Optional[float],
    historical_iv_low: float,
    historical_iv_high: float,
) -> Optional[float]:
    if historical_iv_high <= historical_iv_low or current_iv is None:
        return None

    rank = (current_iv - historical_iv_low) / (historical_iv_high - historical_iv_low) * 100.0
    return max(0.0, min(100.0, rank))
