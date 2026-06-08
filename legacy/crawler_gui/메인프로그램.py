# -*- coding: utf-8 -*-
"""
네이버 카페 게시글 크롤러 - 메인 프로그램
==========================================
"""

import importlib.util
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog


# ── 경로 헬퍼 ─────────────────────────────────────────────────────────

def _modules_dir() -> str:
    """모듈 .py 파일이 있는 폴더 (frozen=sys._MEIPASS, dev=스크립트 폴더)"""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _base_dir() -> str:
    """설정·쿠키·토큰 파일 기준 폴더 (frozen=exe 폴더, dev=스크립트 폴더)"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _load(filename: str):
    """숫자로 시작하는 모듈 파일을 동적으로 로드합니다."""
    path = os.path.join(_modules_dir(), filename)
    spec = importlib.util.spec_from_file_location(
        os.path.splitext(filename)[0], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 경량 모듈 즉시 로드 ────────────────────────────────────────────────
_설정 = _load("06_설정관리.py")
_스케줄 = _load("07_자동스케줄러.py")

_BASE = _base_dir()
_SETTINGS_FILE = os.path.join(_BASE, "settings.json")


# ══════════════════════════════════════════════════════════════════════
#  메인 앱
# ══════════════════════════════════════════════════════════════════════

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("네이버 카페 게시글 크롤러")
        self.geometry("970x730")
        self.minsize(820, 580)

        self._s           = _설정.load_settings(_SETTINGS_FILE)
        self._running     = False
        self._stop_flag   = [False]
        self._timer       = None
        self._biz_dict    = {}     # {네이버ID: 업체명}

        self._build_ui()
        self._refresh_jobs()
        self._auto_load_biz()  # 시작 시 업체목록.txt 자동 로드
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI 구성 ───────────────────────────────────────────────────────

    def _build_ui(self):

        # ── 상단 툴바 ──────────────────────────────────────────────
        bar = tk.Frame(self, pady=6, padx=8, bg="#2c3e50")
        bar.pack(fill=tk.X)

        _btn = lambda parent, t, cmd, **kw: tk.Button(
            parent, text=t, command=cmd,
            relief=tk.FLAT, cursor="hand2",
            bg="#34495e", fg="white", activebackground="#4a6278",
            padx=10, pady=4, **kw)

        _btn(bar, "⚙  기본 설정",    self._open_settings).pack(side=tk.LEFT, padx=4)
        _btn(bar, "🔑  네이버 로그인", self._do_login).pack(side=tk.LEFT, padx=4)
        _btn(bar, "📋  업체목록",     self._on_load_biz).pack(side=tk.LEFT, padx=4)
        _btn(bar, "📊  시트 로드",    self._on_load_biz_sheet).pack(side=tk.LEFT, padx=4)
        _btn(bar, "💾  설정 내보내기", self._export_settings).pack(side=tk.LEFT, padx=4)
        _btn(bar, "📂  설정 불러오기", self._import_settings).pack(side=tk.LEFT, padx=4)
        _btn(bar, "🔍  모니터 체크",  self._do_monitor_check).pack(side=tk.LEFT, padx=4)

        self._status_lbl = tk.Label(
            bar, text="● 대기 중", fg="#95a5a6",
            bg="#2c3e50", font=("", 9))
        self._status_lbl.pack(side=tk.RIGHT, padx=12)

        self._biz_lbl = tk.Label(
            bar, text="업체: 0개", fg="#95a5a6",
            bg="#2c3e50", font=("", 9))
        self._biz_lbl.pack(side=tk.RIGHT, padx=8)

        # ── 작업 목록 ──────────────────────────────────────────────
        jf = tk.LabelFrame(self, text="  작업 목록  ",
                           padx=6, pady=4, font=("", 9, "bold"))
        jf.pack(fill=tk.X, padx=10, pady=(6, 2))

        cols   = ("카페명", "카페ID", "시작번호", "종료번호", "마지막수집", "답글추출", "상태")
        widths = (150, 95, 80, 80, 90, 60, 70)

        self._tree = ttk.Treeview(
            jf, columns=cols, show="headings",
            height=8, selectmode="browse")

        style = ttk.Style()
        style.configure("Treeview", rowheight=24)
        style.configure("Treeview.Heading", font=("", 9, "bold"))

        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="center")

        vsb = ttk.Scrollbar(jf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.tag_configure("running", background="#dff0d8")
        self._tree.tag_configure("done",    background="#d9edf7")
        self._tree.tag_configure("error",   background="#f2dede")

        # ── 작업 버튼 ──────────────────────────────────────────────
        bf = tk.Frame(self, padx=10)
        bf.pack(fill=tk.X, pady=(2, 4))

        for text, cmd in [("＋ 작업 추가", self._add_job),
                          ("✎  편집",      self._edit_job),
                          ("✕  삭제",      self._del_job)]:
            tk.Button(bf, text=text, command=cmd, width=10,
                      relief=tk.GROOVE).pack(side=tk.LEFT, padx=2)

        ttk.Separator(self).pack(fill=tk.X, padx=10, pady=6)

        # ── 실행 컨트롤 ────────────────────────────────────────────
        cf = tk.Frame(self, padx=10, pady=2)
        cf.pack(fill=tk.X)

        self._run_btn = tk.Button(
            cf, text="▶  수집 시작", width=14,
            bg="#27ae60", fg="white", activebackground="#2ecc71",
            font=("", 10, "bold"), relief=tk.FLAT, cursor="hand2",
            command=self._start_crawl)
        self._run_btn.pack(side=tk.LEFT, padx=2)

        self._stop_btn = tk.Button(
            cf, text="■  중지", width=10,
            bg="#e74c3c", fg="white", activebackground="#c0392b",
            font=("", 10, "bold"), relief=tk.FLAT, cursor="hand2",
            state=tk.DISABLED, command=self._stop_crawl)
        self._stop_btn.pack(side=tk.LEFT, padx=2)

        tk.Label(cf, text="  |  ").pack(side=tk.LEFT)

        self._auto_var = tk.BooleanVar(value=False)
        tk.Checkbutton(cf, text="자동 실행",
                       variable=self._auto_var,
                       command=self._toggle_auto).pack(side=tk.LEFT)
        self._auto_time_var = tk.StringVar(
            value=self._s.get("auto_time", "09:00"))
        tk.Entry(cf, textvariable=self._auto_time_var,
                 width=7).pack(side=tk.LEFT, padx=2)
        tk.Label(cf, text="(HH:MM)").pack(side=tk.LEFT)

        tk.Label(cf, text="  |  ").pack(side=tk.LEFT)

        self._upload_var = tk.BooleanVar(
            value=bool(self._s.get("gs_folder_id", "")))
        tk.Checkbutton(cf, text="완료 후 Drive 업로드",
                       variable=self._upload_var).pack(side=tk.LEFT, padx=4)

        # ── 로그 ───────────────────────────────────────────────────
        lf = tk.LabelFrame(self, text="  실행 로그  ",
                           padx=4, pady=4, font=("", 9, "bold"))
        lf.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 10))

        self._log = scrolledtext.ScrolledText(
            lf, state=tk.DISABLED, wrap=tk.WORD,
            font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white")
        self._log.pack(fill=tk.BOTH, expand=True)

        self._log.tag_configure("ok",    foreground="#4ec9b0")
        self._log.tag_configure("err",   foreground="#f48771")
        self._log.tag_configure("info",  foreground="#9cdcfe")
        self._log.tag_configure("plain", foreground="#d4d4d4")

    # ── 작업 목록 갱신 ────────────────────────────────────────────────

    def _refresh_jobs(self):
        for r in self._tree.get_children():
            self._tree.delete(r)

        tag_map = {"수집 중": "running", "완료": "done",
                   "오류": "error", "대기": ""}
        for job in self._s.get("jobs", []):
            status = job.get("status", "대기")
            tag = tag_map.get(status, "")
            self._tree.insert("", tk.END, tags=(tag,), values=(
                job.get("cafe_name", ""),
                job.get("cafe_id", ""),
                job.get("start_id", ""),
                job.get("end_id", "") or "끝까지",
                job.get("last_id", "-"),
                "✓" if job.get("extract_replies") else "-",
                status,
            ))

    def _sel_idx(self):
        sel = self._tree.selection()
        return self._tree.index(sel[0]) if sel else None

    # ── 작업 CRUD ─────────────────────────────────────────────────────

    def _add_job(self):
        JobDialog(self, "작업 추가", on_save=self._on_job_add)

    def _on_job_add(self, d):
        extract_replies = d.pop("extract_replies", False)
        try:
            _설정.add_job(self._s, **d)
        except ValueError as e:
            messagebox.showerror("입력 오류", str(e))
            return
        self._s["jobs"][-1]["extract_replies"] = extract_replies
        _설정.save_settings(self._s, _SETTINGS_FILE)
        self._refresh_jobs()

    def _edit_job(self):
        idx = self._sel_idx()
        if idx is None:
            messagebox.showinfo("알림", "편집할 작업을 선택하세요.")
            return
        JobDialog(self, "작업 편집",
                  initial=self._s["jobs"][idx],
                  on_save=lambda d: self._on_job_edit(idx, d))

    def _on_job_edit(self, idx, d):
        self._s["jobs"][idx].update(d)
        _설정.save_settings(self._s, _SETTINGS_FILE)
        self._refresh_jobs()

    def _del_job(self):
        idx = self._sel_idx()
        if idx is None:
            messagebox.showinfo("알림", "삭제할 작업을 선택하세요.")
            return
        name = self._s["jobs"][idx]["cafe_name"]
        if not messagebox.askyesno("삭제 확인",
                                   f"'{name}' 작업을 삭제하시겠습니까?"):
            return
        self._s["jobs"].pop(idx)
        _설정.save_settings(self._s, _SETTINGS_FILE)
        self._refresh_jobs()

    # ── 기본 설정 ─────────────────────────────────────────────────────

    def _open_settings(self):
        SettingsDialog(self, self._s, on_save=self._on_settings_save)

    def _on_settings_save(self, data):
        self._s.update(data)
        self._auto_time_var.set(data.get("auto_time", "09:00"))
        _설정.save_settings(self._s, _SETTINGS_FILE)
        self._log_msg("설정 저장 완료", "ok")

    # ── 설정 내보내기 / 불러오기 ──────────────────────────────────────

    def _export_settings(self):
        if not os.path.exists(_SETTINGS_FILE):
            messagebox.showwarning("알림", "저장된 설정 파일이 없습니다.")
            return
        path = filedialog.asksaveasfilename(
            title="설정 내보내기",
            defaultextension=".json",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")],
            initialfile="settings.json",
        )
        if not path:
            return
        import shutil
        shutil.copy2(_SETTINGS_FILE, path)
        self._log_msg(f"설정 내보내기 완료: {path}", "ok")

    def _import_settings(self):
        path = filedialog.askopenfilename(
            title="설정 불러오기",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        import shutil
        shutil.copy2(path, _SETTINGS_FILE)
        self._s = _설정.load_settings(_SETTINGS_FILE)
        self._refresh_jobs()
        self._auto_time_var.set(self._s.get("auto_time", "09:00"))
        self._log_msg(f"설정 불러오기 완료: {path}", "ok")

    # ── 네이버 로그인 ─────────────────────────────────────────────────

    def _do_login(self):
        if self._running:
            messagebox.showinfo("알림", "수집 중에는 로그인할 수 없습니다.")
            return
        nid = self._s.get("naver_id", "")
        npw = self._s.get("naver_pw", "")
        if not nid or not npw:
            messagebox.showwarning(
                "알림", "먼저 [기본 설정]에서 네이버 ID/PW를 입력하세요.")
            return
        self._log_msg("네이버 로그인 중... (브라우저가 열립니다)", "info")
        def _run():
            try:
                mod = _load("02_네이버로그인.py")
                mod.naver_login(nid, npw)
                self._log_msg("네이버 로그인 완료", "ok")
            except Exception as e:
                self._log_msg(f"[오류] 로그인 실패: {e}", "err")
        threading.Thread(target=_run, daemon=True).start()

    # ── 크롤링 실행 ───────────────────────────────────────────────────

    def _start_crawl(self):
        if self._running:
            return
        if not self._s.get("jobs"):
            messagebox.showinfo("알림", "작업을 먼저 추가하세요.")
            return
        self._running   = True
        self._stop_flag = [False]
        self._run_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self._set_status("● 수집 중...", "#3498db")
        self._log_msg("=" * 52, "info")
        self._log_msg("수집 시작", "info")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            mod_c = _load("03_게시글수집.py")
            mod_u = (_load("05_구글시트업로드.py")
                     if self._upload_var.get() else None)
            mod_m = _load("08_모니터링.py")

            s       = self._s
            folder  = s.get("gs_folder_id", "")

            # ── 크롤링 전 업체목록 시트 자동 업데이트 ─────────────────
            biz_url = s.get("biz_sheet_url", "")
            if biz_url:
                self._log_msg("업체목록 시트 자동 업데이트 중...", "info")
                try:
                    mod_biz = _load("05_구글시트업로드.py")
                    biz = mod_biz.load_biz_from_sheet(
                        biz_url, _BASE, log_fn=self._log_msg)
                    self._biz_dict = biz
                    cnt = len(biz)
                    self._log_msg(f"업체목록 업데이트 완료: {cnt}개", "ok")
                    self.after(0, lambda c=cnt: self._biz_lbl.config(
                        text=f"업체: {c}개"))
                except Exception as e:
                    self._log_msg(f"[경고] 시트 자동 로드 실패: {e}", "err")

            session = mod_c.build_session(mod_c.COOKIE_FILE)
            mod_l   = _load("02_네이버로그인.py")

            def _relogin():
                nonlocal session
                nid_val = s.get("naver_id", "")
                npw_val = s.get("naver_pw", "")
                if not nid_val or not npw_val:
                    self._log_msg(
                        "[오류] 재로그인 불가: 네이버 ID/PW 가 설정에 없습니다.", "err")
                    return None
                ok = mod_l.naver_login(nid_val, npw_val)
                if ok:
                    self._log_msg("재로그인 성공 → 크롤링 재개", "ok")
                    session = mod_c.build_session(mod_c.COOKIE_FILE)
                    return session
                self._log_msg("[오류] 재로그인 실패 → ID 수집 불가 상태로 계속 진행", "err")
                return None

            for i, job in enumerate(s["jobs"]):
                if self._stop_flag[0]:
                    self._log_msg("중지됨", "err")
                    break

                self._set_job_status(i, "수집 중")
                cafe = job["cafe_name"]
                self._log_msg(
                    f"\n[{i+1}/{len(s['jobs'])}] {cafe} 수집 시작", "info")

                try:
                    # ── 이전 수집 이어서 하기: last_id 있으면 항상 +1부터 ──
                    _last_id_str = job.get("last_id", "")
                    if _last_id_str:
                        effective_start = int(_last_id_str) + 1
                        # job 설정 갱신: start_id 업데이트, last_id 초기화
                        job["start_id"] = str(effective_start)
                        job["last_id"]  = ""
                        _설정.save_settings(s, _SETTINGS_FILE)
                        self.after(0, self._refresh_jobs)
                        self._log_msg(
                            f"이전 수집 이어서: {int(_last_id_str)}번 → {effective_start}번부터 시작", "info")
                    else:
                        effective_start = int(job.get("start_id") or 1)

                    last_id = mod_c.crawl_cafe(
                        session     = session,
                        cafe_name   = cafe,
                        cafe_id     = int(job["cafe_id"]),
                        start_id    = effective_start,
                        end_id      = (int(job["end_id"])
                                       if job.get("end_id") else None),
                        max_missing = int(s.get("max_missing", 100)),
                        output_dir  = _BASE,
                        stop_flag   = self._stop_flag,
                        log_fn      = self._log_msg,
                        biz_dict    = self._biz_dict,
                        login_fn    = _relogin,
                    )

                    if last_id:
                        job["last_id"] = str(last_id)
                        _설정.save_settings(s, _SETTINGS_FILE)
                        self.after(0, self._refresh_jobs)

                    self._set_job_status(i, "완료")
                    self._log_msg(f"{cafe} 완료 (마지막: {last_id})", "ok")

                    start = str(effective_start)
                    tsv   = os.path.join(_BASE, f"{cafe}_{start}_{last_id}.tsv")

                    # 드라이브 업로드
                    if mod_u and folder and last_id:
                        if os.path.exists(tsv):
                            self._log_msg("구글 드라이브 업로드 중...", "info")
                            link = mod_u.upload_tsv_to_drive(
                                tsv, folder,
                                base_dir=_BASE,
                                log_fn=self._log_msg,
                            )
                            if link:
                                self._log_msg(f"업로드 완료: {link}", "ok")
                        else:
                            self._log_msg(
                                f"TSV 파일 없음 (업로드 건너뜀): {tsv}", "err")

                    # 모니터링 등록
                    if last_id and os.path.exists(tsv):
                        try:
                            mod_m.register_from_tsv(
                                tsv,
                                cafe,
                                job["cafe_id"],
                                _BASE,
                                folder_id=s.get("gs_folder_id", ""),
                                log_fn=self._log_msg,
                            )
                        except Exception as e:
                            self._log_msg(f"[모니터] 등록 오류: {e}", "err")

                    # 답글 게시글 별도 추출
                    if job.get("extract_replies") and last_id:
                        if os.path.exists(tsv):
                            self._extract_replies(tsv, cafe)
                            # 침투 게시글 파일도 드라이브 업로드
                            if mod_u and folder:
                                target_tsv = tsv.replace(".tsv", "_침투.tsv")
                                if os.path.exists(target_tsv):
                                    self._log_msg("침투 게시글 파일 구글 드라이브 업로드 중...", "info")
                                    link = mod_u.upload_tsv_to_drive(
                                        target_tsv, folder,
                                        base_dir=_BASE,
                                        log_fn=self._log_msg,
                                    )
                                    if link:
                                        self._log_msg(f"침투 파일 업로드 완료: {link}", "ok")
                        else:
                            self._log_msg(
                                f"TSV 파일 없음 (답글 추출 건너뜀): {tsv}", "err")

                except Exception as e:
                    self._log_msg(f"[오류] {cafe}: {e}", "err")
                    self._set_job_status(i, "오류")

            self._log_msg("\n전체 수집 완료", "ok")
            self._log_msg("=" * 52, "info")

        except Exception as e:
            self._log_msg(f"[치명적 오류] {e}", "err")
        finally:
            self._running = False
            self.after(0, self._on_done)

    def _on_done(self):
        self._run_btn.config(state=tk.NORMAL)
        self._stop_btn.config(state=tk.DISABLED)
        self._set_status("● 대기 중", "#95a5a6")

        if self._auto_var.get() and not self._stop_flag[0]:
            t = self._auto_time_var.get().strip()
            try:
                enabled = [True]
                self._timer = _스케줄.schedule_next_run(
                    t,
                    callback=self._start_crawl,
                    enabled_flag=enabled,
                    log_fn=self._log_msg,
                )
            except ValueError as e:
                self._log_msg(f"[오류] 자동 실행 시각 오류: {e}", "err")

    def _stop_crawl(self):
        self._stop_flag[0] = True
        if self._timer:
            _스케줄.cancel_timer(self._timer, log_fn=self._log_msg)
            self._timer = None
        self._log_msg("중지 요청됨...", "err")
        self._stop_btn.config(state=tk.DISABLED)

    # ── 모니터 체크 ───────────────────────────────────────────────────

    def _do_monitor_check(self):
        if self._running:
            messagebox.showinfo("알림", "수집 중에는 모니터 체크를 실행할 수 없습니다.")
            return
        self._log_msg("=" * 52, "info")
        self._log_msg("게시글 모니터 체크 시작", "info")
        self._set_status("● 모니터 체크 중...", "#8e44ad")

        def _run():
            try:
                mod_m = _load("08_모니터링.py")
                folder   = self._s.get("gs_folder_id", "")
                max_d    = int(self._s.get("monitor_max_daily", 2000))
                mod_m.run_daily_check(
                    base_dir  = _BASE,
                    folder_id = folder,
                    max_daily = max_d,
                    log_fn    = self._log_msg,
                )
            except Exception as e:
                self._log_msg(f"[오류] 모니터 체크 실패: {e}", "err")
            finally:
                self._set_status("● 대기 중", "#95a5a6")
                self._log_msg("모니터 체크 완료", "ok")
                self._log_msg("=" * 52, "info")

        threading.Thread(target=_run, daemon=True).start()

    def _toggle_auto(self):
        if not self._auto_var.get() and self._timer:
            _스케줄.cancel_timer(self._timer, log_fn=self._log_msg)
            self._timer = None

    # ── 업체목록 ──────────────────────────────────────────────────────

    def _auto_load_biz(self):
        biz_path = os.path.join(_BASE, "업체목록.txt")
        if os.path.exists(biz_path):
            self._do_load_biz(biz_path)
        else:
            self._log_msg("업체목록.txt 없음 → 업체여부 '해당없음' 처리", "info")

    def _on_load_biz(self):
        path = filedialog.askopenfilename(
            title="업체목록 파일 선택",
            initialdir=_BASE,
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")])
        if path:
            self._do_load_biz(path)

    def _on_load_biz_sheet(self):
        url = self._s.get("biz_sheet_url", "").strip()
        if not url:
            messagebox.showwarning(
                "알림",
                "구글 시트 URL이 설정되어 있지 않습니다.\n"
                "[기본 설정] → '업체목록 시트 URL' 에 입력하세요.")
            return
        self._log_msg("구글 시트에서 업체목록 로드 중...", "info")
        def _run():
            try:
                mod_u = _load("05_구글시트업로드.py")
                biz   = mod_u.load_biz_from_sheet(url, _BASE, log_fn=self._log_msg)
                self._biz_dict = biz
                count = len(biz)
                self._biz_lbl.config(text=f"업체: {count}개")
                self._log_msg(f"시트 로드 완료: {count}개", "ok")
            except Exception as e:
                self._log_msg(f"[오류] 시트 로드 실패: {e}", "err")
        threading.Thread(target=_run, daemon=True).start()

    def _do_load_biz(self, path: str):
        try:
            mod_c = _load("03_게시글수집.py")
            self._biz_dict = mod_c.load_biz_dict(path)
            count = len(self._biz_dict)
            self._log_msg(f"업체목록 로드 완료: {count}개 ({path})", "ok")
            self._biz_lbl.config(text=f"업체: {count}개")
        except Exception as e:
            self._log_msg(f"[오류] 업체목록 로드 실패: {e}", "err")

    # ── 답글 추출 ─────────────────────────────────────────────────────

    def _extract_replies(self, tsv_path: str, cafe_name: str):
        """TSV에서 답글이거나 업체가 작성한 행을 추려 _침투.tsv로 저장합니다."""
        import csv
        try:
            with open(tsv_path, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f, delimiter="\t"))

            if not rows:
                return

            header = rows[0]
            try:
                reply_col = header.index("답글여부")
            except ValueError:
                self._log_msg(
                    f"[경고] {cafe_name}: '답글여부' 컬럼 없음 → 추출 건너뜀", "err")
                return

            try:
                biz_col = header.index("업체여부")
            except ValueError:
                biz_col = None

            target_rows = []
            for row in rows[1:]:
                is_reply = len(row) > reply_col and row[reply_col] == "답글"
                is_biz   = (biz_col is not None
                            and len(row) > biz_col
                            and row[biz_col] not in ("해당없음", "없음", ""))
                if is_reply or is_biz:
                    target_rows.append(row)

            if not target_rows:
                self._log_msg(f"{cafe_name}: 침투 게시글 없음", "info")
                return

            out_path = tsv_path.replace(".tsv", "_침투.tsv")
            with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
                w.writerow(header)
                w.writerows(target_rows)

            self._log_msg(
                f"침투 게시글 추출 완료: {len(target_rows)}개 → {os.path.basename(out_path)}", "ok")

        except Exception as e:
            self._log_msg(f"[오류] 침투 게시글 추출 실패: {e}", "err")

    def _set_job_status(self, idx, status):
        try:
            self._s["jobs"][idx]["status"] = status
            self.after(0, self._refresh_jobs)
        except Exception:
            pass

    # ── 유틸 ──────────────────────────────────────────────────────────

    def _log_msg(self, msg: str, tag: str = "plain"):
        import datetime
        ts  = datetime.datetime.now().strftime("%H:%M:%S")
        txt = f"[{ts}] {msg}\n"

        def _write():
            self._log.config(state=tk.NORMAL)
            self._log.insert(tk.END, txt, tag)
            self._log.see(tk.END)
            self._log.config(state=tk.DISABLED)

        self.after(0, _write)

    def _set_status(self, text, color="#95a5a6"):
        self.after(0, lambda: self._status_lbl.config(text=text, fg=color))

    def _on_close(self):
        if self._running:
            if not messagebox.askyesno(
                    "종료 확인", "수집 중입니다. 정말 종료하시겠습니까?"):
                return
            self._stop_flag[0] = True
        if self._timer:
            self._timer.cancel()
        self.destroy()


# ══════════════════════════════════════════════════════════════════════
#  기본 설정 다이얼로그
# ══════════════════════════════════════════════════════════════════════

class SettingsDialog(tk.Toplevel):

    def __init__(self, parent, settings, on_save):
        super().__init__(parent)
        self.title("기본 설정")
        self.grab_set()
        self.resizable(False, False)
        self._cb = on_save

        def section(label):
            tk.Label(self, text=label, anchor="w",
                     fg="#2c3e50", font=("", 9, "bold")).pack(
                         fill=tk.X, padx=12, pady=(12, 0))
            ttk.Separator(self).pack(fill=tk.X, padx=12, pady=(2, 0))

        def field(label, var, show=""):
            f = tk.Frame(self)
            f.pack(fill=tk.X, padx=12, pady=4)
            tk.Label(f, text=label, width=24,
                     anchor="w").pack(side=tk.LEFT)
            tk.Entry(f, textvariable=var, width=40,
                     show=show).pack(side=tk.LEFT)

        self._nid   = tk.StringVar(value=settings.get("naver_id", ""))
        self._npw   = tk.StringVar(value=settings.get("naver_pw", ""))
        self._fid   = tk.StringVar(value=settings.get("gs_folder_id", ""))
        self._bsurl = tk.StringVar(value=settings.get("biz_sheet_url", ""))
        self._mmis  = tk.StringVar(value=settings.get("max_missing", "100"))
        self._atime = tk.StringVar(value=settings.get("auto_time", "09:00"))
        self._mmax  = tk.StringVar(value=settings.get("monitor_max_daily", "2000"))

        section("[ 네이버 계정 ]")
        field("아이디", self._nid)
        field("비밀번호", self._npw, show="*")

        section("[ 구글 드라이브 ]")
        field("폴더 URL 또는 ID", self._fid)
        field("업체목록 시트 URL", self._bsurl)

        section("[ 수집 옵션 ]")
        field("연속 빈 글 허용 수", self._mmis)
        field("자동 실행 시각 (HH:MM)", self._atime)

        section("[ 모니터링 옵션 ]")
        field("하루 최대 모니터 체크 건수", self._mmax)

        tk.Button(
            self, text="저장", width=14, bg="#2980b9", fg="white",
            activebackground="#3498db", relief=tk.FLAT, cursor="hand2",
            command=self._save).pack(pady=14)

        self.transient(parent)
        self.geometry(
            f"+{parent.winfo_x()+80}+{parent.winfo_y()+60}")

    def _save(self):
        self._cb({
            "naver_id":           self._nid.get().strip(),
            "naver_pw":           self._npw.get().strip(),
            "gs_folder_id":       self._fid.get().strip(),
            "biz_sheet_url":      self._bsurl.get().strip(),
            "max_missing":        self._mmis.get().strip() or "100",
            "auto_time":          self._atime.get().strip() or "09:00",
            "monitor_max_daily":  self._mmax.get().strip() or "2000",
        })
        self.destroy()


# ══════════════════════════════════════════════════════════════════════
#  작업 추가/편집 다이얼로그
# ══════════════════════════════════════════════════════════════════════

class JobDialog(tk.Toplevel):

    def __init__(self, parent, title, on_save, initial=None):
        super().__init__(parent)
        self.title(title)
        self.grab_set()
        self.resizable(False, False)
        self._cb = on_save

        fields = [
            ("카페 주소명 (예: gimhaezumma)",   "cafe_name", ""),
            ("카페 ID (숫자, 예: 21031223)",    "cafe_id",   ""),
            ("시작 게시글 번호",                 "start_id",  "1"),
            ("종료 번호 (빈 칸 = 끝까지)",       "end_id",    ""),
        ]
        self._vars = {}

        for label, key, default in fields:
            f = tk.Frame(self)
            f.pack(fill=tk.X, padx=14, pady=5)
            tk.Label(f, text=label, width=28, anchor="w").pack(side=tk.LEFT)
            val = initial.get(key, default) if initial else default
            v   = tk.StringVar(value=val)
            tk.Entry(f, textvariable=v, width=28).pack(side=tk.LEFT)
            self._vars[key] = v

        fc = tk.Frame(self)
        fc.pack(fill=tk.X, padx=14, pady=(2, 8))
        self._extract_var = tk.BooleanVar(
            value=bool(initial.get("extract_replies", False)) if initial else False)
        tk.Checkbutton(
            fc,
            text="침투 게시글 추출  (답글 + 업체 게시글 → 크롤링 후 _침투.tsv 자동 생성)",
            variable=self._extract_var,
            anchor="w",
        ).pack(side=tk.LEFT)

        tk.Button(
            self, text="저장", width=14, bg="#2980b9", fg="white",
            activebackground="#3498db", relief=tk.FLAT, cursor="hand2",
            command=self._save).pack(pady=12)

        self.transient(parent)
        self.geometry(
            f"+{parent.winfo_x()+100}+{parent.winfo_y()+80}")

    def _save(self):
        d = {k: v.get().strip() for k, v in self._vars.items()}
        d["extract_replies"] = self._extract_var.get()
        self._cb(d)
        self.destroy()


# ── 진입점 ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
