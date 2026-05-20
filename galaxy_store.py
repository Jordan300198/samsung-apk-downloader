"""
Samsung Galaxy Store API Client — self-contained module.
All data (devices, CSCs, packages, CDNs) embedded.

⚠️  ENDPOINTS TESTÉS UN PAR UN contre l'API réelle.
    Seuls les endpoints qui retournent resultCode=1 avec
    des données valides sont inclus.
"""

import re
import secrets
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Semaphore
from pathlib import Path

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    raise ImportError("pip install requests")

# ═══════════════════════════════════════════════════════
#  ENDPOINTS TESTÉS ✅
# ═══════════════════════════════════════════════════════

API_BASE = "https://vas.samsungapps.com"

ENDPOINTS = {
    # ✅ TESTÉ — retourne resultCode=1 + downloadURI
    "stubDownload":          API_BASE + "/earth/stub/stubDownload.as",
    # ✅ TESTÉ — retourne les mêmes infos que stubDownload
    "overseasStubDownload":  API_BASE + "/overseas/stub/stubDownload.as",
    # ✅ TESTÉ — liste les apps d'une catégorie de contenu
    "contentCategoryList":   API_BASE + "/product/getContentCategoryProductList.as",
}

API_URL = ENDPOINTS["stubDownload"]
API_CATEGORY_URL = ENDPOINTS["contentCategoryList"]

# ═══════════════════════════════════════════════════════
#  SERVEURS CDN (observés dans les URLs de téléchargement)
# ═══════════════════════════════════════════════════════

CDN_SERVERS = {
    "download_main":   "https://ecdn.game.samsungapps.biz",
    "download_backup": "https://cdn.game.samsungapps.com",
    "download_legacy": "https://cd.samsungapps.com",
    "images":          "https://img.samsungapps.com",
    "cache":           "https://cache.samsungapps.com",
    "analytics":       "https://r.game.samsungapps.biz",
}

# ═══════════════════════════════════════════════════════
#  CONTENT CATEGORIES (testées via contentCategoryList)
# ═══════════════════════════════════════════════════════

CONTENT_CATEGORIES = {
    "0000005309": "All Apps & Games", "0000005310": "Featured",
    "0000005311": "Top Games", "0000005312": "Top Apps",
    "0000005313": "New Games", "0000005314": "New Apps",
    "0000005315": "Entertainment", "0000005316": "Lifestyle",
    "0000005317": "Photography", "0000005318": "Music & Audio",
    "0000005319": "Video Players", "0000005320": "Social",
    "0000005321": "Communication", "0000005322": "Productivity",
    "0000005323": "Business", "0000005324": "Education",
    "0000005325": "Tools", "0000005326": "Health & Fitness",
    "0000005327": "Medical", "0000005328": "Travel & Local",
    "0000005329": "Books & Reference", "0000005330": "News & Magazines",
    "0000005331": "Maps & Navigation", "0000005332": "Weather",
    "0000005333": "Customization", "0000005334": "Sports",
    "0000005335": "Finance", "0000005336": "Shopping",
    "0000005337": "Food & Drink", "0000005338": "House & Home",
    "0000005339": "Auto & Vehicles", "0000005340": "Parenting",
    "0000005341": "Comics", "0000005342": "Watch Faces",
}

# ═══════════════════════════════════════════════════════
#  CONSTANTES
# ═══════════════════════════════════════════════════════

ONEUI_SDK = {
    "7": 35, "7.0": 35,
    "8": 36, "8.0": 36, "8.1": 36, "8.5": 36,
    "9": 37, "9.0": 37,
}

