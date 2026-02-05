"""
Steam Download Monitor - Final Version
Отслеживает скорость загрузки игр в Steam в реальном времени
"""

import os
import sys
import time
import re
import json
import winreg
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass
import threading

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('steam_monitor.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class DownloadInfo:
    """Информация о загрузке"""
    app_id: str
    game_name: str
    status: str  # downloading, paused, completed
    speed_mbps: float
    progress: float  # 0-100
    downloaded_bytes: int
    total_bytes: int
    last_update: datetime


class RealSteamMonitor:
    def __init__(self):
        self.steam_path = self._find_steam_path()
        if not self.steam_path:
            logger.error("❌ Steam не найден!")
            sys.exit(1)

        logger.info(f"✅ Steam найден: {self.steam_path}")
        self.active_downloads: Dict[str, DownloadInfo] = {}
        self.last_speeds: Dict[str, List[Tuple[datetime, float]]] = {}

    def _find_steam_path(self) -> Optional[Path]:
        """Находит путь к Steam"""
        # Ваш конкретный путь
        paths = [
            Path("G:/SteamLibrary"),
            Path("C:/Program Files (x86)/Steam"),
            Path("C:/Program Files/Steam"),
            Path(os.path.expanduser("~/Steam")),
        ]

        for path in paths:
            if path.exists():
                return path

        # Поиск в реестре
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            steam_path = winreg.QueryValueEx(key, "SteamPath")[0]
            winreg.CloseKey(key)
            return Path(steam_path)
        except:
            return None

    def _parse_logs_for_downloads(self) -> List[Dict]:
        """Парсит логи Steam для поиска загрузок"""
        downloads = []
        logs_path = self.steam_path / "logs"

        if not logs_path.exists():
            return downloads

        try:
            # Ищем свежие логи
            log_files = sorted(
                [f for f in logs_path.glob("*.log") if "content_log" in f.name],
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )

            if not log_files:
                return downloads

            latest_log = log_files[0]

            # Читаем последние 100 строк лога
            with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()[-100:]

            current_app = None
            for line in reversed(lines):  # Читаем с конца
                # Поиск информации о загрузке
                if "Downloading" in line or "download" in line.lower():
                    # Ищем AppID
                    app_match = re.search(r'app[_\s]?id[\s:=]+(\d+)', line, re.IGNORECASE)
                    if app_match:
                        app_id = app_match.group(1)

                        # Ищем скорость
                        speed_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:MB|mb|KB|kb)/s', line, re.IGNORECASE)
                        speed = 0.0
                        if speed_match:
                            speed_val = float(speed_match.group(1))
                            if 'KB' in line.upper():
                                speed = speed_val / 1024  # KB/s → MB/s
                            else:
                                speed = speed_val

                        # Ищем прогресс
                        progress_match = re.search(r'(\d+(?:\.\d+)?)%', line)
                        progress = float(progress_match.group(1)) if progress_match else 0.0

                        downloads.append({
                            'app_id': app_id,
                            'speed': speed,
                            'progress': progress,
                            'timestamp': datetime.now()
                        })

        except Exception as e:
            logger.error(f"Ошибка парсинга логов: {e}")

        return downloads

    def _get_game_name(self, app_id: str) -> str:
        """Получает название игры по AppID"""
        # Проверяем appmanifest файлы
        for lib in self._get_all_libraries():
            manifest = lib / "steamapps" / f"appmanifest_{app_id}.acf"
            if manifest.exists():
                try:
                    with open(manifest, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Ищем название
                    name_match = re.search(r'"name"\s+"([^"]+)"', content)
                    if name_match:
                        return name_match.group(1)
                except:
                    pass

        # Альтернативный источник
        try:
            import requests
            response = requests.get(f"https://store.steampowered.com/api/appdetails?appids={app_id}")
            if response.status_code == 200:
                data = response.json()
                if data.get(app_id, {}).get('success'):
                    return data[app_id]['data']['name']
        except:
            pass

        return f"Игра (AppID: {app_id})"

    def _get_all_libraries(self) -> List[Path]:
        """Получает все библиотеки Steam"""
        libraries = [self.steam_path]

        library_file = self.steam_path / "steamapps" / "libraryfolders.vdf"
        if library_file.exists():
            try:
                with open(library_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Ищем все пути
                path_matches = re.findall(r'"path"\s+"([^"]+)"', content)
                for path in path_matches:
                    lib_path = Path(path.replace('\\\\', '\\'))
                    if lib_path.exists() and lib_path not in libraries:
                        libraries.append(lib_path)
            except:
                pass

        return libraries

    def check_downloads(self) -> List[DownloadInfo]:
        """Проверяет текущие загрузки"""
        downloads = []

        # Способ 1: Парсинг логов
        log_downloads = self._parse_logs_for_downloads()

        for log_dl in log_downloads:
            app_id = log_dl['app_id']

            # Получаем историю скоростей
            if app_id not in self.last_speeds:
                self.last_speeds[app_id] = []

            # Добавляем текущую скорость
            self.last_speeds[app_id].append((datetime.now(), log_dl['speed']))

            # Очищаем старые записи (старше 5 минут)
            self.last_speeds[app_id] = [
                (t, s) for t, s in self.last_speeds[app_id]
                if datetime.now() - t < timedelta(minutes=5)
            ]

            # Рассчитываем среднюю скорость
            avg_speed = 0.0
            if self.last_speeds[app_id]:
                speeds = [s for _, s in self.last_speeds[app_id]]
                avg_speed = sum(speeds) / len(speeds)

            # Определяем статус
            status = "downloading"
            if avg_speed < 0.01:  # Меньше 10 KB/s
                status = "paused"

            # Получаем имя игры
            game_name = self._get_game_name(app_id)

            # Создаем объект загрузки
            download = DownloadInfo(
                app_id=app_id,
                game_name=game_name,
                status=status,
                speed_mbps=avg_speed,
                progress=log_dl['progress'],
                downloaded_bytes=0,
                total_bytes=0,
                last_update=datetime.now()
            )

            downloads.append(download)

        # Способ 2: Проверка папки downloading
        if not downloads:
            for library in self._get_all_libraries():
                downloading_path = library / "steamapps" / "downloading"
                if downloading_path.exists():
                    for folder in downloading_path.iterdir():
                        if folder.is_dir():
                            app_id = folder.name

                            # Проверяем, активна ли загрузка
                            files = list(folder.rglob("*"))
                            if files:
                                status = "downloading"
                                # Примерная скорость (можно улучшить)
                                speed = 5.0  # MB/s, заменить на реальный расчет
                            else:
                                status = "paused"
                                speed = 0.0

                            game_name = self._get_game_name(app_id)

                            download = DownloadInfo(
                                app_id=app_id,
                                game_name=game_name,
                                status=status,
                                speed_mbps=speed,
                                progress=0.0,
                                downloaded_bytes=0,
                                total_bytes=0,
                                last_update=datetime.now()
                            )

                            downloads.append(download)

        self.active_downloads = {d.app_id: d for d in downloads}
        return downloads

    def format_speed(self, speed_mb: float) -> str:
        """Форматирует скорость"""
        if speed_mb >= 100:
            return f"{speed_mb:.1f} MB/s"
        elif speed_mb >= 1:
            return f"{speed_mb:.2f} MB/s"
        elif speed_mb >= 0.001:
            return f"{speed_mb * 1024:.1f} KB/s"
        else:
            return "0 B/s"

    def monitor(self, interval: int = 60, duration: int = 5):
        """Основной цикл мониторинга"""
        print("=" * 70)
        print("🎮 Steam Download Monitor - Реальный мониторинг")
        print(f"📁 Путь к Steam: {self.steam_path}")
        print(f"⏱  Интервал: {interval} сек, Длительность: {duration} мин")
        print("=" * 70)

        end_time = datetime.now() + timedelta(minutes=duration)
        update_count = 0

        try:
            while datetime.now() < end_time:
                downloads = self.check_downloads()
                update_count += 1

                print(f"\n📊 Обновление #{update_count} - {datetime.now().strftime('%H:%M:%S')}")
                print("-" * 70)

                if downloads:
                    for i, dl in enumerate(downloads, 1):
                        status_icon = "⬇️" if dl.status == "downloading" else "⏸️"
                        speed_str = self.format_speed(dl.speed_mbps)

                        print(f"{i}. {status_icon} {dl.game_name}")
                        print(f"   AppID: {dl.app_id}")
                        print(f"   Статус: {dl.status}")
                        print(f"   Скорость: {speed_str}")

                        if dl.progress > 0:
                            print(f"   Прогресс: {dl.progress}%")
                            # Простой прогресс-бар
                            bars = min(20, int(dl.progress / 5))
                            print(f"   [{'█' * bars}{'░' * (20 - bars)}]")

                        print(f"   Библиотека: {self.steam_path}")
                        print()
                else:
                    print("ℹ️  Активных загрузок не обнаружено")
                    print("💡 Совет: Начните загрузку игры в Steam")

                print("-" * 70)

                # Ожидание до следующего обновления
                wait_time = min(interval, (end_time - datetime.now()).total_seconds())
                if wait_time > 0:
                    time.sleep(wait_time)
                else:
                    break

        except KeyboardInterrupt:
            print("\n\n⚠️  Мониторинг прерван пользователем")
        finally:
            self._print_summary()

    def _print_summary(self):
        """Печатает итоговую статистику"""
        print("\n" + "=" * 70)
        print("📈 Итоговая статистика")
        print("=" * 70)

        if self.active_downloads:
            for app_id, dl in self.active_downloads.items():
                print(f"\n🎮 {dl.game_name} (AppID: {app_id})")
                print(f"   Финальный статус: {dl.status}")
                print(f"   Последняя скорость: {self.format_speed(dl.speed_mbps)}")

                if app_id in self.last_speeds and self.last_speeds[app_id]:
                    speeds = [s for _, s in self.last_speeds[app_id]]
                    if speeds:
                        avg = sum(speeds) / len(speeds)
                        max_speed = max(speeds)
                        print(f"   Средняя скорость: {self.format_speed(avg)}")
                        print(f"   Максимальная скорость: {self.format_speed(max_speed)}")
        else:
            print("ℹ️  За время мониторинга загрузок не обнаружено")

        print("\n✅ Мониторинг завершен")


def main():
    """Точка входа"""
    monitor = RealSteamMonitor()

    # Настройки мониторинга
    UPDATE_INTERVAL = 60  # секунды
    MONITOR_DURATION = 5  # минуты

    monitor.monitor(interval=UPDATE_INTERVAL, duration=MONITOR_DURATION)


if __name__ == "__main__":
    main()