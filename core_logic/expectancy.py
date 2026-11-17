from typing import List
from models.structures import OptionStructure
from models.regime import RegimeState
from core_logic.strategy_selector import StrategyIntent
from models.alerts import TradeExits, ScoredPlay

def calculate_costs(structure: OptionStructure) -> float:
    """Calculates round-trip costs including commissions and bid/ask slippage."""
    commission_per_leg = 0.65 
    total_commission = len(structure.legs) * (commission_per_leg * 2)
    total_slippage = sum((leg.contract.ask - leg.contract.bid) * 100 for leg in structure.legs)
    return total_commission + total_slippage

def evaluate_and_rank(structures: List[OptionStructure], regime: RegimeState, ticker: str, spot: float, intent: StrategyIntent) -> List[ScoredPlay]:
    scored_plays = []
    
    for structure in structures:
        is_naked = "Scalp" in structure.strategy_type
        is_credit = "Bear Call" in structure.strategy_type or "Bull Put" in structure.strategy_type
        
        round_trip_costs = calculate_costs(structure)
        
        if is_naked:
            target_pct = 1.50
            stop_pct = 0.25
            time_stop = 15
            
            reward_usd = structure.max_risk * target_pct
            true_risk_usd = structure.max_risk * stop_pct
            pop = 0.20 # Baseline assumed PoP for momentum gap-and-go
            
        elif is_credit:
            target_pct = 0.50 
            stop_pct = 1.00 # 100% of max loss for credit spreads
            time_stop = 120
            
            reward_usd = structure.net_premium * 100 * target_pct
            true_risk_usd = structure.max_risk * stop_pct
            
            short_leg = next((l for l in structure.legs if l.action == "SELL"), None)
            pop = (1.0 - abs(short_leg.contract.delta)) if short_leg and short_leg.contract.delta else 0.82
            
        else:
            # DIRECTIONAL DEBIT SPREADS
            target_pct = 0.50 # 50% of Max Profit (Width - Debit)
            stop_pct = 1.00   # 100% of Debit (Max Loss)
            time_stop = 120
            
            long_leg = next(l for l in structure.legs if l.action == "BUY")
            short_leg = next((l for l in structure.legs if l.action == "SELL"), None)
            
            if short_leg:
                width_usd = abs(long_leg.contract.strike - short_leg.contract.strike) * 100
                debit_usd = abs(structure.net_premium) * 100
                max_profit_usd = width_usd - debit_usd
                
                reward_usd = max_profit_usd * target_pct
                true_risk_usd = debit_usd * stop_pct 
                
                # Approximate PoP using the short strike delta (probability it expires ITM)
                pop = abs(short_leg.contract.delta) if short_leg.contract.delta else 0.30
            else:
                continue

        # Set default invalidations (To be replaced by precise Breakout levels in Phase 4)
        invalidation_level = regime.gamma_flip if regime.gamma_flip else spot
        invalidation_side = "below" if intent.direction == "UP" else "above"
        
        net_ev_usd = (pop * reward_usd) - ((1 - pop) * true_risk_usd) - round_trip_costs
        
        if true_risk_usd <= 0:
            continue
            
        net_ev_r = net_ev_usd / true_risk_usd
        
        if net_ev_r > 0:
            exits = TradeExits(
                profit_target_pct=target_pct,
                stop_loss_pct=stop_pct,
                time_stop_minutes=time_stop,
                invalidation_level=invalidation_level,
                invalidation_side=invalidation_side
            )
            
            scored_plays.append(ScoredPlay(
                ticker=ticker,
                regime=regime.regime_type,
                intent=intent,
                structure=structure,
                expectancy_score_usd=net_ev_usd,
                net_ev_r=net_ev_r,
                pop=pop,
                pop_source="ASSUMED", # Refined label from Phase 1 feedback
                paper_only=True, 
                exits=exits
            ))
            
    return sorted(scored_plays, key=lambda x: x.net_ev_r, reverse=True)