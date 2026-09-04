"""
LAN Share - a local file-transfer server for offline Wi-Fi hotspot networks.

Run with:  python server.py [--port 5000] [--max-upload-mb 500]

No internet connection is required or used anywhere in this app.
"""

import argparse
import datetime
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename
import psutil
import qrcode

BASE_DIR = Path(__file__).resolve().parent
SHARED_DIR = BASE_DIR / "shared"
STATIC_DIR = BASE_DIR / "static"
QR_PATH = STATIC_DIR / "qr.png"
CERT_DIR = BASE_DIR / "certs"
CERT_PATH = CERT_DIR / "cert.pem"
KEY_PATH = CERT_DIR / "key.pem"

DEFAULT_PORT = 5000
DEFAULT_MAX_UPLOAD_MB = 500

app = Flask(__name__)

SHARED_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def classify_interfaces():
    """Group every active non-loopback IPv4 address by interface type.

    Returns (wifi_ips, bluetooth_ips, other_ips). Classification is based on
    the OS-reported interface name - Windows names these predictably
    ("Wi-Fi", "Bluetooth Network Connection", etc), so no extra permissions
    or driver queries are needed.
    """
    wifi_ips, bt_ips, other_ips = [], [], []
    stats = psutil.net_if_stats()

    for name, addrs in psutil.net_if_addrs().items():
        if name in stats and not stats[name].isup:
            continue
        lname = name.lower()
        for addr in addrs:
            if addr.family != socket.AF_INET or addr.address.startswith("127."):
                continue
            if "bluetooth" in lname or "pan" in lname or "bnep" in lname:
                bt_ips.append(addr.address)
            elif any(k in lname for k in ("wi-fi", "wifi", "wireless", "wlan")):
                wifi_ips.append(addr.address)
            else:
                other_ips.append(addr.address)

    return wifi_ips, bt_ips, other_ips


def pick_url(wifi_ips, bt_ips, other_ips, mode, port):
    """Pick the primary URL to display/QR-encode for the requested mode.

    Returns (url_or_None, warning_or_None).
    """
    if mode == "wifi":
        candidates = wifi_ips or other_ips
        warning = None if candidates else (
            "No active Wi-Fi IP found. Is Wi-Fi connected (any network, "
            "internet not required), or is Mobile Hotspot on?"
        )
    elif mode == "bluetooth":
        candidates = bt_ips
        warning = None if candidates else (
            "No active Bluetooth PAN IP found. Pair the devices first, then "
            "connect via 'View Bluetooth Network Devices' > Connect using > "
            "Access point."
        )
    else:
        candidates = wifi_ips or bt_ips or other_ips
        warning = None if candidates else "No active network IP found on any interface."

    if not candidates:
        return None, warning

    for ip in candidates:
        if ip.startswith("192.168.137."):
            return f"https://{ip}:{port}", None
    return f"https://{candidates[0]}:{port}", None


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def list_files():
    items = []
    for entry in SHARED_DIR.iterdir():
        if entry.is_file():
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "size": human_size(stat.st_size),
                "mtime": stat.st_mtime,
            })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def safe_join_shared(filename: str):
    """Resolve filename inside SHARED_DIR only. Returns None on any traversal attempt."""
    filename = secure_filename(filename)
    if not filename:
        return None
    shared_resolved = SHARED_DIR.resolve()
    target = (SHARED_DIR / filename).resolve()
    try:
        target.relative_to(shared_resolved)
    except ValueError:
        return None
    return target


