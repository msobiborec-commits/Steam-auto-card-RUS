"""
Steam Client module for Steam Card Farmer.
Handles automatic cookie extraction from running Steam processes,
retrieval of exact minute-level playtime for all account games via Steam WebAPI,
badge page parsing, and individual gamecard drop monitoring.
"""

import ctypes
from ctypes import wintypes
import subprocess
import re
import json
import requests
from bs4 import BeautifulSoup

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
PAGE_READWRITE = 0x04
PAGE_READONLY = 0x02
PAGE_EXECUTE_READ = 0x20
PAGE_EXECUTE_READWRITE = 0x40

kernel32 = ctypes.windll.kernel32
TH32CS_SNAPPROCESS = 0x00000002

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

def get_process_pids_by_name(process_name):
    pids = []
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == -1 or snapshot == 0xFFFFFFFFFFFFFFFF:
        return pids
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    if kernel32.Process32First(snapshot, ctypes.byref(entry)):
        target = process_name.lower()
        target_exe = target if target.endswith('.exe') else (target + '.exe')
        while True:
            name = entry.szExeFile.decode('utf-8', errors='ignore').lower()
            if name == target or name == target_exe:
                pids.append(entry.th32ProcessID)
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    kernel32.CloseHandle(snapshot)
    return pids

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]

def parse_playtime(text):
    """
    Fallback parser for Steam badge playtime string (Russian or English).
    Returns float hours.
    """
    if not text:
        return 0.0
    text = text.lower().replace(',', '.')
    
    # Hours match
    hm = re.search(r'([\d\.]+)\s*(?:ч|hr|hour)', text)
    if hm:
        try:
            return float(hm.group(1))
        except ValueError:
            pass
            
    # Minutes match
    mm = re.search(r'([\d\.]+)\s*(?:мин|min)', text)
    if mm:
        try:
            return float(mm.group(1)) / 60.0
        except ValueError:
            pass
            
    return 0.0

