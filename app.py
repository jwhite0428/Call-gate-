import time, datetime as dt, json, html, math
from zoneinfo import ZoneInfo
import streamlit as st
import pandas as pd
from engine import feed,process,read_layer,read_decisions,setting,set_setting,window_stats,bootstrap_history,paper_trades,reset_paper_ledger

st.set_page_config(page_title='Call Gate Style | BTC15 Paper Bot',page_icon='🟢',layout='wide',initial_sidebar_state='collapsed')
# Optional access gate for public Streamlit Cloud deployments.
# Set APP_PASSWORD as a Streamlit app secret; do not commit secrets to GitHub.
import os
try:
    cloud_password = str(st.secrets.get('APP_PASSWORD', '')).strip()
except Exception:
    cloud_password = ''
if cloud_password:
    import hmac
    if not st.session_state.get('authenticated', False):
        st.title('🔒 BTC15 Private Paper Dashboard')
        entered=st.text_input('Dashboard password',type='password')
        if st.button('Unlock dashboard'):
            if hmac.compare_digest(entered,cloud_password):
                st.session_state['authenticated']=True
                st.rerun()
            else:
                st.error('Incorrect password')
        st.stop()
else:
    st.warning('No APP_PASSWORD configured. Anyone with the public app link may access bot settings and paper history. Set APP_PASSWORD in Streamlit Cloud secrets before sharing.')
st.markdown('''<style>
:root{color-scheme:dark}
.stApp{background:#0b111b;color:#eaf3fb}
.block-container{max-width:1180px;padding:0.65rem 0.75rem 3.5rem}
header[data-testid="stHeader"]{background:transparent}
h1,h2,h3,h4{color:#f3f8ff!important}
h1{font-size:1.34rem!important}h3{font-size:1.06rem!important}
p,li,label{color:#d3e1ee}
.bx,.darkbx{background:#17283a;border:1px solid #3d5770;border-radius:11px;padding:11px 12px;margin:2px 0 7px;min-height:67px}
.darkbx{background:#101b2a}
.cap{font-weight:750;letter-spacing:.07em;color:#adc1d3;font-size:.66rem;text-transform:uppercase}
.val{font-weight:750;color:#f5faff;font-size:1.15rem;line-height:1.4;overflow-wrap:anywhere}
.small{font-size:.73rem;color:#b7c8d7;overflow-wrap:anywhere}
.up{color:#64edb1!important}.down{color:#ff91a7!important}.warn{color:#f4d27b!important}
.strip{display:flex;gap:4px;margin:7px 0;overflow:hidden}.pill{min-width:12px;flex:1;text-align:center;padding:4px 0;background:#233549;border:1px solid #527089;border-radius:5px;font-weight:800}
div[data-testid="stVerticalBlockBorderWrapper"]{border:1px solid #3c5068;background:#0f1927;border-radius:12px}
.stButton button{background:#173e32!important;color:#adf9d6!important;border:1px solid #3b8468!important}
[data-testid="stMetric"]{background:#17283a;border:1px solid #415a74;padding:10px;border-radius:10px}
[data-testid="stRadio"] label{font-size:.82rem}
[data-testid="stDataFrame"]{border:1px solid #3d5670;border-radius:9px}
[data-testid="stNumberInput"] input{background:#142338!important;color:#f1f8ff!important}
[data-testid="stProgress"]>div>div{background:#63e5b0!important}
/* Fix Streamlit alert boxes with light backgrounds / illegible white text */
[data-testid="stAlert"], [data-testid="stAlert"]>div,
[data-baseweb="notification"],div[role="alert"]{
 background:#172c3e!important;background-color:#172c3e!important;
 border-color:#46667f!important;color:#f3f8ff!important;border-radius:9px!important;
}
[data-testid="stAlert"] *,[data-baseweb="notification"] *,div[role="alert"] *{color:#f3f8ff!important;opacity:1!important}
[data-testid="stAlert"] svg,[data-baseweb="notification"] svg{fill:#f5ce7a!important;color:#f5ce7a!important}
/* Dense three-across phone summary; does not depend on Streamlit column stacking */
.quickgrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-bottom:9px}
.twogrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin:6px 0 10px}
.fourgrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:6px 0 10px}
@media(max-width:700px){.fourgrid{grid-template-columns:repeat(2,minmax(0,1fr))}}
.quicktile{background:#1a2c40;border:1px solid #405c75;border-radius:10px;padding:10px 8px;min-width:0}
.quicktile .cap{font-size:.59rem;letter-spacing:.04em}
.quicktile .val{font-size:.92rem;line-height:1.2;margin-top:4px}
.quicktile .small{font-size:.61rem;margin-top:3px}
.section-note{color:#abbcce;font-size:.78rem}
@media(max-width:700px){
 .block-container{padding:.4rem .5rem 3rem!important}
 .bx,.darkbx{padding:9px 10px;min-height:58px;margin:2px 0 5px}
 .val{font-size:1.02rem}
 h1{font-size:1.14rem!important}h3{font-size:1.0rem!important}
 [data-testid="stHorizontalBlock"]{gap:.4rem!important}
 [data-testid="column"]{min-width:0!important}
 [data-testid="stRadio"] [role="radiogroup"]{flex-wrap:wrap!important;gap:.3rem!important}
 [data-testid="stDataFrame"]{max-width:100%;overflow:auto}
 button{white-space:normal!important}
 .stCaptionContainer,.stMarkdown p{overflow-wrap:anywhere}
 .quicktile{padding:8px 6px}
 .quicktile .val{font-size:.8rem}
 .quicktile .small{font-size:.57rem}
}
</style>''',unsafe_allow_html=True)
Z=ZoneInfo('America/New_York');now=int(time.time());window=now//900*900;elapsed=now-window
fmt=lambda ts:dt.datetime.fromtimestamp(ts,Z).strftime('%-I:%M %p') if not __import__('os').name=='nt' else dt.datetime.fromtimestamp(ts,Z).strftime('%I:%M %p').lstrip('0')
def fmtwin(w):return f'{fmt(w)}–{fmt(w+900)} ET'
def safe(s):return html.escape(str(s))
def box(title,value,detail='',dark=False,kind=''):
    st.markdown(f'<div class="{"darkbx" if dark else "bx"}"><div class="cap">{safe(title)}</div><div class="val {kind}">{safe(value)}</div><div class="small">{safe(detail)}</div></div>',unsafe_allow_html=True)
