import asyncio
import datetime
import pytz
from data_ingestion.schwab_fetcher import get_price_history, build_2m, extract_levels_and_baseline
from core_logic.breakout import evaluate_bar
from core_logic.strategy_selector import select_strategy
from config.settings import config

# Import pipeline states
from data_ingestion.schwab_fetcher import get_live_market_data as get_schwab_data, get_valid_access_token
from core_logic.regime_classifier import classify_regime
from core_logic.structure_builder import generate_structures
from core_logic.expectancy import evaluate_and_rank
from core_logic.risk_gate import portfolio_gatekeeper
from synthesis.agent_llm import generate_trade_thesis

# Asynchronous Outbox Imports
from dissemination.outbox import enqueue_alert, enqueue_market_scan, outbox_worker
from utils.volatility import get_historical_volatility_rank

MEGA_CAP_TICKERS = ["TSLA", "QQQ", "SPY", "MSFT", "AAPL", "AMZN", "GOOGL", "NVDA", "META", "AMD"]

async def wait_for_next_bar(buffer_seconds: int = 5):
    """Sleeps precisely until `buffer_seconds` past the next 2-minute boundary."""
    eastern = pytz.timezone('US/Eastern')
    now = datetime.datetime.now(eastern)
    
    next_minute = now.minute + (2 - now.minute % 2)
    
    if next_minute >= 60:
        next_minute -= 60
        target_time = now.replace(minute=next_minute, second=buffer_seconds, microsecond=0) + datetime.timedelta(hours=1)
    else:
        target_time = now.replace(minute=next_minute, second=buffer_seconds, microsecond=0)
        
    sleep_duration = (target_time - now).total_seconds()
    
    if sleep_duration < 0:
        sleep_duration += 120  
        
    print(f"[*] Awaiting bar close. Sleeping {sleep_duration:.1f}s until {target_time.strftime('%H:%M:%S ET')}")
    await asyncio.sleep(sleep_duration)

async def run_pipeline(ticker: str, session_open_risk_usd: float, access_token: str = None, positions_this_cycle: int = 0, dispatched_alerts: set = None):
    if dispatched_alerts is None:
        dispatched_alerts = set()

    print(f"\n--- Starting Pipeline for {ticker} ---")
    print("[1/6] Ingesting Market Data & Price History...")
    
    if not config.use_live_schwab_data:
        print("[-] FATAL: Live Schwab data disabled. Scalping requires real-time quotes. Skipping...")
        return session_open_risk_usd, positions_this_cycle
        
    # Fetch live options chain and price history concurrently
    chain_task = asyncio.create_task(get_schwab_data(ticker, access_token=access_token))
    history_task = asyncio.create_task(get_price_history(ticker, access_token=access_token))
    
    chain, df1m = await asyncio.gather(chain_task, history_task)
        
    if not chain or not chain.contracts or df1m is None or df1m.empty:
        print(f"[-] Missing chain or price history for {ticker}.")
        return session_open_risk_usd, positions_this_cycle
    
    historical_vol_rank = await asyncio.to_thread(get_historical_volatility_rank, ticker)

    print("[2/6] Classifying Macro Regime & Evaluating Breakouts...")
    
    regime = classify_regime(chain, historical_vol_rank)
    
    from core_logic.opportunity_filter import is_viable_scalp_environment
    is_viable, reject_reason = is_viable_scalp_environment(chain, regime)
    if not is_viable:
       print(f"[-] Opportunity Rejected: {reject_reason}") 
       await enqueue_market_scan(ticker, regime, reject_reason)
       return session_open_risk_usd, positions_this_cycle
       
    # Execute the Micro Breakout Engine
    now_et = datetime.datetime.now(pytz.timezone('US/Eastern'))
    bars_2m = build_2m(df1m)
    levels, rth_vol_stats = extract_levels_and_baseline(bars_2m, pd.Timestamp(now_et))
    
    breakout = evaluate_bar(bars_2m, pd.Timestamp(now_et), levels, rth_vol_stats)
    
    print(f"      -> Regime: {regime.regime_type} (GEX: ${regime.net_gex:,.0f})") 
    print(f"      -> Breakout: {breakout.state} (Tier {breakout.tier}) | Signals: {breakout.signal_ids}")
    
    # Route to Strategy Selector
    intent = select_strategy(regime, breakout)
    if intent.strategy_type == "NO_TRADE":
        print(f"[-] No valid trade setup for {regime.regime_type} + Breakout Tier {breakout.tier}")
        await enqueue_market_scan(ticker, regime, "NO_TRADE: Matrix rejected setup.")
        return session_open_risk_usd, positions_this_cycle
    
    print(f"[3/6] Generating Defined-Risk Structures ({intent.strategy_type})...")
    structures = generate_structures(chain, regime, intent)
    if not structures:
        print(f"[-] No liquid structures found for {ticker}.")
        return session_open_risk_usd, positions_this_cycle 

    print(f"[4/6] Scoring Expectancy on {len(structures)} candidate structures...")
    
    spot = chain.underlying.price
    scored_plays = evaluate_and_rank(structures, regime, ticker, spot, intent)
    
    if not scored_plays:
        print("[-] No structures passed the strict R-Multiple and Risk limits.")
        return session_open_risk_usd, positions_this_cycle 
        
    top_play = scored_plays[0]
    print(f"      -> Top Play: {top_play.structure.strategy_type} | Net EV(R): {top_play.net_ev_r:.2f}")

    print("[5/6] Checking Portfolio Risk Budget...")
    
    trade_id = f"{ticker}-{top_play.structure.strategy_type}"
    if trade_id in dispatched_alerts:
        print(f"[-] Alert suppressed: {trade_id} already dispatched today.")
        return session_open_risk_usd, positions_this_cycle

    is_approved, reject_reason = portfolio_gatekeeper(
        top_play, 
        session_open_risk_usd, 
        positions_this_cycle=positions_this_cycle, 
        account_balance=10000.0
    )
    
    if not is_approved:
         print(f"[-] Trade rejected: {reject_reason}")
         await enqueue_market_scan(ticker, regime, f"Risk Gate: {reject_reason}")
         return session_open_risk_usd, positions_this_cycle 

    print("[6/6] Synthesizing LLM Thesis and Queueing Webhook...")
    thesis = await asyncio.to_thread(generate_trade_thesis, ticker, regime, top_play)
      
    await enqueue_alert(ticker, regime, top_play, thesis)
    
    print("[+] Alert queued for background delivery.")
    dispatched_alerts.add(trade_id) 
    
    true_trade_risk_usd = top_play.structure.max_risk * top_play.exits.stop_loss_pct
    return session_open_risk_usd + true_trade_risk_usd, positions_this_cycle + 1

