# SECURITY: hardcoded SearchAd credentials were removed during project organization.
# -*- coding: utf-8 -*-
"""
카페마케팅 자동화 GUI v2.0
- 구글 시트 연동 (URL 입력 방식)
- 네이버 검색광고 API 검색량
- 조회수 히스토리 열 관리
- 24시간 반복 스케줄
"""
import sys, io, os, re, json, time, hmac, hashlib, base64, tempfile
import threading, queue
from datetime import datetime, timedelta
from urllib.parse import quote, urlparse

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox

import requests
import gspread
from google.oauth2.service_account import Credentials

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except AttributeError:
    pass  # pythonw.exe 실행 시 콘솔 없음 - 무시

# ══════════════════════════════════════════════════════════════
# 설정 파일 관리
# ══════════════════════════════════════════════════════════════
# EXE로 실행 시 sys.executable(EXE 위치) 기준, 스크립트 실행 시 __file__ 기준
if getattr(sys, "frozen", False):
    _SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(_SCRIPT_DIR, "config.json")

def _auto_detect_key() -> str:
    """스크립트와 같은 폴더에서 JSON 키 파일 자동 탐지"""
    for f in os.listdir(_SCRIPT_DIR):
        if f.endswith(".json") and f != "config.json":
            full = os.path.join(_SCRIPT_DIR, f)
            try:
                with open(full, encoding="utf-8") as fp:
                    d = json.load(fp)
                if d.get("type") == "service_account":
                    return full
            except Exception:
                pass
    return ""

DEFAULT_CFG = {
    "key_path":        _auto_detect_key(),
    "sheet_url":       "",
    "sheet_names":     "시트1",       # 줄바꿈으로 여러 시트 구분
    "naver_customer":  "",
    "naver_api_key":   "",
    "naver_secret":    "",
    "repeat_enabled":  False,
    "repeat_time":     "09:00",
}

def _validate_key_path(path: str) -> str:
    """key_path가 유효한 서비스 계정 파일인지 검증, 아니면 자동탐지"""
    if not path or not os.path.exists(path):
        return _auto_detect_key()
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("type") == "service_account" and "client_email" in d:
            return path
    except Exception:
        pass
    return _auto_detect_key()

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                d = json.load(f)
            cfg = {**DEFAULT_CFG, **d}
            # 이전 버전 sheet_name → sheet_names 마이그레이션
            if "sheet_name" in d and "sheet_names" not in d:
                cfg["sheet_names"] = d["sheet_name"]
            # key_path 자동 검증
            cfg["key_path"] = _validate_key_path(cfg.get("key_path", ""))
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CFG)

def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════
# 유틸
# ══════════════════════════════════════════════════════════════
def extract_sheet_id(url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else ""

def get_service_email(key_path: str) -> str:
    try:
        with open(key_path, encoding="utf-8") as f:
            return json.load(f).get("client_email", "")
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════
# 구글 시트
# ══════════════════════════════════════════════════════════════
GSCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def open_sheet(key_path: str, sheet_url: str, sheet_name: str):
    sheet_id = extract_sheet_id(sheet_url)
    if not sheet_id:
        raise ValueError("유효하지 않은 구글 시트 URL입니다.")
    creds = Credentials.from_service_account_file(key_path, scopes=GSCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(sheet_id)
    ws    = sh.worksheet(sheet_name)
    return sh, ws


def get_data_rows(ws) -> list:
    rows = ws.get_all_values()
    result = []
    for i, row in enumerate(rows[1:], start=2):
        while len(row) < 11:
            row.append("")
        keyword = row[1].strip()
        link    = row[2].strip()
        if keyword:
            result.append({
                "row_idx": i,
                "B": keyword,
                "C": link,
            })
    return result


def prepare_history_columns(ws, sh, now: datetime) -> tuple:
    """
    J열(노출여부)과 K열(조회수) 히스토리 열 관리:
    - 첫 실행(K1이 '조회수' 또는 비어있음): J1·K1 헤더만 변경, 열 삽입 없음
    - 재실행: J(index=9), K(index=10) 위치에 새 열 2개 삽입 후 헤더 설정
      (기존 J,K 데이터는 L,M으로 밀려 히스토리 보존)
    Returns: (j_col, k_col) 열 번호 (1-indexed)
    """
    j_hdr = f"노출({now.strftime('%m%d %H:%M')})"   # 예: 노출(0512 12:00)
    k_hdr = f"조회({now.strftime('%m%d')})"           # 예: 조회(0512)
    current_k = ws.cell(1, 11).value or ""
    if current_k in ("조회수", ""):
        # 첫 실행: 헤더만 변경
        ws.update_cell(1, 10, j_hdr)  # J1
        ws.update_cell(1, 11, k_hdr)  # K1
    else:
        # 재실행: J·K 위치에 새 열 2개 삽입
        sh.batch_update({"requests": [
            {"insertDimension": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                          "startIndex": 9, "endIndex": 10},
                "inheritFromBefore": False,
            }},
            {"insertDimension": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                          "startIndex": 10, "endIndex": 11},
                "inheritFromBefore": False,
            }},
        ]})
        ws.update_cell(1, 10, j_hdr)  # 새 J1
        ws.update_cell(1, 11, k_hdr)  # 새 K1
    return 10, 11  # j_col, k_col