def signalword(s):return ('↑ UP' if s=='UP' else '↓ DOWN' if s=='DOWN' else '⚠ Skip this window' if s=='SKIP' else '⌛ Silent')
def shortword(s):return ('↑ UP' if s=='UP' else '↓ DOWN' if s=='DOWN' else '⚠ SKIP' if s=='SKIP' else '—')
def current(rows):return next((r for r in rows if r['window']==window),None)
def evidence(r):
    try:return json.loads(r['evidence']) if r else {}
    except (TypeError,ValueError):return {}
def tracker(title,rows):
    rows=rows[:100];graded=[r for r in rows if r['outcome'] in ('WIN','LOSS')]
    wins=sum(r['outcome']=='WIN' for r in graded);losses=len(graded)-wins
    percentage=f'{100*wins/len(graded):.1f}%' if graded else '—'
    st.markdown(f'<span class="cap">{safe(title)}</span> &nbsp; <span class="small">{wins} correct of {len(graded)} graded · {percentage}</span>',unsafe_allow_html=True)
    colors={'WIN':('#71f2c3','✓'),'LOSS':('#ff96a8','×'),'SKIP':('#ffd483','△')}
    snippets=[]
    for r in rows[:12]:
        color,mark=colors.get(r['outcome'],('#7896b5','·'))
        snippets.append(f'<span class="pill" style="color:{color}">{mark}</span>')
    st.markdown('<div class="strip">'+''.join(snippets or ['<span class="small">No graded observations yet</span>'])+'</div>',unsafe_allow_html=True)
    st.caption(f'{losses} wrong · {sum(r["side"]=="SKIP" for r in rows)} skipped · {sum(r["outcome"] is None for r in rows)} pending · skips excluded from win rate')