CSC_LIST = {
    "OXM": {"mcc": "262", "mnc": "01", "region": "EU",  "name": "Open Multi-CSC"},
    "DBT": {"mcc": "262", "mnc": "01", "region": "EU",  "name": "Germany"},
    "ILO": {"mcc": "425", "mnc": "01", "region": "ME",  "name": "Israel"},
    "KOO": {"mcc": "450", "mnc": "05", "region": "KR",  "name": "Korea"},
    "EUX": {"mcc": "208", "mnc": "01", "region": "EU",  "name": "Europe"},
    "XEF": {"mcc": "208", "mnc": "01", "region": "EU",  "name": "France"},
    "ITV": {"mcc": "222", "mnc": "01", "region": "EU",  "name": "Italy"},
    "BTU": {"mcc": "234", "mnc": "15", "region": "EU",  "name": "UK"},
    "XAA": {"mcc": "310", "mnc": "260", "region": "US", "name": "USA"},
    "INS": {"mcc": "404", "mnc": "05", "region": "IN",  "name": "India"},
    "TGY": {"mcc": "454", "mnc": "00", "region": "HK",  "name": "Hong Kong"},
    "BRI": {"mcc": "466", "mnc": "01", "region": "TW",  "name": "Taiwan"},
    "XSG": {"mcc": "424", "mnc": "02", "region": "ME",  "name": "UAE"},
    "SIN": {"mcc": "525", "mnc": "05", "region": "SG",  "name": "Singapore"},
}

FAST_COMBOS = [
    ("DBT", "262", "01"), ("ILO", "425", "01"), ("OXM", "262", "01"),
    ("EUX", "208", "01"), ("BTU", "234", "15"), ("XAA", "310", "260"),
]

DEVICES = {
    "S26 Ultra":     {"eu": "SM-S948B", "cn": "SM-S9480", "oneui": "8.5"},
    "S26+":          {"eu": "SM-S946B", "cn": "SM-S9460", "oneui": "8.5"},
    "S26":           {"eu": "SM-S941B", "cn": "SM-S9410", "oneui": "8.5"},
    "S25 Ultra":     {"eu": "SM-S938B", "cn": "SM-S9380", "oneui": "8.5"},
    "S25+":          {"eu": "SM-S936B", "cn": "SM-S9360", "oneui": "8.5"},
    "S25":           {"eu": "SM-S931B", "cn": "SM-S9310", "oneui": "8.5"},
    "S24 Ultra":     {"eu": "SM-S928B", "cn": "SM-S9280", "oneui": "8.5"},
    "S24+":          {"eu": "SM-S926B", "cn": "SM-S9260", "oneui": "8.5"},
    "S24":           {"eu": "SM-S921B", "cn": "SM-S9210", "oneui": "8.5"},
    "S24 FE":        {"eu": "SM-S721B", "cn": None,       "oneui": "8"},
    "S23 Ultra":     {"eu": "SM-S918B", "cn": "SM-S9180", "oneui": "8"},
    "S23+":          {"eu": "SM-S916B", "cn": "SM-S9160", "oneui": "8"},
    "S23":           {"eu": "SM-S911B", "cn": "SM-S9110", "oneui": "8"},
    "S23 FE":        {"eu": "SM-S711B", "cn": None,       "oneui": "7"},
    "S22 Ultra":     {"eu": "SM-S908B", "cn": "SM-S9080", "oneui": "7"},
    "S22+":          {"eu": "SM-S906B", "cn": "SM-S9060", "oneui": "7"},
    "S22":           {"eu": "SM-S901B", "cn": "SM-S9010", "oneui": "7"},
    "Z Fold 7":      {"eu": "SM-F968B", "cn": "SM-F9680", "oneui": "9"},
    "Z Flip 7":      {"eu": "SM-F751B", "cn": "SM-F7510", "oneui": "9"},
    "Z Fold 6":      {"eu": "SM-F956B", "cn": "SM-F9560", "oneui": "8.5"},
    "Z Flip 6":      {"eu": "SM-F741B", "cn": "SM-F7410", "oneui": "8.5"},
    "Z Fold 5":      {"eu": "SM-F946B", "cn": "SM-F9460", "oneui": "7"},
    "Z Flip 5":      {"eu": "SM-F731B", "cn": "SM-F7310", "oneui": "7"},
    "A56":           {"eu": "SM-A566B", "cn": None,       "oneui": "8.5"},
    "A36":           {"eu": "SM-A366B", "cn": None,       "oneui": "8.5"},
    "A26":           {"eu": "SM-A266B", "cn": None,       "oneui": "8.5"},
    "A55":           {"eu": "SM-A556B", "cn": None,       "oneui": "7"},
    "A54":           {"eu": "SM-A546B", "cn": None,       "oneui": "7"},
    "A35":           {"eu": "SM-A356B", "cn": None,       "oneui": "7"},
    "A15":           {"eu": "SM-A155F", "cn": None,       "oneui": "7"},
    "Tab S10 Ultra": {"eu": "SM-X926B", "cn": "SM-X9260", "oneui": "8.5"},
    "Tab S10+":      {"eu": "SM-X826B", "cn": "SM-X8260", "oneui": "8.5"},
    "Tab S10":       {"eu": "SM-X716B", "cn": "SM-X7160", "oneui": "8.5"},
    "Tab S9 Ultra":  {"eu": "SM-X916B", "cn": "SM-X9160", "oneui": "7"},
    "Tab S9+":       {"eu": "SM-X816B", "cn": "SM-X8160", "oneui": "7"},
    "Tab S9":        {"eu": "SM-X716B", "cn": "SM-X7160", "oneui": "7"},
    "XCover 7 Pro":  {"eu": "SM-G556W", "cn": None,       "oneui": "8"},
    "XCover 7":      {"eu": "SM-G556B", "cn": None,       "oneui": "7"},
}