def write_row(ws, row_idx: int, vals: dict, k_col: int):
    """
    vals 키: d, e, f, g, h, i, j, k  (없는 키는 업데이트 안 함)
    k_col: 조회수 열 번호(1-indexed)
    """
    # D~J 일괄 (D=4 ~ J=10)
    cells_dj = [
        vals.get("d", ""),
        vals.get("e", ""),
        vals.get("f", ""),
        vals.get("g", ""),
        vals.get("h", ""),
        vals.get("i", ""),
        vals.get("j", ""),
    ]
    ws.update(
        values=[[ str(v) for v in cells_dj ]],
        range_name=f"D{row_idx}:J{row_idx}",
    )
    if "k" in vals:
        ws.update_cell(row_idx, k_col, str(vals["k"]))


# ══════════════════════════════════════════════════════════════
# 셀레니움 드라이버
# ══════════════════════════════════════════════════════════════
def build_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--no-first-run")
    opts.add_argument("--lang=ko-KR")
    opts.add_argument("--disable-crash-reporter")
    # 매 실행마다 고유한 임시 프로필 디렉토리 사용 → 좀비 프로세스 프로필 충돌 방지
    _tmp_profile = tempfile.mkdtemp(prefix="cafe_chrome_")
    opts.add_argument(f"--user-data-dir={_tmp_profile}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("prefs",
        {"profile.managed_default_content_settings.images": 2})
    opts.page_load_strategy = "eager"
    driver = webdriver.Chrome(options=opts)  # Selenium Manager가 자동으로 ChromeDriver 버전 매칭
    driver.set_page_load_timeout(30)   # 페이지 로드 30초 제한
    driver.set_script_timeout(20)      # JS 실행 20초 제한
    return driver


# ══════════════════════════════════════════════════════════════
# E열: 네이버 키워드 API
# ══════════════════════════════════════════════════════════════
def _api_sig(secret: str, ts: str, method: str, path: str) -> str:
    msg = f"{ts}.{method}.{path}".encode("utf-8")
    return base64.b64encode(
        hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    ).decode("utf-8")

def _parse_cnt(val) -> int:
    s = str(val).strip().lstrip("<").strip()
    try:
        return max(int(s) - 1, 0)
    except ValueError:
        return 0

def get_search_volume(keyword: str, customer: str, api_key: str, secret: str) -> int:
    path = "/keywordstool"
    ts   = str(int(time.time() * 1000))
    headers = {
        "X-Timestamp":  ts,
        "X-API-KEY":    api_key,
        "X-Customer":   customer,
        "X-Signature":  _api_sig(secret, ts, "GET", path),
        "Content-Type": "application/json; charset=UTF-8",
    }
    resp = requests.get(
        "https://api.searchad.naver.com" + path,
        headers=headers,
        params={"hintKeywords": keyword, "showDetail": "1"},
        timeout=10,
    )
    if not resp.ok:
        return 0
    kws    = resp.json().get("keywordList", [])
    exact  = [k for k in kws if k.get("relKeyword", "").strip() == keyword.strip()]
    target = exact[0] if exact else (kws[0] if kws else None)
    if not target:
        return 0
    return _parse_cnt(target.get("monthlyPcQcCnt", 0)) + \
           _parse_cnt(target.get("monthlyMobileQcCnt", 0))


# ══════════════════════════════════════════════════════════════
# J열: 노출 여부
# ══════════════════════════════════════════════════════════════
def _cafe_id(url: str):
    m = re.search(r"cafe\.naver\.com/([^/?#]+)/(\d+)", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None

def check_exposure(driver, keyword: str, target_url: str) -> str:
    driver.get(f"https://search.naver.com/search.naver?query={quote(keyword)}")
    try:
        WebDriverWait(driver, 8).until(
            lambda d: len(d.find_elements(By.TAG_NAME, "a")) > 10)
        time.sleep(0.5)
    except Exception:
        time.sleep(2)

    tid = _cafe_id(target_url)
    hrefs = driver.execute_script("""
        var h=[];
        document.querySelectorAll('a[href]').forEach(function(a){
            var u=a.href||'';
            if(u.startsWith('http')) h.push(u);
        });
        return h;
    """) or []

    for link in hrefs:
        if (tid and tid in link) or target_url.rstrip("/") in link:
            return "1"
    return "0"


# ══════════════════════════════════════════════════════════════
# D,K열: 카페 게시글 제목 + 조회수
# ══════════════════════════════════════════════════════════════
def get_cafe_post_info(driver, url: str) -> dict:
    driver.get(url)
    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1.5)
    except Exception:
        time.sleep(2)

    title, views = "", 0
    try:
        WebDriverWait(driver, 8).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "cafe_main")))
        WebDriverWait(driver, 6).until(
            lambda d: d.find_elements(By.CSS_SELECTOR,
                "h3, .ArticleTitle, .title_subject, [class*='title']"))
        time.sleep(0.3)

        src = driver.page_source
        for sel in [".ArticleTitle .title_text", "h3.title", ".title_subject",
                    "[class*='tit_h3']", "[class*='article'] h3", "h3"]:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                t = el.text.strip()
                if t and len(t) > 2:
                    title = t; break
            if title: break

        for pat in [r"조회\s+([0-9,]+)", r"읽음\s+([0-9,]+)", r'"readCount"\s*:\s*(\d+)']:
            m = re.search(pat, src)
            if m:
                ns = m.group(1).replace(",", "")
                if ns.isdigit():
                    views = int(ns); break

        driver.switch_to.default_content()
    except Exception:
        try: driver.switch_to.default_content()
        except Exception: pass

    if not title:
        raw = driver.title or ""
        if " : 네이버 카페" in raw:
            title = raw.replace(" : 네이버 카페", "").strip()

    return {"title": title or "(제목 미확인)", "views": views}


