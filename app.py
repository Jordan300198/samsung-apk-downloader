#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║    Samsung APK Downloader — Web Platform                    ║
║    Modern, animated, glassmorphism UI                       ║
║    Powered by Galaxy Store API                              ║
╚══════════════════════════════════════════════════════════════╝
"""

import sys
import os
import json
import time
import queue
import threading
import secrets
from pathlib import Path
from datetime import datetime
from functools import partial

# ── Import self-contained galaxy_store module ──
from galaxy_store import (
    GalaxyStoreClient, SAMSUNG_PACKAGES, PACKAGE_CATEGORY,
    CATEGORIES, DEVICES, CSC_LIST, ONEUI_SDK, CAT_EMOJI,
    ENDPOINTS, CDN_SERVERS, CONTENT_CATEGORIES,
    fmt_size, fmt_speed, fmt_time,
    build_device_list, build_csc_list, resolve_sdks,
)

# ── AI Service (Gemini 2.5 Flash) ──
from ai_service import (
    verify_latest_version, ai_search, analyze_package_name,
    batch_verify, system_check as ai_system_check, is_available as ai_available,
)

# ── Flask ──
from flask import (
    Flask, render_template, request, jsonify,
    Response, send_file
)
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CORS(app)

# ── Config ──
OUTPUT_DIR = Path(__file__).parent / "downloads"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Global client (lazy init) ──
_client = None
_client_lock = threading.Lock()

def get_client():
    global _client
    with _client_lock:
        if _client is None:
            _client = GalaxyStoreClient(debug=False, rate_limit=12)
    return _client

# ── Progress tracking via SSE ──
_progress_queues = {}
_progress_lock = threading.Lock()

def register_progress(task_id: str) -> queue.Queue:
    q = queue.Queue()
    with _progress_lock:
        _progress_queues[task_id] = q
    return q

def unregister_progress(task_id: str):
    with _progress_lock:
        _progress_queues.pop(task_id, None)

def send_progress(task_id: str, data: dict):
    with _progress_lock:
        q = _progress_queues.get(task_id)
        if q:
            q.put(data)

def progress_generator(task_id: str):
    q = register_progress(task_id)
    try:
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        while True:
            try:
                data = q.get(timeout=30)
                yield f"data: {json.dumps(data)}\n\n"
                if data.get("type") in ("complete", "error"):
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
    finally:
        unregister_progress(task_id)

# ── API: Search apps ──

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify({"results": []})
    
    results = []
    for pkg, name in SAMSUNG_PACKAGES.items():
        if q in pkg.lower() or q in name.lower():
            cat = PACKAGE_CATEGORY.get(pkg, "")
            results.append({
                "package": pkg,
                "name": name,
                "category": cat,
                "emoji": CAT_EMOJI.get(cat, "📦"),
            })
    return jsonify({"results": results})

# ── API: Browse by category ──

@app.route("/api/categories")
def api_categories():
    cats = []
    for cat in CATEGORIES:
        n = sum(1 for v in PACKAGE_CATEGORY.values() if v == cat)
        cats.append({
            "name": cat,
            "count": n,
            "emoji": CAT_EMOJI.get(cat, "📦"),
        })
    return jsonify({"categories": cats})

@app.route("/api/category/<cat_name>")
def api_category(cat_name: str):
    items = []
    for pkg, name in SAMSUNG_PACKAGES.items():
        if PACKAGE_CATEGORY.get(pkg) == cat_name:
            items.append({
                "package": pkg,
                "name": name,
                "category": cat_name,
                "emoji": CAT_EMOJI.get(cat_name, "📦"),
            })
    return jsonify({"results": items})

# ── API: Devices / Regions / OneUI ──

@app.route("/api/devices")
def api_devices():
    region = request.args.get("region", "all")
    raw = []
    for name, info in DEVICES.items():
        entry = {"name": name, "oneui": info.get("oneui", "?")}
        if region in ("all", "EU") and info.get("eu"):
            entry["eu"] = info["eu"]
        if region in ("all", "CN") and info.get("cn"):
            entry["cn"] = info["cn"]
        raw.append(entry)
    return jsonify({"devices": raw})

@app.route("/api/config")
def api_config():
    return jsonify({
        "regions": [
            {"code": "all", "name": "🌍 Toutes les régions"},
            {"code": "EU", "name": "🇪🇺 Europe"},
            {"code": "CN", "name": "🇨🇳 Chine"},
        ],
        "oneui_versions": [
            {"ver": "7",   "label": "One UI 7   · SDK 35", "sdk": 35},
            {"ver": "8",   "label": "One UI 8   · SDK 36", "sdk": 36},
            {"ver": "8.5", "label": "One UI 8.5 · SDK 36", "sdk": 36},
            {"ver": "9",   "label": "One UI 9   · SDK 37", "sdk": 37},
        ],
        "csc_list": [
            {"code": c, "name": info["name"], "region": info["region"]}
            for c, info in CSC_LIST.items()
        ],
    })

# ── API: Quick check / Full scan ──

@app.route("/api/check", methods=["POST"])
def api_check():
    data = request.get_json()
    package = data.get("package", "").strip()
    region = data.get("region", "all")
    oneui = data.get("oneui", "8.5")
    device_id = data.get("device_id")
    
    if not package:
        return jsonify({"error": "Package manquant"}), 400
    
    client = get_client()
    sdks = resolve_sdks(None, False, oneui)
    
    # Quick check first
    result = client.quick_find(package, sdks)
    if result:
        return jsonify({
            "found": True,
            "quick": True,
            "result": {
                "package": result["package"],
                "name": result.get("name", package),
                "versionName": result.get("versionName", ""),
                "versionCode": result.get("versionCode", "0"),
                "contentSize": result.get("contentSize", "0"),
                "downloadURI": result.get("downloadURI", ""),
                "device": result.get("device", ""),
                "csc": result.get("csc", ""),
                "sdk": result.get("sdk", ""),
                "size_formatted": fmt_size(int(result.get("contentSize", 0))),
            }
        })
    
    # Full scan
    devices = build_device_list(region)
    csclist = build_csc_list(region)
    
    result = client.find_latest(package, devices, csclist, sdks, workers=12)
    if result:
        return jsonify({
            "found": True,
            "quick": False,
            "result": {
                "package": result["package"],
                "name": result.get("name", package),
                "versionName": result.get("versionName", ""),
                "versionCode": result.get("versionCode", "0"),
                "contentSize": result.get("contentSize", "0"),
                "downloadURI": result.get("downloadURI", ""),
                "device": result.get("device", ""),
                "csc": result.get("csc", ""),
                "sdk": result.get("sdk", ""),
                "size_formatted": fmt_size(int(result.get("contentSize", 0))),
            }
        })
    
    return jsonify({"found": False})

# ── API: Scan all ──

@app.route("/api/scan", methods=["POST"])
def api_scan():
    data = request.get_json()
    region = data.get("region", "all")
    oneui = data.get("oneui", "8.5")
    category = data.get("category")
    task_id = data.get("task_id", secrets.token_hex(8))
    
    client = get_client()
    sdks = resolve_sdks(None, False, oneui)
    devices = build_device_list(region)
    csclist = build_csc_list(region)
    
    pkgs = [(pkg, name) for pkg, name in SAMSUNG_PACKAGES.items()
            if (not category) or PACKAGE_CATEGORY.get(pkg) == category]
    
    def run_scan():
        results = []
        total = len(pkgs)
        for idx, (pkg, name) in enumerate(pkgs, 1):
            find = client.quick_find(pkg, sdks) or client.find_latest(pkg, devices, csclist, sdks, workers=12)
            if find:
                results.append(find)
            send_progress(task_id, {
                "type": "progress",
                "current": idx,
                "total": total,
                "package": pkg,
                "name": name,
                "found": find is not None,
                "percent": round(idx / total * 100, 1),
            })
        send_progress(task_id, {
            "type": "complete",
            "results": results,
            "count": len(results),
        })
    
    threading.Thread(target=run_scan, daemon=True).start()
    
    return jsonify({"task_id": task_id, "total": len(pkgs)})

@app.route("/api/scan/stream/<task_id>")
def scan_stream(task_id: str):
    return Response(
        progress_generator(task_id),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

# ── API: Download ──

@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json()
    url = data.get("url")
    package = data.get("package")
    version = data.get("version")
    
    if not url or not package:
        return jsonify({"error": "URL et package requis"}), 400
    
    task_id = secrets.token_hex(8)
    filename = f"{package}-{version or 'latest'}.apk"
    dest = OUTPUT_DIR / filename
    
    def run_dl():
        client = get_client()
        try:
            send_progress(task_id, {"type": "download_start", "filename": filename})
            
            def cb(done, total):
                pct = round(done / total * 100, 1) if total else 0
                send_progress(task_id, {
                    "type": "download_progress",
                    "done": done,
                    "total": total,
                    "percent": pct,
                    "size_done": fmt_size(done),
                    "size_total": fmt_size(total) if total else "?",
                })
            
            result = client.download(url, dest, cb)
            send_progress(task_id, {
                "type": "complete",
                "filename": filename,
                "size": result["size"],
                "size_fmt": fmt_size(result["size"]),
                "speed": fmt_speed(result["speed"]),
                "elapsed": fmt_time(result["elapsed"]),
                "path": str(dest),
            })
        except Exception as exc:
            send_progress(task_id, {"type": "error", "message": str(exc)})
    
    threading.Thread(target=run_dl, daemon=True).start()
    
    return jsonify({"task_id": task_id, "filename": filename})

@app.route("/api/download/stream/<task_id>")
def download_stream(task_id: str):
    return Response(
        progress_generator(task_id),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

# ── API: Serve downloaded file ──

@app.route("/api/file/<filename>")
def api_file(filename: str):
    path = OUTPUT_DIR / filename
    if not path.exists():
        return jsonify({"error": "Fichier introuvable"}), 404
    return send_file(path, as_attachment=True, download_name=filename)

# ── API: History ──

@app.route("/api/history")
def api_history():
    hist_path = OUTPUT_DIR / "_history.json"
    if not hist_path.exists():
        return jsonify({"history": []})
    try:
        history = json.loads(hist_path.read_text())
        for h in history:
            if "size" in h:
                h["size_fmt"] = fmt_size(h["size"])
            if "speed" in h:
                h["speed_fmt"] = fmt_speed(h["speed"])
        return jsonify({"history": reversed(history[-50:])})
    except Exception:
        return jsonify({"history": []})

@app.route("/api/history/clear", methods=["POST"])
def api_history_clear():
    hist_path = OUTPUT_DIR / "_history.json"
    if hist_path.exists():
        hist_path.unlink()
    return jsonify({"ok": True})

# ── AI Routes (Gemini 2.5 Flash) ──

@app.route("/api/ai/status")
def api_ai_status():
    """Check AI system readiness."""
    return jsonify(ai_system_check())


@app.route("/api/ai/verify", methods=["POST"])
def api_ai_verify():
    """Verify if a found version is the latest using AI."""
    data = request.get_json()
    package = data.get("package", "")
    version = data.get("versionName", "")
    code = data.get("versionCode", "")
    name = data.get("name", "")

    if not package:
        return jsonify({"error": "Package requis"}), 400

    result = verify_latest_version(package, version, code, name)
    return jsonify(result)


@app.route("/api/ai/batch-verify", methods=["POST"])
def api_ai_batch_verify():
    """Batch verify multiple packages with AI."""
    data = request.get_json()
    packages = data.get("packages", [])

    if not packages:
        return jsonify({"error": "Liste de packages requise"}), 400

    results = batch_verify(packages)
    return jsonify({"results": results})


@app.route("/api/ai/search")
def api_ai_search():
    """Natural language search powered by AI."""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"results": []})

    results = ai_search(q)
    return jsonify({"results": results})


# ═══════════════════════════════════════════════════════
#  INFOS SERVEURS / CDN / ENDPOINTS (testés)
# ═══════════════════════════════════════════════════════

# ── Content Categories (Galaxy Store browse) ✅ testé ──

@app.route("/api/content-categories")
def api_content_categories():
    """List all Galaxy Store content categories."""
    return jsonify({
        "categories": get_client().list_content_categories()
    })


@app.route("/api/browse-category", methods=["POST"])
def api_browse_category():
    """Browse apps in a Galaxy Store content category."""
    data = request.get_json() or {}
    cat_id = data.get("category_id", "0000005309")
    model = data.get("device", "SM-S948B")
    sdk = data.get("sdk", 37)
    page = data.get("page", 1)
    page_size = data.get("page_size", 20)

    result = get_client().browse_content_category(cat_id, model, sdk, page_size, page)
    return jsonify({
        "category_id": cat_id,
        "category_name": CONTENT_CATEGORIES.get(cat_id, "Unknown"),
        "result": result,
    })


# ── Servers / Endpoints / CDN (infos statiques vérifiées) ──

@app.route("/api/servers")
def api_servers():
    """List all known CDN servers."""
    return jsonify(get_client().get_servers())


@app.route("/api/endpoints")
def api_endpoints():
    """List verified API endpoints."""
    eps = dict(ENDPOINTS)
    return jsonify({"count": len(eps), "endpoints": eps})


@app.route("/api/resolve-cdn")
def api_resolve_cdn():
    """Identify which CDN a download URL belongs to."""
    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "url parameter required"}), 400
    return jsonify({"url": url, "cdn": get_client().resolve_download_domain(url)})


# ── Health check (for Render) ──

@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": "4.1.0"})

# ── Pages ──

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/scan")
def scan_page():
    return render_template("scan.html")

@app.route("/history")
def history_page():
    return render_template("history.html")

@app.route("/about")
def about_page():
    return render_template("about.html")

# ── Main ──

if __name__ == "__main__":
    print(f"""
{'='*55}
  Samsung APK Downloader — Web Platform
  http://localhost:5050
{'='*55}
""")
    app.run(host="0.0.0.0", port=5050, debug=True, threaded=True)