def setting_toggle(key,caption,default='1'):
    prev=setting(key,default);val=st.toggle(caption,value=prev=='1',key=key)
    if val!=(prev=='1'):set_setting(key,'1' if val else '0')
    return val

st.title('🟢 BTC15 · SIGNALS & PAPER P&L')
st.caption('GitHub + Streamlit Cloud · BTC 15-minute windows · paper only · no chart')
st.caption('⚠ Streamlit Cloud collects while active; sleeping/restarts can interrupt tracking or erase local history. Not a 24/7 worker.')
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=20000,key='refresh')
except ImportError:st.warning('Install requirements to enable automatic refresh.')
@st.cache_data(ttl=18,show_spinner=False)
def live_feed():return feed()
@st.cache_data(ttl=3600,show_spinner=False)
def backfill():bootstrap_history();return True
candles={};price=None;online=False
try:
    backfill();candles,price=live_feed();process(candles,price,now);online=True
except Exception as exc:st.error(f'BTC price feed unavailable: {exc}. The dashboard will not fabricate prices or signals.')
call=read_layer('call');quant=read_layer('quant');learning=read_layer('learning');decisions=read_decisions()
s=window_stats(candles,now,price) if online else {}
trades=paper_trades()

# PHONE QUICK READ — mirrors active signal and paper totals without requiring scrolling.
latest_call=next((r for r in call if r['window']==window),None)
latest_quant=next((r for r in quant if r['window']==window),None)
valid_quotes=[t for t in trades if t.get('entry_source') in ('KALSHI_LIVE_ASK','KALSHI_MARKET_ASK')]
settled_quotes=[t for t in valid_quotes if t['status']=='CLOSED' and t['result'] in ('WIN','LOSS')]
net_quotes=sum(float(t['pnl']) for t in settled_quotes)
st.markdown('<div class="cap" style="margin:6px 0">LIVE OVERVIEW · PAPER ONLY</div>',unsafe_allow_html=True)
def quick_tile(label,value,detail,kind=''):
    return f'<div class="quicktile"><div class="cap">{safe(label)}</div><div class="val {kind}">{safe(value)}</div><div class="small">{safe(detail)}</div></div>'
quick_call=latest_call['side'] if latest_call else 'WAIT'
quick_quant=latest_quant['side'] if latest_quant else 'WAIT'
st.markdown('<div class="quickgrid">'+quick_tile('CALL',quick_call,f'Min {setting("call_minute",6)}','up' if quick_call=='UP' else 'down' if quick_call=='DOWN' else '')+quick_tile('QUANT',quick_quant,'Gate','up' if quick_quant=='UP' else 'down' if quick_quant=='DOWN' else '')+quick_tile('PAPER P&L',f'${net_quotes:+,.2f}',f'{len(settled_quotes)} settled','up' if net_quotes>=0 else 'down')+'</div>',unsafe_allow_html=True)
# MARKET HEADER — no chart
st.markdown('**CRYPTO**　　<span class="up">● BTC</span>　　**15 min**　　<span class="up">● LIVE FEED</span>　　**CALLS / PAPER TRADING**' if online else '**CRYPTO**　　BTC　　15 min　　● FEED OFFLINE',unsafe_allow_html=True)
with st.container(border=True):
    a,b=st.columns([1,1])
    with a:
        box('TIME LEFT IN WINDOW',f'{(900-elapsed)//60:02d}:{(900-elapsed)%60:02d}',fmtwin(window))
        st.progress(elapsed/900)
    with b:
        box('BTC NOW · COINBASE',f'${price:,.2f}' if price else 'Unavailable',f'Window open: ${s["window_open"]:,.2f}' if s else 'Waiting for complete price data',kind='up' if s and s['gap']>=0 else 'down')
    st.caption('Target is the BTC/USD spot price at the 15-minute window open. The screenshot website may use different feeds/market reference strikes.')