# ══════════════════════════════════════════════════════════════
# G,H,I열: A/B 타입 판별
# ══════════════════════════════════════════════════════════════
_STD_SET = {
    "AI 브리핑","뉴스","이미지","동영상","블로그","카페","지식iN","어학사전",
    "지식백과","학술정보","지도","웹사이트","스포츠","전체","클립","인플루언서",
    "VIEW","숏텐츠","쇼핑","연관 검색어","네이버 가격비교","네이버플러스 스토어",
    "네이버 클립","플레이스","새로 오픈했어요",
}
_STD_PAT = [
    re.compile(r".+관련\s*광고"), re.compile(r"^함께\s*보는.+숏텐츠"),
    re.compile(r"^플레이스"),     re.compile(r".+관련\s*브랜드\s*콘텐츠"),
    re.compile(r"^브랜드\s*검색$"), re.compile(r".+FAQ$"),
]
def _norm(t): return re.sub(r"\s+", " ", t).strip()
def _is_std(t):
    n = _norm(t)
    return n in _STD_SET or any(p.search(n) for p in _STD_PAT)

def check_naver_type(driver, keyword: str) -> dict:
    driver.get(f"https://search.naver.com/search.naver?query={quote(keyword)}")
    try:
        WebDriverWait(driver, 6).until(
            lambda d: len(d.find_elements(By.TAG_NAME, "h2")) >= 2)
        time.sleep(0.3)
    except Exception:
        time.sleep(1.5)

    try:
        all_h2 = driver.execute_script("""
            var r=[];
            document.querySelectorAll('h2').forEach(function(el){
                var t=el.innerText.replace(/\\s+/g,' ').trim();
                if(t) r.push(t);
            });
            return r;
        """) or []
        seen, clean = set(), []
        for t in all_h2:
            t = _norm(t)
            if t and t not in seen: seen.add(t); clean.append(t)
    except Exception:
        clean = []

    a_boxes = [h for h in clean if _norm(h) and not _is_std(h)]
    normals  = [h for h in clean if _norm(h) in _STD_SET]
    return {"type": "A" if a_boxes else "B", "a_boxes": a_boxes, "normals": normals}


# ══════════════════════════════════════════════════════════════
# F열: 노출구좌
# ══════════════════════════════════════════════════════════════
_EXCL = re.compile(
    r"naver\.com/(search|ad|adcr|adsManager|npost|login|join|help|policy|"
    r"notice|trend|datalab|shopping/gate|main|index|mail|band|news/read|"
    r"series|map|view/v)|accounts\.naver|nid\.naver|static\.naver|"
    r"shopping\.naver|tv\.naver|dict\.naver|jdict\.naver|terms\.naver|"
    r"developers\.naver|mybox\.naver|pay\.naver", re.IGNORECASE)

def _classify(url: str):
    u = url.lower()
    if _EXCL.search(u) or "javascript:" in u or u.startswith("#"): return None
    if "cafe.naver.com" in u:
        return "cafe" if re.search(r"cafe\.naver\.com/[^/]+/\d+", u) else None
    if "blog.naver.com" in u:
        return "blog" if re.search(r"blog\.naver\.com/[^/?#]+/\d+", u) else None
    if "post.naver.com" in u:
        return "blog" if re.search(r"post\.naver\.com/[^/?#]+/\d+", u) else None
    if "kin.naver.com" in u:
        return "kin"  if re.search(r"kin\.naver\.com/(qna/detail|knowledge)", u) else None
    if "naver.com" not in u and u.startswith("http"):
        return "other"
    return None

def count_result_types(driver, keyword: str) -> str:
    driver.get(f"https://search.naver.com/search.naver?query={quote(keyword)}")
    try:
        WebDriverWait(driver, 8).until(
            lambda d: len(d.find_elements(By.TAG_NAME, "a")) > 10)
        time.sleep(0.8)
    except Exception:
        time.sleep(2)

    hrefs = driver.execute_script("""
        var h=[];
        document.querySelectorAll('a[href]').forEach(function(a){
            var u=a.href||'';
            if(u.startsWith('http')) h.push(u);
        });
        return h;
    """) or []

    counts, seen = {"cafe":0,"blog":0,"kin":0,"other":0}, set()
    for href in hrefs:
        try:
            p = urlparse(href)
            base = f"{p.scheme}://{p.netloc}{p.path}".rstrip("/")
        except Exception:
            base = href
        if base in seen: continue
        cat = _classify(href)
        if cat: seen.add(base); counts[cat] += 1

    parts = []
    if counts["cafe"]:  parts.append(f"카{counts['cafe']}")
    if counts["blog"]:  parts.append(f"블{counts['blog']}")
    if counts["kin"]:   parts.append(f"지{counts['kin']}")
    if counts["other"]: parts.append(f"기{counts['other']}")
    return "".join(parts) or "기0"


