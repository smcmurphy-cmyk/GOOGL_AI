from pydantic import BaseModel, Field
from typing import Optional
from models.regime import RegimeState
from models.structures import OptionStructure

class TradeExits(BaseModel):
    profit_target_pct: float = Field(..., description="Target % of max credit/debit (e.g., 0.50 for 50%)")
    stop_loss_pct: float = Field(..., description="Stop out % of max risk (e.g., 1.00 for 100%)")
    time_stop_days: int = Field(..., description="0 = Intraday exit, 1 = Next day exit")
    time_stop_minutes: int = 0
    invalidation_level: Optional[float] = Field(None, description="Underlying price that invalidates the trade")

class ScoredPlay(BaseModel):
    ticker: str
    regime: RegimeState
    structure: OptionStructure
    expectancy_score: float = 0.0
    exits: Optional[TradeExits] = None