🇷🇺 [Читать на русском](README_RU.md)

An interactive conveyor arcade application featuring real-time collision detection, competitive global leaderboard state management, and Cloudflare Tunnel edge deployment.

### Key Architectural Highlights:
* **Event-Driven Conveyor Engine:** Dynamic object generation, progressive velocity scaling, and precise collision detection written in vanilla JavaScript.
* **Competitive Leaderboard Persistence:** Backend score validation tracking global player rankings with atomic high-score persistence in SQLite.
* **Edge Tunnel Deployment:** Local backend ingress powered by Cloudflare Tunnels (`cloudflared`) providing secure CORS bypass and public HTTPS routing for Telegram Web Apps without exposing public ports.
* **Telegram Ecosystem Integration:** Session authentication mapped against unique Telegram identifiers for decentralized player profile tracking.

### Tech Stack:
* Python 3.12
* Aiohttp / Flask (Backend API & ranking engine)
* JavaScript / HTML5 Canvas (Physics & rendering runtime)
* Cloudflare Tunnel (Zero-trust secure edge proxy)
* python-dotenv (Configuration security)

### Quick Start:
```bash
pip install -r requirements.txt
python main8.py
