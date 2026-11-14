from pydantic import BaseModel
from typing import Literal, Optional

class RegimeState(BaseModel):
    regime_type: Literal["MEAN_REVERSION", "DIRECTIONAL_BREAKOUT", "PINNED_BULLISH", "PINNED_BEARISH", "UNCERTAIN"]
    net_gex: float
    gamma_flip: Optional[float] = None
    call_wall: Optional[float] = None
    put_wall: Optional[float] = None
    is_tradeable: bool = False