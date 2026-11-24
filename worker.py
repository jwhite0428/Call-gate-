from engine import feed,process,bootstrap_history
import time,datetime as dt
print('BTC15 research worker running: paper only; leave this window open. Ctrl+C to stop.',flush=True)
while True:
    try:
        bootstrap_history()
        candles,price=feed();window=process(candles,price)
        print(dt.datetime.now().isoformat(timespec='seconds'),f'BTC ${price:,.2f}',f'window {window}',flush=True)
    except KeyboardInterrupt:break
    except Exception as exc:print('Feed error; no invented signals:',exc,flush=True)
    time.sleep(20)
