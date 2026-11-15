from typing import List, Optional
from models.market_data import OptionsChain, OptionContract
from pydantic import BaseModel
from collections import defaultdict
from datetime import date

class GEXProfile(BaseModel):
    net_gex: float
    gamma_flip: Optional[float]
    call_wall: Optional[float]
    put_wall: Optional[float]
    sorted_strikes: List[float]

def calculate_gex_profile(chain: OptionsChain, max_dte: int = 45, min_oi: int = 10) -> GEXProfile:
    if not chain or not chain.contracts:
        return GEXProfile(net_gex=0.0, gamma_flip=None, call_wall=None, put_wall=None, sorted_strikes=[])
        
    today = date.today()
    valid_contracts = [
        c for c in chain.contracts 
        if c.gamma and c.gamma > 0 
        and (c.expiration - today).days <= max_dte
        and (c.open_interest or 0) >= min_oi
    ]
    
    spot = chain.underlying.price
    if spot <= 0 or not valid_contracts:
        return GEXProfile(net_gex=0.0, gamma_flip=None, call_wall=None, put_wall=None, sorted_strikes=[])

    strike_gex = defaultdict(float)
    call_gex_by_strike = defaultdict(float)
    put_gex_by_strike = defaultdict(float)
    
    total_net_gex = 0.0
    
    for c in valid_contracts:
        oi = c.open_interest or 0
        # Standard Dealer GEX formula for a 1% underlying move
        gex = c.gamma * oi * 100 * (spot ** 2) * 0.01
        
        if c.option_type == "call":
            strike_gex[c.strike] += gex
            call_gex_by_strike[c.strike] += gex
            total_net_gex += gex
        else:
            strike_gex[c.strike] -= gex
            put_gex_by_strike[c.strike] -= gex
            total_net_gex -= gex
            
    sorted_strikes = sorted(strike_gex.keys())
    
    call_wall = max(call_gex_by_strike, key=call_gex_by_strike.get) if call_gex_by_strike else None
    put_wall = min(put_gex_by_strike, key=put_gex_by_strike.get) if put_gex_by_strike else None

    # STEPS 2 & 3: Mathematically correct Gamma Flip (Zero-Crossing)
    gamma_flip = None
    cumulative = 0.0
    
    for strike in sorted_strikes:
        prev = cumulative
        cumulative += strike_gex[strike]
        
        # Sign change detection
        if prev < 0 <= cumulative or prev > 0 >= cumulative:
            gamma_flip = strike
            break
            
    return GEXProfile(
        net_gex=total_net_gex,
        gamma_flip=gamma_flip,
        call_wall=call_wall,
        put_wall=put_wall,
        sorted_strikes=sorted_strikes
    )