with st.container(border=True):
    a,b=st.columns([5,1])
    with a:st.markdown('### 📞 Call');st.caption('Buys YES on UP and NO on DOWN in hypothetical paper mode when two readings agree.')
    with b:setting_toggle('call_enabled','ON')
    modes=['Display only','Display, then confirm','Place trades automatically']
    with st.expander('⚙️ Call execution settings',expanded=False):
        modes=['Display only','Display, then confirm','Place trades automatically']
        prev=setting('call_mode',modes[0]); mode=st.radio('EXECUTION MODE',modes,index=modes.index(prev) if prev in modes else 0,horizontal=True,key='mode')
        if mode!=prev:set_setting('call_mode',mode)
        minute=int(setting('call_minute','6'))
        m=st.number_input('SIGNAL TIMING · minute 1–14',1,14,minute,help='If changed mid-window, previously locked predictions are never retroactively changed.')
        if m!=minute:set_setting('call_minute',m)
    minute=int(setting('call_minute','6'))
    cr=current(call)
    st.markdown('<div class="twogrid">'+quick_tile('SIGNAL TIMING','LOCKED' if cr else 'SILENT',f'Minute {minute}')+quick_tile('CALL',shortword(cr['side']) if cr else 'WAITING',f'{cr["confidence"]:.1f}% confidence' if cr else 'Before signal')+'</div>',unsafe_allow_html=True)
    st.markdown('**TWO READINGS, MINUTE '+str(minute)+'** · must agree')
    vals=evidence(cr).get('readings',[])
    st.markdown('<div class="twogrid">'+quick_tile('CURRENT RULE',shortword(vals[0]) if len(vals)>0 else '—','Reading 1')+quick_tile('3-FACTOR SCORE',shortword(vals[1]) if len(vals)>1 else '—','Reading 2')+'</div>',unsafe_allow_html=True)
    if cr:st.info('✓ Agreed — Call locked for the window' if cr['side'] in ('UP','DOWN') else '⚠ Skip this window — readings do not agree or market conditions do not qualify')
    tracker('ROLLING 100 CALLS',call)

with st.container(border=True):
    a,b=st.columns([5,1])
    with a:st.markdown('### 🧠 Quant gate');st.caption('Three readings, one decision. When enabled, a conflicting gate prevents a simulated automatic entry.')
    with b:setting_toggle('gate_enabled','ON')
    with st.expander('⚙️ Quant execution display settings',expanded=False):
        qmode=setting('gate_mode','Display only')
        qnew=st.radio('QUANT EXECUTION MODE',modes,index=modes.index(qmode) if qmode in modes else 0,horizontal=True,key='quant_mode')
        if qnew!=qmode:set_setting('gate_mode',qnew)
    qr=current(quant)
    st.markdown('<div class="twogrid">'+quick_tile('SIGNAL TIMING','LOCKED' if qr else 'SILENT',f'Minute {minute}')+quick_tile('QUANT',shortword(qr['side']) if qr else 'WAITING','Advisory / gate')+'</div>',unsafe_allow_html=True)
    st.markdown('**THREE READINGS, ONE ORDER** · all must agree')
    vals=evidence(qr).get('readings',[])
    st.markdown('<div class="quickgrid">'+quick_tile('READING 1',shortword(vals[0]) if len(vals)>0 else '—','')+quick_tile('READING 2',shortword(vals[1]) if len(vals)>1 else '—','')+quick_tile('FINAL CHECK',shortword(vals[2]) if len(vals)>2 else '—','')+'</div>',unsafe_allow_html=True)
    if qr:st.info('✓ All agree' if qr['side']!='SKIP' else '⚠ Skip this window — three readings do not agree')
    tracker('ROLLING 100 QUANT READS',quant)
    st.caption('Quant Gate display mode is informational. Simulated entry selection is controlled by the Call mode; Quant Gate can veto, but never create an entry.')

