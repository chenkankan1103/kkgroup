# Discord Activities Preview - Merchant Example

This folder contains a minimal custom Discord Activity that mirrors a simple button interaction from the
`shop_commands` merchant system. It lets you preview an "in‑voice‑channel" web‑app with a button and the
ability to read/update the user's KKcoin balance via the existing database logic.

## Overview

- **Front-end**: `index.html` + `main.js` using the Activities SDK to connect to Discord.
- **Back-end**: `server.py` (Flask) exposes endpoints that wrap the same database helpers already used by the
bot. This allows you to reuse `get_user_kkcoin`/`update_user_kkcoin` logic.

## Prerequisites

1. Node.js (for Activities SDK) - install from https://nodejs.org/
2. Python virtual environment with the project's requirements (already exists in this repo).
3. A Discord application with Activities enabled:
   - Go to the [Discord Developer Portal](https://discord.com/developers/applications).
   - Select or create your bot application.
   - Under "Rich Presence > Activities" add a new activity. The `URL` should point to your hosted
     `index.html` (see preview steps below).
   - You may use a tool like `ngrok` to expose your localhost to HTTPS.

## Previewing Locally

1. **Start the Python backend** (in the repo root):
   ```powershell
   cd c:\Users\88697\Desktop\kkgroup\activities\merchant
   # activate your venv if not already
   & c:\Users\88697\Desktop\kkgroup\.venv\Scripts\Activate.ps1
   pip install flask
   python server.py
   ```
   The API will listen on `http://localhost:5000` by default.

2. **Serve the frontend** (any static server, e.g., using `http-server` from npm):
   ```bash
   cd activities/merchant
   npm install -g http-server
   http-server -p 3000
   ```

3. **Expose via HTTPS** (for Discord to load it):
   ```bash
   ngrok http 3000
   ```
   Use the generated `https://...` URL as the Activity URL in the Developer Portal.

4. **Start activity in voice channel**: join a voice channel in your server where the bot is present,
   click the rocket icon, and select your custom activity. A webview will open showing the simple
   merchant button interface.

## Extending

- Add additional endpoints to `server.py` for other interactions (e.g. gambling, shop purchases).
- Enhance the React/HTML UI as desired.
- Once ready, deploy the frontend/backend to a static host and update the activity URL accordingly.

Happy prototyping!