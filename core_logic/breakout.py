import pandas as pd
from datetime import time
from typing import List, Tuple
from core_logic.strategy_selector import BreakoutSignal
from data_ingestion.schwab_fetcher import DailyLevels

def evaluate_bar(bars_2m: pd.DataFrame, target_timestamp: pd.Timestamp, levels: DailyLevels, rth_vol_stats: pd.DataFrame, k: float = 3.0) -> BreakoutSignal:
    """Evaluates the most recently completed 2-minute candle against the gap-and-go rules."""
    
    # 1. Isolate the most recently COMPLETED bar (requires a 2-min offset)
    completed_bars = bars_2m[bars_2m.index + pd.Timedelta(minutes=2) <= target_timestamp]
    if completed_bars.empty or levels is None or levels.pm_high is None or levels.rth_open is None:
        return BreakoutSignal(state="NONE", signal_ids=[], tier=0, volume_z=None, option_flow_confirmed=False)
        
    current_bar_time = completed_bars.index[-1]
    tt = current_bar_time.time()
    
    if not (time(9, 30) <= tt < time(16, 0)):
        return BreakoutSignal(state="NONE", signal_ids=[], tier=0, volume_z=None, option_flow_confirmed=False)
        
    b = completed_bars.iloc[-1]
    prev_close = completed_bars["close"].iloc[-2] if len(completed_bars) > 1 else None
    
    # 2. Volume Baseline Check
    if current_bar_time not in rth_vol_stats.index:
        return BreakoutSignal(state="NONE", signal_ids=[], tier=0, volume_z=None, option_flow_confirmed=False)
        
    mu = rth_vol_stats.loc[current_bar_time, "vol_mean"]
    sd = rth_vol_stats.loc[current_bar_time, "vol_std"]
    
    if pd.isna(mu) or pd.isna(sd) or sd == 0:
        return BreakoutSignal(state="NONE", signal_ids=[], tier=0, volume_z=None, option_flow_confirmed=False)
        
    vol_z = (b["volume"] - mu) / sd
    on_vol = vol_z >= k
    
    # 3. Rule Evaluations
    PH, PL, PC = levels.prior_high, getattr(levels, 'prior_low', levels.prior_close), levels.prior_close
    PMH, PML = levels.pm_high, levels.pm_low
    o, c = b["open"], b["close"]
    
    first_candle = tt == time(9, 30)
    second_candle = tt == time(9, 32)
    
    gap_up = levels.rth_open > PH and levels.rth_open > PC
    gap_down = levels.rth_open < PL and levels.rth_open < PC
    
    signals = []
    state = "NONE"
    tier = 0
    
    # --- LONG RULES ---
    if gap_up and c > PMH and prev_close is not None and prev_close <= PMH and on_vol:
        signals.append("A_ORB")
    if gap_up and c <= PMH and on_vol and c >= o:
        signals.append("B_ALT")
    if first_candle and o <= PH and o <= PMH and o <= PC and c > PH and c > PMH and c > PC and on_vol:
        signals.append("C_POWER_REVERSAL")
    if first_candle and o <= PMH and c > PMH and on_vol:
        signals.append("D_BLUE")
    if second_candle and c > PMH and c > PH and c > PC and on_vol:
        signals.append("F_SECOND_CANDLE")
        
    # --- SHORT RULES (Mirrored) ---
    if gap_down and c < PML and prev_close is not None and prev_close >= PML and on_vol:
        signals.append("A_ORB_DOWN")
    if gap_down and c >= PML and on_vol and c <= o:
        signals.append("B_ALT_DOWN")
    if first_candle and o >= PL and o >= PML and o >= PC and c < PL and c < PML and c < PC and on_vol:
        signals.append("C_POWER_REVERSAL_DOWN")
    if first_candle and o >= PML and c < PML and on_vol:
        signals.append("D_BLUE_DOWN")
    if second_candle and c < PML and c < PL and c < PC and on_vol:
        signals.append("F_SECOND_CANDLE_DOWN")
        
    # 4. Tier Resolution
    if any(s in signals for s in ["A_ORB", "A_ORB_DOWN", "C_POWER_REVERSAL", "C_POWER_REVERSAL_DOWN", "F_SECOND_CANDLE", "F_SECOND_CANDLE_DOWN"]):
        tier = 1
    elif any(s in signals for s in ["D_BLUE", "D_BLUE_DOWN"]):
        tier = 2
    elif any(s in signals for s in ["B_ALT", "B_ALT_DOWN"]):
        tier = 3
        
    if signals:
        state = "UP" if "DOWN" not in signals[0] else "DOWN"
        
    return BreakoutSignal(
        state=state,
        signal_ids=signals,
        tier=tier,
        volume_z=float(vol_z),
        option_flow_confirmed=False # Placeholder for future Vol/OI scanner integration
    )