with st.container(border=True):
    st.markdown('### 💵 PAPER PROFIT / LOSS & WINS')
    st.caption('NEW entries attempt to use observed public Kalshi best-ask quotes (YES for UP, NO for DOWN). Quotes are NOT confirmed fills. Fees remain configurable estimates. Older 50¢-assumption trades are displayed separately and never mislabeled as market quotes.')
    quoted=[t for t in trades if t.get('entry_source') in ('KALSHI_LIVE_ASK','KALSHI_MARKET_ASK')]
    finished=[t for t in quoted if t['status']=='CLOSED' and t['result'] in ('WIN','LOSS')]
    wins=sum(t['result']=='WIN' for t in finished)
    losses=sum(t['result']=='LOSS' for t in finished)
    pnl=sum(float(t['pnl']) for t in finished)
    open_trades=[t for t in quoted if t['status']=='OPEN']
    st.markdown('<div class="fourgrid">'+quick_tile('PAPER NET',f'${pnl:+,.2f}',f'{len(finished)} settled','up' if pnl>=0 else 'down')+quick_tile('WINS',str(wins),'Settled','up')+quick_tile('LOSSES',str(losses),'Settled','down')+quick_tile('WIN RATE',f'{100*wins/len(finished):.1f}%' if finished else '—',f'{len(open_trades)} open')+'</div>',unsafe_allow_html=True)
    with st.expander('Paper trade budget & fee ESTIMATE (new entries only)'):
        st.caption('Entry prices come from the real Kalshi order book, NOT from the old 50¢ setting. Actual fills may be worse, may be unavailable, or may not happen at all. Fees are still an estimated flat amount per contract.')
        st.info('Fixed paper budget: **$10.00 maximum per new entry**, including estimated fees. Only whole contracts can be simulated, so total spent may be slightly below $10. This is not a live-money purchase.')
        old=float(setting('paper_fee_cents','1'))
        new=st.number_input('Estimated fee per contract (¢)',min_value=0.0,max_value=20.0,value=old,step=0.5)
        if new!=old:set_setting('paper_fee_cents',new)
    with st.expander('Reset paper profit / losses / wins'):
        st.warning('Resets ALL paper trades (including legacy assumed-price trades and open positions) to $0 P&L, 0 wins, and 0 losses. Signal accuracy, Call, Quant Gate, Learning Call and bot settings stay unchanged. Old paper trades are archived in the local SQLite database.')
        confirm_reset=st.checkbox('I understand: reset the complete paper-trading ledger',key='confirm_reset_paper')
        if st.button('Reset paper P&L to $0',disabled=not confirm_reset,type='primary'):
            reset_count=reset_paper_ledger()
            st.session_state['paper_reset_message']=f'Paper ledger reset: {reset_count} trades archived. Your P&L, wins and losses now start at zero.'
            st.rerun()
    if st.session_state.get('paper_reset_message'):
        st.success(st.session_state.pop('paper_reset_message'))
    st.caption('New paper entries require a valid active KXBTC15M market and a live best ask. Without one, the entry is skipped. Kalshi official market results determine new trade wins/losses; paper P&L is still estimated because no actual fills occurred.')
    if trades:
        display=pd.DataFrame(trades).copy()
        display['Window ET']=display['window'].map(fmtwin)
        display['Paper P&L ($)']=display['pnl'].map(lambda x: f'${x:+,.2f}' if x is not None else 'OPEN')
        display['Observed entry ask (¢)']=display.apply(lambda r:round(r['assumed_entry_price']*100,2) if r['entry_source'] in ('KALSHI_LIVE_ASK','KALSHI_MARKET_ASK') else None,axis=1)
        display['Legacy assumed (¢)']=display.apply(lambda r:round(r['assumed_entry_price']*100,2) if r['entry_source'] not in ('KALSHI_LIVE_ASK','KALSHI_MARKET_ASK') else None,axis=1)
        display['Quote ET']=display['quote_ts'].map(lambda x:fmt(int(x)) if pd.notna(x) else '—')
        display['Cost + fee ($)']=display['entry_cost'].round(2)
        with st.expander('📋 Detailed paper trade ledger',expanded=False):
            st.dataframe(display[['Window ET','side','status','result','entry_source','market_ticker','Quote ET','Observed entry ask (¢)','Legacy assumed (¢)','contracts','Cost + fee ($)','Paper P&L ($)']],hide_index=True,use_container_width=True,height=230)
        previous=[t for t in trades if t.get('entry_source') not in ('KALSHI_LIVE_ASK','KALSHI_MARKET_ASK') and t['status']=='CLOSED' and t['pnl'] is not None]
        if previous:st.info(f'LEGACY assumed-price history: {len(previous)} settled paper entries, illustrative net P&L ${sum(float(t["pnl"]) for t in previous):+,.2f}. Excluded from quote-based totals above.')
        st.download_button('Download paper P&L CSV',display.to_csv(index=False).encode(),'btc15_paper_pnl.csv','text/csv')
    else:
        st.info('No automatic paper entries yet. Choose “Place trades automatically” in Call to begin collecting simulated results. The worker must remain running.')

