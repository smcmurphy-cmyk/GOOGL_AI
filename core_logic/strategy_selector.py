from typing import Literal, Optional
from pydantic import BaseModel
from models.regime import RegimeState

class BreakoutSignal(BaseModel):
    state: Literal["NONE", "UP", "DOWN"]
    signal_ids: list[str]
    tier: Literal[0, 1, 2, 3] 
    volume_z: Optional[float]
    option_flow_confirmed: Optional[bool]

class StrategyIntent(BaseModel):
    strategy_type: Literal["MEAN_REVERSION", "DIRECTIONAL_DEBIT_SPREAD", "NAKED_LONG_SCALP", "NO_TRADE"]
    direction: Literal["UP", "DOWN", "NONE"]
    size_multiplier: float = 1.0

def select_strategy(regime: RegimeState, breakout: BreakoutSignal) -> StrategyIntent:
    """Routes the macro regime and micro breakout into a specific trade structure intent."""
    
    if regime.regime_type == "LONG_GAMMA":
        # Dealers dampen moves. Fade the walls, ignore breakouts.
        if breakout.tier in [1, 2]:
            return StrategyIntent(strategy_type="NO_TRADE", direction="NONE")
        
        # Fading logic is handled by the structure builder near GEX walls
        return StrategyIntent(strategy_type="MEAN_REVERSION", direction="NONE")
        
    elif regime.regime_type == "SHORT_GAMMA":
        # Dealers amplify moves. Buy the breakouts.
        if breakout.tier == 1:
            if breakout.option_flow_confirmed:
                return StrategyIntent(strategy_type="NAKED_LONG_SCALP", direction=breakout.state)
            return StrategyIntent(strategy_type="DIRECTIONAL_DEBIT_SPREAD", direction=breakout.state)
            
        elif breakout.tier == 2:
            # Tier 2 signals lack the strength for naked long delta. Use half-size defined risk.
            return StrategyIntent(strategy_type="DIRECTIONAL_DEBIT_SPREAD", direction=breakout.state, size_multiplier=0.5)
            
    elif regime.regime_type == "NEUTRAL":
        # No structural edge. Only take highest-conviction flow signals at half size.
        if breakout.tier == 1 and breakout.option_flow_confirmed:
            return StrategyIntent(strategy_type="NAKED_LONG_SCALP", direction=breakout.state, size_multiplier=0.5)
            
    return StrategyIntent(strategy_type="NO_TRADE", direction="NONE")