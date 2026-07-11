"""
Tkinter 授权窗口 — 试用倒计时 / 授权码激活 / 状态显示

在 EXE 启动时弹出，验证通过后关闭，主程序继续。
"""
import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

import license as lic

# ── 颜色 ──
BG = "#1a1a2e"
FG = "#e0e0e0"
ACCENT = "#e94560"
ACCENT_HOVER = "#ff6b81"
SECONDARY = "#16213e"
TEXT_SECONDARY = "#a0a0a0"
SUCCESS = "#2ecc71"
WARNING = "#f39c12"


def _center(win, w, h):
    """窗口居中"""
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")


def _make_button(parent, text, command, bg=ACCENT, fg="#fff", width=100):
    """自定义按钮（因 ttk 样式有限，用 tk.Frame + Label 模拟）
    返回对象支持 .configure(state=...) 以便运行时禁用。
    """
    import tkinter as tk

    frame = tk.Frame(parent, bg=bg, width=width, height=38, cursor="hand2")
    frame.pack_propagate(False)
    label = tk.Label(frame, text=text, bg=bg, fg=fg, font=("微软雅黑", 12, "bold"))
    label.pack(expand=True, fill="both")

    def on_enter(e):
        if _btn.enabled:
            frame.configure(bg=ACCENT_HOVER)
            label.configure(bg=ACCENT_HOVER)

    def on_leave(e):
        if _btn.enabled:
            frame.configure(bg=bg)
            label.configure(bg=bg)

    def on_click(e):
        if _btn.enabled:
            command()

    frame.bind("<Enter>", on_enter)
    frame.bind("<Leave>", on_leave)
    frame.bind("<Button-1>", on_click)
    label.bind("<Button-1>", on_click)

    class _ButtonWrapper:
        def __init__(self):
            self.enabled = True

        def configure(self, **kwargs):
            if "state" in kwargs:
                self.enabled = kwargs.pop("state") != "disabled"
                if self.enabled:
                    frame.configure(cursor="hand2", bg=bg)
                    label.configure(fg=fg, bg=bg)
                else:
                    frame.configure(cursor="", bg=TEXT_SECONDARY)
                    label.configure(fg=TEXT_SECONDARY, bg=TEXT_SECONDARY)
            if "text" in kwargs:
                label.configure(text=kwargs.pop("text"))
            if kwargs:
                try:
                    frame.configure(**kwargs)
                except tk.TclError:
                    pass

        def pack(self, **kwargs):
            frame.pack(**kwargs)

        def __getattr__(self, name):
            return getattr(frame, name)

    _btn = _ButtonWrapper()
    return _btn


def _create_entry(parent, placeholder="", width=30, show=""):
    """带占位符的输入框"""
    var = tk.StringVar()
    entry = tk.Entry(
        parent,
        textvariable=var,
        font=("Consolas", 12),
        bg=SECONDARY,
        fg=FG,
        insertbackground=FG,
        relief="flat",
        bd=8,
        width=width,
        show=show,
        disabledforeground=TEXT_SECONDARY,
    )
    entry.var = var

    # 占位符
    if placeholder:
        entry.insert(0, placeholder)
        entry.bind("<FocusIn>", lambda e: (
            entry.delete(0, "end") if entry.get() == placeholder else None
        ))

    return entry


