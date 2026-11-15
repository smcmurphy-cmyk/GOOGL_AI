from datetime import date
from typing import List
from models.market_data import OptionsChain, OptionContract
from models.structures import OptionStructure, Leg
from models.regime import RegimeState

def get_nearest_liquid_contract(contracts: List[OptionContract], target_strike: float) -> OptionContract:
    """Finds the contract closest to the target strike, prioritizing volume if equidistant."""
    if not contracts:
        return None
    return sorted(contracts, key=lambda c: (abs(c.strike - target_strike), -(c.volume or 0)))[0]

def get_wing_contract(contracts: List[OptionContract], short_strike: float, direction: str, width: float = 5.0) -> OptionContract:
    """Selects the protective wing contract dynamically based on width."""
    target = short_strike + width if direction == "up" else short_strike - width
    return get_nearest_liquid_contract(contracts, target)

def generate_structures(chain: OptionsChain, regime: RegimeState) -> List[OptionStructure]:
    structures = []
    today = date.today()
    
    # P2.9: Strict 0-3 DTE Scalping Window
    valid_calls = [c for c in chain.contracts if c.option_type == "call" and 0 <= (c.expiration - today).days <= 3]
    valid_puts = [c for c in chain.contracts if c.option_type == "put" and 0 <= (c.expiration - today).days <= 3]
    
    if not valid_calls or not valid_puts:
        return structures

    # P0.1 & P1.6: MEAN REVERSION (Credit Spreads at Walls)
    if regime.regime_type == "MEAN_REVERSION":
        
        # Bear Call Spread @ Call Wall
        if regime.call_wall:
            short_call = get_nearest_liquid_contract(valid_calls, regime.call_wall)
            # Enforce 15-35 Delta Band
            if short_call and short_call.delta and 0.15 <= abs(short_call.delta) <= 0.35:
                long_call = get_wing_contract(valid_calls, short_call.strike, "up")
                if long_call and short_call.bid > long_call.ask:
                    net_credit = short_call.bid - long_call.ask
                    width = long_call.strike - short_call.strike
                    # Enforce >= 30% Credit-to-Width Ratio
                    if width > 0 and (net_credit / width) >= 0.30: 
                        structures.append(OptionStructure(
                            strategy_type="Bear Call Spread",
                            legs=[Leg(contract=short_call, action="SELL", ratio=1), Leg(contract=long_call, action="BUY", ratio=1)],
                            net_premium=net_credit,
                            max_risk=(width - net_credit) * 100,
                            probability_of_profit=1.0 - abs(short_call.delta)
                        ))
        
        # Bull Put Spread @ Put Wall
        if regime.put_wall:
            short_put = get_nearest_liquid_contract(valid_puts, regime.put_wall)
            # Enforce 15-35 Delta Band
            if short_put and short_put.delta and 0.15 <= abs(short_put.delta) <= 0.35:
                long_put = get_wing_contract(valid_puts, short_put.strike, "down")
                if long_put and short_put.bid > long_put.ask:
                    net_credit = short_put.bid - long_put.ask
                    width = short_put.strike - long_put.strike
                    # Enforce >= 30% Credit-to-Width Ratio
                    if width > 0 and (net_credit / width) >= 0.30:
                        structures.append(OptionStructure(
                            strategy_type="Bull Put Spread",
                            legs=[Leg(contract=short_put, action="SELL", ratio=1), Leg(contract=long_put, action="BUY", ratio=1)],
                            net_premium=net_credit,
                            max_risk=(width - net_credit) * 100,
                            probability_of_profit=1.0 - abs(short_put.delta)
                        ))
    
    # DIRECTIONAL BREAKOUT (Debit Spreads at Gamma Flip)
    elif regime.regime_type == "DIRECTIONAL_BREAKOUT" and regime.gamma_flip:
        spot = chain.underlying.get("price", 0.0)
        
        # Spot below flip: Downward Momentum -> Bear Put Debit
        if spot < regime.gamma_flip:
            long_put = get_nearest_liquid_contract(valid_puts, spot) 
            if long_put:
                short_put = get_wing_contract(valid_puts, long_put.strike, "down")
                if short_put and long_put.ask > short_put.bid:
                    net_debit = long_put.ask - short_put.bid
                    width = long_put.strike - short_put.strike
                    # Enforce max 50% debit-to-width ratio for >1:1 R/R
                    if width > 0 and (net_debit / width) <= 0.50:
                        structures.append(OptionStructure(
                            strategy_type="Bear Put Debit Spread",
                            legs=[Leg(contract=long_put, action="BUY", ratio=1), Leg(contract=short_put, action="SELL", ratio=1)],
                            net_premium=-net_debit,  # Negative for debit
                            max_risk=net_debit * 100,
                            probability_of_profit=0.50 # Standard proxy for ATM debit spreads
                        ))
                        
        # Spot above flip: Upward Momentum -> Bull Call Debit
        elif spot > regime.gamma_flip:
            long_call = get_nearest_liquid_contract(valid_calls, spot) 
            if long_call:
                short_call = get_wing_contract(valid_calls, long_call.strike, "up")
                if short_call and long_call.ask > short_call.bid:
                    net_debit = long_call.ask - short_call.bid
                    width = short_call.strike - long_call.strike
                    if width > 0 and (net_debit / width) <= 0.50:
                        structures.append(OptionStructure(
                            strategy_type="Bull Call Debit Spread",
                            legs=[Leg(contract=long_call, action="BUY", ratio=1), Leg(contract=short_call, action="SELL", ratio=1)],
                            net_premium=-net_debit,
                            max_risk=net_debit * 100,
                            probability_of_profit=0.50 
                        ))
                        
    return structures