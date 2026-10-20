"""
Farming Engine for Steam Card Farmer.
Manages:
1. Phase 1: Simultaneous Idling (Разгон до 2 часов) for games with < 2 hours of playtime.
   Reads exact minute-level playtime from the account.
   Each game calculates its own remaining time until 2 hours.
   All games that need boost run simultaneously in parallel.
   As soon as a specific game reaches 2 hours, its SAM process is individually closed!
2. Phase 2: Individual Farming (1-by-1 with Close & Check cycle).
   Steam registers session time and grants cards upon session closing/restart.
   The engine runs the game for a cycle (e.g. 15 min), closes SAM, checks for card drops,
   and if Steam hasn't loaded the drop yet, performs a secondary control check after 20 seconds!
   Once 1 card drops, it relaunches the game. When all cards are collected, it moves to the next game!
3. Robust Process Lifecycle & Zero-Leak Guarantee:
   Uses Windows Job Objects (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE) to guarantee that if Python exits,
   crashes, or is closed, Windows Kernel automatically kills all child SAM processes.
   Includes startup and shutdown cleanup to prevent any orphaned background processes.
"""

import time
import threading
import subprocess
import os
import json
import glob
import atexit
from datetime import datetime

import ctypes
from ctypes import wintypes

kernel32 = ctypes.windll.kernel32

JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(f, ctypes.c_uint64) for f in [
        'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
        'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount'
    ]]

class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('PerProcessUserTimeLimit', wintypes.LARGE_INTEGER),
        ('PerJobUserTimeLimit', wintypes.LARGE_INTEGER),
        ('LimitFlags', wintypes.DWORD),
        ('MinimumWorkingSetSize', ctypes.c_size_t),
        ('MaximumWorkingSetSize', ctypes.c_size_t),
        ('ActiveProcessLimit', wintypes.DWORD),
        ('Affinity', ctypes.c_size_t),
        ('PriorityClass', wintypes.DWORD),
        ('SchedulingClass', wintypes.DWORD),
    ]

class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ('IoInfo', IO_COUNTERS),
        ('ProcessMemoryLimit', ctypes.c_size_t),
        ('JobMemoryLimit', ctypes.c_size_t),
        ('PeakProcessMemoryLimit', ctypes.c_size_t),
        ('PeakJobMemoryLimit', ctypes.c_size_t),
    ]

class WindowsJobManager:
    """Ensures child processes are automatically killed by Windows Kernel when parent dies."""
    def __init__(self):
        self.hJob = None
        if os.name == 'nt':
            try:
                self.hJob = kernel32.CreateJobObjectW(None, None)
                if self.hJob:
                    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                    kernel32.SetInformationJobObject(
                        self.hJob,
                        JobObjectExtendedLimitInformation,
                        ctypes.byref(info),
                        ctypes.sizeof(info)
                    )
            except Exception:
                self.hJob = None

    def assign_process(self, proc):
        if self.hJob and proc and hasattr(proc, '_handle') and proc._handle:
            try:
                return bool(kernel32.AssignProcessToJobObject(self.hJob, int(proc._handle)))
            except Exception:
                pass
        return False

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_TERMINATE = 0x0001

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ('dwSize', wintypes.DWORD),
        ('cntUsage', wintypes.DWORD),
        ('th32ProcessID', wintypes.DWORD),
        ('th32DefaultHeapID', ctypes.POINTER(wintypes.ULONG)),
        ('th32ModuleID', wintypes.DWORD),
        ('cntThreads', wintypes.DWORD),
        ('th32ParentProcessID', wintypes.DWORD),
        ('pcPriClassBase', wintypes.LONG),
        ('dwFlags', wintypes.DWORD),
        ('szExeFile', ctypes.c_char * 260)
    ]

def kill_processes_by_name(process_name):
    """Cleanly terminates processes matching name via pure Win32 API without cmd or console."""
    if os.name != 'nt':
        return
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == -1 or snapshot == 0xFFFFFFFFFFFFFFFF:
        return
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    if kernel32.Process32First(snapshot, ctypes.byref(entry)):
        target = process_name.lower()
        target_exe = target if target.endswith('.exe') else (target + '.exe')
        while True:
            name = entry.szExeFile.decode('utf-8', errors='ignore').lower()
            if name == target or name == target_exe:
                h = kernel32.OpenProcess(PROCESS_TERMINATE, False, entry.th32ProcessID)
                if h:
                    kernel32.TerminateProcess(h, 1)
                    kernel32.CloseHandle(h)
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    kernel32.CloseHandle(snapshot)

def kill_pid_cleanly(pid):
    """Terminates process by PID cleanly via Win32 API without cmd."""
    if os.name == 'nt' and pid:
        h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if h:
            kernel32.TerminateProcess(h, 1)
            kernel32.CloseHandle(h)

