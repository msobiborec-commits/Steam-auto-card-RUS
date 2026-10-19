"""
Steam Card Auto-Farmer & Drop Tracker: SecretBall Cyber Edition
A graphical application that automates Steam trading card farming via SAM emulation:
- Bypasses the 2-hour refund wait by idling all new games simultaneously in Phase 1.
- Automatically farms games 1-by-1 in Phase 2 with Close & Check cycles:
  closes game, checks for card drops, performs a 20-second control check if needed,
  restarts the game upon drop, and transitions to the next game when completed.
- Displays comprehensive session statistics, live progress, and time estimations.
- Features a stylish Cyber/SecretBall theme with custom wallpaper, mascot card, and neon HUD.
"""

import sys
import os
import time
import threading
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from steam_client import SteamClient
from farming_engine import FarmingEngine, GameItem, format_duration, find_sam_executable, cleanup_all_sam_processes
import theme_manager
from theme_manager import (
    BG_DARK, BG_CARD, BG_CARD_BORDER, BG_HOVER, BG_INPUT,
    TEXT_WHITE, TEXT_LIGHT, TEXT_MUTED,
    ACCENT_CYAN, COLOR_LIME, COLOR_GOLD, COLOR_RED, COLOR_PURPLE, COLOR_BLUE
)

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, engine):
        super().__init__(parent)
        self.engine = engine
        self.title("⚙ Настройки — SecretBall Edition")
        self.geometry("600x500")
        self.resizable(False, False)
        self.configure(bg=BG_DARK)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._center_window()

    def _center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        pad_opts = {'padx': 18, 'pady': 6}

        # SAM Path
        lbl_sam = tk.Label(self, text="Путь к SAM.Game.exe:", fg=ACCENT_CYAN, bg=BG_DARK, font=("Segoe UI", 9, "bold"))
        lbl_sam.pack(anchor="w", **pad_opts)

        sam_frame = tk.Frame(self, bg=BG_DARK)
        sam_frame.pack(fill="x", padx=18)

        self.sam_var = tk.StringVar(value=self.engine.sam_path)
        sam_entry = tk.Entry(sam_frame, textvariable=self.sam_var, bg=BG_INPUT, fg=TEXT_WHITE,
                             insertbackground=TEXT_WHITE, relief="flat", font=("Segoe UI", 9))
        sam_entry.pack(side="left", fill="x", expand=True, ipady=4)

        btn_browse = tk.Button(sam_frame, text="Обзор...", bg=BG_HOVER, fg=TEXT_WHITE, relief="flat",
                               activebackground=ACCENT_CYAN, command=self._browse_sam, cursor="hand2")
        btn_browse.pack(side="left", padx=(6, 4))

        btn_detect = tk.Button(sam_frame, text="Автопоиск", bg=BG_HOVER, fg=TEXT_LIGHT, relief="flat",
                               command=self._autodetect_sam, cursor="hand2")
        btn_detect.pack(side="left")

        # Boost 2 Hours Settings
        lbl_boost = tk.Label(self, text="⚡ Фаза 1: Разгон до 2 часов (параллельный запуск):", fg=COLOR_GOLD, bg=BG_DARK, font=("Segoe UI", 9, "bold"))
        lbl_boost.pack(anchor="w", padx=18, pady=(12, 4))

        self.boost_enabled_var = tk.BooleanVar(value=self.engine.boost_enabled)
        chk_boost = tk.Checkbutton(self, text="Включить одновременный разгон до 2 часов для новых игр",
                                   variable=self.boost_enabled_var, bg=BG_DARK, fg=TEXT_WHITE, selectcolor=BG_INPUT,
                                   activebackground=BG_DARK, activeforeground=TEXT_WHITE, font=("Segoe UI", 9))
        chk_boost.pack(anchor="w", padx=18)

        threshold_frame = tk.Frame(self, bg=BG_DARK)
        threshold_frame.pack(anchor="w", padx=18, pady=4)
        lbl_th = tk.Label(threshold_frame, text="Порог разгона (часов, ровно 2.0 ч. = 120 мин):", fg=TEXT_LIGHT, bg=BG_DARK, font=("Segoe UI", 9))
        lbl_th.pack(side="left")
        self.threshold_var = tk.DoubleVar(value=self.engine.boost_threshold_hours)
        th_spin = tk.Spinbox(threshold_frame, from_=1.0, to=4.0, increment=0.1, textvariable=self.threshold_var,
                             bg=BG_INPUT, fg=TEXT_WHITE, insertbackground=TEXT_WHITE, relief="flat", font=("Segoe UI", 9), width=8)
        th_spin.pack(side="left", padx=8)

        # Farming Cycle & Close/Check Settings
        lbl_cycle = tk.Label(self, text="🎮 Фаза 2: Цикл фарма и проверки дропа (Close & Check):", fg=COLOR_LIME, bg=BG_DARK, font=("Segoe UI", 9, "bold"))
        lbl_cycle.pack(anchor="w", padx=18, pady=(12, 4))

        cycle_frame = tk.Frame(self, bg=BG_DARK)
        cycle_frame.pack(anchor="w", padx=18, pady=4)
        lbl_c = tk.Label(cycle_frame, text="Длительность сессии игры до закрытия и проверки (мин):", fg=TEXT_LIGHT, bg=BG_DARK, font=("Segoe UI", 9))
        lbl_c.pack(side="left")
        self.cycle_var = tk.IntVar(value=self.engine.cycle_duration_min)
        cycle_spin = tk.Spinbox(cycle_frame, from_=5, to=60, increment=1, textvariable=self.cycle_var,
                                bg=BG_INPUT, fg=TEXT_WHITE, insertbackground=TEXT_WHITE, relief="flat", font=("Segoe UI", 9), width=8)
        cycle_spin.pack(side="left", padx=8)

        delay_frame = tk.Frame(self, bg=BG_DARK)
        delay_frame.pack(anchor="w", padx=18, pady=4)
        lbl_d = tk.Label(delay_frame, text="Задержка перед контрольной проверкой Steam (сек):", fg=TEXT_LIGHT, bg=BG_DARK, font=("Segoe UI", 9))
        lbl_d.pack(side="left")
        self.delay_var = tk.IntVar(value=self.engine.control_check_delay_sec)
        delay_spin = tk.Spinbox(delay_frame, from_=5, to=60, increment=5, textvariable=self.delay_var,
                                bg=BG_INPUT, fg=TEXT_WHITE, insertbackground=TEXT_WHITE, relief="flat", font=("Segoe UI", 9), width=8)
        delay_spin.pack(side="left", padx=8)

        # Process visibility
        self.hidden_var = tk.BooleanVar(value=self.engine.launch_hidden)
        chk_hidden = tk.Checkbutton(self, text="Запускать SAM в скрытом фоновом режиме (рекомендуется)",
                                    variable=self.hidden_var, bg=BG_DARK, fg=TEXT_WHITE, selectcolor=BG_INPUT,
                                    activebackground=BG_DARK, activeforeground=TEXT_WHITE, font=("Segoe UI", 9))
        chk_hidden.pack(anchor="w", padx=18, pady=(8, 12))

        # Action Buttons
        btn_frame = tk.Frame(self, bg=BG_DARK)
        btn_frame.pack(side="bottom", fill="x", padx=18, pady=14)

        btn_save = tk.Button(btn_frame, text="Сохранить настройки", bg=COLOR_LIME, fg="#000000", font=("Segoe UI", 9, "bold"),
                             relief="flat", cursor="hand2", padx=14, pady=6, command=self._save_settings)
        btn_save.pack(side="right", padx=4)

        btn_cancel = tk.Button(btn_frame, text="Отмена", bg=BG_HOVER, fg=TEXT_WHITE, font=("Segoe UI", 9),
                               relief="flat", cursor="hand2", padx=14, pady=6, command=self.destroy)
        btn_cancel.pack(side="right", padx=4)

    def _browse_sam(self):
        chosen = filedialog.askopenfilename(
            title="Выберите SAM.Game.exe",
            filetypes=[("SAM.Game executable", "SAM.Game.exe"), ("Executable", "*.exe"), ("All files", "*.*")]
        )
        if chosen:
            self.sam_var.set(chosen)

    def _autodetect_sam(self):
        detected = find_sam_executable()
        if detected:
            self.sam_var.set(detected)
            messagebox.showinfo("Автопоиск", f"SAM.Game.exe успешно найден:\n{detected}")
        else:
            messagebox.showwarning("Автопоиск", "Не удалось автоматически найти SAM.Game.exe. Укажите путь вручную.")

    def _save_settings(self):
        self.engine.sam_path = self.sam_var.get().strip()
        self.engine.boost_enabled = self.boost_enabled_var.get()
        self.engine.boost_threshold_hours = float(self.threshold_var.get())
        self.engine.cycle_duration_min = int(self.cycle_var.get())
        self.engine.control_check_delay_sec = int(self.delay_var.get())
        self.engine.launch_hidden = self.hidden_var.get()
        self.engine.save_config()
        messagebox.showinfo("Настройки", "Настройки успешно сохранены!")
        self.destroy()

class SteamFarmerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Steam Card Auto-Farmer: SecretBall Cyber Edition ⚽")
        self.root.geometry("1160x780")
        self.root.minsize(980, 660)
        self.root.configure(bg=BG_DARK)

        # Initialize assets
        theme_manager.ensure_assets()
        self.header_avatar_img = theme_manager.get_header_avatar()
        self.mascot_img = theme_manager.get_mascot_image()

        # Initialize Steam Client and Farming Engine
        self.steam_client = SteamClient()
        self.engine = FarmingEngine(self.steam_client)

        # Hook engine callbacks
        self.engine.on_log = self._on_engine_log
        self.engine.on_stats_updated = self._on_stats_updated
        self.engine.on_game_changed = self._on_game_changed
        self.engine.on_card_dropped = self._on_card_dropped
        self.engine.on_phase_changed = self._on_phase_changed

        self._build_background_canvas()
        self._build_styles()
        self._build_ui()

        # Handle window close cleanly
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Background timer for session elapsed time and UI ticks
        self.timer_running = True
        self.root.after(1000, self._tick_timer)

        # Initial badges scan in separate thread
        threading.Thread(target=self._initial_load, daemon=True).start()

    def _build_background_canvas(self):
        """Creates the full window background canvas displaying the stylized SecretBall wallpaper."""
        self.bg_canvas = tk.Canvas(self.root, highlightthickness=0, bd=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._bg_image_ref = None
        self._resize_job = None
        self.root.bind("<Configure>", self._on_window_resize)

    def _on_window_resize(self, event):
        if event.widget != self.root:
            return
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(120, self._update_background_canvas)

    def _update_background_canvas(self):
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        if w > 200 and h > 200:
            img = theme_manager.get_wallpaper_image(w, h)
            if img:
                self._bg_image_ref = img
                self.bg_canvas.delete("all")
                self.bg_canvas.create_image(0, 0, image=img, anchor="nw")

    def _build_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        # Notebook tabs
        style.configure("Custom.TNotebook", background=BG_DARK, borderwidth=0)
        style.configure("Custom.TNotebook.Tab", background=BG_CARD, foreground=TEXT_LIGHT,
                        padding=[16, 7], font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("Custom.TNotebook.Tab",
                  background=[('selected', BG_HOVER)],
                  foreground=[('selected', ACCENT_CYAN)])

        # Treeview styling
        style.configure("Custom.Treeview",
                        background=BG_INPUT,
                        foreground=TEXT_LIGHT,
                        fieldbackground=BG_INPUT,
                        rowheight=27,
                        font=("Segoe UI", 9),
                        borderwidth=0)
        style.map("Custom.Treeview",
                  background=[('selected', BG_HOVER)],
                  foreground=[('selected', ACCENT_CYAN)])

        style.configure("Custom.Treeview.Heading",
                        background=BG_CARD,
                        foreground=TEXT_WHITE,
                        font=("Segoe UI", 9, "bold"),
                        relief="flat")
        style.map("Custom.Treeview.Heading",
                  background=[('active', BG_HOVER)])

        # Progressbar styling
        style.configure("Custom.Horizontal.TProgressbar",
                        troughcolor=BG_INPUT,
                        background=COLOR_LIME,
                        thickness=14)

    def _build_ui(self):
        # 1. Top Header Bar (Cyber Edition)
        header = tk.Frame(self.root, bg=BG_CARD, height=70, highlightbackground=BG_CARD_BORDER, highlightthickness=1)
        header.pack(fill="x", side="top", padx=14, pady=(8, 4))
        header.pack_propagate(False)

        title_frame = tk.Frame(header, bg=BG_CARD)
        title_frame.pack(side="left", padx=12, pady=6)

        # Circular neon avatar in header
        if self.header_avatar_img:
            lbl_avatar = tk.Label(title_frame, image=self.header_avatar_img, bg=BG_CARD)
            lbl_avatar.pack(side="left", padx=(0, 10))

        text_subframe = tk.Frame(title_frame, bg=BG_CARD)
        text_subframe.pack(side="left")

        title_sub_frame = tk.Frame(text_subframe, bg=BG_CARD)
        title_sub_frame.pack(anchor="w")

        lbl_title = tk.Label(title_sub_frame, text="⚽ STEAM CARD FARMER: SECRET BALL EDITION 🔥",
                             fg=TEXT_WHITE, bg=BG_CARD, font=("Segoe UI", 12, "bold"))
        lbl_title.pack(side="left")

        lbl_badge = tk.Label(title_sub_frame, text=" PRO ", fg="#000000", bg=COLOR_LIME,
                             font=("Segoe UI", 7, "bold"), padx=4, pady=1)
        lbl_badge.pack(side="left", padx=8)

        account_name = self.steam_client.steam_id or "Обнаружен"
        self.lbl_status_account = tk.Label(text_subframe, text=f"Steam ID: {account_name} | Авторизация: Активна (Live) • Заряжен на дроп",
                                           fg=COLOR_LIME, bg=BG_CARD, font=("Segoe UI", 8))
        self.lbl_status_account.pack(anchor="w")

        # Header Action Buttons
        btn_box = tk.Frame(header, bg=BG_CARD)
        btn_box.pack(side="right", padx=14, pady=12)

        self.btn_force_check = tk.Button(btn_box, text="🔄 Проверить дроп", bg=BG_HOVER, fg=ACCENT_CYAN, relief="flat",
                                         font=("Segoe UI", 9, "bold"), cursor="hand2", padx=8, pady=4, command=self._force_check)
        self.btn_force_check.pack(side="left", padx=4)

        self.btn_skip_boost = tk.Button(btn_box, text="⚡ Пропуск 2ч", bg=BG_HOVER, fg=COLOR_GOLD, relief="flat",
                                        font=("Segoe UI", 9), cursor="hand2", padx=8, pady=4, command=self._skip_boost)
        self.btn_skip_boost.pack(side="left", padx=4)

        btn_refresh = tk.Button(btn_box, text="🔄 Значки", bg=BG_HOVER, fg=TEXT_WHITE, relief="flat",
                                font=("Segoe UI", 9), cursor="hand2", padx=8, pady=4, command=self._refresh_badges)
        btn_refresh.pack(side="left", padx=4)

        btn_settings = tk.Button(btn_box, text="⚙ Настройки", bg=BG_HOVER, fg=TEXT_LIGHT, relief="flat",
                                 font=("Segoe UI", 9), cursor="hand2", padx=8, pady=4, command=self._open_settings)
        btn_settings.pack(side="left", padx=4)

        btn_cleanup = tk.Button(btn_box, text="🧹 Очистить SAM", bg=BG_HOVER, fg=TEXT_MUTED, relief="flat",
                                font=("Segoe UI", 9), cursor="hand2", padx=8, pady=4, command=self._manual_cleanup_sam)
        btn_cleanup.pack(side="left", padx=4)

        # 2. Key Metrics Cards (4 Neon HUD Boxes)
        metrics_frame = tk.Frame(self.root, bg=BG_DARK)
        metrics_frame.pack(fill="x", padx=14, pady=(4, 6))

        for i in range(4):
            metrics_frame.columnconfigure(i, weight=1)

        self.card_total = self._create_metric_card(metrics_frame, 0, "🎮 ВСЕГО КАРТОЧЕК", "0", ACCENT_CYAN, "Найдено во всех значках")
        self.card_session = self._create_metric_card(metrics_frame, 1, "🏆 ВЫПАЛО В СЕССИИ", "+0", COLOR_LIME, "Выпало с момента запуска")
        self.card_remaining = self._create_metric_card(metrics_frame, 2, "⏳ ОСТАЛОСЬ ПОЛУЧИТЬ", "0", COLOR_GOLD, "Карточек осталось выбить")
        self.card_time = self._create_metric_card(metrics_frame, 3, "⚡ РАСЧЕТНОЕ ВРЕМЯ", "0 ч.", COLOR_PURPLE, "~20-30 мин на 1 карту")

        # 3. Current Activity & Progress Banner
        banner_frame = tk.Frame(self.root, bg=BG_CARD, highlightbackground=BG_CARD_BORDER, highlightthickness=1)
        banner_frame.pack(fill="x", padx=14, pady=(2, 6))

        banner_top = tk.Frame(banner_frame, bg=BG_CARD)
        banner_top.pack(fill="x", padx=14, pady=(8, 4))

        self.lbl_current_game = tk.Label(banner_top, text="💤 Статус: Готов к работе. Нажмите 'НАЧАТЬ ФАРМ'",
                                         fg=TEXT_WHITE, bg=BG_CARD, font=("Segoe UI", 10, "bold"))
        self.lbl_current_game.pack(side="left")

        self.lbl_game_timer = tk.Label(banner_top, text="Время сессии: 00:00:00", fg=ACCENT_CYAN, bg=BG_CARD, font=("Segoe UI", 9, "bold"))
        self.lbl_game_timer.pack(side="right")

        prog_box = tk.Frame(banner_frame, bg=BG_CARD)
        prog_box.pack(fill="x", padx=14, pady=(0, 6))

        self.progress_bar = ttk.Progressbar(prog_box, style="Custom.Horizontal.TProgressbar", orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", side="left", expand=True, padx=(0, 10))

        self.lbl_progress_text = tk.Label(prog_box, text="0% завершено", fg=TEXT_MUTED, bg=BG_CARD, font=("Segoe UI", 8))
        self.lbl_progress_text.pack(side="right")

        self.lbl_phase_detail = tk.Label(banner_frame, text="", fg=COLOR_GOLD, bg=BG_CARD, font=("Segoe UI", 8, "italic"))
        self.lbl_phase_detail.pack(anchor="w", padx=14, pady=(0, 6))

        # 4. Middle Work Area: Split into Left (Tabs + Log) and Right (SecretBall Mascot Card)
        work_area = tk.Frame(self.root, bg=BG_DARK)
        work_area.pack(fill="both", expand=True, padx=14, pady=4)

        # Left Column: PanedWindow (Tabs on top, Logs on bottom)
        paned = tk.PanedWindow(work_area, orient="vertical", bg=BG_DARK, sashwidth=4, sashrelief="flat")
        paned.pack(side="left", fill="both", expand=True)

        # Tabs Container
        tab_container = tk.Frame(paned, bg=BG_CARD, highlightbackground=BG_CARD_BORDER, highlightthickness=1)
        paned.add(tab_container, minsize=200, height=270)

        self.notebook = ttk.Notebook(tab_container, style="Custom.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=6, pady=6)

        # Tab 1: Queue Treeview
        tab_queue = tk.Frame(self.notebook, bg=BG_CARD)
        self.notebook.add(tab_queue, text=" 📋 Очередь игр на фарм ")

        cols_q = ("title", "appid", "playtime", "status", "session_dropped", "drops_left", "initial_drops")
        self.tree_queue = ttk.Treeview(tab_queue, columns=cols_q, show="headings", style="Custom.Treeview")
        self.tree_queue.heading("title", text="Название игры")
        self.tree_queue.heading("appid", text="AppID")
        self.tree_queue.heading("playtime", text="Наиграно")
        self.tree_queue.heading("status", text="Статус / Разгон")
        self.tree_queue.heading("session_dropped", text="В сессии")
        self.tree_queue.heading("drops_left", text="Осталось")
        self.tree_queue.heading("initial_drops", text="Всего")

        self.tree_queue.column("title", width=330, anchor="w")
        self.tree_queue.column("appid", width=85, anchor="center")
        self.tree_queue.column("playtime", width=95, anchor="center")
        self.tree_queue.column("status", width=170, anchor="center")
        self.tree_queue.column("session_dropped", width=95, anchor="center")
        self.tree_queue.column("drops_left", width=85, anchor="center")
        self.tree_queue.column("initial_drops", width=85, anchor="center")

        scroll_q = ttk.Scrollbar(tab_queue, orient="vertical", command=self.tree_queue.yview)
        self.tree_queue.configure(yscrollcommand=scroll_q.set)

        self.tree_queue.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        scroll_q.pack(side="right", fill="y", padx=(0, 6), pady=6)

        # Tab 2: Dropped Cards Breakdown
        tab_dropped = tk.Frame(self.notebook, bg=BG_CARD)
        self.notebook.add(tab_dropped, text=" 🏆 Полученные карточки за сессию ")

        dropped_header = tk.Frame(tab_dropped, bg=BG_CARD)
        dropped_header.pack(fill="x", padx=10, pady=(6, 2))

        self.lbl_dropped_summary = tk.Label(dropped_header, text="Всего в этой сессии получено: 0 карточек из 0 игр",
                                            fg=COLOR_LIME, bg=BG_CARD, font=("Segoe UI", 9, "bold"))
        self.lbl_dropped_summary.pack(side="left")

        cols_d = ("title", "appid", "dropped_now", "drops_left", "last_drop", "status")
        self.tree_dropped = ttk.Treeview(tab_dropped, columns=cols_d, show="headings", style="Custom.Treeview")
        self.tree_dropped.heading("title", text="Название игры")
        self.tree_dropped.heading("appid", text="AppID")
        self.tree_dropped.heading("dropped_now", text="Получено карточек")
        self.tree_dropped.heading("drops_left", text="Осталось дофармить")
        self.tree_dropped.heading("last_drop", text="Время выпадения")
        self.tree_dropped.heading("status", text="Статус игры")

        self.tree_dropped.column("title", width=340, anchor="w")
        self.tree_dropped.column("appid", width=95, anchor="center")
        self.tree_dropped.column("dropped_now", width=130, anchor="center")
        self.tree_dropped.column("drops_left", width=130, anchor="center")
        self.tree_dropped.column("last_drop", width=130, anchor="center")
        self.tree_dropped.column("status", width=150, anchor="center")

        scroll_d = ttk.Scrollbar(tab_dropped, orient="vertical", command=self.tree_dropped.yview)
        self.tree_dropped.configure(yscrollcommand=scroll_d.set)

        self.tree_dropped.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        scroll_d.pack(side="right", fill="y", padx=(0, 6), pady=6)

        # Bottom Pane: Live Event & Drop Log
        log_container = tk.Frame(paned, bg=BG_CARD, highlightbackground=BG_CARD_BORDER, highlightthickness=1)
        paned.add(log_container, minsize=110, height=140)

        log_header = tk.Frame(log_container, bg=BG_CARD)
        log_header.pack(fill="x", padx=10, pady=(4, 2))

        lbl_log_title = tk.Label(log_header, text="📜 Журнал выпадений и событий в реальном времени", fg=TEXT_WHITE, bg=BG_CARD, font=("Segoe UI", 9, "bold"))
        lbl_log_title.pack(side="left")

        btn_clear_log = tk.Button(log_header, text="Очистить", bg=BG_CARD, fg=TEXT_MUTED, relief="flat",
                                  font=("Segoe UI", 8), cursor="hand2", command=self._clear_log)
        btn_clear_log.pack(side="right")

        self.log_text = tk.Text(log_container, bg=BG_INPUT, fg=TEXT_LIGHT, insertbackground=TEXT_WHITE,
                                relief="flat", font=("Consolas", 9), wrap="word", height=5)
        log_scroll = ttk.Scrollbar(log_container, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)

        self.log_text.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 6))
        log_scroll.pack(side="right", fill="y", padx=(0, 10), pady=(0, 6))

        # Text color tags
        self.log_text.tag_config("SUCCESS", foreground=COLOR_LIME)
        self.log_text.tag_config("ERROR", foreground=COLOR_RED)
        self.log_text.tag_config("WARNING", foreground=COLOR_GOLD)
        self.log_text.tag_config("INFO", foreground=ACCENT_CYAN)
        self.log_text.tag_config("DEBUG", foreground=TEXT_MUTED)

        # Right Column: SecretBall Mascot Guardian Card
        self.mascot_visible = True
        self.mascot_panel = tk.Frame(work_area, bg=BG_CARD, width=265, highlightbackground=BG_CARD_BORDER, highlightthickness=1)
        self.mascot_panel.pack(side="right", fill="y", padx=(10, 0))
        self.mascot_panel.pack_propagate(False)

        mascot_header = tk.Frame(self.mascot_panel, bg=BG_CARD)
        mascot_header.pack(fill="x", padx=10, pady=(8, 4))

        lbl_m_title = tk.Label(mascot_header, text="⚽ SECRET BALL 🏆", fg=ACCENT_CYAN, bg=BG_CARD, font=("Segoe UI", 10, "bold"))
        lbl_m_title.pack(side="left")

        self.btn_toggle_mascot = tk.Button(mascot_header, text="✖", bg=BG_CARD, fg=TEXT_MUTED, relief="flat",
                                           font=("Segoe UI", 8, "bold"), cursor="hand2", command=self._toggle_mascot)
        self.btn_toggle_mascot.pack(side="right")

        # Portrait
        if self.mascot_img:
            lbl_m_img = tk.Label(self.mascot_panel, image=self.mascot_img, bg=BG_CARD)
            lbl_m_img.pack(padx=8, pady=(2, 6))

        # Dynamic Status / Reaction Box
        mascot_box = tk.Frame(self.mascot_panel, bg=BG_INPUT, highlightbackground=ACCENT_CYAN, highlightthickness=1)
        mascot_box.pack(fill="x", padx=10, pady=4)

        self.lbl_mascot_quote = tk.Label(mascot_box, text="⚽ ФАРМ НА МАКСИМАЛКАХ!",
                                         fg=COLOR_LIME, bg=BG_INPUT, font=("Segoe UI", 9, "bold"), wraplength=230, justify="center")
        self.lbl_mascot_quote.pack(fill="x", padx=6, pady=(6, 2))

        self.lbl_mascot_sub = tk.Label(mascot_box, text="Ждем команду 'Начать фарм'",
                                       fg=TEXT_LIGHT, bg=BG_INPUT, font=("Segoe UI", 8), wraplength=230, justify="center")
        self.lbl_mascot_sub.pack(fill="x", padx=6, pady=(0, 6))

        # 5. Bottom Control Bar
        bottom_bar = tk.Frame(self.root, bg=BG_DARK, height=60)
        bottom_bar.pack(fill="x", side="bottom", padx=14, pady=(4, 10))

        self.btn_start = tk.Button(bottom_bar, text="▶ НАЧАТЬ ФАРМ", bg=COLOR_LIME, fg="#000000",
                                   font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
                                   padx=20, pady=7, command=self._toggle_start_pause)
        self.btn_start.pack(side="left", padx=(0, 6))

        self.btn_stop = tk.Button(bottom_bar, text="⏹ СТОП", bg=COLOR_RED, fg=TEXT_WHITE,
                                  font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                                  padx=14, pady=7, state="disabled", command=self._stop_farming)
        self.btn_stop.pack(side="left", padx=4)

        self.btn_skip_game = tk.Button(bottom_bar, text="⏭ ПРОПУСТИТЬ ИГРУ", bg=COLOR_BLUE, fg=TEXT_WHITE,
                                       font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2",
                                       padx=12, pady=7, state="disabled", command=self._skip_game)
        self.btn_skip_game.pack(side="left", padx=4)

        self.btn_restore_mascot = tk.Button(bottom_bar, text="⚽ Показать маскота", bg=BG_HOVER, fg=ACCENT_CYAN,
                                            font=("Segoe UI", 8), relief="flat", cursor="hand2", command=self._toggle_mascot)

        # Informative guide tip
        tip_text = "💡 Дроп засчитывается при закрытии/перезапуске игры. Приложение работает непрерывно в фоне и закрывает процессы только по крестику или Стоп."
        lbl_tip = tk.Label(bottom_bar, text=tip_text, fg=TEXT_MUTED, bg=BG_DARK, font=("Segoe UI", 8), wraplength=500, justify="left")
        lbl_tip.pack(side="right", padx=6)

    def _toggle_mascot(self):
        if self.mascot_visible:
            self.mascot_panel.pack_forget()
            self.mascot_visible = False
            self.btn_restore_mascot.pack(side="left", padx=8)
        else:
            self.btn_restore_mascot.pack_forget()
            self.mascot_panel.pack(side="right", fill="y", padx=(10, 0))
            self.mascot_visible = True

    def _create_metric_card(self, parent, col, title, initial_val, val_color, subtext):
        card = tk.Frame(parent, bg=BG_CARD, highlightbackground=BG_CARD_BORDER, highlightthickness=1)
        card.grid(row=0, column=col, padx=4, sticky="nsew")

        # Top neon accent line
        accent_strip = tk.Frame(card, bg=val_color, height=3)
        accent_strip.pack(fill="x", side="top")

        content = tk.Frame(card, bg=BG_CARD, padx=12, pady=7)
        content.pack(fill="both", expand=True)

        lbl_t = tk.Label(content, text=title, fg=TEXT_MUTED, bg=BG_CARD, font=("Segoe UI", 8, "bold"))
        lbl_t.pack(anchor="w")

        lbl_v = tk.Label(content, text=initial_val, fg=val_color, bg=BG_CARD, font=("Segoe UI", 15, "bold"))
        lbl_v.pack(anchor="w", pady=(1, 0))

        lbl_s = tk.Label(content, text=subtext, fg=TEXT_MUTED, bg=BG_CARD, font=("Segoe UI", 7))
        lbl_s.pack(anchor="w")

        return lbl_v

    def _initial_load(self):
        self.engine.load_games()
        self.root.after(0, self._update_table_and_stats)

    def _refresh_badges(self):
        if self.engine.is_running:
            messagebox.showinfo("Информация", "Сначала остановите фарм, чтобы обновить значки из Steam.")
            return
        threading.Thread(target=self._initial_load, daemon=True).start()

    def _open_settings(self):
        SettingsDialog(self.root, self.engine)

    def _clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def _toggle_start_pause(self):
        if not self.engine.is_running:
            success = self.engine.start()
            if success:
                self.btn_start.configure(text="⏸ ПАУЗА", bg=COLOR_GOLD, fg="#000000")
                self.btn_stop.configure(state="normal")
                self.btn_skip_game.configure(state="normal")
                self._update_mascot_reaction("RUNNING")
            else:
                if not self.engine.sam_path or not os.path.isfile(self.engine.sam_path):
                    messagebox.showwarning(
                        "SAM.Game.exe не найден",
                        "Файл SAM.Game.exe не обнаружен!\n\n"
                        "Убедитесь, что папка 'SAM' находится рядом с ботом, или укажите путь к SAM.Game.exe в Настройках ⚙."
                    )
                elif not self.engine.games:
                    messagebox.showinfo(
                        "Нет игр для фарма",
                        "Список значков пуст или Steam еще не авторизован.\n\n"
                        "Убедитесь, что Steam запущен и выполнен вход в аккаунт, затем нажмите кнопку '🔄 Значки'."
                    )
        elif not self.engine.is_paused:
            self.engine.pause()
            self.btn_start.configure(text="▶ ПРОДОЛЖИТЬ", bg=COLOR_LIME, fg="#000000")
            self._update_mascot_reaction("PAUSED")
        else:
            self.engine.start()
            self.btn_start.configure(text="⏸ ПАУЗА", bg=COLOR_GOLD, fg="#000000")
            self._update_mascot_reaction("RUNNING")

    def _stop_farming(self):
        self.engine.stop()
        self.btn_start.configure(text="▶ НАЧАТЬ ФАРМ", bg=COLOR_LIME, fg="#000000")
        self.btn_stop.configure(state="disabled")
        self.btn_skip_game.configure(state="disabled")
        self.lbl_current_game.configure(text="⏹ Статус: Фарм остановлен пользователем")
        self.lbl_phase_detail.configure(text="")
        self._update_mascot_reaction("STOPPED")

    def _skip_game(self):
        self.engine.skip_current_game()

    def _skip_boost(self):
        if self.engine.is_running and self.engine.current_phase == "BOOST":
            self.engine.skip_boost_phase()
        else:
            messagebox.showinfo("Разгон", "Фаза одновременного разгона сейчас не активна.")

    def _force_check(self):
        if self.engine.is_running and self.engine.current_phase == "FARMING":
            self.engine.trigger_immediate_check()
        else:
            messagebox.showinfo("Проверка", "Сейчас не выполняется одиночный фарм игры.")

    def _on_engine_log(self, formatted_msg, level):
        self.root.after(0, self._append_log, formatted_msg, level)

    def _append_log(self, text, level):
        self.log_text.insert(tk.END, text + "\n", level)
        self.log_text.see(tk.END)

    def _on_stats_updated(self):
        self.root.after(0, self._update_table_and_stats)

    def _on_phase_changed(self, phase):
        self.root.after(0, self._update_phase_banner, phase)

    def _on_game_changed(self, game):
        self.root.after(0, self._update_current_game_label, game)

    def _on_card_dropped(self, game, count):
        self.root.after(0, self._handle_card_dropped, game, count)

    def _handle_card_dropped(self, game, count):
        self._update_table_and_stats()
        self._update_mascot_reaction("DROP", game, count)

    def _update_mascot_reaction(self, event_type, game=None, count=1):
        if not hasattr(self, 'lbl_mascot_quote'):
            return
        if event_type == "DROP":
            self.lbl_mascot_quote.configure(text="🎉 ДРОП КАРТОЧКИ! ⚽", fg=COLOR_LIME)
            title = game.title if game else ""
            self.lbl_mascot_sub.configure(text=f"Выпала карта из '{title}'! Копилка пополняется!")
        elif event_type == "RUNNING":
            phase = self.engine.current_phase
            boost_count = len(self.engine.boost_procs)
            if phase == "FARMING" and boost_count > 0:
                self.lbl_mascot_quote.configure(text="🎮 ФАРМ + ⚡ РАЗГОН!", fg=COLOR_LIME)
                self.lbl_mascot_sub.configure(text=f"Фармим готовую игру, параллельно греем {boost_count} игр!")
            elif phase == "BOOST":
                self.lbl_mascot_quote.configure(text="⚡ РАЗГОН 2 ЧАСА!", fg=COLOR_GOLD)
                self.lbl_mascot_sub.configure(text=f"Греем {boost_count} игр до 2ч, скоро начнется дроп!")
            else:
                self.lbl_mascot_quote.configure(text="🎯 ОХОТА ЗА ДРОПОМ!", fg=COLOR_LIME)
                self.lbl_mascot_sub.configure(text="SAM на позиции, ждем карточки!")
        elif event_type == "PAUSED":
            self.lbl_mascot_quote.configure(text="⏸ ПЕРЕРЫВ", fg=COLOR_GOLD)
            self.lbl_mascot_sub.configure(text="Фарм на паузе. Нажми 'Продолжить'")
        elif event_type == "STOPPED":
            self.lbl_mascot_quote.configure(text="⏹ ОТДЫХ", fg=TEXT_MUTED)
            self.lbl_mascot_sub.configure(text="Все процессы SAM выключены.")
        elif event_type == "COMPLETED":
            self.lbl_mascot_quote.configure(text="👑 ЧЕМПИОН! 100%", fg=COLOR_LIME)
            self.lbl_mascot_sub.configure(text="Все карточки на аккаунте собраны!")

    def _update_phase_banner(self, phase):
        if phase == "BOOST":
            boost_count = len(self.engine.boost_procs)
            self.lbl_current_game.configure(
                text=f"⚡ ФАЗА 1: Одновременный разгон до 2 часов ({boost_count} игр запущено в фоне)"
            )
            self.lbl_phase_detail.configure(text="Нет готовых игр. Параллельный разгон: как только первая игра достигнет 2ч, начнется фарм!")
            self._update_mascot_reaction("RUNNING")
        elif phase == "FARMING":
            game = self.engine.current_game
            title = game.title if game else "Очередь"
            drops = game.current_drops if game else 0
            boost_count = len(self.engine.boost_procs)
            if boost_count > 0:
                self.lbl_current_game.configure(
                    text=f"🎮 Фарм: \"{title}\" (Осталось: {drops} карт) • ⚡ Разгон в фоне: {boost_count} игр"
                )
                self.lbl_phase_detail.configure(
                    text=f"Параллельный режим: игра фармится, пока {boost_count} игр разгоняются до 2ч в фоне"
                )
            else:
                self.lbl_current_game.configure(
                    text=f"🎮 Одиночный фарм игры: \"{title}\" (Осталось: {drops} карт)"
                )
            self._update_mascot_reaction("RUNNING")
        elif phase == "COMPLETED":
            self.lbl_current_game.configure(text="🎉 ВСЕ КАРТОЧКИ ПО ВСЕМ ИГРАМ УСПЕШНО ПОЛУЧЕНЫ!")
            self.lbl_phase_detail.configure(text="Фарм завершен")
            self.btn_start.configure(text="▶ НАЧАТЬ ФАРМ", bg=COLOR_LIME, fg="#000000")
            self.btn_stop.configure(state="disabled")
            self.btn_skip_game.configure(state="disabled")
            self._update_mascot_reaction("COMPLETED")
        elif phase == "PAUSED":
            self.lbl_current_game.configure(text="⏸ Пауза: процесс фарма временно приостановлен")

    def _update_current_game_label(self, game):
        if self.engine.current_phase == "FARMING" and game:
            boost_count = len(self.engine.boost_procs)
            boost_note = f" • ⚡ Разгон: {boost_count} игр" if boost_count > 0 else ""
            self.lbl_current_game.configure(
                text=f"🎮 Фарм: \"{game.title}\" (AppID: {game.appid}) | Осталось: {game.current_drops} карт{boost_note}"
            )
            if hasattr(self, 'lbl_mascot_sub'):
                self.lbl_mascot_sub.configure(text=f"Фармим '{game.title}' (осталось {game.current_drops} шт.)")

    def _update_table_and_stats(self):
        total_initial = self.engine.initial_total_drops
        session_dropped = self.engine.total_session_dropped
        remaining = self.engine.total_remaining_drops

        self.card_total.configure(text=str(total_initial))
        self.card_session.configure(text=f"+{session_dropped}")
        self.card_remaining.configure(text=str(remaining))
        self.card_time.configure(text=self.engine.format_estimated_time())

        if self.engine.current_phase == "FARMING" and self.engine.is_running:
            rem = self.engine.current_cycle_remaining
            rem_m = rem // 60
            rem_s = rem % 60
            boost_count = len(self.engine.boost_procs)
            boost_note = f" • ⚡ В фоне разгон: {boost_count} игр" if boost_count > 0 else ""
            self.lbl_phase_detail.configure(
                text=f"До закрытия и проверки: {rem_m:02d}:{rem_s:02d}{boost_note}"
            )

        if total_initial > 0:
            percent = int((session_dropped / total_initial) * 100)
            self.progress_bar['value'] = percent
            self.lbl_progress_text.configure(
                text=f"{percent}% получено ({session_dropped} из {total_initial} карточек, осталось {remaining})"
            )
        else:
            self.progress_bar['value'] = 0
            self.lbl_progress_text.configure(text="0% завершено")

        # Update Queue Treeview
        selected_q = self.tree_queue.selection()
        self.tree_queue.delete(*self.tree_queue.get_children())
        for g in self.engine.games:
            status_text = g.status
            if self.engine.is_paused and g == self.engine.current_game:
                status_text = "⏸ Пауза"

            self.tree_queue.insert("", "end", iid=str(g.appid), values=(
                g.title,
                g.appid,
                g.total_playtime_str,
                status_text,
                f"+{g.session_dropped}" if g.session_dropped > 0 else "0",
                g.current_drops,
                g.initial_drops
            ))
        if selected_q and self.tree_queue.exists(selected_q[0]):
            self.tree_queue.selection_set(selected_q[0])

        # Update Dropped Cards Tab
        dropped_games = [g for g in self.engine.games if g.session_dropped > 0]
        self.lbl_dropped_summary.configure(
            text=f"Всего в этой сессии получено: {session_dropped} карточек из {len(dropped_games)} игр"
        )
        self.tree_dropped.delete(*self.tree_dropped.get_children())
        for g in dropped_games:
            time_str = g.last_drop_time.strftime("%H:%M:%S") if g.last_drop_time else "-"
            game_state = "Все собраны 🎉" if g.current_drops == 0 else f"Осталось: {g.current_drops}"
            self.tree_dropped.insert("", "end", iid=f"drop_{g.appid}", values=(
                g.title,
                g.appid,
                f"+{g.session_dropped}",
                g.current_drops,
                time_str,
                game_state
            ))

    def _tick_timer(self):
        if self.timer_running:
            if self.engine.is_running and self.engine.session_start_time:
                delta = datetime.now() - self.engine.session_start_time
                elapsed = str(timedelta(seconds=int(delta.total_seconds())))
                self.lbl_game_timer.configure(text=f"Время сессии: {elapsed}")
            self.root.after(1000, self._tick_timer)

    def _manual_cleanup_sam(self):
        if self.engine.is_running:
            self.engine.stop()
        self.engine._stop_all_processes()
        messagebox.showinfo("Очистка", "Все фоновые процессы SAM принудительно закрыты. Оперативная память очищена!")

    def _on_close(self):
        if self.engine.is_running:
            if messagebox.askyesno("Выход", "Фарм карточек запущен. Остановить фарм и закрыть приложение?"):
                self.timer_running = False
                self.engine.stop()
                self.engine._stop_all_processes()
                self.root.destroy()
        else:
            self.timer_running = False
            self.engine._stop_all_processes()
            self.root.destroy()

def main():
    root = tk.Tk()
    app = SteamFarmerApp(root)
    root.mainloop()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        try:
            with open("crash_log.txt", "w", encoding="utf-8") as f:
                f.write(err_msg)
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("Ошибка запуска Steam Card Farmer", f"Произошла ошибка при запуске:\n\n{err_msg}")
            r.destroy()
        except Exception:
            pass