with st.container(border=True):
    st.markdown('### 🧩 Learning Call')
    st.caption('Historical-analogue predictions using previously completed 15-minute BTC windows. Locked after four complete minutes.')
    lr=current(learning);a,b=st.columns(2)
    with a:box('WINDOW STATUS','Locked in for this window' if lr else 'Waiting for completed price data',f'{len(learning)} recorded learning reads')
    with b:box('PREDICTED CALL',signalword(lr['side']) if lr else 'Waiting for data',f'{lr["confidence"]:.1f}% model estimate' if lr else 'Awaiting minute 4')
    st.caption('Requires 25 completed historical windows to activate. Model probabilities are empirical estimates, not calibrated contract win probabilities.')
    tracker('LEARNING CALL TRACKER',learning)

with st.container(border=True):
    st.markdown('### 🧾 Paper bot & decisions')
    decision=next((r for r in decisions if r['window']==window),None)
    box('CURRENT 15-MIN DECISION',signalword(decision['side']) if decision else 'Waiting for Call',decision['reason'] if decision else 'Evaluating at selected Call minute')
    if decision and decision['side']!='SKIP' and decision['mode']=='Display, then confirm':
        ack=st.checkbox('I confirm this paper signal (no real order)',key=f'ack_{window}')
        st.info('Paper signal confirmed in this browser view.' if ack else 'Awaiting manual confirmation in this browser view.')
    st.caption('Automatic remains PAPER-ONLY: reads public Kalshi KXBTC15M best-ask quotes and official market results, without orders or account credentials. No guaranteed fills; fee estimates and available size may differ from actual trading. Missing market quotes mean NO paper trade.')
    if decisions:
        df=pd.DataFrame(decisions);df['Window ET']=df['window'].map(fmtwin)
        with st.expander('Recent decisions and SKIP reasons',expanded=False):
            st.dataframe(df[['Window ET','side','mode','price','reason']],hide_index=True,use_container_width=True)