# ══════════════════════════════════════════════════════════════
# 워커: 한 행 처리
# ══════════════════════════════════════════════════════════════
def process_one_row(driver, ws, row: dict, k_col: int, cfg: dict, q: queue.Queue, stop_ev):
    kw       = row["B"]
    link     = row["C"]
    ri       = row["row_idx"]
    has_link = bool(link)
    row_data = row.get("data", [])

    def _cell(idx):
        """row_data에서 특정 인덱스 셀 값 반환 (없으면 빈 문자열)"""
        return row_data[idx].strip() if len(row_data) > idx else ""

    def log(msg, tag=None):
        q.put(("log", msg, tag))

    log(f"\n  키워드: 【{kw}】" + (f"  |  링크: {link[:50]}..." if len(link)>50 else f"  |  링크: {link}" if link else "  (링크 없음)"), "INFO")

    vals = {}

    # ── J열: 노출현황 (항상 실행) ─────────────────────────────
    if has_link and not stop_ev.is_set():
        try:
            j = check_exposure(driver, kw, link)
            vals["j"] = j
            log(f"    J 노출현황 : {j}", "A" if j=="1" else "B")
        except Exception as e:
            vals["j"] = "오류"
            log(f"    J 오류: {str(e)[:60]}", "ERR")
        time.sleep(2)

    # ── D,K열: 게시글 제목 + 조회수 (항상 실행) ──────────────
    if has_link and not stop_ev.is_set():
        try:
            info = get_cafe_post_info(driver, link)
            vals["d"] = info["title"]
            vals["k"] = info["views"]
            log(f"    D 제목    : {info['title']}", None)
            log(f"    K 조회수  : {info['views']:,}", None)
        except Exception as e:
            vals["d"] = "오류"
            vals["k"] = 0
            log(f"    D,K 오류: {str(e)[:60]}", "ERR")
        time.sleep(1.5)

    # ── G,H,I열: A/B 타입 (G열에 이미 값 있으면 스킵) ────────
    if not stop_ev.is_set():
        if _cell(6):   # G열에 이미 값 있음 → 스킵
            vals["g"] = _cell(6)
            vals["h"] = _cell(7)
            vals["i"] = _cell(8)
            log(f"    G,H,I 스킵 (기존: {vals['g']})", None)
        else:
            try:
                t = check_naver_type(driver, kw)
                vals["g"] = t["type"]
                vals["h"] = " | ".join(t["a_boxes"])
                vals["i"] = " | ".join(t["normals"])
                tag = "A" if t["type"]=="A" else "B"
                log(f"    G 타입    : {t['type']}", tag)
                if t["a_boxes"]: log(f"    H A박스   : {vals['h']}", "BOX")
                if t["normals"]: log(f"    I 일반섹션: {vals['i']}", None)
            except Exception as e:
                vals["g"] = "오류"
                log(f"    G,H,I 오류: {str(e)[:60]}", "ERR")
            time.sleep(2)

    # ── F열: 노출구좌 (F열에 이미 값 있으면 스킵) ────────────
    if not stop_ev.is_set():
        if _cell(5):   # F열에 이미 값 있음 → 스킵
            vals["f"] = _cell(5)
            log(f"    F 스킵 (기존: {vals['f']})", None)
        else:
            try:
                vals["f"] = count_result_types(driver, kw)
                log(f"    F 노출구좌: {vals['f']}", None)
            except Exception as e:
                vals["f"] = "오류"
                log(f"    F 오류: {str(e)[:60]}", "ERR")
            time.sleep(2)

    # ── E열: 검색량 (E열에 이미 값 있으면 스킵) ─────────────
    if not stop_ev.is_set():
        if _cell(4):   # E열에 이미 값 있음 → 스킵
            vals["e"] = _cell(4)
            log(f"    E 스킵 (기존: {vals['e']})", None)
        else:
            try:
                vol = get_search_volume(
                    kw, cfg["naver_customer"], cfg["naver_api_key"], cfg["naver_secret"])
                vals["e"] = vol
                log(f"    E 검색량  : {vol:,}", None)
            except Exception as e:
                vals["e"] = 0
                log(f"    E 오류: {str(e)[:60]}", "ERR")
            time.sleep(0.3)

    # ── 시트 업데이트 ────────────────────────────────────────
    if not stop_ev.is_set():
        try:
            if has_link:
                write_row(ws, ri, vals, k_col)
            else:
                # C열 없음: E,F,G,H,I만
                partial = {k: vals.get(k, "") for k in ("e","f","g","h","i")}
                ws.update(
                    values=[[str(partial["e"]), str(partial["f"]),
                             str(partial["g"]), str(partial["h"]),
                             str(partial["i"])]],
                    range_name=f"E{ri}:I{ri}",
                )
            log(f"    ✔ 행 {ri} 업데이트 완료", "INFO")
        except Exception as e:
            log(f"    ✘ 시트 업데이트 실패: {e}", "ERR")


