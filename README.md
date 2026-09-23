# LAN Share

A tiny local file-transfer server for offline Wi-Fi hotspot networks. No
internet connection is required or used anywhere — every asset (CSS, JS,
QR code) is generated and served locally.

Typical setup: your PC creates a Wi-Fi hotspot with no internet
passthrough. Anyone who joins that hotspot opens a browser and goes to
`https://<your-ip>:5000` to upload or download files with you, entirely
over the local network. The server uses a self-signed HTTPS certificate
(no internet/CA needed), so each browser will show a one-time
"connection not private" warning to click through - see
[HTTPS and the certificate warning](#https-and-the-certificate-warning).

## 1. Turn on Windows Mobile Hotspot

1. Open **Settings > Network & Internet > Mobile hotspot**.
2. Turn **Mobile hotspot** on.
   - If you have no internet connection, Windows may show a warning icon
     next to the toggle. That's fine — the hotspot still creates a local
     Wi-Fi network that devices can join and reach this server on, it
     just won't relay internet traffic.
3. Note the **Network name** and **Network password** shown there —
   that's what other devices connect to.
4. By default, Windows assigns the host PC the address `192.168.137.1`
   on this hotspot.

## 2. Find your host PC's local IP

Open Command Prompt and run:

```
ipconfig
```

Look for an adapter named something like **"Wireless LAN adapter Local
Area Connection* N"** or **"Ethernet adapter Local Area Connection*
N"** — the one with an IPv4 address in the `192.168.137.x` range. That
address (usually `192.168.137.1`) is what you'll share with other
devices, and what `server.py` will print automatically on startup.

## 3. Install and run

### Easiest: the exe (no Python needed)

Download `release/LAN-Share.exe` from this repo, put it in any folder,
and double-click it. It creates `shared/` and `certs/` next to itself.
When the Windows Firewall prompt appears, allow **Private networks**.
Flags work the same from a terminal: `LAN-Share.exe --port 8080`.

To rebuild the exe yourself, run `build.bat` (inside the venv below).

### From source

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python server.py
```

Optional flags:

```
python server.py --port 8080 --max-upload-mb 1000 --mode wifi
```

## Modes: Wi-Fi vs Bluetooth

`--mode` controls which network `server.py` advertises (the URL it prints
and the QR code it generates). The server always listens on every
interface regardless of mode - this only affects what's shown on screen.

- `--mode auto` (default) - prefers Wi-Fi if available, falls back to
  Bluetooth, then anything else.
- `--mode wifi` - use when you have a Wi-Fi hotspot or any Wi-Fi
  connection active (see "Turn on Windows Mobile Hotspot" above).
- `--mode bluetooth` - use when there's no Wi-Fi network available at
  all (no router, no phone, no hotspot-capable adapter). See below.

### Bluetooth mode setup

If your Wi-Fi adapter doesn't support standalone hotspot mode (check
with `netsh wlan show drivers` and look for "Hosted network supported"),
and you have no router or phone to anchor a Wi-Fi connection to, you can
still transfer files with zero internet and zero extra hardware over
Bluetooth:

1. On **both** PCs: Settings > Bluetooth & devices > turn Bluetooth on.
2. On PC A: Settings > Bluetooth & devices > **Add device** > Bluetooth >
   select PC B when it appears > confirm the matching PIN on both
   screens.
3. Once paired: **Control Panel > Network and Internet > Network
   Connections**, right-click **Bluetooth Network Connection** > **View
   Bluetooth Network Devices** > select the paired PC > **Connect
   using > Access point**. (Pairing alone does not bring the IP link up
   - this step does.)
4. Run `ipconfig` and note the new IP under the Bluetooth Network
   Connection adapter.
5. Run `python server.py --mode bluetooth` and share the printed URL.

Bluetooth PAN is much slower than Wi-Fi - fine for documents and
photos, but expect a long wait for anything multiple gigabytes in
size.

On startup you'll see something like:

```
============================================================
  LAN Share
============================================================
  Share this: https://192.168.137.1:5000
  Shared folder: C:\...\LAN-Share\shared
  Max upload size: 500 MB per file
  Using a self-signed certificate - browsers will show a
  'connection not private' warning once per device. Click
  Advanced > Proceed (wording varies by browser) to continue.
  Press Ctrl+C to stop.
============================================================
```

A QR code encoding that same URL is generated at `static/qr.png` and
shown on the page itself, so anyone already viewing the page on one
device can let someone else scan it instead of typing the address.

## 4. Use it

On another device, join the hotspot's Wi-Fi network, then open
`https://192.168.137.1:5000` (or scan the QR code from a device that's
already on the page) in any browser. From there you can:

- Drag and drop files onto the page, or click the drop zone to browse
  and select files (multiple at once).
- Watch the live upload progress bar.
- See every file currently shared, with its size, a **Download** link,
  and a **Delete** button (asks for confirmation first).

The file list refreshes automatically every few seconds, so if someone
else uploads or deletes something, you'll see it without reloading the
page.

Files are stored in the `shared/` folder next to `server.py` and
persist across restarts.

## HTTPS and the certificate warning

`server.py` serves HTTPS using a self-signed certificate it generates on
first run (`certs/cert.pem` / `certs/key.pem`, kept next to `server.py`
and reused across restarts as long as your IP doesn't change). There's
no real certificate authority behind it - it's just enough to encrypt
the connection - so every browser on every device will show a warning
like **"Your connection is not private"** (Chrome) or **"Warning:
Potential Security Risk"** (Firefox) the first time it visits.

That's expected. Click **Advanced** (or **Show Details**) and then
**Proceed to \<ip\> (unsafe)** / **Accept the Risk and Continue**. This
is safe to do here: you generated the certificate yourself, on your own
PC, for a server you control on a network you trust.

If a new device's Wi-Fi/hotspot address ever shows up that the current
certificate doesn't cover, `server.py` regenerates it automatically on
the next startup - so the warning may reappear once after that, even on
devices that already clicked through before.

## Troubleshooting

**Other devices on the hotspot can't reach the page / connection times
out.**

This is almost always the **Windows Defender Firewall** prompt. The
first time you run `server.py`, Windows will pop up a dialog titled
something like *"Windows Defender Firewall has blocked some features of
this app"* for Python. You **must** check the box for **Private
networks** (a Windows Mobile Hotspot network is classified as Private)
and click **Allow access**. If you accidentally dismissed the prompt or
clicked Cancel:

1. Open **Control Panel > System and Security > Windows Defender
   Firewall > Allow an app or feature through Windows Defender
   Firewall**.
2. Click **Change settings**, find **Python** (or add it manually via
   **Allow another app...** and browse to your `venv\Scripts\python.exe`
   or system Python).
3. Check the **Private** column checkbox for it.
4. Click **OK** and restart `server.py`.

**"Address already in use" on startup.**

Something else is already listening on port 5000. Run with a different
port: `python server.py --port 5050`.

**Upload fails with a 413 / "exceeds max upload size" error.**

Raise the limit: `python server.py --max-upload-mb 2000` (or whatever
size you need, in megabytes).

## What this app deliberately does not have

No authentication, no database, no cloud deployment config, no Docker,
no AI/LLM integration. It's a single-purpose local utility — anyone on
your hotspot can upload, download, and delete files, by design. Only
run it on a network you control and trust.