with st.expander("📊 BTC movement, window history & hourly statistics", expanded=False):
    with st.container(border=True):
        a,b=st.columns(2)
        with a:
            st.markdown('#### 15-minute up/down counter')
            c,d=st.columns(2)
            with c:box('↑ UP',s.get('ups','—'),'Recently completed windows',kind='up')
            with d:box('↓ DOWN',s.get('downs','—'),'Recently completed windows',kind='down')
            st.caption(f'{s.get("history_count",0)} settled BTC spot windows observed; counter summarizes last 12')
        with b:
            st.markdown('#### Where BTC stands')
            box('WINDOW OPEN',f'${s["window_open"]:,.2f}' if s else '—',fmtwin(window))
            c,d=st.columns(2)
            with c:box('DISTANCE FROM TARGET',f'${s["gap"]:+,.2f}' if s else '—','Current spot minus window open',kind='up' if s and s['gap']>=0 else 'down')
            with d:box('GAP PER MINUTE LEFT',f'${s["per_min"]:,.2f}' if s else '—','Required per-minute gain to finish above open')
            c,d=st.columns(2)
            with c:box('1 MIN',f'${price-s["past1"]:+,.2f}' if s and s['past1'] is not None else '—',dark=True)
            with d:box('5 MIN',f'${price-s["past5"]:+,.2f}' if s and s['past5'] is not None else '—',dark=True)

    with st.container(border=True):
        a,b=st.columns(2)
        with a:
            st.markdown('#### Move needed')
            box('BTC MUST RISE TO FINISH ABOVE OPEN',f'${s["needed"]:,.2f}' if s else '—',f'{(900-elapsed)//60}m {(900-elapsed)%60}s remaining' if s else 'Awaiting data',kind='up')
            st.caption('A required movement calculation, **not** a probability or guaranteed outcome.')
        with b:
            st.markdown('#### How much BTC has been moving')
            c,d=st.columns(2)
            with c:box('TYPICAL 1-MIN MOVE',f'±${s["typical1"]:,.2f}' if s and s['typical1'] is not None else '—','Absolute 1m price body',dark=True)
            with d:box('TYPICAL 15-MIN MOVE',f'±${s["typical"]:,.2f}' if s and s['typical'] is not None else '—','Mean completed window net change',dark=True)
            st.caption('Real historical spot price movements; average absolute movement is not an implied forecast.')

    with st.container(border=True):
        a,b=st.columns(2)
        with a:
            st.markdown('#### Candle lean')
            if s and len(s['completed'])>=12:
                recent=s['completed'][-12:];total=sum(delta for _,delta in recent);up=sum(delta>0 for _,delta in recent)
                box('LAST 12 WINDOWS',('UP' if total>0 else 'DOWN' if total<0 else 'FLAT'),f'{up} green · {len(recent)-up} red · net ${total:+,.2f}',kind='up' if total>=0 else 'down')
            else:box('READING STORED HISTORY','Waiting for sufficient history','Requires at least 12 recorded complete windows')
        with b:
            st.markdown('#### Market edge')
            box('MODEL VS CONTRACT ODDS','Not calibrated','Quote retrieval is used for paper entries; no validated market edge estimate',kind='warn')
            st.caption('A genuine edge needs an identified market, contract price, a calibrated prediction, fees, and real executable quotes. No implied odds are invented.')

    with st.container(border=True):
        a,b=st.columns(2)
        with a:
            st.markdown('#### Window history')
            recent=(s.get('completed') or [])[-12:][::-1]
            if recent:
                st.dataframe(pd.DataFrame([{'Window (ET)':fmtwin(w),'Direction':'UP' if delta>0 else 'DOWN' if delta<0 else 'TIE','Net BTC change':round(delta,2)} for w,delta in recent]),hide_index=True,use_container_width=True,height=270)
            else:st.caption('Waiting for settled price windows')
        with b:
            st.markdown('#### Typical 15-min move by hour')
            bh=s.get('byhour',{})
            if bh:
                st.dataframe(pd.DataFrame([{'UTC hour':f'{i:02d}:00','Mean absolute move':f'${bh[i]:,.2f}'} for i in sorted(bh)]),hide_index=True,use_container_width=True,height=270)
            else:st.caption('Accumulating historical completed windows')

with st.expander('Full prediction history / CSV downloads'):
    choice=st.selectbox('Signal layer',['call','quant','learning'])
    rows=read_layer(choice)
    if rows:
        df=pd.DataFrame(rows);df['Window ET']=df['window'].map(fmtwin)
        st.dataframe(df[['Window ET','side','confidence','spot','outcome','close_price']],hide_index=True,use_container_width=True)
        st.download_button('Download CSV',df.to_csv(index=False).encode(),f'{choice}_btc15.csv','text/csv')
    else:st.caption('No samples yet')
st.caption('Cloud dashboard collects only while open; SQLite may reset on restart. Research-only. Signals are original transparent rules, not a replica of the private model in the screenshots. Accuracy grades spot window direction using Coinbase 1-minute candles; skips are excluded. Always-on tracking requires worker.py and persistent storage.')