# ══════════════════════════════════════════════════════════════
# GUI 애플리케이션
# ══════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("카페마케팅 자동화 v2.0")
        self.geometry("900x750")
        self.resizable(True, True)
        self.configure(bg="#f0f0f0")

        self.cfg      = load_config()
        self.q        = queue.Queue()
        self.stop_ev  = threading.Event()
        self.running  = False
        self._sched_id = None   # tkinter after 스케줄 ID

        self._build_ui()
        self._apply_config()
        self._poll_queue()

    # ── UI 구성 ────────────────────────────────────────────
    def _build_ui(self):
        BG   = "#f0f0f0"
        PAD  = {"padx": 8, "pady": 4}
        FONT = ("맑은 고딕", 9)
        BOLD = ("맑은 고딕", 9, "bold")

        # ── 구글 시트 설정 ─────────────────────────────────
        fr_gs = tk.LabelFrame(self, text=" 구글 시트 연동 ", bg=BG, font=BOLD)
        fr_gs.pack(fill="x", **PAD)

        r0 = tk.Frame(fr_gs, bg=BG); r0.pack(fill="x", padx=6, pady=3)
        tk.Label(r0, text="스프레드시트 URL:", bg=BG, font=FONT).pack(side="left")
        self.sv_url = tk.StringVar()
        self.sv_url.trace_add("write", self._on_url_change)
        tk.Entry(r0, textvariable=self.sv_url, width=55, font=FONT).pack(side="left", padx=4)
        tk.Button(r0, text="연결 확인", bg="#4a90d9", fg="white", font=BOLD,
                  relief="flat", padx=8, command=self._test_sheet).pack(side="left")

        r1 = tk.Frame(fr_gs, bg=BG); r1.pack(fill="x", padx=6, pady=2)
        tk.Label(r1, text="시트명:", bg=BG, font=FONT).pack(side="left", anchor="nw", pady=2)
        _sf = tk.Frame(r1, bg=BG); _sf.pack(side="left", padx=4)
        self.txt_sheets = tk.Text(_sf, height=3, width=28, font=FONT,
                                  relief="sunken", borderwidth=1)
        self.txt_sheets.pack(side="left")
        _sb = tk.Scrollbar(_sf, orient="vertical", command=self.txt_sheets.yview)
        _sb.pack(side="left", fill="y")
        self.txt_sheets.config(yscrollcommand=_sb.set)
        tk.Label(r1, text="줄바꿈으로 여러 시트 구분\n(위에서부터 순서대로 처리)",
                 bg=BG, font=("맑은 고딕", 8), fg="#666").pack(side="left", padx=6)

        r2 = tk.Frame(fr_gs, bg=BG); r2.pack(fill="x", padx=6, pady=2)
        tk.Label(r2, text="JSON 인증키:", bg=BG, font=FONT).pack(side="left")
        self.sv_key = tk.StringVar()
        tk.Entry(r2, textvariable=self.sv_key, width=48, font=FONT,
                 state="readonly").pack(side="left", padx=4)
        tk.Button(r2, text="찾아보기", bg="#7f8c8d", fg="white", font=BOLD,
                  relief="flat", padx=6, command=self._browse_key).pack(side="left")

        self.lbl_email = tk.Label(fr_gs, text="서비스 계정: (키 파일을 선택하세요)",
                                  bg=BG, font=("맑은 고딕", 8), fg="#555")
        self.lbl_email.pack(anchor="w", padx=8, pady=(0, 4))

        self.lbl_share = tk.Label(fr_gs, text="", bg="#fff3cd",
                                  font=("맑은 고딕", 8), fg="#856404",
                                  wraplength=760, justify="left")

        # ── 네이버 API 설정 ────────────────────────────────
        fr_nv = tk.LabelFrame(self, text=" 네이버 검색광고 API ", bg=BG, font=BOLD)
        fr_nv.pack(fill="x", **PAD)

        r3 = tk.Frame(fr_nv, bg=BG); r3.pack(fill="x", padx=6, pady=4)
        tk.Label(r3, text="고객ID:", bg=BG, font=FONT).pack(side="left")
        self.sv_cust = tk.StringVar()
        tk.Entry(r3, textvariable=self.sv_cust, width=14, font=FONT).pack(side="left", padx=4)
        tk.Label(r3, text="엑세스 라이선스:", bg=BG, font=FONT).pack(side="left", padx=(10,0))
        self.sv_apikey = tk.StringVar()
        tk.Entry(r3, textvariable=self.sv_apikey, width=34, font=FONT).pack(side="left", padx=4)

        r4 = tk.Frame(fr_nv, bg=BG); r4.pack(fill="x", padx=6, pady=(0,4))
        tk.Label(r4, text="비밀키:", bg=BG, font=FONT).pack(side="left")
        self.sv_secret = tk.StringVar()
        tk.Entry(r4, textvariable=self.sv_secret, width=55, font=FONT, show="*").pack(side="left", padx=4)
        tk.Button(r4, text="👁", bg=BG, font=FONT, relief="flat",
                  command=self._toggle_secret).pack(side="left")
        self._secret_visible = False

        # ── 실행 제어 ─────────────────────────────────────
        fr_ctrl = tk.LabelFrame(self, text=" 실행 제어 ", bg=BG, font=BOLD)
        fr_ctrl.pack(fill="x", **PAD)

        r5 = tk.Frame(fr_ctrl, bg=BG); r5.pack(fill="x", padx=6, pady=4)
        self.btn_start = tk.Button(r5, text="▶  지금 실행", bg="#27ae60", fg="white",
                                   font=BOLD, relief="flat", padx=14,
                                   command=self._start)
        self.btn_start.pack(side="left")
        self.btn_stop = tk.Button(r5, text="■  중지", bg="#e74c3c", fg="white",
                                  font=BOLD, relief="flat", padx=12,
                                  command=self._stop, state="disabled")
        self.btn_stop.pack(side="left", padx=6)

        self.progress = ttk.Progressbar(r5, mode="determinate", length=250)
        self.progress.pack(side="left", padx=(10,4))
        self.lbl_prog = tk.Label(r5, text="대기 중", bg=BG, font=FONT)
        self.lbl_prog.pack(side="left")

        r6 = tk.Frame(fr_ctrl, bg=BG); r6.pack(fill="x", padx=6, pady=(0,4))
        self.var_repeat = tk.BooleanVar()
        tk.Checkbutton(r6, text="24시간 반복 실행", variable=self.var_repeat,
                       bg=BG, font=FONT, command=self._on_repeat_toggle).pack(side="left")
        tk.Label(r6, text="매일", bg=BG, font=FONT).pack(side="left", padx=(12,2))
        self.sv_time = tk.StringVar(value="09:00")
        tk.Entry(r6, textvariable=self.sv_time, width=7, font=FONT).pack(side="left")
        tk.Label(r6, text="에 실행", bg=BG, font=FONT).pack(side="left", padx=2)
        self.lbl_next = tk.Label(r6, text="", bg=BG, font=("맑은 고딕", 8), fg="#555")
        self.lbl_next.pack(side="left", padx=(20,0))

        # ── 실시간 로그 ────────────────────────────────────
        fr_log = tk.LabelFrame(self, text=" 실시간 진행 현황 ", bg=BG, font=BOLD)
        fr_log.pack(fill="both", expand=True, **PAD)

        self.log_box = scrolledtext.ScrolledText(
            fr_log, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white", wrap="word", state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=4, pady=4)

        self.log_box.tag_config("A",    foreground="#4ec9b0")
        self.log_box.tag_config("B",    foreground="#9cdcfe")
        self.log_box.tag_config("INFO", foreground="#dcdcaa")
        self.log_box.tag_config("ERR",  foreground="#f44747")
        self.log_box.tag_config("BOX",  foreground="#ce9178")

        # ── 상태 바 ───────────────────────────────────────
        sb = tk.Frame(self, bg="#ddd", height=1); sb.pack(fill="x", padx=8)
        sf = tk.Frame(self, bg=BG); sf.pack(fill="x", padx=8, pady=2)
        self.lbl_status = tk.Label(sf, text="준비", bg=BG, font=("맑은 고딕", 8), fg="#555")
        self.lbl_status.pack(side="left")

    # ── 설정 적용 / 저장 ───────────────────────────────────
    def _apply_config(self):
        self.sv_url.set(self.cfg.get("sheet_url", ""))
        self.txt_sheets.delete("1.0", "end")
        self.txt_sheets.insert("1.0", self.cfg.get("sheet_names", "시트1"))
        self.sv_key.set(self.cfg.get("key_path", ""))
        self.sv_cust.set(self.cfg.get("naver_customer", ""))
        self.sv_apikey.set(self.cfg.get("naver_api_key", ""))
        self.sv_secret.set(self.cfg.get("naver_secret", ""))
        self.var_repeat.set(self.cfg.get("repeat_enabled", False))
        self.sv_time.set(self.cfg.get("repeat_time", "09:00"))
        if self.sv_key.get():
            self._update_email_label(self.sv_key.get())

    def _get_sheet_names(self) -> list:
        """시트명 Text 위젯에서 줄 단위로 파싱"""
        raw = self.txt_sheets.get("1.0", "end")
        return [s.strip() for s in raw.splitlines() if s.strip()]

    def _save_current_config(self):
        self.cfg.update({
            "sheet_url":      self.sv_url.get(),
            "sheet_names":    self.txt_sheets.get("1.0", "end").strip(),
            "key_path":       self.sv_key.get(),
            "naver_customer": self.sv_cust.get(),
            "naver_api_key":  self.sv_apikey.get(),
            "naver_secret":   self.sv_secret.get(),
            "repeat_enabled": self.var_repeat.get(),
            "repeat_time":    self.sv_time.get(),
        })
        save_config(self.cfg)

    # ── UI 이벤트 ─────────────────────────────────────────
    def _browse_key(self):
        path = filedialog.askopenfilename(
            title="JSON 인증키 파일 선택",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")])
        if not path: return
        self.sv_key.set(path)
        self._update_email_label(path)

    def _update_email_label(self, path: str):
        email = get_service_email(path)
        if email:
            self.lbl_email.config(
                text=f"서비스 계정 이메일: {email}",
                fg="#1a5276")

    def _on_url_change(self, *_):
        url = self.sv_url.get().strip()
        if not url: return
        key_path = self.sv_key.get()
        if key_path:
            email = get_service_email(key_path)
            if email:
                self.lbl_share.config(
                    text=f"⚠ 새 스프레드시트를 연결하실 경우, 아래 이메일을 스프레드시트 공유(편집자)에 추가해주세요:\n{email}")
                self.lbl_share.pack(fill="x", padx=6, pady=(0,4))

    def _on_repeat_toggle(self):
        if not self.var_repeat.get():
            self.lbl_next.config(text="")
            if self._sched_id:
                self.after_cancel(self._sched_id)
                self._sched_id = None

    def _toggle_secret(self):
        self._secret_visible = not self._secret_visible
        entries = [w for w in self.winfo_children()
                   if isinstance(w, tk.LabelFrame)]
        # 비밀키 Entry 직접 접근
        for fr in entries:
            for w in fr.winfo_children():
                for sub in (w.winfo_children() if hasattr(w,'winfo_children') else []):
                    if isinstance(sub, tk.Entry) and sub.cget("show") == "*":
                        sub.config(show="" if self._secret_visible else "*")

    def _test_sheet(self):
        """연결 확인 (다중 시트)"""
        sheet_names = self._get_sheet_names()
        if not sheet_names:
            messagebox.showerror("오류", "시트명을 입력해주세요.")
            return
        results = []
        for name in sheet_names:
            try:
                sh, ws = open_sheet(self.sv_key.get(), self.sv_url.get(), name)
                rows = get_data_rows(ws)
                results.append(f"✔ [{name}]  {len(rows)}행")
            except Exception as e:
                results.append(f"✘ [{name}]  {str(e)[:60]}")
        msg = "\n".join(results)
        if all(r.startswith("✔") for r in results):
            messagebox.showinfo("연결 성공", msg)
        else:
            messagebox.showwarning("연결 확인", msg)

    # ── 실행 / 중지 ────────────────────────────────────────
    def _start(self):
        if self.running: return
        self._save_current_config()
        self.running = True
        self.stop_ev.clear()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.progress["value"] = 0
        self._log("\n" + "="*58 + "\n", "INFO")
        self._log(f"  실행 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n", "INFO")
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def _stop(self):
        self.stop_ev.set()
        self._log("\n  [중지 요청됨...]\n", "ERR")
        if self._sched_id:
            self.after_cancel(self._sched_id)
            self._sched_id = None
            self.lbl_next.config(text="")

    # ── 워커 스레드 ───────────────────────────────────────
    def _worker(self):
        cfg         = dict(self.cfg)
        sheet_names = [s.strip() for s in cfg.get("sheet_names","시트1").split("\n") if s.strip()]
        if not sheet_names:
            self.q.put(("log", "  시트명이 입력되지 않았습니다.\n", "ERR"))
            self.q.put(("done",)); return

        # 소켓 전체 타임아웃 설정 (gspread API 응답 무한 대기 방지)
        import socket as _sock
        _sock.setdefaulttimeout(30)

        driver = None
        try:
            self.q.put(("log", "  ChromeDriver 초기화 중...\n", "INFO"))
            driver = build_driver(headless=True)
            self.q.put(("log", "  초기화 완료\n", "INFO"))

            for s_idx, sheet_name in enumerate(sheet_names, 1):
                if self.stop_ev.is_set(): break

                self.q.put(("log",
                    f"\n{'='*52}\n  [{s_idx}/{len(sheet_names)}] 시트: 【{sheet_name}】\n{'='*52}\n",
                    "INFO"))

                # ── 시트 연결 ───────────────────────────
                try:
                    sh, ws = open_sheet(cfg["key_path"], cfg["sheet_url"], sheet_name)
                except Exception as e:
                    self.q.put(("log", f"  시트 연결 실패: {e}\n", "ERR"))
                    continue

                # ── 총 행수 미리 파악 (진행률용) ─────────
                try:
                    col_b      = ws.col_values(2)
                    total_rows = sum(1 for v in col_b[1:] if v.strip())
                except Exception:
                    total_rows = 0
                self.q.put(("log", f"  처리 대상: {total_rows}행\n", "INFO"))
                self.q.put(("total", total_rows))

                if total_rows == 0:
                    self.q.put(("log", "  처리할 데이터가 없습니다.\n", "ERR"))
                    continue

                # ── J,K 히스토리 열 준비 ────────────────
                now = datetime.now()
                try:
                    j_col, k_col = prepare_history_columns(ws, sh, now)
                    self.q.put(("log", "  J,K 히스토리 열 준비 완료\n", "INFO"))
                except Exception as e:
                    self.q.put(("log", f"  히스토리 열 준비 오류: {e}\n", "ERR"))
                    j_col, k_col = 10, 11

                # ── 행 단위 실시간 처리 ──────────────────
                row_idx        = 2
                processed      = 0
                driver_err_cnt = 0   # 연속 드라이버 오류 카운터
                restart_cnt    = 0   # 정기 재시작 카운터 (20행마다)

                while not self.stop_ev.is_set():
                    # 처리 직전 행 데이터 새로 취득 (중간 추가/삭제 반영)
                    try:
                        row_data = ws.row_values(row_idx)
                        driver_err_cnt = 0
                    except Exception as e:
                        self.q.put(("log", f"  행 {row_idx} 읽기 오류: {e}\n", "ERR"))
                        break

                    while len(row_data) < 11:
                        row_data.append("")

                    keyword = row_data[1].strip()
                    if not keyword:
                        break          # B열 비어있으면 시트 종료

                    link = row_data[2].strip()
                    row  = {"row_idx": row_idx, "B": keyword, "C": link, "data": row_data}
                    processed += 1
                    self.q.put(("progress", processed, total_rows))

                    try:
                        process_one_row(driver, ws, row, k_col, cfg, self.q, self.stop_ev)
                    except Exception as e:
                        # 드라이버 크래시 등 예상치 못한 오류
                        driver_err_cnt += 1
                        self.q.put(("log",
                            f"  행 {row_idx} 예외: {str(e)[:80]}\n"
                            f"  (연속 오류 {driver_err_cnt}회)\n", "ERR"))

                        if driver_err_cnt >= 3:
                            # 드라이버 재시작 시도
                            self.q.put(("log", "  드라이버 재시작 중...\n", "INFO"))
                            try: driver.quit()
                            except Exception: pass
                            try:
                                driver = build_driver(headless=True)
                                driver_err_cnt = 0
                                self.q.put(("log", "  드라이버 재시작 완료\n", "INFO"))
                            except Exception as e2:
                                self.q.put(("log",
                                    f"  드라이버 재시작 실패: {e2}\n"
                                    "  → 작업을 중단합니다.\n", "ERR"))
                                self.stop_ev.set()
                                break

                    if not self.stop_ev.is_set():
                        time.sleep(3)
                    row_idx     += 1
                    restart_cnt += 1
                    if restart_cnt >= 20 and not self.stop_ev.is_set():
                        self.q.put(("log", "  ── 드라이버 정기 재시작 (20행) ──\n", "INFO"))
                        try: driver.quit()
                        except Exception: pass
                        try:
                            driver = build_driver(headless=True)
                            restart_cnt = 0
                            self.q.put(("log", "  재시작 완료\n", "INFO"))
                        except Exception as e2:
                            self.q.put(("log", f"  재시작 실패: {e2}\n", "ERR"))
                            self.stop_ev.set()
                            break

                self.q.put(("log",
                    f"\n  시트 【{sheet_name}】 완료 ({processed}행 처리)\n", "INFO"))

            if self.stop_ev.is_set():
                self.q.put(("log", "\n  중지됨\n", "ERR"))
            else:
                self.q.put(("log",
                    f"\n  전체 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n", "INFO"))

        except Exception as e:
            self.q.put(("log", f"\n  오류 발생: {e}\n", "ERR"))

        finally:
            # 정상/오류/중지 어느 경우든 드라이버 종료 + 버튼 복구
            if driver:
                try: driver.quit()
                except Exception: pass
            self.q.put(("done",))

    # ── 큐 폴링 ──────────────────────────────────────────
    def _poll_queue(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._log(msg[1], msg[2] if len(msg)>2 else None)
                elif kind == "total":
                    self.progress["maximum"] = msg[1]
                elif kind == "progress":
                    idx, total = msg[1], msg[2]
                    self.progress["value"] = idx
                    self.lbl_prog.config(text=f"{idx}/{total}")
                    self.lbl_status.config(text=f"처리 중... {idx}/{total}")
                elif kind == "done":
                    self._finish()
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _log(self, text, tag=None):
        self.log_box.config(state="normal")
        self.log_box.insert("end", text, tag or "")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _finish(self):
        self.running = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.lbl_status.config(text="완료")

        if self.var_repeat.get() and not self.stop_ev.is_set():
            self._schedule_next()

    # ── 반복 스케줄 ───────────────────────────────────────
    def _schedule_next(self):
        time_str = self.sv_time.get().strip()
        try:
            h, m = map(int, time_str.split(":"))
        except Exception:
            self._log("  반복 시간 형식 오류 (HH:MM 으로 입력)\n", "ERR")
            return

        now  = datetime.now()
        next_run = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)

        delay_ms = int((next_run - now).total_seconds() * 1000)
        self.lbl_next.config(
            text=f"다음 실행: {next_run.strftime('%m/%d %H:%M')} ({int(delay_ms/60000)}분 후)")
        self._log(f"\n  ⏰ 다음 실행: {next_run.strftime('%Y-%m-%d %H:%M')}\n", "INFO")

        self._sched_id = self.after(delay_ms, self._start)

    # ── 창 닫기 ───────────────────────────────────────────
    def destroy(self):
        self._save_current_config()
        self.stop_ev.set()
        if self._sched_id:
            self.after_cancel(self._sched_id)
        super().destroy()


# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = App()
    app.mainloop()
