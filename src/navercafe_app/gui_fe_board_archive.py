from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from navercafe_app.auth.naver_session import NaverSessionManager, cookies_to_session
from navercafe_app.crawlers.fe_board_archive import archive_board, parse_board_url

DEFAULT_URL = "https://cafe.naver.com/f-e/cafes/14793916/menus/1556?viewType=L"
DEFAULT_PRESET_PATH = Path("data/fe_board_archive_presets.json")
DEFAULT_COOKIE_PATH = Path("data/session/naver_cookies.json")


class PresetStore:
    """JSON-backed GUI presets for non-developers who reuse the desktop program."""

    def __init__(self, path: str | Path = DEFAULT_PRESET_PATH):
        self.path = Path(path)

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        presets = data.get("presets", data) if isinstance(data, dict) else data
        return [item for item in presets if isinstance(item, dict) and item.get("name")]

    def save(self, presets: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"presets": presets}, ensure_ascii=False, indent=2), encoding="utf-8")

    def upsert(self, preset: dict[str, Any]) -> list[dict[str, Any]]:
        presets = [item for item in self.load() if item.get("name") != preset.get("name")]
        presets.append(preset)
        presets.sort(key=lambda item: str(item.get("name", "")))
        self.save(presets)
        return presets


class FeBoardArchiveApp(tk.Tk):
    """Desktop GUI wrapper for the Naver Cafe f-e board archive crawler."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Naver Cafe 게시판 아카이브")
        self.geometry("1050x760")
        self.resizable(True, True)
        self.messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.preset_store = PresetStore()
        self.presets: list[dict[str, Any]] = self.preset_store.load()
        self._build_ui()
        self._refresh_preset_names()
        self.after(200, self._drain_messages)
        self.after(400, self._check_login_status_async)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="프리셋").grid(row=0, column=0, sticky="w", pady=4)
        preset_row = ttk.Frame(frame)
        preset_row.grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)
        preset_row.columnconfigure(0, weight=1)
        self.preset_var = tk.StringVar(value="")
        self.preset_combo = ttk.Combobox(preset_row, textvariable=self.preset_var, state="readonly")
        self.preset_combo.grid(row=0, column=0, sticky="ew")
        ttk.Button(preset_row, text="불러오기", command=self._load_selected_preset).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(preset_row, text="현재값 저장", command=self._save_current_preset).grid(row=0, column=2, padx=(8, 0))

        ttk.Label(frame, text="게시판 URL").grid(row=1, column=0, sticky="w", pady=4)
        self.url_var = tk.StringVar(value=DEFAULT_URL)
        ttk.Entry(frame, textvariable=self.url_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(frame, text="게시판 이름").grid(row=2, column=0, sticky="w", pady=4)
        self.board_name_var = tk.StringVar(value="줌슐랭_리스트")
        ttk.Entry(frame, textvariable=self.board_name_var).grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="저장 폴더").grid(row=3, column=0, sticky="w", pady=4)
        self.output_var = tk.StringVar(value=str(Path.cwd() / "output" / "naver_cafe_archive"))
        ttk.Entry(frame, textvariable=self.output_var).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="찾기", command=self._browse_output).grid(row=3, column=2, sticky="ew", padx=(8, 0), pady=4)

        session_box = ttk.LabelFrame(frame, text="로그인/세션", padding=10)
        session_box.grid(row=4, column=0, columnspan=3, sticky="ew", pady=8)
        session_box.columnconfigure(1, weight=1)
        ttk.Label(session_box, text="상태").grid(row=0, column=0, sticky="w")
        self.login_status_var = tk.StringVar(value="확인 전")
        ttk.Label(session_box, textvariable=self.login_status_var).grid(row=0, column=1, sticky="w")
        ttk.Button(session_box, text="로그인 상태 확인", command=self._check_login_status_async).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(session_box, text="쿠키 삭제", command=self._clear_cookies).grid(row=0, column=3, padx=(8, 0))
        ttk.Button(session_box, text="로그인 갱신", command=self._refresh_login_async).grid(row=0, column=4, padx=(8, 0))

        options = ttk.LabelFrame(frame, text="실행 옵션", padding=10)
        options.grid(row=5, column=0, columnspan=3, sticky="ew", pady=8)
        for i in range(6):
            options.columnconfigure(i, weight=1)

        ttk.Label(options, text="시작 페이지").grid(row=0, column=0, sticky="w")
        self.start_page_var = tk.StringVar(value="1")
        ttk.Entry(options, textvariable=self.start_page_var, width=8).grid(row=0, column=1, sticky="w")

        ttk.Label(options, text="끝 페이지(선택)").grid(row=0, column=2, sticky="w")
        self.end_page_var = tk.StringVar(value="")
        ttk.Entry(options, textvariable=self.end_page_var, width=8).grid(row=0, column=3, sticky="w")

        ttk.Label(options, text="최대 글 수(선택)").grid(row=0, column=4, sticky="w")
        self.limit_var = tk.StringVar(value="")
        ttk.Entry(options, textvariable=self.limit_var, width=8).grid(row=0, column=5, sticky="w")

        self.list_only_var = tk.BooleanVar(value=True)
        self.download_images_var = tk.BooleanVar(value=True)
        self.force_login_var = tk.BooleanVar(value=False)
        self.headless_var = tk.BooleanVar(value=False)
        self.overwrite_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(options, text="목록만 테스트", variable=self.list_only_var).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="사진 다운로드", variable=self.download_images_var).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="로그인 강제 갱신", variable=self.force_login_var).grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="로그인 창 숨김", variable=self.headless_var).grid(row=1, column=3, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="기존 글 덮어쓰기", variable=self.overwrite_var).grid(row=1, column=4, sticky="w", pady=(8, 0))

        ttk.Label(options, text="요청 간격(초)").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.delay_var = tk.StringVar(value="1.0")
        ttk.Entry(options, textvariable=self.delay_var, width=8).grid(row=2, column=1, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=3, sticky="ew", pady=8)
        self.run_btn = ttk.Button(buttons, text="수집 시작", command=self._start)
        self.run_btn.pack(side=tk.LEFT)
        ttk.Button(buttons, text="목록만 빠른 테스트", command=self._quick_list_test).pack(side=tk.LEFT, padx=8)
        ttk.Button(buttons, text="저장 폴더 열기", command=self._open_output_folder).pack(side=tk.LEFT, padx=8)

        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=7, column=0, columnspan=3, sticky="ew", pady=4)

        pane = ttk.PanedWindow(frame, orient=tk.VERTICAL)
        pane.grid(row=8, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
        frame.rowconfigure(8, weight=1)

        result_frame = ttk.LabelFrame(pane, text="결과 표", padding=6)
        columns = ("status", "article_id", "title", "images", "error")
        self.result_tree = ttk.Treeview(result_frame, columns=columns, show="headings", height=8)
        for col, title, width in [
            ("status", "상태", 90),
            ("article_id", "글ID", 100),
            ("title", "제목", 360),
            ("images", "사진", 80),
            ("error", "오류", 360),
        ]:
            self.result_tree.heading(col, text=title)
            self.result_tree.column(col, width=width, anchor=tk.W)
        self.result_tree.pack(fill=tk.BOTH, expand=True)
        pane.add(result_frame, weight=1)

        log_frame = ttk.LabelFrame(pane, text="실행 로그", padding=6)
        self.log = tk.Text(log_frame, height=12, wrap="word")
        self.log.pack(fill=tk.BOTH, expand=True)
        pane.add(log_frame, weight=1)

    def _browse_output(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_var.get() or str(Path.cwd()))
        if selected:
            self.output_var.set(selected)

    def _open_output_folder(self) -> None:
        path = Path(self.output_var.get())
        path.mkdir(parents=True, exist_ok=True)
        try:
            import os

            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("폴더 열기 실패", str(exc))

    def _quick_list_test(self) -> None:
        self.list_only_var.set(True)
        self._start()

    def _parse_optional_int(self, value: str) -> int | None:
        value = value.strip()
        return int(value) if value else None

    def _current_preset(self) -> dict[str, Any]:
        name = self.board_name_var.get().strip() or "새 프리셋"
        return {
            "name": name,
            "url": self.url_var.get().strip(),
            "board_name": self.board_name_var.get().strip(),
            "output": self.output_var.get().strip(),
            "start_page": self.start_page_var.get().strip(),
            "end_page": self.end_page_var.get().strip(),
            "limit": self.limit_var.get().strip(),
            "delay": self.delay_var.get().strip(),
            "download_images": self.download_images_var.get(),
            "headless": self.headless_var.get(),
        }

    def _refresh_preset_names(self) -> None:
        names = [str(item.get("name")) for item in self.presets]
        self.preset_combo.configure(values=names)
        if names and not self.preset_var.get():
            self.preset_var.set(names[0])

    def _save_current_preset(self) -> None:
        try:
            parse_board_url(self.url_var.get().strip())
        except Exception as exc:
            messagebox.showerror("프리셋 저장 오류", str(exc))
            return
        self.presets = self.preset_store.upsert(self._current_preset())
        self._refresh_preset_names()
        self.preset_var.set(self.board_name_var.get().strip() or "새 프리셋")
        self._log(f"프리셋 저장: {self.preset_var.get()}")

    def _load_selected_preset(self) -> None:
        selected = self.preset_var.get()
        preset = next((item for item in self.presets if item.get("name") == selected), None)
        if not preset:
            return
        self.url_var.set(str(preset.get("url", DEFAULT_URL)))
        self.board_name_var.set(str(preset.get("board_name", selected)))
        self.output_var.set(str(preset.get("output", self.output_var.get())))
        self.start_page_var.set(str(preset.get("start_page", "1")))
        self.end_page_var.set(str(preset.get("end_page", "")))
        self.limit_var.set(str(preset.get("limit", "")))
        self.delay_var.set(str(preset.get("delay", "1.0")))
        self.download_images_var.set(bool(preset.get("download_images", True)))
        self.headless_var.set(bool(preset.get("headless", False)))
        self._log(f"프리셋 불러오기: {selected}")

    def _manager(self) -> NaverSessionManager:
        return NaverSessionManager(env_path=".env")

    def _check_login_status_async(self) -> None:
        threading.Thread(target=self._check_login_status_worker, daemon=True).start()

    def _check_login_status_worker(self) -> None:
        try:
            manager = self._manager()
            cookies = manager.session_store.load_cookies()
            if not cookies:
                self.messages.put(("status", "저장된 로그인 쿠키 없음"))
                return
            session = cookies_to_session(cookies, manager.user_agent)
            valid = manager.validate_session(session)
            message = f"저장 쿠키 {'유효' if valid else '만료/확인 필요'} ({len(cookies)}개)"
            self.messages.put(("status", message))
        except Exception as exc:
            self.messages.put(("status", f"확인 실패: {exc}"))

    def _clear_cookies(self) -> None:
        if not messagebox.askyesno("쿠키 삭제", "저장된 네이버 로그인 쿠키를 삭제할까요?"):
            return
        try:
            store = self._manager().session_store
            store.clear()
            self.login_status_var.set("저장된 로그인 쿠키 없음")
            self._log(f"쿠키 삭제 완료: {store.path}")
        except Exception as exc:
            messagebox.showerror("쿠키 삭제 실패", str(exc))

    def _refresh_login_async(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("실행 중", "수집 작업 중에는 로그인 갱신을 시작할 수 없습니다.")
            return
        self.run_btn.configure(state=tk.DISABLED)
        self.progress.start(10)
        threading.Thread(target=self._refresh_login_worker, daemon=True).start()

    def _refresh_login_worker(self) -> None:
        try:
            self._log("로그인 갱신을 시작합니다. 필요한 경우 열린 Chrome에서 CAPTCHA/2FA를 직접 완료하세요.")
            state = self._manager().ensure_login(force_login=True, headless=self.headless_var.get())
            self.messages.put(("status", f"{state.source}: {state.message}"))
        except Exception as exc:
            self.messages.put(("log", f"로그인 갱신 실패: {exc}"))
            self.messages.put(("status", f"로그인 갱신 실패: {exc}"))
        finally:
            self.messages.put(("done", None))

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("실행 중", "이미 수집 작업이 실행 중입니다.")
            return
        try:
            parse_board_url(self.url_var.get().strip())
            int(self.start_page_var.get())
            self._parse_optional_int(self.end_page_var.get())
            self._parse_optional_int(self.limit_var.get())
            float(self.delay_var.get())
        except Exception as exc:
            messagebox.showerror("입력 오류", str(exc))
            return
        self.log.delete("1.0", tk.END)
        for row in self.result_tree.get_children():
            self.result_tree.delete(row)
        self.run_btn.configure(state=tk.DISABLED)
        self.progress.start(10)
        self.worker = threading.Thread(target=self._run_worker, daemon=True)
        self.worker.start()

    def _run_worker(self) -> None:
        try:
            target = parse_board_url(self.url_var.get().strip())
            self._log(f"대상: cafe_id={target.cafe_id}, menu_id={target.menu_id}")
            session = None
            if not self.list_only_var.get():
                self._log("로그인 세션을 확인합니다. CAPTCHA/2FA가 있으면 열린 브라우저에서 직접 처리하세요.")
                session = self._manager().get_requests_session(
                    force_login=self.force_login_var.get(),
                    headless=self.headless_var.get(),
                )
            results = archive_board(
                target=target,
                output_dir=self.output_var.get(),
                session=session,
                board_name=self.board_name_var.get().strip() or "board",
                start_page=int(self.start_page_var.get()),
                end_page=self._parse_optional_int(self.end_page_var.get()),
                limit=self._parse_optional_int(self.limit_var.get()),
                delay=float(self.delay_var.get()),
                download_images=self.download_images_var.get(),
                details=not self.list_only_var.get(),
                skip_existing=not self.overwrite_var.get(),
            )
            self.messages.put(("results", [asdict(result) for result in results]))
            list_only = sum(1 for item in results if item.status == "list_only")
            ok = sum(1 for item in results if item.status == "ok")
            skipped = sum(1 for item in results if item.status == "skipped")
            errors = [item for item in results if item.status == "error"]
            self._log(f"완료: list_only={list_only}, ok={ok}, skipped={skipped}, error={len(errors)}")
            if self.list_only_var.get():
                self._log("본문/사진까지 받으려면 '목록만 테스트' 체크를 끄고 실행하세요.")
            for err in errors[:10]:
                self._log(f"실패: {err.article_id} {err.title} - {err.error}")
            self._log(f"저장 위치: {self.output_var.get()}")
        except Exception as exc:
            self._log(f"오류: {exc}")
        finally:
            self.messages.put(("done", None))

    def _log(self, text: str) -> None:
        self.messages.put(("log", text))

    def _show_results(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            images = f"{row.get('images_downloaded', 0)}/{row.get('images_total', 0)}"
            self.result_tree.insert(
                "",
                tk.END,
                values=(
                    row.get("status", ""),
                    row.get("article_id", ""),
                    row.get("title", ""),
                    images,
                    row.get("error", ""),
                ),
            )

    def _drain_messages(self) -> None:
        while True:
            try:
                msg_type, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            if msg_type == "done":
                self.progress.stop()
                self.run_btn.configure(state=tk.NORMAL)
            elif msg_type == "status":
                self.login_status_var.set(str(payload))
            elif msg_type == "results":
                self._show_results(payload)
            else:
                self.log.insert(tk.END, str(payload) + "\n")
                self.log.see(tk.END)
        self.after(200, self._drain_messages)


def main() -> None:
    app = FeBoardArchiveApp()
    app.mainloop()


if __name__ == "__main__":
    main()
