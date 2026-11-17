from datetime import date
from typing import List, Optional
from models.market_data import OptionsChain, OptionContract
from models.structures import OptionStructure, Leg
from models.regime import RegimeState
from core_logic.strategy_selector import StrategyIntent

def is_valid_market(contract: OptionContract, is_short: bool = False) -> bool:
    if contract.bid is None or contract.ask is None: return False
    if contract.ask <= contract.bid: return False
    if is_short and contract.bid <= 0.0: return False
    if not is_short and contract.ask <= 0.0: return False
    return True

def get_nearest_liquid_contract(contracts: List[OptionContract], target_strike: float, is_short: bool = False) -> Optional[OptionContract]:
    valid_contracts = [c for c in contracts if is_valid_market(c, is_short)]
    if not valid_contracts: return None
    return sorted(valid_contracts, key=lambda c: (abs(c.strike - target_strike), -(c.volume or 0)))[0]

def get_wing_contract(contracts: List[OptionContract], short_leg: OptionContract, direction: str, steps_out: int = 1) -> Optional[OptionContract]:
    same_expiry = sorted([c for c in contracts if c.expiration == short_leg.expiration and is_valid_market(c, is_short=False)], key=lambda c: c.strike)
    try:
        idx = next(i for i, c in enumerate(same_expiry) if c.strike == short_leg.strike)
    except StopIteration:
        return None
    target_idx = idx + steps_out if direction == "up" else idx - steps_out
    if 0 <= target_idx < len(same_expiry):
        return same_expiry[target_idx]
    return None

def generate_structures(chain: OptionsChain, regime: RegimeState, intent: StrategyIntent) -> List[OptionStructure]:
    structures = []
    if intent.strategy_type == "NO_TRADE":
        return structures
        
    today = date.today()
    spot = chain.underlying.price
    dtes_to_check = [0, 1, 2] # Generate across multiple DTEs for the scorer to rank
    
    for target_dte in dtes_to_check:
        valid_calls = [c for c in chain.contracts if c.option_type == "call" and (c.expiration - today).days == target_dte]
        valid_puts = [c for c in chain.contracts if c.option_type == "put" and (c.expiration - today).days == target_dte]
        
        if not valid_calls or not valid_puts:
            continue

        if intent.strategy_type == "MEAN_REVERSION" and regime.call_wall:
            short_call = get_nearest_liquid_contract(valid_calls, regime.call_wall, is_short=True)
            if short_call:
                long_call = get_wing_contract(valid_calls, short_call, "up")
                if long_call and short_call.bid > long_call.ask:
                    net_credit = short_call.bid - long_call.ask
                    width = long_call.strike - short_call.strike
                    if width > 0:
                        structures.append(OptionStructure(
                            strategy_type=f"Bear Call Spread {target_dte}DTE",
                            legs=[Leg(contract=short_call, action="SELL", ratio=intent.size_multiplier), 
                                  Leg(contract=long_call, action="BUY", ratio=intent.size_multiplier)],
                            net_premium=net_credit,
                            max_risk=(width - net_credit) * 100 * intent.size_multiplier,
                            probability_of_profit=1.0 - abs(short_call.delta) if short_call.delta else 0.82
                        ))
            continue # Skip directional logic for this DTE loop

        # DIRECTIONAL STRATEGIES (Debit Spreads & Naked Scalps)
        contracts = valid_calls if intent.direction == "UP" else valid_puts
        direction_wing = "up" if intent.direction == "UP" else "down"
        
        atm_long = get_nearest_liquid_contract(contracts, spot, is_short=False)
        if not atm_long:
            continue
            
        otm_long = get_wing_contract(contracts, atm_long, direction_wing, steps_out=1)
        long_candidates = [atm_long]
        if otm_long:
            long_candidates.append(otm_long)
            
        for long_leg in long_candidates:
            if intent.strategy_type == "DIRECTIONAL_DEBIT_SPREAD":
                short_leg = get_wing_contract(contracts, long_leg, direction_wing, steps_out=1)
                if short_leg and long_leg.ask > short_leg.bid:
                    net_debit = long_leg.ask - short_leg.bid
                    width = abs(long_leg.strike - short_leg.strike)
                    if width > 0:
                        strat_name = f"Bull Call Debit {target_dte}DTE" if intent.direction == "UP" else f"Bear Put Debit {target_dte}DTE"
                        structures.append(OptionStructure(
                            strategy_type=strat_name,
                            legs=[Leg(contract=long_leg, action="BUY", ratio=intent.size_multiplier), 
                                  Leg(contract=short_leg, action="SELL", ratio=intent.size_multiplier)],
                            net_premium=-net_debit, 
                            max_risk=net_debit * 100 * intent.size_multiplier,
                            probability_of_profit=abs(short_leg.delta) if short_leg.delta else 0.30 
                        ))
                        
            elif intent.strategy_type == "NAKED_LONG_SCALP":
                # Cap naked premium at $2.50. This constraint remains to protect against heavy OTM slippage.
                if 0 < long_leg.ask <= 2.50:
                    strat_name = f"Long Call Scalp {target_dte}DTE" if intent.direction == "UP" else f"Long Put Scalp {target_dte}DTE"
                    structures.append(OptionStructure(
                        strategy_type=strat_name,
                        legs=[Leg(contract=long_leg, action="BUY", ratio=intent.size_multiplier)],
                        net_premium=-long_leg.ask,
                        max_risk=long_leg.ask * 100 * intent.size_multiplier,
                        probability_of_profit=0.20 
                    ))

    return structures