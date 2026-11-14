import asyncio
from config.settings import config

# Import pipeline states
from data_ingestion.schwab_fetcher import get_live_market_data as get_schwab_data, get_valid_access_token
from data_ingestion.cboe_fetcher import get_market_data as get_cboe_data
from core_logic.regime_classifier import classify_regime
from core_logic.structure_builder import generate_structures
from core_logic.expectancy_scorer import evaluate_and_rank
from core_logic.portfolio_risk import portfolio_gatekeeper
from synthesis.agent_llm import generate_trade_thesis
from dissemination.sheet_webhook import post_to_sheet, post_market_scan

# Update import to reflect accurate naming
from utils.volatility import get_historical_volatility_rank

# Hardcoded for the test run. Later, move this to config/universe.py
MEGA_CAP_TICKERS = ["TSLA", "QQQ", "SPY"]

async def run_pipeline(ticker: str, session_open_risk_usd: float, access_token: str = None):
    print(f"\n--- Starting Pipeline for {ticker} ---")
    print("[1/6] Ingesting Market Data...")
    
    if config.use_live_schwab_data:
        chain = await get_schwab_data(ticker, access_token=access_token) 
    else:
        # Fix: Add await to the CBOE fallback
        chain = await get_cboe_data(ticker)
        
    if not chain or not chain.contracts:
        return session_open_risk_usd
    

    historical_vol_rank = get_historical_volatility_rank(ticker)

    print("[2/6] Classifying Macro Regime...")
    
    regime = classify_regime(chain, historical_vol_rank)
    print(f"      -> {regime.regime_type} (GEX: ${regime.net_gex:,.0f})") 
    
    # --- NEW PHASE 2: OPPORTUNITY FILTER ---
    from core_logic.opportunity_filter import is_viable_scalp_environment
    
    is_viable, reject_reason = is_viable_scalp_environment(chain, regime)
    
    if not is_viable:
        print(f"[-] Opportunity Rejected: {reject_reason}") 
        
        # ACTIVATE MARKET SCAN LOGGING
        await post_market_scan(ticker, regime, reject_reason)
        
        return session_open_risk_usd
    
    # STATE 3: STRUCTURE GENERATION
    print("[3/6] Generating Defined-Risk Structures...")
    structures = generate_structures(chain, regime)
    if not structures:
        print(f"[-] No valid structures found for {ticker} in current regime.")
        return session_open_risk_usd 

    # STATE 4: EXPECTANCY SCORING
    print(f"[4/6] Scoring Expectancy on {len(structures)} candidate structures...")
    
    # FIX: Passed regime and ticker into the upgraded scorer
    scored_plays = evaluate_and_rank(structures, regime, ticker, account_balance=10000.0)
    
    if not scored_plays:
        print("[-] No structures passed the strict R-Multiple and Risk limits.")
        return session_open_risk_usd 
        
    top_play = scored_plays[0]
    
    # FIX: Mapped attribute to the new expectancy_score field
    print(f"      -> Top Play: {top_play.structure.strategy_type} | Score: {top_play.expectancy_score:.2f}")

    # STATE 5: PORTFOLIO GATEKEEPER
    print("[5/6] Checking Portfolio Risk Budget...")
    if not portfolio_gatekeeper(top_play, session_open_risk_usd, account_balance=10000.0):
        print("[-] Trade rejected: Executing this would breach maximum daily risk.")
        return session_open_risk_usd 

    # STATE 6: SYNTHESIS & DISSEMINATION
    print("[6/6] Synthesizing LLM Thesis and Dispatching Webhook...")
    thesis = generate_trade_thesis(ticker, regime, top_play)
    
    # POST to webhook (Ensure your .env has WEBHOOK_URL defined)
    success = await post_to_sheet(ticker, regime, top_play, thesis)
    
    if success:
        print("[+] Alert successfully dispatched!")
        # FIX: Mapped risk tracking to the new OptionStructure max_risk field
        return session_open_risk_usd + top_play.structure.max_risk
    else:
        print("[-] Failed to dispatch webhook.")
        return session_open_risk_usd 

async def main():
    print("INITIALIZING MEGA-CAP OPTIONS AGENT...")
    
    while True:
        # 1. Check if we are inside the morning rush window
        from datetime import datetime, time
        import pytz
        
        nyc_tz = pytz.timezone('America/New_York')
        now = datetime.now(nyc_tz).time()
        
        # Match the target window: 9:35 to 11:00 EST (6:35 to 8:00 PST)
        market_open = time(9, 35)
        market_close = time(11, 0)
        
        if not (market_open <= now <= market_close):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Outside morning scalp window. Sleeping for 60 seconds...")
            await asyncio.sleep(60)
            continue
            
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] WAKING AGENT FOR 2-MINUTE SCAN CYCLE...")

        # 2. Fetch/Refresh the Access Token
        session_access_token = None
        if config.use_live_schwab_data:
            print("[+] Authenticating with Schwab API...")
            try:
                session_access_token = await get_valid_access_token()
                print("[+] Live Token Acquired.")
            except Exception as e:
                print(f"[-] Token acquisition failed: {e}. Retrying next cycle.")
                await asyncio.sleep(60)
                continue

        # 3. Track accumulated risk across the session
        session_open_risk_usd = 0.0 
        
        for ticker in MEGA_CAP_TICKERS:
            session_open_risk_usd = await run_pipeline(
                ticker, 
                session_open_risk_usd, 
                access_token=session_access_token
            ) 
            await asyncio.sleep(2) # Stagger requests to respect API rate limits
            
        print("\nSCAN CYCLE COMPLETE.") 
        print(f"Total Projected Risk Allocated This Cycle: ${session_open_risk_usd:,.2f}")
        
        # 4. Sleep for exactly 2 minutes before the next scan
        print("Agent resting for 2 minutes...")
        await asyncio.sleep(120) 

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAgent gracefully shut down by user.")