async def main():
    print("INITIALIZING MEGA-CAP OPTIONS AGENT...")
    session_open_risk_usd = 0.0 
    dispatched_alerts = set()
    eastern = pytz.timezone('US/Eastern')

    while True:
        now_et = datetime.datetime.now(eastern)
        
        market_open = datetime.time(9, 32)
        market_close = datetime.time(16, 0)
        
        # 1. Deep Hibernation: Check if it's the weekend or outside market hours
        is_weekend = now_et.weekday() >= 5
        is_outside_hours = not (market_open <= now_et.time() < market_close)
        
        if is_weekend or is_outside_hours:
            # Calculate exactly when 09:32 ET occurs next
            next_open = now_et.replace(hour=9, minute=32, second=0, microsecond=0)
            
            # If it's already past 09:32 today, push to tomorrow
            if now_et >= next_open:
                next_open += datetime.timedelta(days=1)
                
            # Keep pushing forward if the next open lands on a Saturday (5) or Sunday (6)
            while next_open.weekday() >= 5:
                next_open += datetime.timedelta(days=1)
                
            sleep_seconds = (next_open - now_et).total_seconds()
            
            # Format the output for the console so you know exactly when it will wake up
            hours, remainder = divmod(sleep_seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            print(f"[{now_et.strftime('%H:%M:%S ET')}] Market closed. Hibernating for {int(hours)}h {int(minutes)}m until {next_open.strftime('%A %m/%d at %H:%M ET')}...")
            
            await asyncio.sleep(sleep_seconds)
            continue
            
        # 2. If we ARE in market hours, sync perfectly to the next 2-minute bar close
        await wait_for_next_bar(buffer_seconds=5)
        
        print(f"\n[{datetime.datetime.now(eastern).strftime('%H:%M:%S ET')}] WAKING AGENT FOR 2-MINUTE SCAN CYCLE...")

        session_access_token = None
        if config.use_live_schwab_data:
            print("[+] Authenticating with Schwab API...")
            try:
                session_access_token = await get_valid_access_token()
                print("[+] Live Token Acquired.")
            except Exception as e:
                print(f"[-] Token acquisition failed: {e}. Retrying next cycle.")
                continue

        positions_this_cycle = 0
        
        for ticker in MEGA_CAP_TICKERS:
            try:
                session_open_risk_usd, positions_this_cycle = await run_pipeline(
                    ticker, 
                    session_open_risk_usd, 
                    access_token=session_access_token,
                    positions_this_cycle=positions_this_cycle,
                    dispatched_alerts=dispatched_alerts
                ) 
            except Exception as e:
                print(f"[-] CRITICAL PIPELINE ERROR for {ticker}: {type(e).__name__} - {e}")
                continue
                
            await asyncio.sleep(2) 
            
        print("\nSCAN CYCLE COMPLETE.") 
        print(f"Total Projected Risk Allocated This Cycle: ${session_open_risk_usd:,.2f}")

async def application_runner():
    # FINAL STEP C FIX: Start the outbox worker concurrently with the main loop
    worker_task = asyncio.create_task(outbox_worker())
    
    await main()

if __name__ == "__main__":
    try:
        asyncio.run(application_runner())
    except KeyboardInterrupt:
        print("\nAgent gracefully shut down by user.")