def unique_path(path: Path) -> Path:
    """Avoid clobbering existing files: file.txt -> file (1).txt -> file (2).txt ..."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem} ({counter}){suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def generate_qr(url: str) -> None:
    img = qrcode.make(url)
    img.save(QR_PATH)


def _cert_covers_ips(cert_bytes: bytes, ips: set) -> bool:
    cert = x509.load_pem_x509_certificate(cert_bytes)
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    covered = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
    return ips.issubset(covered)


def ensure_cert(ips: list) -> tuple:
    """Return (cert_path, key_path) for a self-signed cert covering every
    given IP, generating (or regenerating, if a new IP shows up) as needed.

    Reused across runs so the same LAN Wi-Fi/hotspot IPs don't retrigger a
    fresh "untrusted certificate" prompt on client devices every restart.
    """
    ip_set = {"127.0.0.1", *ips}

    if CERT_PATH.exists() and KEY_PATH.exists():
        try:
            if _cert_covers_ips(CERT_PATH.read_bytes(), ip_set):
                return CERT_PATH, KEY_PATH
        except (ValueError, x509.ExtensionNotFound):
            pass  # fall through and regenerate

    CERT_DIR.mkdir(exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "LAN Share")])
    san = [x509.IPAddress(ipaddress.ip_address(ip)) for ip in sorted(ip_set)]
    san.append(x509.DNSName("localhost"))
    now = datetime.datetime.now(datetime.timezone.utc)

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .sign(key, hashes.SHA256())
    )

    KEY_PATH.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    CERT_PATH.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return CERT_PATH, KEY_PATH


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template(
        "index.html",
        files=list_files(),
        max_upload_mb=app.config.get("MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB),
        server_url=app.config.get("SERVER_URL", ""),
        server_warning=app.config.get("SERVER_WARNING", ""),
        mode=app.config.get("MODE", "auto"),
        all_urls=app.config.get("ALL_URLS", []),
    )


@app.route("/api/files")
def api_files():
    return jsonify(list_files())


@app.route("/upload", methods=["POST"])
def upload():
    uploaded = request.files.getlist("files")
    saved, skipped = [], []

    for f in uploaded:
        if not f or f.filename == "":
            continue
        filename = secure_filename(f.filename)
        if not filename:
            skipped.append(f.filename)
            continue
        dest = unique_path(SHARED_DIR / filename)
        f.save(dest)
        saved.append(dest.name)

    return jsonify({"saved": saved, "skipped": skipped})


@app.route("/download/<path:filename>")
def download(filename):
    target = safe_join_shared(filename)
    if target is None or not target.is_file():
        abort(404)
    return send_from_directory(SHARED_DIR, target.name, as_attachment=True)


@app.route("/delete/<path:filename>", methods=["POST"])
def delete(filename):
    target = safe_join_shared(filename)
    if target is None or not target.is_file():
        abort(404)
    target.unlink()
    return jsonify({"deleted": target.name})


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"error": "File exceeds the max upload size."}), 413


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "Not found."}), 404


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LAN Share - local file transfer server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                         help=f"Port to run the server on (default: {DEFAULT_PORT})")
    parser.add_argument("--max-upload-mb", type=int, default=DEFAULT_MAX_UPLOAD_MB,
                         help=f"Max upload size per file, in MB (default: {DEFAULT_MAX_UPLOAD_MB})")
    parser.add_argument("--mode", choices=["auto", "wifi", "bluetooth"], default="auto",
                         help="Which network to advertise/QR-encode: wifi, bluetooth, or "
                              "auto-detect (default: auto)")
    args = parser.parse_args()

    app.config["MAX_CONTENT_LENGTH"] = args.max_upload_mb * 1024 * 1024
    app.config["MAX_UPLOAD_MB"] = args.max_upload_mb
    app.config["MODE"] = args.mode

    wifi_ips, bt_ips, other_ips = classify_interfaces()
    server_url, warning = pick_url(wifi_ips, bt_ips, other_ips, args.mode, args.port)
    app.config["SERVER_URL"] = server_url or ""
    app.config["SERVER_WARNING"] = warning or ""

    all_urls = []
    for ip in wifi_ips:
        all_urls.append({"label": "Wi-Fi", "url": f"https://{ip}:{args.port}"})
    for ip in bt_ips:
        all_urls.append({"label": "Bluetooth", "url": f"https://{ip}:{args.port}"})
    for ip in other_ips:
        all_urls.append({"label": "Other", "url": f"https://{ip}:{args.port}"})
    app.config["ALL_URLS"] = all_urls

    cert_path, key_path = ensure_cert(wifi_ips + bt_ips + other_ips)

    print("=" * 60)
    print("  LAN Share")
    print("=" * 60)
    print(f"  Mode: {args.mode}")
    if server_url:
        print(f"  Share this: {server_url}")
        generate_qr(server_url)
    else:
        print(f"  WARNING: {warning}")
        print("  Starting anyway - the server listens on all interfaces, so it")
        print("  will work as soon as a matching connection appears. Run")
        print("  'ipconfig' once connected to find the address to share.")

    if all_urls:
        print("  All detected addresses:")
        for entry in all_urls:
            print(f"    [{entry['label']}] {entry['url']}")

    print(f"  Shared folder: {SHARED_DIR}")
    print(f"  Max upload size: {args.max_upload_mb} MB per file")
    print("  Using a self-signed certificate - browsers will show a")
    print("  'connection not private' warning once per device. Click")
    print("  Advanced > Proceed (wording varies by browser) to continue.")
    print("  Press Ctrl+C to stop.")
    print("=" * 60)

    app.run(host="0.0.0.0", port=args.port, debug=False, ssl_context=(str(cert_path), str(key_path)))


if __name__ == "__main__":
    main()