_PKG = {
    "com.sec.android.app.launcher":                         ("One UI Home",                 "System"),
    "com.samsung.android.honeyboard":                       ("Samsung Keyboard",             "System"),
    "com.sec.android.inputmethod":                          ("Samsung Keyboard (Legacy)",    "System"),
    "com.samsung.android.emoji.font":                       ("Emoji Font",                  "System"),
    "com.samsung.android.dynamiclock":                      ("Dynamic Lockscreen",           "System"),
    "com.samsung.android.app.talkback":                     ("TalkBack",                    "System"),
    "com.samsung.android.livewallpaper":                    ("Live Wallpaper",               "System"),
    "com.samsung.android.stickercenter":                    ("Sticker Center",              "System"),
    "com.samsung.android.iceview":                          ("Edge Panels",                 "System"),
    "com.samsung.android.forest":                           ("Digital Wellbeing",            "System"),
    "com.samsung.android.fota":                             ("FOTA",                        "System"),
    "com.samsung.android.samsungpositioning":               ("Location Service",             "System"),
    "com.samsung.android.authfw":                           ("Auth Framework",              "System"),
    "com.samsung.android.server.iris":                      ("Iris Service",                "System"),
    "com.samsung.android.svoiceime":                        ("Voice Input",                 "System"),
    "com.sec.android.multiproject":                         ("Multi Project",                "System"),
    "com.samsung.android.allshare.service.mediashare":      ("Media Share Service",         "System"),
    "com.samsung.android.awingservice":                     ("AWIN Service",                 "System"),
    "com.samsung.android.da.daagent":                       ("Dual Messenger",              "System"),
    "com.samsung.android.beaconmanager":                    ("Bluetooth Beacon Manager",     "System"),
    "com.samsung.android.spage.service":                    ("Samsung Free Service",         "System"),
    "com.sec.android.soagent":                              ("Update Agent",                 "System"),
    "com.wssyncmldm":                                       ("Software Update",              "System"),
    "com.samsung.android.livedrawing":                      ("Live Drawing",                 "System"),
    "com.samsung.android.spen.core":                        ("S Pen Core",                  "System"),
    "com.samsung.android.pocketsense":                      ("Pocket Sense",                "System"),
    "com.samsung.android.knox.attestation":                 ("Knox Attestation",            "Security"),
    "com.samsung.android.knox.containeragent":              ("Knox Container Agent",        "Security"),
    "com.samsung.android.knox.analytics.uploader":          ("Knox Analytics Uploader",     "Security"),
    "com.samsung.android.KnoxAids":                         ("Knox Aids",                  "Security"),
    "com.samsung.android.sm.devicesecurity":                ("Device Security",             "Security"),
    "com.samsung.android.lool":                             ("Device Care",                 "Security"),
    "com.samsung.android.samsungpass":                      ("Samsung Pass",                "Security"),
    "com.samsung.android.fmm":                              ("Find My Mobile",              "Security"),
    "com.samsung.android.knox.enrollment":                  ("Knox Enrollment",             "Security"),
    "com.samsung.android.securitylogagent":                 ("Security Log Agent",          "Security"),
    "com.samsung.android.app.notes":                        ("Samsung Notes",               "Productivity"),
    "com.samsung.android.app.clock":                        ("Samsung Clock",               "Productivity"),
    "com.samsung.android.calendar":                         ("Samsung Calendar",            "Productivity"),
    "com.samsung.android.app.reminder":                     ("Reminder",                   "Productivity"),
    "com.sec.android.app.popupcalculator":                  ("Calculator",                  "Productivity"),
    "com.sec.android.app.voicenote":                        ("Voice Recorder",              "Productivity"),
    "com.sec.android.app.myfiles":                          ("My Files",                   "Productivity"),
    "com.samsung.android.app.sharelive":                    ("Quick Share",                 "Productivity"),
    "com.samsung.android.mcfserver":                        ("Multi Control / Flow",        "Productivity"),
    "com.samsung.android.samsungflow":                      ("Samsung Flow",                "Productivity"),
    "com.samsung.android.privateshare":                     ("Private Share",               "Productivity"),
    "com.samsung.android.linksharingapp":                   ("Link Sharing",                "Productivity"),
    "com.samsung.android.scloud":                           ("Samsung Cloud",               "Productivity"),
    "com.samsung.android.smartswitchassistant":             ("Smart Switch",                "Productivity"),
    "com.samsung.android.dex.desktop":                      ("Samsung DeX",                 "DeX"),
    "com.samsung.desktopsystemui":                          ("DeX System UI",               "DeX"),
    "com.samsung.android.app.dex.desktop.focus":            ("DeX Focus Mode",              "DeX"),
    "com.samsung.android.mdx.kit":                          ("DeX Kit",                     "DeX"),
    "com.samsung.android.incallui":                         ("Phone / In-Call UI",          "Communication"),
    "com.samsung.android.dialer":                           ("Samsung Dialer",              "Communication"),
    "com.samsung.android.messaging":                        ("Samsung Messages",            "Communication"),
    "com.samsung.android.contacts":                         ("Samsung Contacts",            "Communication"),
    "com.samsung.android.email.provider":                   ("Samsung Email",               "Communication"),
    "com.sec.android.app.sbrowser":                         ("Samsung Internet",            "Browser"),
    "com.sec.android.app.sbrowser.beta":                    ("Samsung Internet (Beta)",     "Browser"),
    "com.sec.android.app.camera":                           ("Samsung Camera",              "Camera & AR"),
    "com.samsung.android.app.dressroom":                    ("Photo Editor",                "Camera & AR"),
    "com.sec.android.gallery3d":                            ("Samsung Gallery",             "Camera & AR"),
    "com.samsung.android.ardrawing":                        ("AR Drawing",                  "Camera & AR"),
    "com.samsung.android.aremoji":                          ("AR Emoji",                    "Camera & AR"),
    "com.samsung.android.arzone":                           ("AR Zone",                     "Camera & AR"),
    "com.samsung.android.app.camera.sticker.facear.preload":("Face AR Preload",             "Camera & AR"),
    "com.samsung.android.visionintelligence":               ("Vision Intelligence",         "Camera & AR"),
    "com.samsung.android.app.capture":                      ("Smart Capture",              "Camera & AR"),
    "com.sec.android.app.music":                            ("Samsung Music",               "Media"),
    "com.samsung.android.video":                            ("Samsung Video Player",        "Media"),
    "com.samsung.android.tvplus":                           ("Samsung TV Plus",             "Media"),
    "com.sec.android.app.fm":                               ("FM Radio",                   "Media"),
    "com.samsung.android.storyalbum":                       ("Story Album",                 "Media"),
    "com.samsung.android.photostudio":                      ("Photo Studio",                "Media"),
    "com.samsung.android.bixby.agent":                      ("Bixby",                      "AI & Bixby"),
    "com.samsung.android.bixby.service":                    ("Bixby Service",              "AI & Bixby"),
    "com.samsung.android.app.settings.bixby":               ("Bixby Settings",             "AI & Bixby"),
    "com.samsung.android.app.routines":                     ("Bixby Routines",             "AI & Bixby"),
    "com.samsung.android.bixby.wakeup":                     ("Bixby Wakeup",              "AI & Bixby"),
    "com.samsung.android.bixbyvision.framework":            ("Bixby Vision Framework",     "AI & Bixby"),
    "com.samsung.android.aicoreservice":                    ("AI Core Service",            "AI & Bixby"),
    "com.samsung.android.app.galaxyai":                     ("Galaxy AI",                  "AI & Bixby"),
    "com.samsung.android.intelligenceservice":               ("Intelligence Service",       "AI & Bixby"),
    "com.samsung.android.app.bixbytextcall":                ("Bixby Text Call",            "AI & Bixby"),
    "com.samsung.android.goodlock":                         ("Good Lock",                  "Good Lock"),
    "com.samsung.android.app.nixhead":                      ("NiceLock (Lockscreen)",      "Good Lock"),
    "com.samsung.android.onehand":                          ("One Hand Operation+",       "Good Lock"),
    "com.samsung.android.multistar":                        ("MultiStar (Multi-Window)",   "Good Lock"),
    "com.samsung.android.quickstar":                        ("QuickStar (Quick Panel)",    "Good Lock"),
    "com.samsung.android.app.soundassistant":               ("Sound Assistant",            "Good Lock"),
    "com.samsung.android.app.navicoach":                    ("NavStar",                    "Good Lock"),
    "com.samsung.android.app.clockface":                    ("ClockFace",                 "Good Lock"),
    "com.samsung.android.app.homeup":                       ("HomeUp (Launcher)",          "Good Lock"),
    "com.samsung.android.app.galaxylab":                    ("Galaxy Labs",                "Good Lock"),
    "com.samsung.android.app.registar":                     ("RegiStar",                  "Good Lock"),
    "com.samsung.android.app.lockstar":                     ("LockStar",                  "Good Lock"),
    "com.sec.android.app.samsungapps":                      ("Galaxy Store",               "Store"),
    "com.samsung.android.themestore":                       ("Galaxy Themes",              "Store"),
    "com.samsung.android.app.spage":                        ("Samsung Free",               "Store"),
    "com.samsung.android.mobileservice":                    ("Samsung Members",            "Store"),
    "com.samsung.android.voc":                              ("Samsung Members (Legacy)",   "Store"),
    "com.samsung.android.app.tips":                         ("Samsung Tips",               "Store"),
    "com.samsung.android.samsunglabs":                      ("Samsung Labs",              "Store"),
    "com.samsung.android.shealth":                          ("Samsung Health",             "Health"),
    "com.sec.android.app.shealth":                          ("Samsung Health (alt pkg)",   "Health"),
    "com.samsung.android.app.watchmanager":                 ("Galaxy Wearable",            "Health"),
    "com.samsung.android.kidsinstaller":                    ("Samsung Kids Installer",     "Health"),
    "com.samsung.android.shealthmonitor":                   ("Samsung Health Monitor",     "Health"),
    "com.samsung.android.waterplugin":                      ("Galaxy Watch 4 Plugin",      "Wearables"),
    "com.samsung.android.heartplugin":                      ("Galaxy Watch 5 Plugin",      "Wearables"),
    "com.samsung.wearable.watch6plugin":                    ("Galaxy Watch 6 Plugin",      "Wearables"),
    "com.samsung.android.ringplugin":                       ("Galaxy Ring Plugin",         "Wearables"),
    "com.samsung.accessory.neobeanmgr":                     ("Galaxy Buds Live Plugin",    "Wearables"),
    "com.samsung.accessory.berrymgr":                       ("Galaxy Buds 2 Plugin",      "Wearables"),
    "com.samsung.accessory.zenithmgr":                      ("Galaxy Buds 2 Pro Plugin",  "Wearables"),
    "com.samsung.accessory.pearlmgr":                       ("Galaxy Buds FE Plugin",     "Wearables"),
    "com.samsung.android.modenplugin":                      ("Galaxy Fit Plugin",         "Wearables"),
    "com.samsung.android.neatplugin":                       ("Galaxy Fit 2 Plugin",       "Wearables"),
    "com.samsung.android.fit3plugin":                       ("Galaxy Fit 3 Plugin",       "Wearables"),
    "com.samsung.android.oneconnect":                       ("SmartThings",                "IoT"),
    "com.samsung.android.smartthings":                      ("SmartThings Hub",            "IoT"),
    "com.samsung.android.game.gamehome":                    ("Game Launcher",              "Games"),
    "com.samsung.android.game.gametools":                   ("Game Tools",                 "Games"),
    "com.samsung.android.game.gos":                         ("Game Optimizing Service",    "Games"),
    "com.samsung.android.spay":                             ("Samsung Pay",                "Payments"),
    "com.samsung.android.samsungpay.wallet":                ("Samsung Wallet",             "Payments"),
    "com.sec.android.widgetapp.weatherwidget":              ("Weather Widget",             "Widgets"),
    "com.samsung.android.weather":                          ("Weather",                    "Widgets"),
    "com.samsung.accessibility":                            ("Accessibility Suite",        "Accessibility"),
    "com.samsung.android.app.singleactionswitch":           ("Single Action Switch",       "Accessibility"),
    "com.samsung.android.soundpicker":                      ("Sound Picker",              "Accessibility"),
}

