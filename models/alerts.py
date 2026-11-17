from pydantic import BaseModel
from models.structures import OptionStructure
from core_logic.strategy_selector import StrategyIntent

class TradeExits(BaseModel):
    profit_target_pct: float
    stop_loss_pct: float
    time_stop_minutes: int
    invalidation_level: float
    invalidation_side: str 

class ScoredPlay(BaseModel):
    ticker: str
    regime: str
    intent: StrategyIntent
    structure: OptionStructure
    expectancy_score_usd: float
    net_ev_r: float
    pop: float
    pop_source: str
    paper_only: bool
    exits: TradeExits