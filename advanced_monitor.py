# steam_monitor.py
import os
import sys
import time
import winreg
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Tuple

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AdvancedSteamMonitor:
    """Улучшенный монитор загрузок Steam с учетом паузы"""

    def __init__(self, steam_path=None):
        if steam_path:
            self.steam_path = Path(steam_path)
        else:
            self.steam_path = self._find_steam_path()

        if not self.steam_path:
            logger.error("Steam не найден на системе")
            sys.exit(1)

        logger.info(f"✅ Steam найден: {self.steam_path}")

        self.last_sizes = {}
        self.download_history = {}

    def _find_steam_path(self) -> Optional[Path]:
        """Находит путь установки Steam"""
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

    def get_download_info(self):
        """Получает полную информацию о загрузке"""
        info = {
            'game_name': 'Неизвестно',
            'app_id': '0',
            'progress': 0,
            'speed_mb': 0.0,
            'status': 'idle',  # downloading, paused, idle, completed
            'size_downloaded': 0,
            'size_total': 0
        }

        # Проверяем папку downloading
        downloading_path = self.steam_path / "steamapps" / "downloading"
        if downloading_path.exists():
            folders = list(downloading_path.iterdir())
            if folders:
                app_id = folders[0].name
                info['app_id'] = app_id

                # Получаем имя игры
                info['game_name'] = self._get_game_name(app_id)

                # Проверяем прогресс через appmanifest
                progress_data = self._get_download_progress(app_id)
                if progress_data:
                    info['progress'] = progress_data['progress']
                    info['size_downloaded'] = progress_data['downloaded']
                    info['size_total'] = progress_data['total']

                # Рассчитываем скорость по изменению размера папки
                speed = self._calculate_speed(app_id)
                info['speed_mb'] = speed

                # Определяем статус
                if speed > 0.1:  # Больше 100 KB/s
                    info['status'] = 'downloading'
                elif speed <= 0.1 and info['progress'] < 100:
                    info['status'] = 'paused'
                else:
                    info['status'] = 'idle'

        return info

    def _calculate_speed(self, app_id):
        """Рассчитывает скорость по изменению размера папки"""
        download_folder = self.steam_path / "steamapps" / "downloading" / app_id

        if not download_folder.exists():
            return 0.0

        # Считаем текущий размер
        current_size = 0
        file_count = 0
        for file_path in download_folder.rglob("*"):
            if file_path.is_file():
                current_size += file_path.stat().st_size
                file_count += 1

        current_time = time.time()

        # Сохраняем предыдущий размер
        if app_id not in self.last_sizes:
            self.last_sizes[app_id] = (current_time, current_size, file_count)
            return 0.0

        last_time, last_size, last_count = self.last_sizes[app_id]
        time_diff = current_time - last_time

        if time_diff >= 1:  # Если прошла хотя бы 1 секунда
            size_diff = current_size - last_size
            speed = size_diff / time_diff / (1024 * 1024)  # MB/s

            # Обновляем запись
            self.last_sizes[app_id] = (current_time, current_size, file_count)

            # Добавляем в историю для статистики
            if app_id not in self.download_history:
                self.download_history[app_id] = []
            self.download_history[app_id].append((current_time, speed))

            # Ограничиваем историю
            self.download_history[app_id] = [
                (t, s) for t, s in self.download_history[app_id]
                if current_time - t < 300  # 5 минут
            ]

            return round(speed, 2)

        return 0.0

    def _get_download_progress(self, app_id):
        """Получает прогресс загрузки из appmanifest"""
        manifest_file = self.steam_path / "steamapps" / f"appmanifest_{app_id}.acf"

        if manifest_file.exists():
            try:
                with open(manifest_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Ищем BytesDownloaded и SizeOnDisk
                import re
                downloaded_match = re.search(r'"BytesDownloaded"\s+"(\d+)"', content)
                total_match = re.search(r'"SizeOnDisk"\s+"(\d+)"', content)

                if downloaded_match and total_match:
                    downloaded = int(downloaded_match.group(1))
                    total = int(total_match.group(1))

                    if total > 0:
                        progress = (downloaded / total) * 100
                        return {
                            'progress': round(progress, 1),
                            'downloaded': downloaded,
                            'total': total
                        }
            except Exception as e:
                logger.error(f"Ошибка чтения appmanifest: {e}")

        return None

    def _get_game_name(self, app_id):
        """Получает название игры"""
        manifest_file = self.steam_path / "steamapps" / f"appmanifest_{app_id}.acf"

        if manifest_file.exists():
            try:
                with open(manifest_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '"name"' in line:
                            parts = line.strip().split('"')
                            if len(parts) >= 4:
                                return parts[3]
            except:
                pass

        return f"Игра (ID: {app_id})"

    def format_speed(self, speed_mb):
        """Форматирует скорость"""
        if speed_mb >= 100:
            return f"{speed_mb:.1f} MB/s"
        elif speed_mb >= 1:
            return f"{speed_mb:.2f} MB/s"
        elif speed_mb >= 0.001:
            return f"{speed_mb * 1024:.1f} KB/s"
        else:
            return "0 B/s"

    def start_monitoring(self, update_interval=60, duration_minutes=5):
        """Запускает мониторинг"""
        print("=" * 70)
        print("🎮 Steam Download Monitor - Реальный мониторинг")
        print(f"📁 Путь к Steam: {self.steam_path}")
        print(f"⏱  Интервал: {update_interval} сек, Длительность: {duration_minutes} мин")
        print("=" * 70)

        end_time = time.time() + (duration_minutes * 60)
        update_count = 0

        try:
            while time.time() < end_time:
                update_count += 1
                info = self.get_download_info()

                print(f"\n📊 Обновление #{update_count} - {datetime.now().strftime('%H:%M:%S')}")
                print("-" * 70)

                if info['app_id'] != '0':
                    # Определяем иконку статуса
                    if info['status'] == 'downloading':
                        status_icon = "⬇️"
                        status_text = "Загружается"
                    elif info['status'] == 'paused':
                        status_icon = "⏸️"
                        status_text = "На паузе"
                    else:
                        status_icon = "ℹ️"
                        status_text = info['status']

                    print(f"{status_icon} {info['game_name']}")
                    print(f"   AppID: {info['app_id']}")
                    print(f"   Статус: {status_text}")
                    print(f"   Скорость: {self.format_speed(info['speed_mb'])}")

                    if info['progress'] > 0:
                        print(f"   Прогресс: {info['progress']}%")
                        # Прогресс-бар
                        bars = min(20, int(info['progress'] / 5))
                        print(f"   [{'█' * bars}{'░' * (20 - bars)}]")

                    print(f"   Библиотека: {self.steam_path}")

                    # Показываем реальную скорость из Steam (39.3 Мбит/с = ~4.91 MB/s)
                    real_speed_mbps = info['speed_mb'] * 8  # MB/s → Мбит/с
                    print(f"   Скорость (Мбит/с): {real_speed_mbps:.1f}")
                else:
                    print("ℹ️  Активных загрузок не обнаружено")
                    print("💡 Совет: Начните загрузку игры в Steam")

                print("-" * 70)

                # Ожидание до следующего обновления
                wait_time = min(update_interval, end_time - time.time())
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

        for app_id in self.download_history:
            if self.download_history[app_id]:
                speeds = [s for _, s in self.download_history[app_id]]
                if speeds:
                    avg_speed = sum(speeds) / len(speeds)
                    max_speed = max(speeds)

                    print(f"\n🎮 {self._get_game_name(app_id)} (AppID: {app_id})")
                    print(f"   Средняя скорость: {self.format_speed(avg_speed)}")
                    print(f"   Максимальная скорость: {self.format_speed(max_speed)}")
                    print(f"   Всего измерений: {len(speeds)}")

        print("\n✅ Мониторинг завершен")