class AuthWindow:
    """授权窗口"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("海龟汤 · 授权")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        _center(self.root, 480, 430)

        # 确保窗口显示在最前面
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.focus_force()
        self.root.after(100, lambda: self.root.attributes('-topmost', False))

        self.result = None  # 最终结果
        self._trial_timer_id = None

        self._build_ui()
        self._check_initial_state()

        # 关闭窗口 = 退出程序
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        root = self.root

        # ── 标题 ──
        title_frame = tk.Frame(root, bg=BG)
        title_frame.pack(fill="x", padx=30, pady=(30, 5))

        tk.Label(
            title_frame,
            text="海龟汤控制面板",
            font=("微软雅黑", 18, "bold"),
            bg=BG,
            fg=FG,
        ).pack()

        tk.Label(
            title_frame,
            text="直播互动工具",
            font=("微软雅黑", 10),
            bg=BG,
            fg=TEXT_SECONDARY,
        ).pack()

        # ── 状态区域 ──
        self.status_frame = tk.Frame(root, bg=BG)
        self.status_frame.pack(fill="both", padx=30, pady=(10, 0), expand=True)

        self.status_label = tk.Label(
            self.status_frame,
            text="正在检查授权...",
            font=("微软雅黑", 10),
            bg=BG,
            fg=TEXT_SECONDARY,
            wraplength=420,
            justify="center",
        )
        self.status_label.pack(expand=True)

        # ── 机器码 ──
        mc_frame = tk.Frame(root, bg=BG)
        mc_frame.pack(fill="x", padx=30, pady=(0, 2))

        tk.Label(
            mc_frame,
            text="机器码",
            font=("微软雅黑", 9),
            bg=BG, fg=TEXT_SECONDARY,
        ).pack(anchor="w")

        mc_row = tk.Frame(mc_frame, bg=BG)
        mc_row.pack(fill="x", pady=(2, 0))

        self.mc_label = tk.Label(
            mc_row,
            text=lic.get_machine_id(),
            font=("Consolas", 10),
            bg=BG, fg=FG,
        )
        self.mc_label.pack(side="left")

        self.copy_mc_btn = tk.Label(
            mc_row,
            text="复制",
            font=("微软雅黑", 9),
            bg=BG, fg=ACCENT, cursor="hand2",
        )
        self.copy_mc_btn.pack(side="left", padx=(8, 0))
        self.copy_mc_btn.bind("<Button-1>", lambda e: self._copy_machine_code())
        self.mc_label.bind("<Button-1>", lambda e: self._copy_machine_code())
        self.mc_label.configure(cursor="hand2")

        # ── 授权码输入 ──
        input_frame = tk.Frame(root, bg=BG)
        input_frame.pack(fill="x", padx=30, pady=(5, 5))

        tk.Label(
            input_frame,
            text="授权码",
            font=("微软雅黑", 10),
            bg=BG,
            fg=TEXT_SECONDARY,
        ).pack(anchor="w")

        entry_row = tk.Frame(input_frame, bg=BG)
        entry_row.pack(fill="x", pady=(4, 0))

        self.key_entry = _create_entry(entry_row, "LIC-XXXXXXXX-XXXXXXXX-XXXXXXXX", width=26)
        self.key_entry.pack(side="left")
        # 回车触发激活
        self.key_entry.bind("<Return>", lambda e: self._activate())

        self.activate_btn = _make_button(
            entry_row, "激活", self._activate, bg=ACCENT, width=80
        )
        self.activate_btn.pack(side="left", padx=(8, 0))

        # ── 底部按钮 ──
        bottom_frame = tk.Frame(root, bg=BG)
        bottom_frame.pack(fill="x", padx=30, pady=(5, 25))

        self.trial_btn = _make_button(
            bottom_frame, "免费试用 5 小时", self._start_trial, bg=SECONDARY, width=140
        )
        self.trial_btn.pack(side="left")

        # 购买按钮（仅信息展示）
        self.buy_btn = tk.Label(
            bottom_frame,
            text="购买授权",
            font=("微软雅黑", 10),
            bg=BG,
            fg=ACCENT,
            cursor="hand2",
        )
        self.buy_btn.pack(side="right", padx=(0, 5))
        self.buy_btn.bind("<Button-1>", lambda e: self._show_purchase_info())

    def _check_initial_state(self):
        """检查授权状态，更新 UI"""
        status = lic.check()
        if status.get("ok"):
            # 已有有效授权，直接通过
            msg = (
                f"已有有效授权（{status.get('source')}）"
                if status.get("source") == "license"
                else f"试用剩余 {lic.format_remaining(status['remaining_seconds'])}"
            )
            self.status_label.configure(text=msg, fg=SUCCESS)
            auto_close = status.get("source") == "license"
            if auto_close:
                # 已有授权码 → 自动通过
                self.root.after(800, self._on_ok)
            else:
                # 试用中 → 显示倒计时
                self._show_trial_countdown(status["remaining_seconds"])
        elif status.get("reason") == "trial_expired":
            self.status_label.configure(text="免费试用已结束，点击下方按钮可重置", fg=WARNING)
            self.trial_btn.configure(text="重新试用 5 小时")
        elif status.get("reason") == "trial_not_started":
            self.status_label.configure(text="欢迎使用！可免费试用 5 小时", fg=TEXT_SECONDARY)
        elif status.get("reason") == "license_expired":
            self.status_label.configure(text="授权码已过期，请购买新授权", fg=WARNING)

    def _show_trial_countdown(self, remaining: int):
        """显示试用倒计时（每秒更新）"""
        self.status_label.configure(
            text=f"试用剩余 {lic.format_remaining(remaining)}",
            fg=SUCCESS,
        )
        if remaining > 0:
            self._trial_timer_id = self.root.after(
                1000, lambda: self._tick_trial(remaining - 1)
            )

    def _tick_trial(self, remaining: int):
        if remaining <= 0:
            self.status_label.configure(text="免费试用已结束", fg=WARNING)
            self.trial_btn.configure(state="disabled")
            self.trial_btn.config(bg=TEXT_SECONDARY)
            return

        # 每 30 秒重新从文件读取（避免界面冻结）
        if remaining % 30 == 0:
            status = lic.check()
            if status.get("ok") and status.get("source") == "trial":
                remaining = status["remaining_seconds"]

        self.status_label.configure(
            text=f"试用剩余 {lic.format_remaining(remaining)}",
            fg=SUCCESS,
        )
        self._trial_timer_id = self.root.after(1000, lambda: self._tick_trial(remaining - 1))

    def _copy_machine_code(self):
        """复制机器码到剪贴板"""
        mc = lic.get_machine_id()
        self.root.clipboard_clear()
        self.root.clipboard_append(mc)
        self.status_label.configure(text="机器码已复制，请发送给作者", fg=SUCCESS)

    def _start_trial(self):
        """点击「免费试用」"""
        lic.start_trial()
        status = lic.check()
        if status.get("ok"):
            self.status_label.configure(text="已开启免费试用！", fg=SUCCESS)
            self.root.after(500, self._on_ok)
        else:
            self.status_label.configure(text="启动试用失败，请重试", fg=ACCENT)

    def _activate(self):
        """尝试激活授权码"""
        key = self.key_entry.var.get().strip()
        if not key or key == "LIC-XXXXXXXX-XXXXXXXX-XXXXXXXX":
            self.status_label.configure(text="请输入授权码", fg=ACCENT)
            return

        result = lic.activate(key)
        if result.get("ok"):
            self.status_label.configure(
                text="激活成功！" + (
                    " 永久授权" if result.get("is_permanent")
                    else f" 有效期 {result.get('remaining_days', 0)} 天"
                ),
                fg=SUCCESS,
            )
            self.root.after(500, self._on_ok)
        else:
            self.status_label.configure(text=result.get("error", "激活失败"), fg=ACCENT)

    def _show_purchase_info(self):
        messagebox.showinfo(
            "购买授权",
            "请联系作者获取授权码\n\n"
            "授权类型:\n"
            "  • 7 天      — 体验版\n"
            "  • 30 天     — 标准版\n"
            "  • 365 天    — 年度版\n"
            "  • 永久      — 终身版\n\n"
            "购买后请将机器码和授权类型发送给作者。\n"
            "机器码可在授权窗口底部查看并复制。",
        )

    def _on_ok(self):
        """授权通过，关闭窗口"""
        self.result = lic.check()
        self._cleanup()
        self.root.destroy()

    def _on_close(self):
        """用户关闭窗口 → 退出程序"""
        if messagebox.askokcancel("退出", "确定要退出吗？"):
            self._cleanup()
            self.root.destroy()
            sys.exit(0)

    def _cleanup(self):
        if self._trial_timer_id:
            self.root.after_cancel(self._trial_timer_id)
            self._trial_timer_id = None

    def run(self) -> dict | None:
        """运行授权窗口，返回状态信息（成功时）或 None（取消时）"""
        self.root.mainloop()
        return self.result


# ═══════════════════════════════════════════
# 快捷入口（供 admin_console / overlay 调用）
# ═══════════════════════════════════════════

def run_auth() -> dict | None:
    """
    运行授权检查流程：
    1. 如果已有有效授权 → 静默通过
    2. 否则弹出 Tkinter 窗口
    3. 用户取消 → sys.exit(0)
    返回: status dict (含 ok=True)
    """
    print("[Auth] 开始授权检查...", flush=True)
    # 先检查本地授权
    status = lic.check()
    print(f"[Auth] check() 返回: {status.get('ok')}, reason={status.get('reason')}", flush=True)
    if status.get("ok"):
        return status

    # 弹出授权窗口
    win = AuthWindow()
    result = win.run()
    if result is None:
        sys.exit(0)
    return result


if __name__ == "__main__":
    # 测试模式
    run_auth()
    print("授权通过，继续运行")