SAMSUNG_PACKAGES = {k: v[0] for k, v in _PKG.items()}
PACKAGE_CATEGORY = {k: v[1] for k, v in _PKG.items()}
CATEGORIES = sorted(set(PACKAGE_CATEGORY.values()))

CAT_EMOJI = {
    "System": "\U0001f539", "Security": "\U0001f6e1\ufe0f",
    "Productivity": "\U0001f4cb", "DeX": "\U0001f4bb",
    "Communication": "\U0001f4de", "Browser": "\U0001f310",
    "Camera & AR": "\U0001f4f7", "Media": "\U0001f3b5",
    "AI & Bixby": "\U0001f916", "Good Lock": "\U0001f512",
    "Store": "\U0001f4e6", "Health": "\u2764\ufe0f",
    "Wearables": "\u231a", "IoT": "\U0001f3e0",
    "Games": "\U0001f3ae", "Payments": "\U0001f4b3",
    "Widgets": "\U0001f9f0", "Accessibility": "\u267f",
}

# ═══════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════

def fmt_size(n: int) -> str:
    if n >= 1_048_576: return f"{n / 1_048_576:.1f} MB"
    return f"{n / 1024:.0f} KB"

def fmt_speed(bps: float) -> str:
    if bps >= 1_048_576: return f"{bps / 1_048_576:.1f} MB/s"
    elif bps >= 1_024: return f"{bps / 1_024:.0f} KB/s"
    return f"{bps:.0f} B/s"

