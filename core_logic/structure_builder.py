from typing import List, Optional
from datetime import date
from models.market_data import OptionsChain, OptionContract
from models.regime import RegimeState
from models.structures import OptionStructure, Leg

def get_nearest_liquid_contract(contracts: List[OptionContract], target_strike: float, min_bid: float = 0.10, min_oi: int = 15) -> Optional[OptionContract]:
    """Finds the most liquid contract closest to the GEX topography target."""
    valid_contracts = [c for c in contracts if c.bid >= min_bid and (c.open_interest or 0) >= min_oi]
    if not valid_contracts:
        return None
    # Sort by absolute distance to the target strike and return the closest one
    return min(valid_contracts, key=lambda c: abs(c.strike - target_strike))

def get_wing_contract(contracts: List[OptionContract], short_strike: float, direction: str, min_width: float = 1.0) -> Optional[OptionContract]:
    """Dynamically finds the next available strike to act as the defined-risk wing."""
    if direction == "up":
        candidates = [c for c in contracts if c.strike >= short_strike + min_width]
        return min(candidates, key=lambda c: c.strike) if candidates else None
    else:
        candidates = [c for c in contracts if c.strike <= short_strike - min_width]
        return max(candidates, key=lambda c: c.strike) if candidates else None

def generate_structures(chain: OptionsChain, regime: RegimeState) -> List[OptionStructure]:
    """
    Constructs defined-risk vertical spreads (Credit/Debit) using GEX Topography mapping.
    """
    structures = []
    
    # 10 DTE window to capture liquid Friday OPEX walls
    target_dte = 10 
    today = date.today()
    
    valid_calls = [c for c in chain.contracts if c.option_type == "call" and (c.expiration - today).days <= target_dte]
    valid_puts = [c for c in chain.contracts if c.option_type == "put" and (c.expiration - today).days <= target_dte]
    
    if not valid_calls or not valid_puts:
        return structures

    # ---------------------------------------------------------
    # REGIME: MEAN REVERSION or PINNED (Fading the extremes)
    # ---------------------------------------------------------
    if regime.regime_type in ["MEAN_REVERSION", "PINNED_BULLISH", "PINNED_BEARISH"]:
        
        # 1. Bear Call Credit Spread (Fading the Call Wall)
        if regime.call_wall:
            short_call = get_nearest_liquid_contract(valid_calls, regime.call_wall)
            if short_call:
                long_call = get_wing_contract(valid_calls, short_call.strike, "up")
                
                if long_call and short_call.bid > long_call.ask:
                    net_credit = short_call.bid - long_call.ask
                    width = long_call.strike - short_call.strike
                    structures.append(OptionStructure(
                        strategy_type="Bear Call Spread",
                        legs=[
                            Leg(contract=short_call, action="SELL", ratio=1),
                            Leg(contract=long_call, action="BUY", ratio=1)
                        ],
                        net_premium=net_credit,
                        max_risk=(width - net_credit) * 100,
                        probability_of_profit=1.0 - abs(short_call.delta if short_call.delta else 0.5)
                    ))
                    
        # 2. Bull Put Credit Spread (Fading the Put Wall)
        if regime.put_wall:
            short_put = get_nearest_liquid_contract(valid_puts, regime.put_wall)
            if short_put:
                long_put = get_wing_contract(valid_puts, short_put.strike, "down")
                
                if long_put and short_put.bid > long_put.ask:
                    net_credit = short_put.bid - long_put.ask
                    width = short_put.strike - long_put.strike
                    structures.append(OptionStructure(
                        strategy_type="Bull Put Spread",
                        legs=[
                            Leg(contract=short_put, action="SELL", ratio=1),
                            Leg(contract=long_put, action="BUY", ratio=1)
                        ],
                        net_premium=net_credit,
                        max_risk=(width - net_credit) * 100,
                        probability_of_profit=1.0 - abs(short_put.delta if short_put.delta else 0.5)
                    ))

    # ---------------------------------------------------------
    # REGIME: DIRECTIONAL BREAKOUT (Riding the momentum)
    # ---------------------------------------------------------
    elif regime.regime_type == "DIRECTIONAL_BREAKOUT" and regime.gamma_flip:
        spot = chain.underlying.price
        
        # 1. Bearish Breakout (Spot drops below Flip Line)
        if spot < regime.gamma_flip:
            long_put = get_nearest_liquid_contract(valid_puts, regime.gamma_flip)
            if long_put:
                short_put = get_wing_contract(valid_puts, long_put.strike, "down")
                
                if short_put and long_put.ask > short_put.bid:
                    net_debit = long_put.ask - short_put.bid
                    width = long_put.strike - short_put.strike
                    
                    if net_debit < width: # Valid spread pricing check
                        structures.append(OptionStructure(
                            strategy_type="Bear Put Debit Spread",
                            legs=[
                                Leg(contract=long_put, action="BUY", ratio=1),
                                Leg(contract=short_put, action="SELL", ratio=1)
                            ],
                            net_premium=-net_debit, # Negative to mathematically separate cost from credit
                            max_risk=net_debit * 100,
                            probability_of_profit=abs(long_put.delta if long_put.delta else 0.5)
                        ))

        # 2. Bullish Breakout (Spot breaks above Flip Line)
        elif spot > regime.gamma_flip:
            long_call = get_nearest_liquid_contract(valid_calls, regime.gamma_flip)
            if long_call:
                short_call = get_wing_contract(valid_calls, long_call.strike, "up")
                
                if short_call and long_call.ask > short_call.bid:
                    net_debit = long_call.ask - short_call.bid
                    width = short_call.strike - long_call.strike
                    
                    if net_debit < width: # Valid spread pricing check
                        structures.append(OptionStructure(
                            strategy_type="Bull Call Debit Spread",
                            legs=[
                                Leg(contract=long_call, action="BUY", ratio=1),
                                Leg(contract=short_call, action="SELL", ratio=1)
                            ],
                            net_premium=-net_debit, # Negative to mathematically separate cost from credit
                            max_risk=net_debit * 100,
                            probability_of_profit=abs(long_call.delta if long_call.delta else 0.5)
                        ))

    return structures