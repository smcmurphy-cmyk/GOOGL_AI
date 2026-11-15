from datetime import date
from typing import List
from models.market_data import OptionsChain, OptionContract
from models.structures import OptionStructure, Leg
from models.regime import RegimeState
from utils.flow_analyzer import check_rejection_flow, find_breakout_flow

def get_nearest_liquid_contract(contracts: List[OptionContract], target_strike: float) -> OptionContract:
    if not contracts: return None
    return sorted(contracts, key=lambda c: (abs(c.strike - target_strike), -(c.volume or 0)))[0]

def get_wing_contract(contracts: List[OptionContract], short_strike: float, direction: str, width: float = 5.0) -> OptionContract:
    target = short_strike + width if direction == "up" else short_strike - width
    return get_nearest_liquid_contract(contracts, target)

def generate_structures(chain: OptionsChain, regime: RegimeState) -> List[OptionStructure]:
    structures = []
    today = date.today()
    
    valid_calls = [c for c in chain.contracts if c.option_type == "call" and 0 <= (c.expiration - today).days <= 3]
    valid_puts = [c for c in chain.contracts if c.option_type == "put" and 0 <= (c.expiration - today).days <= 3]
    
    if not valid_calls or not valid_puts:
        return structures

    spot = chain.underlying.price

    # MEAN REVERSION (Reversal Scalps vs Standard Fades)
    if regime.regime_type == "MEAN_REVERSION":
        
        # Call Wall Evaluation
        if regime.call_wall:
            short_call = get_nearest_liquid_contract(valid_calls, regime.call_wall)
            if short_call and short_call.delta and 0.15 <= abs(short_call.delta) <= 0.35:
                
                # Check if flow rejects the breakout (Vol/OI < 1.0)
                if check_rejection_flow(short_call):
                    # REVERSAL SCALP: Long Put at the Call Wall
                    long_put_reversal = get_nearest_liquid_contract(valid_puts, spot)
                    if long_put_reversal and long_put_reversal.ask > 0:
                        structures.append(OptionStructure(
                            strategy_type="Long Put Reversal Scalp",
                            legs=[Leg(contract=long_put_reversal, action="BUY", ratio=1)],
                            net_premium=-long_put_reversal.ask,
                            max_risk=long_put_reversal.ask * 100,
                            probability_of_profit=abs(long_put_reversal.delta) if long_put_reversal.delta else 0.50
                        ))
                else:
                    # Standard Bear Call Spread logic
                    long_call = get_wing_contract(valid_calls, short_call.strike, "up")
                    if long_call and short_call.bid > long_call.ask:
                        net_credit = short_call.bid - long_call.ask
                        width = long_call.strike - short_call.strike
                        if width > 0 and (net_credit / width) >= 0.30: 
                            structures.append(OptionStructure(
                                strategy_type="Bear Call Spread",
                                legs=[Leg(contract=short_call, action="SELL", ratio=1), Leg(contract=long_call, action="BUY", ratio=1)],
                                net_premium=net_credit,
                                max_risk=(width - net_credit) * 100,
                                probability_of_profit=1.0 - abs(short_call.delta)
                            ))

        # Put Wall Evaluation
        if regime.put_wall:
            short_put = get_nearest_liquid_contract(valid_puts, regime.put_wall)
            if short_put and short_put.delta and 0.15 <= abs(short_put.delta) <= 0.35:
                
                if check_rejection_flow(short_put):
                    # REVERSAL SCALP: Long Call at the Put Wall
                    long_call_reversal = get_nearest_liquid_contract(valid_calls, spot)
                    if long_call_reversal and long_call_reversal.ask > 0:
                        structures.append(OptionStructure(
                            strategy_type="Long Call Reversal Scalp",
                            legs=[Leg(contract=long_call_reversal, action="BUY", ratio=1)],
                            net_premium=-long_call_reversal.ask,
                            max_risk=long_call_reversal.ask * 100,
                            probability_of_profit=abs(long_call_reversal.delta) if long_call_reversal.delta else 0.50
                        ))
                else:
                    # Standard Bull Put Spread logic
                    long_put = get_wing_contract(valid_puts, short_put.strike, "down")
                    if long_put and short_put.bid > long_put.ask:
                        net_credit = short_put.bid - long_put.ask
                        width = short_put.strike - long_put.strike
                        if width > 0 and (net_credit / width) >= 0.30:
                            structures.append(OptionStructure(
                                strategy_type="Bull Put Spread",
                                legs=[Leg(contract=short_put, action="SELL", ratio=1), Leg(contract=long_put, action="BUY", ratio=1)],
                                net_premium=net_credit,
                                max_risk=(width - net_credit) * 100,
                                probability_of_profit=1.0 - abs(short_put.delta)
                            ))
    
    # DIRECTIONAL BREAKOUT (Debit Spreads & Flow Breakouts)
    elif regime.regime_type == "DIRECTIONAL_BREAKOUT" and regime.gamma_flip:
        
        if spot < regime.gamma_flip: # Downward Momentum
            # Check for aggressive Put flow
            breakout_put = find_breakout_flow(valid_puts, spot, "down")
            
            if breakout_put and breakout_put.ask > 0:
                # BREAKOUT SCALP: Long Put
                structures.append(OptionStructure(
                    strategy_type="Long Put Breakout Scalp",
                    legs=[Leg(contract=breakout_put, action="BUY", ratio=1)],
                    net_premium=-breakout_put.ask,
                    max_risk=breakout_put.ask * 100,
                    probability_of_profit=abs(breakout_put.delta) if breakout_put.delta else 0.50
                ))
            else:
                # Standard Bear Put Debit Spread logic
                long_put = get_nearest_liquid_contract(valid_puts, spot) 
                if long_put:
                    short_put = get_wing_contract(valid_puts, long_put.strike, "down")
                    if short_put and long_put.ask > short_put.bid:
                        net_debit = long_put.ask - short_put.bid
                        width = long_put.strike - short_put.strike
                        if width > 0 and (net_debit / width) <= 0.50:
                            structures.append(OptionStructure(
                                strategy_type="Bear Put Debit Spread",
                                legs=[Leg(contract=long_put, action="BUY", ratio=1), Leg(contract=short_put, action="SELL", ratio=1)],
                                net_premium=-net_debit,
                                max_risk=net_debit * 100,
                                probability_of_profit=0.50 
                            ))
                            
        elif spot > regime.gamma_flip: # Upward Momentum
            # Check for aggressive Call flow
            breakout_call = find_breakout_flow(valid_calls, spot, "up")
            
            if breakout_call and breakout_call.ask > 0:
                # BREAKOUT SCALP: Long Call
                structures.append(OptionStructure(
                    strategy_type="Long Call Breakout Scalp",
                    legs=[Leg(contract=breakout_call, action="BUY", ratio=1)],
                    net_premium=-breakout_call.ask,
                    max_risk=breakout_call.ask * 100,
                    probability_of_profit=abs(breakout_call.delta) if breakout_call.delta else 0.50
                ))
            else:
                # Standard Bull Call Debit Spread logic
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