def fmt_time(secs: float) -> str:
    if secs < 60: return f"{secs:.1f}s"
    return f"{secs/60:.0f}m {secs%60:.0f}s"

def build_device_list(region: str = "all") -> list:
    out = []
    for name, info in DEVICES.items():
        if region in ("all", "EU") and info.get("eu"):
            out.append((f"{name} EU", info["eu"]))
        if region in ("all", "CN") and info.get("cn"):
            out.append((f"{name} CN", info["cn"]))
    return out

def build_csc_list(region: str = "all") -> list:
    priority = ["OXM", "DBT", "ILO", "KOO"]
    out = [(c, CSC_LIST[c]) for c in priority if c in CSC_LIST]
    for csc, info in CSC_LIST.items():
        if csc in priority: continue
        if region == "all" or info["region"] == region:
            out.append((csc, info))
    return out

def resolve_sdks(oneui_arg, _unused=None, _unused2=None) -> list:
    if oneui_arg:
        sdk = ONEUI_SDK.get(str(oneui_arg).strip())
        return [sdk or 36]
    return [36]

def device_supports_sdk(device_name: str, sdk: int) -> bool:
    for name, info in DEVICES.items():
        if info.get("eu") and info["eu"] in device_name:
            mapped = ONEUI_SDK.get(info.get("oneui", ""))
            return mapped is not None and sdk <= mapped
        if info.get("cn") and info["cn"] in device_name:
            mapped = ONEUI_SDK.get(info.get("oneui", ""))
            return mapped is not None and sdk <= mapped
    return True