class SteamClient:
    def __init__(self, manual_cookie=None):
        self.manual_cookie = manual_cookie
        self.cookies = {}
        self.steam_id = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache'
        }
        self.refresh_cookies()

    def refresh_cookies(self):
        """Extract cookies automatically from steamwebhelper or use manual cookie."""
        if self.manual_cookie:
            self.cookies = {
                'steamLoginSecure': self.manual_cookie.strip(),
                'Steam_Language': 'russian'
            }
            if '||' in self.manual_cookie:
                self.steam_id = self.manual_cookie.split('||')[0]
            return True

        cookie_str = self._extract_from_steam_processes()
        if cookie_str:
            self.cookies = {
                'steamLoginSecure': cookie_str,
                'Steam_Language': 'russian'
            }
            if '||' in cookie_str:
                self.steam_id = cookie_str.split('||')[0]
            return True
        return False

    def _extract_from_steam_processes(self):
        pids = get_process_pids_by_name("steamwebhelper")
        if not pids:
            return None

        jwt_pattern = re.compile(rb'(7656\d{13}(?:%7C%7C|\|\|)[A-Za-z0-9_\-\.]+)')
        candidates = []

        for pid in pids:
            hProcess = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
            if not hProcess:
                continue
            try:
                address = 0
                mbi = MEMORY_BASIC_INFORMATION()
                mbi_size = ctypes.sizeof(mbi)
                while kernel32.VirtualQueryEx(hProcess, ctypes.c_void_p(address), ctypes.byref(mbi), mbi_size):
                    if mbi.State == MEM_COMMIT and mbi.Protect in (PAGE_READWRITE, PAGE_READONLY, PAGE_EXECUTE_READ, PAGE_EXECUTE_READWRITE):
                        if mbi.RegionSize <= 16 * 1024 * 1024:
                            buf = ctypes.create_string_buffer(mbi.RegionSize)
                            bytesRead = ctypes.c_size_t()
                            if kernel32.ReadProcessMemory(hProcess, ctypes.c_void_p(mbi.BaseAddress), buf, mbi.RegionSize, ctypes.byref(bytesRead)):
                                data = buf.raw[:bytesRead.value]
                                if b'steamLoginSecure' in data:
                                    pos = 0
                                    while True:
                                        pos = data.find(b'steamLoginSecure', pos)
                                        if pos == -1:
                                            break
                                        chunk = data[pos:pos+1500]
                                        for m in jwt_pattern.findall(chunk):
                                            val = m.decode('ascii', errors='ignore').replace('%7C%7C', '||')
                                            parts = val.split('||')
                                            if len(parts) == 2 and len(parts[1].split('.')) == 3:
                                                candidates.append(val)
                                        pos += 16
                    address += mbi.RegionSize
                    if address >= 0x7FFFFFFFFFFF or candidates:
                        break
                if candidates:
                    break
            finally:
                kernel32.CloseHandle(hProcess)

        return candidates[0] if candidates else None

    def get_owned_games_playtime(self):
        """
        Retrieves exact playtime in minutes for all games on the account.
        Uses Steam's official IPlayerService/GetOwnedGames WebAPI with the web token
        extracted from the user's SSR community profile data.
        Returns: dict of {appid (int): playtime_forever_minutes (int)}
        """
        if not self.cookies:
            self.refresh_cookies()
        if not self.steam_id:
            return {}

        url = f"https://steamcommunity.com/profiles/{self.steam_id}/games/?tab=all"
        try:
            resp = requests.get(url, cookies=self.cookies, headers=self.headers, timeout=12)
            if resp.status_code != 200:
                return {}

            soup = BeautifulSoup(resp.text, 'html.parser')
            s_tag = soup.find('script', id='valve-ssr-data')
            if not s_tag or not s_tag.string:
                return {}

            ssr_data = json.loads(s_tag.string)
            loader_data = ssr_data.get('loaderData', [])
            if not loader_data:
                return {}

            token_info = json.loads(loader_data[0]) if isinstance(loader_data[0], str) else loader_data[0]
            token = token_info.get('strWebAPIToken')
            if not token:
                return {}

            api_url = (
                f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
                f"?access_token={token}&steamid={self.steam_id}&include_appinfo=1&include_played_free_games=1"
            )
            api_resp = requests.get(api_url, timeout=12)
            if api_resp.status_code != 200:
                return {}

            games = api_resp.json().get('response', {}).get('games', [])
            playtime_map = {}
            for g in games:
                appid = g.get('appid')
                mins = g.get('playtime_forever', 0)
                if appid is not None:
                    playtime_map[int(appid)] = int(mins)
            return playtime_map
        except Exception:
            return {}

    def get_badges_with_drops(self):
        """
        Parses all badges pages and returns list of games with card drops remaining,
        with exact minute-level playtime from GetOwnedGames.
        Returns: list of dicts:
            [{
                'appid': int,
                'title': str,
                'drops_left': int,
                'playtime_minutes': int
            }]
        """
        if not self.cookies:
            if not self.refresh_cookies():
                raise Exception("Не удалось получить авторизацию Steam. Убедитесь, что Steam запущен и вы вошли в аккаунт.")

        # Fetch exact playtimes across the entire library in one fast WebAPI request
        playtime_map = self.get_owned_games_playtime()

        all_games = []
        page = 1
        visited_urls = set()

        while True:
            url = f"https://steamcommunity.com/my/badges/?p={page}"
            if url in visited_urls:
                break
            visited_urls.add(url)

            resp = requests.get(url, cookies=self.cookies, headers=self.headers, timeout=15)
            if resp.status_code != 200:
                raise Exception(f"Ошибка запроса значков: статус {resp.status_code}")

            resp.encoding = 'utf-8'
            soup = BeautifulSoup(resp.text, 'html.parser')
            rows = soup.find_all('div', class_='badge_row')
            if not rows:
                break

            for row in rows:
                progress_info = row.find('span', class_='progress_info_bold')
                if not progress_info:
                    continue

                text = progress_info.text.strip()
                if not ('карточ' in text.lower() or 'card' in text.lower() or 'drop' in text.lower()):
                    continue

                match = re.search(r'(\d+)', text)
                if not match:
                    continue
                drops_left = int(match.group(1))
                if drops_left <= 0:
                    continue

                # AppID
                link = row.find('a', href=re.compile(r'/gamecards/(\d+)'))
                if not link:
                    continue
                appid_match = re.search(r'/gamecards/(\d+)', link['href'])
                if not appid_match:
                    continue
                appid = int(appid_match.group(1))

                # Game Title
                title_el = row.find('div', class_='badge_title')
                title = ""
                if title_el:
                    for s in title_el.find_all(class_='badge_view_details'):
                        s.decompose()
                    for a in title_el.find_all('a'):
                        a.decompose()
                    title = title_el.get_text(strip=True)
                if not title:
                    title = f"AppID {appid}"

                # Exact Playtime in minutes: prioritize WebAPI exact minutes, fallback to HTML parsing
                if appid in playtime_map:
                    playtime_minutes = playtime_map[appid]
                else:
                    playtime_el = row.find('div', class_='badge_title_stats_playtime')
                    raw_playtime = playtime_el.get_text(strip=True) if playtime_el else ""
                    playtime_minutes = int(parse_playtime(raw_playtime) * 60)

                all_games.append({
                    'appid': appid,
                    'title': title,
                    'drops_left': drops_left,
                    'playtime_minutes': playtime_minutes
                })

            # Check pagination
            pagelinks = soup.find_all('a', class_='pagelink')
            has_next = any(p.text.strip() == str(page + 1) for p in pagelinks)
            if has_next:
                page += 1
            else:
                break

        return all_games

    def check_game_drops(self, appid):
        """
        Queries https://steamcommunity.com/my/gamecards/<appid>/
        Returns: drops_remaining (int) or None on request failure.
        """
        if not self.cookies:
            self.refresh_cookies()

        url = f"https://steamcommunity.com/my/gamecards/{appid}/"
        try:
            resp = requests.get(url, cookies=self.cookies, headers=self.headers, timeout=12)
        except Exception:
            return None

        if resp.status_code == 403 or 'login' in resp.url.lower():
            if self.refresh_cookies():
                try:
                    resp = requests.get(url, cookies=self.cookies, headers=self.headers, timeout=12)
                except Exception:
                    return None
            else:
                return None

        if resp.status_code != 200:
            return None

        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
        progress_info = soup.find('span', class_='progress_info_bold')
        if not progress_info:
            all_text = soup.get_text().lower()
            if 'больше нет карточек' in all_text or 'no card drops remaining' in all_text or 'получили все' in all_text:
                return 0
            return 0

        text = progress_info.text.strip()
        match = re.search(r'(\d+)', text)
        if match and ('карточ' in text.lower() or 'card' in text.lower() or 'выпад' in text.lower()):
            return int(match.group(1))

        all_text = soup.get_text().lower()
        if 'больше нет карточек' in all_text or 'no card drops remaining' in all_text or 'получили все' in all_text:
            return 0

        return 0
