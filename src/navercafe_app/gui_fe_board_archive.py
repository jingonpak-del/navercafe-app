from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from navercafe_app.crawlers.fe_board_archive import archive_board, parse_board_url
from navercafe_app.auth.naver_session import NaverSessionManager

DEFAULT_URL = "https://cafe.naver.com/f-e/cafes/14793916/menus/1556?viewType=L"


class FeBoardArchiveApp(tk.Tk):
    """Small desktop GUI wrapper for the Naver Cafe f-e board archive crawler."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Naver Cafe 게시판 아카이브")
        self.geometry("820x620")
        self.resizable(True, True)
        self.messages: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None
        self._build_ui()
        self.after(200, self._drain_messages)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="게시판 URL").grid(row=0, column=0, sticky="w", pady=4)
        self.url_var = tk.StringVar(value=DEFAULT_URL)
        ttk.Entry(frame, textvariable=self.url_var).grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(frame, text="게시판 이름").grid(row=1, column=0, sticky="w", pady=4)
        self.board_name_var = tk.StringVar(value="줌슐랭_리스트")
        ttk.Entry(frame, textvariable=self.board_name_var).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="저장 폴더").grid(row=2, column=0, sticky="w", pady=4)
        self.output_var = tk.StringVar(value=str(Path.cwd() / "output" / "naver_cafe_archive"))
        ttk.Entry(frame, textvariable=self.output_var).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="찾기", command=self._browse_output).grid(row=2, column=2, sticky="ew", padx=(8, 0), pady=4)

        options = ttk.LabelFrame(frame, text="실행 옵션", padding=10)
        options.grid(row=3, column=0, columnspan=3, sticky="ew", pady=8)
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
        buttons.grid(row=4, column=0, columnspan=3, sticky="ew", pady=8)
        self.run_btn = ttk.Button(buttons, text="수집 시작", command=self._start)
        self.run_btn.pack(side=tk.LEFT)
        ttk.Button(buttons, text="목록만 빠른 테스트", command=self._quick_list_test).pack(side=tk.LEFT, padx=8)

        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=5, column=0, columnspan=3, sticky="ew", pady=4)

        ttk.Label(frame, text="실행 로그").grid(row=6, column=0, sticky="w", pady=(10, 4))
        self.log = tk.Text(frame, height=20, wrap="word")
        self.log.grid(row=7, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(7, weight=1)

    def _browse_output(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_var.get() or str(Path.cwd()))
        if selected:
            self.output_var.set(selected)

    def _quick_list_test(self) -> None:
        self.list_only_var.set(True)
        self._start()

    def _parse_optional_int(self, value: str) -> int | None:
        value = value.strip()
        return int(value) if value else None

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
                session = NaverSessionManager(env_path=".env").get_requests_session(
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
            if self.list_only_var.get():
                list_only = sum(1 for item in results if item.status == "list_only")
                self._log(f"목록 저장 완료: {list_only}개. 본문/사진까지 받으려면 '목록만 테스트' 체크를 끄고 실행하세요.")
            else:
                list_only = sum(1 for item in results if item.status == "list_only")
                ok = sum(1 for item in results if item.status == "ok")
                skipped = sum(1 for item in results if item.status == "skipped")
                errors = [item for item in results if item.status == "error"]
                self._log(f"완료: list_only={list_only}, ok={ok}, skipped={skipped}, error={len(errors)}")
                for err in errors[:10]:
                    self._log(f"실패: {err.article_id} {err.title} - {err.error}")
            self._log(f"저장 위치: {self.output_var.get()}")
        except Exception as exc:
            self._log(f"오류: {exc}")
        finally:
            self.messages.put("__DONE__")

    def _log(self, text: str) -> None:
        self.messages.put(text)

    def _drain_messages(self) -> None:
        while True:
            try:
                msg = self.messages.get_nowait()
            except queue.Empty:
                break
            if msg == "__DONE__":
                self.progress.stop()
                self.run_btn.configure(state=tk.NORMAL)
                continue
            self.log.insert(tk.END, msg + "\n")
            self.log.see(tk.END)
        self.after(200, self._drain_messages)


def main() -> None:
    app = FeBoardArchiveApp()
    app.mainloop()


if __name__ == "__main__":
    main()