# ═══════════════════════════════════════════════════════
#  GALAXY STORE CLIENT
#  Méthodes TESTÉES une par une contre l'API réelle
# ═══════════════════════════════════════════════════════

class GalaxyStoreClient:
    def __init__(self, debug: bool = False, rate_limit: int = 8):
        self.debug = debug
        self._sem = Semaphore(rate_limit)
        self.session = self._make_session()

    @staticmethod
    def _make_session() -> requests.Session:
        s = requests.Session()
        retry = Retry(total=4, backoff_factor=0.6,
            status_forcelist={429, 500, 502, 503, 504},
            allowed_methods={"GET"}, raise_on_status=False)
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.mount("http://", HTTPAdapter(max_retries=retry))
        s.headers.update({
            "User-Agent": "SamsungApps/4.5.97.1",
            "Accept": "application/xml, text/xml, */*",
        })
        return s

    @staticmethod
    def _parse_xml(xml_text: str) -> dict:
        result = {}
        try:
            for elem in ET.fromstring(xml_text).iter():
                if elem.text and elem.text.strip():
                    result[elem.tag] = elem.text.strip()
        except ET.ParseError:
            pass
        if "downloadURI" not in result:
            m = re.search(r"CDATA\[(https?://[^\]]+)\]", xml_text)
            if m:
                result["downloadURI"] = m.group(1)
        return result

    # ─── 1. stubDownload (GET) ✅ TESTÉ ───

    def query(self, package: str, model: str, sdk: int,
              csc: str = "DBT", mcc: str = "262", mnc: str = "01",
              endpoint: str = "stubDownload") -> dict:
        params = {
            "appId": package, "deviceId": model,
            "mcc": mcc, "mnc": mnc, "csc": csc,
            "sdkVer": str(sdk), "abiType": "64",
            "extuk": secrets.token_hex(8),
        }
        url = ENDPOINTS.get(endpoint, endpoint)
        with self._sem:
            try:
                resp = self.session.get(url, params=params, timeout=20)
                resp.raise_for_status()
            except requests.RequestException:
                return {}
        return self._parse_xml(resp.text)

    # ─── 2. overseasStubDownload (GET) ✅ TESTÉ ───

    def query_overseas(self, package: str, model: str, sdk: int,
                        csc: str = "DBT", mcc: str = "262",
                        mnc: str = "01") -> dict:
        return self.query(package, model, sdk, csc, mcc, mnc,
                          endpoint="overseasStubDownload")

    # ─── 3. contentCategoryList (GET) ✅ TESTÉ ───

    def browse_content_category(self, category_id: str = "0000005309",
                                 model: str = "SM-S948B",
                                 sdk: int = 37,
                                 page_size: int = 20,
                                 page: int = 1) -> dict:
        params = {
            "contentCategoryID": category_id,
            "deviceId": model, "sdkVer": str(sdk),
            "mcc": "262", "mnc": "01", "csc": "DBT",
            "abiType": "64", "extuk": secrets.token_hex(8),
            "pageSize": str(page_size), "pageNo": str(page),
        }
        return self._get_xml(ENDPOINTS["contentCategoryList"], params)

    def _get_xml(self, url: str, params: dict = None, timeout: int = 20) -> dict:
        with self._sem:
            try:
                resp = self.session.get(url, params=params, timeout=timeout)
                resp.raise_for_status()
            except requests.RequestException:
                return {}
        return self._parse_xml(resp.text)

    def list_content_categories(self) -> dict:
        return dict(CONTENT_CATEGORIES)

    @staticmethod
    def get_servers() -> dict:
        return {"cdn_servers": dict(CDN_SERVERS)}

    @staticmethod
    def get_endpoints() -> dict:
        return dict(ENDPOINTS)

    @staticmethod
    def resolve_download_domain(download_url: str) -> str:
        for name, server in CDN_SERVERS.items():
            if server.split("://")[1] in download_url:
                return name
        return "unknown"

    # ═══════════════════════════════════════════════════════
    #  MÉTHODES ORIGINALES (inchangées, déjà testées)
    # ═══════════════════════════════════════════════════════

    def find_latest(self, package: str, devices: list, csclist: list,
                    sdks: list, workers: int = 8, progress=None, task_id=None):
        best = {}
        best_code = -1
        lock = Lock()

        combos = [
            (label, model, csc_code, csc_info, sdk)
            for sdk in sdks
            for label, model in devices
            for csc_code, csc_info in csclist
            if device_supports_sdk(model, sdk)
        ]

        def check(combo):
            nonlocal best, best_code
            label, model, csc_code, csc_info, sdk = combo
            primary = (csc_info["mcc"], csc_info["mnc"])
            fallback = ("425", "01")
            pairs = [primary]
            if primary != fallback:
                pairs.append(fallback)

            for mcc, mnc in pairs:
                info = self.query(package, model, sdk, csc_code, mcc, mnc)
                if info.get("resultCode") == "1" and info.get("downloadURI"):
                    try:
                        vcode = int(info.get("versionCode", "0"))
                    except ValueError:
                        continue
                    with lock:
                        if vcode > best_code:
                            best_code = vcode
                            best.update({
                                "package": package,
                                "name": SAMSUNG_PACKAGES.get(package, package),
                                "versionCode": str(vcode),
                                "versionName": info.get("versionName", ""),
                                "downloadURI": info.get("downloadURI", ""),
                                "contentSize": info.get("contentSize", "0"),
                                "device": model, "csc": csc_code,
                                "mcc": mcc, "mnc": mnc, "sdk": sdk,
                            })
                    return

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(check, c): c for c in combos}
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception:
                    pass
        return best if best else None

    def quick_find(self, package: str, sdks: list) -> dict | None:
        best = {}
        best_code = -1
        lock = Lock()

        quick_devices = [
            ("S26 Ultra EU", "SM-S948B"), ("S25 EU", "SM-S931B"),
            ("S24 EU", "SM-S921B"), ("S23 EU", "SM-S911B"),
            ("Z Fold 6 EU", "SM-F956B"), ("A56 EU", "SM-A566B"),
        ]

        combos = [
            (model, csc, mcc, mnc, sdk)
            for sdk in sdks
            for _, model in quick_devices
            for csc, mcc, mnc in FAST_COMBOS
        ]

        def check(combo):
            nonlocal best, best_code
            model, csc, mcc, mnc, sdk = combo
            info = self.query(package, model, sdk, csc, mcc, mnc)
            if info.get("resultCode") == "1" and info.get("downloadURI"):
                try:
                    vcode = int(info.get("versionCode", "0"))
                except ValueError:
                    return
                with lock:
                    if vcode > best_code:
                        best_code = vcode
                        best.update({
                            "package": package,
                            "name": SAMSUNG_PACKAGES.get(package, package),
                            "versionCode": str(vcode),
                            "versionName": info.get("versionName", ""),
                            "downloadURI": info.get("downloadURI", ""),
                            "contentSize": info.get("contentSize", "0"),
                            "device": model, "csc": csc,
                            "mcc": mcc, "mnc": mnc, "sdk": sdk,
                        })

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(check, combos))
        return best if best else None

    def download(self, url: str, dest, progress_cb=None) -> dict:
        dest = Path(dest)
        existing = dest.stat().st_size if dest.exists() else 0
        headers = {"Range": f"bytes={existing}-"} if existing else {}

        resp = self.session.get(url, stream=True, timeout=120, headers=headers)
        if resp.status_code == 416:
            return {"size": existing, "elapsed": 0.0, "speed": 0.0, "resumed": True}
        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0)) + existing
        done = existing
        t0 = __import__("time").monotonic()
        with open(dest, "ab" if existing else "wb") as fh:
            for chunk in resp.iter_content(512 * 1024):
                if chunk:
                    fh.write(chunk)
                    done += len(chunk)
                    if progress_cb:
                        progress_cb(done, total)
        elapsed = __import__("time").monotonic() - t0
        speed = done / elapsed if elapsed > 0 else 0
        return {"size": done, "elapsed": elapsed, "speed": speed, "resumed": bool(existing)}