def cleanup_all_sam_processes():
    """Forcefully terminates any existing or orphaned SAM.Game.exe processes cleanly."""
    kill_processes_by_name("SAM.Game")

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
BOOST_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "boost_state.json")

def find_sam_executable():
    """Tries to find SAM.Game.exe automatically on the system."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "SAM", "SAM.Game.exe"),
        os.path.join(base_dir, "SAM.Game.exe"),
        os.path.join(base_dir, "SteamAchievementManager", "SAM.Game.exe"),
        os.path.expandvars(r"%USERPROFILE%\OneDrive\Desktop\SteamAchievementManager-7.0.41\SAM.Game.exe"),
        os.path.expandvars(r"%USERPROFILE%\Desktop\SteamAchievementManager-7.0.41\SAM.Game.exe"),
    ]
    search_dirs = [
        base_dir,
        os.path.dirname(base_dir),
        os.path.expandvars(r"%USERPROFILE%\Desktop"),
        os.path.expandvars(r"%USERPROFILE%\OneDrive\Desktop"),
        os.path.expandvars(r"%USERPROFILE%\Downloads"),
    ]
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for match in glob.glob(os.path.join(d, "*SAM*", "SAM.Game.exe")):
            candidates.append(match)
        for match in glob.glob(os.path.join(d, "*SteamAchievementManager*", "SAM.Game.exe")):
            candidates.append(match)

    for p in candidates:
        if os.path.isfile(p):
            return os.path.abspath(p)
    return ""

def format_duration(seconds):
    """Formats seconds into human readable 'X ч. Y мин.' string."""
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h} ч. {m:02d} мин."
    if m > 0:
        return f"{m} мин. {s:02d} сек."
    return f"{s} сек."

class GameItem:
    def __init__(self, appid, title, drops_left, playtime_minutes=0):
        self.appid = int(appid)
        self.title = str(title)
        self.initial_drops = int(drops_left)
        self.current_drops = int(drops_left)
        self.session_dropped = 0
        self.initial_playtime_mins = int(playtime_minutes) # Steam baseline when first checked
        self.boost_seconds_served = 0.0                    # Actual seconds boosted on this computer's clock
        self.farm_seconds = 0.0                            # Actual seconds spent in farming
        self.status = "В очереди"
        self.last_drop_time = None

    @property
    def total_playtime_minutes(self):
        return self.initial_playtime_mins + int((self.boost_seconds_served + self.farm_seconds) / 60)

    @property
    def total_playtime_hours(self):
        return self.total_playtime_minutes / 60.0

    @property
    def total_playtime_str(self):
        mins = self.total_playtime_minutes
        if mins == 0:
            return "0 мин."
        if mins < 60:
            return f"{mins} мин."
        h = mins // 60
        rem_m = mins % 60
        if rem_m == 0:
            return f"{h} ч."
        return f"{h} ч. {rem_m:02d} мин."

    def remaining_boost_seconds(self, threshold_hours=2.0):
        target_sec = int(round(threshold_hours * 3600))
        served_sec = int(self.initial_playtime_mins * 60 + self.boost_seconds_served)
        return max(0, target_sec - served_sec)

    def remaining_boost_minutes(self, threshold_hours=2.0):
        import math
        return int(math.ceil(self.remaining_boost_seconds(threshold_hours) / 60.0))

    def remaining_boost_str(self, threshold_hours=2.0):
        return format_duration(self.remaining_boost_seconds(threshold_hours))

    def needs_boost(self, threshold_hours=2.0):
        if self.current_drops <= 0 or self.status in ("✅ Завершено", "Завершено", "⏭ Пропущено", "Пропущено"):
            return False
        return self.remaining_boost_seconds(threshold_hours) > 0

class FarmingEngine:
    def __init__(self, steam_client):
        self.steam_client = steam_client
        self.job_manager = WindowsJobManager()
        
        # Settings
        self.sam_path = find_sam_executable()
        self.cycle_duration_min = 15      # Session cycle before close & check (minutes)
        self.control_check_delay_sec = 20 # Control check delay if Steam hasn't synced (seconds)
        self.minutes_per_card = 25        # Average minutes per card for estimate (20-30m)
        self.boost_enabled = True         # Simultaneous 2-hour boost for games < 2h
        self.boost_threshold_hours = 2.0  # Exactly 2.0 hours (120 minutes)
        self.launch_hidden = True         # Run SAM completely hidden without popup windows
        self.launch_minimized = False     # Run SAM minimized
        self.simultaneous_limit = 30      # Max games in parallel (Steam client safe limit is 32)
        
        self.load_config()

        # Engine State
        self.games = []
        self.current_phase = "IDLE"       # IDLE, BOOST, FARMING, PAUSED, COMPLETED
        self.current_index = -1
        self.current_proc = None          # Single SAM process for Phase 2
        self.boost_procs = {}             # {appid: Popen} for Phase 1
        
        self.is_running = False
        self.is_paused = False
        
        self.session_start_time = None
        self.phase_start_time = None
        self.current_cycle_remaining = 0  # Seconds remaining until next close & check
        self.total_session_dropped = 0
        self.initial_total_drops = 0

        self._thread = None
        self._stop_event = threading.Event()
        self._skip_event = threading.Event()
        self._skip_boost_event = threading.Event()
        self._force_check_event = threading.Event()
        self._proc_lock = threading.Lock()

        # Callbacks for GUI
        self.on_log = lambda msg, level="INFO": None
        self.on_stats_updated = lambda: None
        self.on_game_changed = lambda game: None
        self.on_card_dropped = lambda game, count: None
        self.on_phase_changed = lambda phase: None

        # Clean up any leftover processes from previous crashes or ungraceful exits
        cleanup_all_sam_processes()

        # Ensure all child processes are killed on normal or abnormal exit
        atexit.register(self._stop_all_processes)

    def load_config(self):
        """Loads persistent configuration if available."""
        if os.path.isfile(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("sam_path") and os.path.isfile(data["sam_path"]):
                    self.sam_path = data["sam_path"]
                self.cycle_duration_min = max(3, int(data.get("cycle_duration_min", self.cycle_duration_min)))
                self.control_check_delay_sec = max(5, int(data.get("control_check_delay_sec", self.control_check_delay_sec)))
                self.minutes_per_card = max(5, int(data.get("minutes_per_card", self.minutes_per_card)))
                self.boost_enabled = bool(data.get("boost_enabled", self.boost_enabled))
                self.boost_threshold_hours = float(data.get("boost_threshold_hours", self.boost_threshold_hours))
                self.launch_hidden = bool(data.get("launch_hidden", self.launch_hidden))
                self.launch_minimized = bool(data.get("launch_minimized", self.launch_minimized))
            except Exception:
                pass

    def save_config(self):
        """Saves current configuration to file."""
        data = {
            "sam_path": self.sam_path,
            "cycle_duration_min": self.cycle_duration_min,
            "control_check_delay_sec": self.control_check_delay_sec,
            "minutes_per_card": self.minutes_per_card,
            "boost_enabled": self.boost_enabled,
            "boost_threshold_hours": self.boost_threshold_hours,
            "launch_hidden": self.launch_hidden,
            "launch_minimized": self.launch_minimized
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def _load_boost_state(self):
        """Loads saved boost progress from disk so computer-clock time is preserved across restarts."""
        if os.path.isfile(BOOST_STATE_PATH):
            try:
                with open(BOOST_STATE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_boost_state(self):
        """Saves current boost progress to disk so computer-clock time is preserved across restarts."""
        try:
            data = self._load_boost_state()
            now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for g in self.games:
                key = str(g.appid)
                target_sec = max(0, int(round(self.boost_threshold_hours * 3600)) - (g.initial_playtime_mins * 60))
                rem_sec = g.remaining_boost_seconds(self.boost_threshold_hours)
                data[key] = {
                    "title": g.title,
                    "steam_baseline_mins": g.initial_playtime_mins,
                    "target_boost_seconds": target_sec,
                    "boost_seconds_served": round(g.boost_seconds_served, 1),
                    "remaining_boost_seconds": rem_sec,
                    "completed": (rem_sec <= 0),
                    "last_updated": now_iso
                }
            with open(BOOST_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def log(self, msg, level="INFO"):
        now_str = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{now_str}] {msg}"
        if self.on_log:
            self.on_log(formatted, level)

    def load_games(self):
        """Loads badges with card drops from Steam client, synchronizes baseline and local PC boost progress."""
        self.log("Загрузка списка значков и точного времени игр из Steam...", "INFO")
        try:
            items = self.steam_client.get_badges_with_drops()
            saved_state = self._load_boost_state()

            loaded_games = []
            for g in items:
                appid = g['appid']
                title = g['title']
                drops_left = g['drops_left']
                steam_mins = g.get('playtime_minutes', 0)

                key = str(appid)
                saved = saved_state.get(key, {})
                saved_baseline = saved.get("steam_baseline_mins")
                saved_served = float(saved.get("boost_seconds_served", 0.0))
                saved_comp = bool(saved.get("completed", False))

                # Determine effective baseline and served boost time
                if saved_baseline is not None:
                    # If Steam's server playtime has progressed beyond what we tracked before:
                    if steam_mins > saved_baseline + int(saved_served / 60):
                        effective_baseline = steam_mins
                        effective_served = 0.0
                    else:
                        effective_baseline = saved_baseline
                        effective_served = saved_served
                else:
                    effective_baseline = steam_mins
                    effective_served = 0.0

                item = GameItem(appid, title, drops_left, effective_baseline)
                item.boost_seconds_served = effective_served

                # If previously completed or threshold reached on PC clock:
                if saved_comp or item.remaining_boost_seconds(self.boost_threshold_hours) <= 0:
                    needed_total = max(0, int(round(self.boost_threshold_hours * 3600)) - effective_baseline * 60)
                    item.boost_seconds_served = max(effective_served, float(needed_total))
                    item.status = "Готов к фарму"

                loaded_games.append(item)

            self.games = loaded_games
            self.initial_total_drops = sum(g.current_drops for g in self.games)
            self._save_boost_state()

            self.log(f"Загружено игр с карточками: {len(self.games)}. Всего карточек: {self.initial_total_drops}", "SUCCESS")
            
            need_boost = [g for g in self.games if g.needs_boost(self.boost_threshold_hours)]
            if need_boost:
                self.log(f"ℹ Игр, требующих разгона до 2ч: {len(need_boost)}.", "INFO")
                for g in need_boost:
                    rem_str = g.remaining_boost_str(self.boost_threshold_hours)
                    served_str = format_duration(g.boost_seconds_served)
                    self.log(f"   • {g.title}: База Steam={g.initial_playtime_mins} мин. + Разогнано на ПК={served_str} -> осталось на таймере ПК: {rem_str}", "INFO")
            else:
                self.log(f"ℹ Все игры имеют более {self.boost_threshold_hours:.1f} ч. наигранности. Разгон не требуется.", "INFO")

            if self.on_stats_updated:
                self.on_stats_updated()
            return True
        except Exception as e:
            self.log(f"Ошибка загрузки значков: {e}", "ERROR")
            return False

    @property
    def total_remaining_drops(self):
        return sum(g.current_drops for g in self.games if g.status not in ("✅ Завершено", "Завершено", "⏭ Пропущено", "Пропущено"))

    @property
    def current_game(self):
        if 0 <= self.current_index < len(self.games):
            return self.games[self.current_index]
        return None

    def get_time_estimation_details(self):
        """Calculates realistic time estimation with parallel boost + farm."""
        boost_sec_needed = 0
        games_needing_boost = [g for g in self.games if g.needs_boost(self.boost_threshold_hours)]
        if self.boost_enabled and games_needing_boost:
            boost_sec_needed = max(
                0,
                max(g.remaining_boost_seconds(self.boost_threshold_hours) for g in games_needing_boost)
            )

        # Games ready to farm immediately (playtime >= 2h)
        ready_games = [g for g in self.games if not g.needs_boost(self.boost_threshold_hours)]
        ready_drops = sum(g.current_drops for g in ready_games if g.status not in ("✅ Завершено", "Завершено", "⏭ Пропущено", "Пропущено"))
        ready_farm_sec = ready_drops * (self.minutes_per_card * 60)

        # Games that will be farmed after boost
        boost_drops = sum(g.current_drops for g in games_needing_boost if g.status not in ("✅ Завершено", "Завершено", "⏭ Пропущено", "Пропущено"))
        boost_farm_sec = boost_drops * (self.minutes_per_card * 60)

        # Because boost and ready-game farming run IN PARALLEL:
        # Time for initial overlap is max(boost_sec_needed, ready_farm_sec)
        if self.boost_enabled and games_needing_boost:
            total_sec_avg = max(boost_sec_needed, ready_farm_sec) + boost_farm_sec
            total_sec_min = max(boost_sec_needed, ready_drops * 15 * 60) + (boost_drops * 15 * 60)
            total_sec_max = max(boost_sec_needed, ready_drops * 30 * 60) + (boost_drops * 30 * 60)
        else:
            total_drops = self.total_remaining_drops
            total_sec_avg = total_drops * (self.minutes_per_card * 60)
            total_sec_min = total_drops * (15 * 60)
            total_sec_max = total_drops * (30 * 60)

        total_drops = self.total_remaining_drops
        farm_sec_avg = total_drops * (self.minutes_per_card * 60)

        return {
            'boost_needed': bool(games_needing_boost and self.boost_enabled),
            'boost_games_count': len(games_needing_boost),
            'ready_games_count': len(ready_games),
            'boost_sec': boost_sec_needed,
            'farm_sec_avg': farm_sec_avg,
            'total_sec_avg': total_sec_avg,
            'total_sec_min': total_sec_min,
            'total_sec_max': total_sec_max,
            'total_drops': total_drops
        }

    def format_estimated_time(self):
        details = self.get_time_estimation_details()
        total_str = format_duration(details['total_sec_avg'])
        min_str = format_duration(details['total_sec_min'])
        max_str = format_duration(details['total_sec_max'])
        
        if details['boost_needed']:
            boost_str = format_duration(details['boost_sec'])
            if details['ready_games_count'] > 0:
                return f"~{total_str} (параллельно разгон {boost_str})"
            else:
                return f"~{total_str} (~{boost_str} разгон)"
        else:
            return f"~{total_str} (от {min_str} до {max_str})"

    def start(self):
        if self.is_running and not self.is_paused:
            return True

        if not self.sam_path or not os.path.isfile(self.sam_path):
            self.log("Путь к SAM.Game.exe не найден! Укажите путь в настройках.", "ERROR")
            return False

        if not self.games:
            success = self.load_games()
            if not success or not self.games:
                self.log("Нет игр для фарма!", "WARNING")
                return False

        if self.is_paused:
            self.is_paused = False
            self.log("Фарм возобновлен.", "INFO")
            with self._proc_lock:
                if self.current_game and self.current_game.status == "▶ Фармится":
                    self.current_proc = self._start_process(self.current_game.appid)
                for appid in list(self.boost_procs.keys()):
                    if self.boost_procs[appid] is None:
                        self.boost_procs[appid] = self._start_process(appid)
            if self.on_phase_changed:
                self.on_phase_changed(self.current_phase)
            if self.on_stats_updated:
                self.on_stats_updated()
            return True

        self.is_running = True
        self.is_paused = False
        self._stop_event.clear()
        self._skip_event.clear()
        self._skip_boost_event.clear()
        self._force_check_event.clear()
        
        if not self.session_start_time:
            self.session_start_time = datetime.now()

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.log("🚀 Фармер успешно запущен!", "SUCCESS")
        return True

    def pause(self):
        if not self.is_running or self.is_paused:
            return
        self.is_paused = True
        self._pause_all_processes()
        self._save_boost_state()
        self.log("⏸ Фарм поставлен на паузу.", "WARNING")
        if self.on_phase_changed:
            self.on_phase_changed("PAUSED")
        if self.on_stats_updated:
            self.on_stats_updated()

    def stop(self):
        self.is_running = False
        self.is_paused = False
        self._stop_event.set()
        self._save_boost_state()
        self._stop_all_processes()
        self.current_phase = "IDLE"
        self.current_cycle_remaining = 0
        self.log("⏹ Фарм остановлен пользователем.", "WARNING")
        if self.on_phase_changed:
            self.on_phase_changed("IDLE")
        if self.on_stats_updated:
            self.on_stats_updated()

    def skip_current_game(self):
        if self.is_running and self.current_phase == "FARMING" and self.current_game:
            self.log(f"⏭ Пропуск текущей игры: {self.current_game.title}", "INFO")
            self.current_game.status = "⏭ Пропущено"
            self._skip_event.set()

    def skip_boost_phase(self):
        """Allows user to skip 2-hour boost and proceed to farming immediately."""
        self._skip_boost_event.set()
        with self._proc_lock:
            for appid, p in list(self.boost_procs.items()):
                if p:
                    self._stop_process(p)
            self.boost_procs.clear()
            for g in self.games:
                if g.status.startswith("⚡"):
                    g.status = "Готов к фарму"
                    # Mark served time so it stays ready in saved state
                    needed_total = max(0, int(round(self.boost_threshold_hours * 3600)) - g.initial_playtime_mins * 60)
                    g.boost_seconds_served = max(g.boost_seconds_served, float(needed_total))
        self._save_boost_state()
        self.log("⚡ Разгон до 2 часов пропущен пользователем. Все игры готовы к прямому фарму!", "WARNING")
        if self.on_stats_updated:
            self.on_stats_updated()

    def trigger_immediate_check(self):
        """Forces an immediate close, check, and control check sequence."""
        if self.is_running and self.current_phase == "FARMING" and self.current_game:
            self.log("🔄 Запрошена немедленная проверка: закрываем игру и проверяем выпадение карточек...", "INFO")
            self._force_check_event.set()

    def _start_process(self, appid):
        sam_dir = os.path.dirname(self.sam_path)
        cmd = [self.sam_path, str(appid)]

        flags = 0
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            if self.launch_hidden:
                startupinfo.wShowWindow = 0  # SW_HIDE
                flags |= 0x08000000  # CREATE_NO_WINDOW
            elif self.launch_minimized:
                startupinfo.wShowWindow = 6  # SW_MINIMIZE

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=sam_dir,
                startupinfo=startupinfo,
                creationflags=flags
            )
            # Assign to Windows Job Object so child is forcefully killed if Python terminates
            self.job_manager.assign_process(proc)
            return proc
        except Exception as e:
            self.log(f"Ошибка запуска SAM для AppID {appid}: {e}", "ERROR")
            return None

    def _stop_process(self, proc):
        if not proc:
            return
        pid = proc.pid
        try:
            proc.terminate()
            proc.wait(timeout=1.5)
        except Exception:
            pass
        if proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=1.0)
            except Exception:
                pass
        if proc.poll() is None and pid:
            kill_pid_cleanly(pid)

    def _pause_all_processes(self):
        with self._proc_lock:
            if self.current_proc:
                self._stop_process(self.current_proc)
                self.current_proc = None
            for appid, proc in list(self.boost_procs.items()):
                if proc:
                    self._stop_process(proc)
                self.boost_procs[appid] = None

    def _stop_all_processes(self):
        with self._proc_lock:
            if self.current_proc:
                self._stop_process(self.current_proc)
                self.current_proc = None
            for appid, proc in list(self.boost_procs.items()):
                if proc:
                    self._stop_process(proc)
            self.boost_procs.clear()
        cleanup_all_sam_processes()

    def _boost_worker(self, boost_games):
        """
        Runs parallel boost for games with < 2 hours of playtime in the background.
        Tracks exact computer-clock elapsed seconds and verifies completion against PC time.
        """
        self.log("=" * 60, "INFO")
        self.log(f"⚡ [ПАРАЛЛЕЛЬНЫЙ РАЗГОН] Запущен фоновый буст для {len(boost_games)} игр до 2 часов.", "INFO")
        self.log("💡 Игры разгоняются одновременно в фоне по часам ПК, пока идет поочередный фарм готовых игр!", "INFO")
        self.log("=" * 60, "INFO")

        # Start SAM for each game needing boost
        for g in boost_games:
            if self._stop_event.is_set() or self._skip_boost_event.is_set() or not self.is_running:
                break
            rem_str = g.remaining_boost_str(self.boost_threshold_hours)
            g.status = f"⚡ Разгон ({rem_str})"
            p = self._start_process(g.appid)
            if p:
                with self._proc_lock:
                    self.boost_procs[g.appid] = p
            time.sleep(0.2)

        self._save_boost_state()
        if self.on_stats_updated:
            self.on_stats_updated()

        now = time.time()
        last_tick = now
        last_state_save = now
        last_ui_update = now

        while self.is_running and not self._stop_event.is_set():
            if self._skip_boost_event.is_set():
                self.log("⚡ Фоновый разгон остановлен: игры переведены на прямой фарм.", "WARNING")
                with self._proc_lock:
                    for appid, p in list(self.boost_procs.items()):
                        if p:
                            self._stop_process(p)
                    self.boost_procs.clear()
                    for g in boost_games:
                        if g.status.startswith("⚡"):
                            g.status = "Готов к фарму"
                            needed_total = max(0, int(round(self.boost_threshold_hours * 3600)) - g.initial_playtime_mins * 60)
                            g.boost_seconds_served = max(g.boost_seconds_served, float(needed_total))
                self._save_boost_state()
                if self.on_stats_updated:
                    self.on_stats_updated()
                break

            if self.is_paused:
                last_tick = time.time()
                time.sleep(0.5)
                continue

            time.sleep(1.0)
            now = time.time()
            elapsed_dt = max(0.0, now - last_tick)
            last_tick = now

            still_boosting = 0
            with self._proc_lock:
                for g in boost_games:
                    if g.appid in self.boost_procs:
                        proc = self.boost_procs[g.appid]
                        if proc is not None:
                            g.boost_seconds_served += elapsed_dt

                        rem_sec = g.remaining_boost_seconds(self.boost_threshold_hours)
                        if rem_sec <= 0:
                            # Reached exact required boost duration on computer clock
                            self.log(f"✅ Игра '{g.title}' достигла 2.0 часов на часах ПК ({g.total_playtime_str})! Разгон завершен.", "SUCCESS")
                            if self.boost_procs[g.appid]:
                                self._stop_process(self.boost_procs[g.appid])
                            del self.boost_procs[g.appid]
                            g.status = "Готов к фарму"
                            if self.on_stats_updated:
                                self.on_stats_updated()
                        else:
                            rem_str = format_duration(rem_sec)
                            g.status = f"⚡ Разгон ({rem_str})"
                            still_boosting += 1

            if now - last_state_save >= 10.0:
                last_state_save = now
                self._save_boost_state()

            if now - last_ui_update >= 2.0:
                last_ui_update = now
                if self.on_stats_updated:
                    self.on_stats_updated()

            if still_boosting == 0:
                self._save_boost_state()
                self.log("🎉 [ФОНОВЫЙ РАЗГОН ЗАВЕРШЕН] Все игры успешно разогнаны до 2 часов на часах компьютера!", "SUCCESS")
                if self.on_stats_updated:
                    self.on_stats_updated()
                break

    def _farm_single_game(self, game):
        """Farms an individual ready game with Close & Check cycles until done or skipped."""
        game.status = "▶ Фармится"
        if self.on_game_changed:
            self.on_game_changed(game)
        if self.on_stats_updated:
            self.on_stats_updated()

        self.log(f"🎮 Запуск фарма: \"{game.title}\" (AppID: {game.appid}). Нужно карточек: {game.current_drops}", "INFO")

        self.current_proc = self._start_process(game.appid)
        if not self.current_proc:
            game.status = "Ошибка"
            return

        cycle_start_time = time.time()
        cycle_target_sec = self.cycle_duration_min * 60
        self._skip_event.clear()
        self._force_check_event.clear()

        while self.is_running and not self._stop_event.is_set():
            if self._skip_event.is_set():
                self._stop_process(self.current_proc)
                self.current_proc = None
                break

            if self.is_paused:
                time.sleep(1)
                continue

            time.sleep(1)
            game.farm_seconds += 1

            cycle_elapsed = time.time() - cycle_start_time
            self.current_cycle_remaining = max(0, int(cycle_target_sec - cycle_elapsed))

            if self._force_check_event.is_set() or cycle_elapsed >= cycle_target_sec:
                forced = self._force_check_event.is_set()
                self._force_check_event.clear()

                # 1. Close process to sync session
                game.status = "🔄 Закрытие и проверка..."
                if forced:
                    self.log(f"🔄 [Ручная проверка] Закрываем '{game.title}' для синхронизации Steam...", "INFO")
                else:
                    self.log(f"🔄 Сессия {self.cycle_duration_min} мин. завершена. Закрываем '{game.title}' для синхронизации Steam...", "INFO")

                self._stop_process(self.current_proc)
                self.current_proc = None
                if self.on_stats_updated:
                    self.on_stats_updated()

                time.sleep(3)  # Allow Steam to process game close

                # 2. Check #1 (Dual Verification: gamecards + badges page)
                new_drops = self.steam_client.check_game_drops(game.appid)
                badge_drops = self.steam_client.check_badges_page_drops(game.appid)

                # If either check indicates 0, the game has 100% completed card drops!
                if new_drops == 0 or badge_drops == 0:
                    verified_drops = 0
                elif new_drops is not None and badge_drops is not None:
                    verified_drops = min(new_drops, badge_drops)
                elif new_drops is not None:
                    verified_drops = new_drops
                else:
                    verified_drops = badge_drops

                card_dropped = False

                if verified_drops is not None and verified_drops < game.current_drops:
                    card_dropped = True
                    dropped = game.current_drops - verified_drops
                    game.session_dropped += dropped
                    self.total_session_dropped += dropped
                    game.current_drops = verified_drops
                    game.last_drop_time = datetime.now()

                    self.log(f"✨ ПОЛУЧЕНА КАРТОЧКА (+{dropped})! Игра: \"{game.title}\". Осталось: {verified_drops}", "SUCCESS")
                    if self.on_card_dropped:
                        self.on_card_dropped(game, dropped)
                    if self.on_stats_updated:
                        self.on_stats_updated()

                    if verified_drops == 0:
                        game.status = "✅ Завершено"
                        self.log(f"🏆 Все доступные карточки для \"{game.title}\" получены! (Подтверждено проверкой значков Steam)", "SUCCESS")
                        time.sleep(2)
                        break
                    else:
                        time.sleep(2)
                        self.current_proc = self._start_process(game.appid)
                        game.status = "▶ Фармится"
                        cycle_start_time = time.time()
                        self.log(f"🎮 Перезапуск \"{game.title}\" (осталось получить: {verified_drops} карт)...", "INFO")
                elif verified_drops == 0:
                    game.current_drops = 0
                    game.status = "✅ Завершено"
                    self.log(f"🏆 Все доступные карточки для \"{game.title}\" получены! (Подтверждено проверкой значков Steam)", "SUCCESS")
                    if self.on_stats_updated:
                        self.on_stats_updated()
                    time.sleep(2)
                    break
                else:
                    # 20-second control check wait
                    game.status = f"⏳ Контроль ({self.control_check_delay_sec}с)..."
                    self.log(f"⏳ Карточка пока не отобразилась. Ждем {self.control_check_delay_sec} сек. для контрольной проверки Steam...", "INFO")
                    if self.on_stats_updated:
                        self.on_stats_updated()

                    for _ in range(self.control_check_delay_sec):
                        if self._stop_event.is_set() or not self.is_running or self._skip_event.is_set():
                            break
                        time.sleep(1)

                    if self._stop_event.is_set() or not self.is_running or self._skip_event.is_set():
                        break

                    # 3. Check #2 (Control Check with Dual Verification)
                    new_drops2 = self.steam_client.check_game_drops(game.appid)
                    badge_drops2 = self.steam_client.check_badges_page_drops(game.appid)

                    if new_drops2 == 0 or badge_drops2 == 0:
                        verified_drops2 = 0
                    elif new_drops2 is not None and badge_drops2 is not None:
                        verified_drops2 = min(new_drops2, badge_drops2)
                    elif new_drops2 is not None:
                        verified_drops2 = new_drops2
                    else:
                        verified_drops2 = badge_drops2

                    if verified_drops2 is not None and verified_drops2 < game.current_drops:
                        card_dropped = True
                        dropped = game.current_drops - verified_drops2
                        game.session_dropped += dropped
                        self.total_session_dropped += dropped
                        game.current_drops = verified_drops2
                        game.last_drop_time = datetime.now()

                        self.log(f"✨ ПОЛУЧЕНА КАРТОЧКА НА КОНТРОЛЬНОЙ ПРОВЕРКЕ (+{dropped})! Игра: \"{game.title}\". Осталось: {verified_drops2}", "SUCCESS")
                        if self.on_card_dropped:
                            self.on_card_dropped(game, dropped)
                        if self.on_stats_updated:
                            self.on_stats_updated()

                        if verified_drops2 == 0:
                            game.status = "✅ Завершено"
                            self.log(f"🏆 Все доступные карточки для \"{game.title}\" получены! (Подтверждено проверкой значков Steam)", "SUCCESS")
                            time.sleep(2)
                            break
                        else:
                            time.sleep(2)
                            self.current_proc = self._start_process(game.appid)
                            game.status = "▶ Фармится"
                            cycle_start_time = time.time()
                            self.log(f"🎮 Перезапуск \"{game.title}\" (осталось получить: {verified_drops2} карт)...", "INFO")
                    elif verified_drops2 == 0:
                        game.current_drops = 0
                        game.status = "✅ Завершено"
                        self.log(f"🏆 Все доступные карточки для \"{game.title}\" получены! (Подтверждено проверкой значков Steam)", "SUCCESS")
                        if self.on_stats_updated:
                            self.on_stats_updated()
                        time.sleep(2)
                        break
                    else:
                        self.log(f"ℹ Карточка пока не выпала (осталось: {game.current_drops}). Перезапускаем \"{game.title}\" на новый цикл...", "INFO")
                        self.current_proc = self._start_process(game.appid)
                        game.status = "▶ Фармится"
                        cycle_start_time = time.time()
                        if self.on_stats_updated:
                            self.on_stats_updated()

            if self.on_stats_updated:
                self.on_stats_updated()

    def _run_loop(self):
        """
        Main orchestrator:
        - Launches background parallel boost for games with < 2 hours.
        - Immediately farms ready games (>= 2h) 1 by 1 in parallel with boost!
        - Acts as Phase 1 (Boost only) only when 0 games are ready for farming.
        """
        try:
            # 1. Start parallel boost in background for games with < 2 hours
            boost_games = [g for g in self.games if g.needs_boost(self.boost_threshold_hours) and g.current_drops > 0]
            if self.boost_enabled and boost_games:
                threading.Thread(target=self._boost_worker, args=(boost_games,), daemon=True).start()

            # 2. Farming orchestrator loop
            while self.is_running and not self._stop_event.is_set():
                if self.is_paused:
                    time.sleep(1)
                    continue

                # Find next game ready for farming:
                # - has drops remaining
                # - not finished / not skipped
                # - not currently in active boost process
                # - either has >= 2h played, or boost was skipped
                ready_game = None
                with self._proc_lock:
                    for idx, g in enumerate(self.games):
                        if g.current_drops > 0 and g.status not in ("✅ Завершено", "Завершено", "⏭ Пропущено", "Пропущено"):
                            if self._skip_boost_event.is_set() or not g.needs_boost(self.boost_threshold_hours):
                                if g.appid not in self.boost_procs:
                                    ready_game = g
                                    self.current_index = idx
                                    break

                if not ready_game:
                    # Check if any games are still in boost or waiting for boost
                    with self._proc_lock:
                        still_boosting = len(self.boost_procs) > 0
                        has_pending = any(
                            g.current_drops > 0 and g.status not in ("✅ Завершено", "Завершено", "⏭ Пропущено", "Пропущено")
                            for g in self.games
                        )
                        any_needs_boost = any(g.needs_boost(self.boost_threshold_hours) for g in self.games)

                    if has_pending and (still_boosting or any_needs_boost) and not self._skip_boost_event.is_set():
                        # Phase 1: Only boost is active (no games ready for farming yet)
                        if self.current_phase != "BOOST":
                            self.current_phase = "BOOST"
                            self.phase_start_time = datetime.now()
                            if self.on_phase_changed:
                                self.on_phase_changed("BOOST")
                        time.sleep(1)
                        continue
                    else:
                        # All cards collected across all games!
                        self.log("🎉 Все карточки для всех игр в очереди успешно получены!", "SUCCESS")
                        self.current_phase = "COMPLETED"
                        if self.on_phase_changed:
                            self.on_phase_changed("COMPLETED")
                        break

                # We have a ready game!
                if self.current_phase != "FARMING":
                    self.current_phase = "FARMING"
                    self.phase_start_time = datetime.now()
                    if self.on_phase_changed:
                        self.on_phase_changed("FARMING")

                self._farm_single_game(ready_game)

        except Exception as e:
            self.log(f"Критическая ошибка в цикле фарма: {e}", "ERROR")
        finally:
            self._save_boost_state()
            self._stop_all_processes()
            self.is_running = False
            self.current_cycle_remaining = 0
            if self.current_phase != "COMPLETED":
                self.current_phase = "IDLE"
            if self.on_phase_changed:
                self.on_phase_changed(self.current_phase)
            if self.on_stats_updated:
                self.on_stats_updated()
