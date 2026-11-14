from pydantic import BaseModel, Field
from typing import Literal, Optional

class RegimeState(BaseModel):
    regime_type: Literal["MEAN_REVERSION", "DIRECTIONAL_BREAKOUT", "UNCERTAIN", "PINNED_BULLISH"]
    net_gex: float
    iv_rank: Optional[float] = None
    primary_pin_strike: Optional[float] = None
    volatility_wall_strike: Optional[float] = None
    call_wall: Optional[float] = None
    put_wall: Optional[float] = None
    gamma_flip: Optional[float] = None
    
    # Actionable strikes for the Structure Builder
    primary_pin_strike: Optional[float] = Field(None, description="Strike with the highest positive GEX")
    volatility_wall_strike: Optional[float] = Field(None, description="Strike with the highest negative GEX")
    
    @property
    def is_tradeable(self) -> bool:
        """Helper to quickly drop uncertain tickers from the pipeline."""
        return self.regime_type != "UNCERTAIN"
    