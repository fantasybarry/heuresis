# Sharing one Alpaca feed between two machines

Alpaca allows **one real-time stream connection per account**. If two machines both start the live monitor with the same keys, the second is rejected with `Alpaca stream: connection limit exceeded` (error 406). The data pool fixes this: one machine holds the single Alpaca stream and relays it to every Nomisma app, including its own.

```
                    ┌──────────── Machine A ─────────────┐
 Alpaca stream ────►│ data pool (run.py --pool, :8770)   │
  (one connection)  │      │                             │
                    │      └──► Nomisma app (127.0.0.1)  │
                    └──────┬─────────────────────────────┘
                           │ local network, TCP 8770
                           ▼
                    ┌──────────── Machine B ─────────────┐
                    │ Nomisma app (NOMISMA_POOL=A:8770)  │
                    └────────────────────────────────────┘
```

Only the live stream goes through the pool. Each app still loads its own calendar, history, and snapshots directly from Alpaca, so **both machines need Alpaca keys**. Those requests share one account rate limit: 200 requests/minute on the free Basic plan, 10,000 on Algo Trader Plus.

## Before you start

- Both machines run this version of Nomisma (it includes `nomisma/pool.py`). Rebuild desktop apps after updating the source.
- Both machines are on the same local network, and you know Machine A's local IP address:
  - macOS: **System Settings → Wi-Fi → Details → TCP/IP**, or `ipconfig getifaddr en0`
  - Windows: `ipconfig` → **IPv4 Address**
- Pick a shared token of at least 16 characters, for example:
  ```sh
  python3 -c "import secrets; print(secrets.token_urlsafe(24))"
  ```

## Machine A — runs the pool and uses the data

1. Edit `.env` in the project directory (the desktop app uses the same file; **Open Configuration Folder** shows it):
   ```dotenv
   ALPACA_API_KEY=your_key_here
   ALPACA_SECRET_KEY=your_secret_here
   ALPACA_FEED=iex
   ALPACA_PAPER=true
   NOMISMA_POOL=127.0.0.1:8770
   NOMISMA_POOL_TOKEN=your-shared-token
   ```
   `NOMISMA_POOL` must be set here too. Without it, Machine A's own app connects to Alpaca beside the pool and one of them gets error 406.

2. Start the pool in its own terminal and leave it running:
   ```sh
   python3 run.py --pool --port 8770
   ```
   It prints `Nomisma data pool listening on 0.0.0.0:8770`. It connects to Alpaca only once an app subscribes.

3. Allow incoming connections on TCP 8770. On macOS, choose **Allow** when the firewall asks about Python. If you use a stricter firewall, add an inbound rule for that port.

4. Start Nomisma as usual (`python3 run.py`, **Launch Nomisma.command**, or the desktop app). If it was already running, restart it so it reads `.env`.

5. In **Live monitor → Configure**, choose **Alpaca**, enter symbols, save, and click **Start**.

## Machine B — uses the data

1. Edit `.env`. On Windows desktop builds, it is `%LOCALAPPDATA%\Nomisma\.env` (**File → Open configuration folder**):
   ```dotenv
   ALPACA_API_KEY=your_key_here
   ALPACA_SECRET_KEY=your_secret_here
   ALPACA_FEED=iex
   ALPACA_PAPER=true
   NOMISMA_POOL=192.168.1.20:8770
   NOMISMA_POOL_TOKEN=your-shared-token
   ```
   Replace `192.168.1.20` with Machine A's IP. Use the same keys, feed, and token as Machine A.

2. Start or restart Nomisma. On Windows desktop builds, use **File → Restart local service**.

3. In **Live monitor → Configure**, choose **Alpaca**, enter symbols, save, and click **Start**.

Both monitors should now show **Live**.

## Daily order

1. Start the pool on Machine A.
2. Start the monitors on either machine, in any order.

If the pool stops, both monitors show **Reconnecting** and resume on their own once it is back.

## What to expect

- **Symbols**: each machine receives only the symbols it monitors. Together the two machines can watch up to **50 unique symbols**; Alpaca's Basic plan streams at most **30**. A symbol watched on both machines counts once.
- **Adding symbols**: when one machine starts with symbols the pool isn't streaming yet, the pool reconnects to Alpaca for everyone. The other machine briefly shows **Connecting**, then **Live**, and missed minute bars are filled from history.
- **Alpaca errors**: if the Alpaca stream drops, both monitors disconnect and reconnect with their usual backoff. A symbol-limit rejection stops both monitors until you shorten the lists.
- **Slow machines**: a machine that can't keep up is disconnected and reconnects. It never holds up the other one.

## Troubleshooting

| Message | Cause | Fix |
|---|---|---|
| `Could not reach the data pool at …` | The pool isn't running, the IP or port is wrong, or a firewall is blocking it | Check step 2 on Machine A. Test from Machine B with `nc -vz <A-ip> 8770` (macOS) or `Test-NetConnection <A-ip> -Port 8770` (Windows) |
| `The data pool rejected this workstation's token.` | The tokens are different | Copy the token exactly to both `.env` files and restart |
| `Set NOMISMA_POOL_TOKEN (16+ characters)…` | The pool machine has no token or a short one | Set it in Machine A's `.env` |
| `Alpaca stream: connection limit exceeded…` | Something else is using the stream: an app without `NOMISMA_POOL`, or a second pool | Set `NOMISMA_POOL` on every machine and run only one pool |
| `The data pool is full…` | The two machines together watch more than 50 symbols | Shorten one list |
| `Alpaca stream: subscription symbol limit exceeded…` | The combined list exceeds your Alpaca plan, for example 30 on Basic | Shorten the lists or upgrade the plan |

## Security

The pool sends market data **unencrypted** over your local network. The token is its only protection. Keep port 8770 on a trusted home or office network, and never forward it to the internet. Alpaca's market-data terms also apply to sharing its data between devices.
