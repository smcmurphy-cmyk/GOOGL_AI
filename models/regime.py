from pydantic import BaseModel
from typing import Literal, Optional

class RegimeState(BaseModel):
    regime_type: Literal["LONG_GAMMA", "SHORT_GAMMA", "NEUTRAL"]
    net_gex: float
    gamma_flip: Optional[float]
    call_wall: Optional[float]
    put_wall: Optional[float]
    is_tradeable: bool
    