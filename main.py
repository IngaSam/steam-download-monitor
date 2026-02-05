from steam_monitor import SteamDownloadMonitor


def main():
    print("=" * 60)
    print("Steam Download Monitor v2.0")
    print("Отслеживание скорости загрузки игр")
    print("=" * 60)

    monitor = SteamDownloadMonitor()
    monitor.start_monitoring(
        update_interval=60,  # секунды
        duration_minutes=5  # минут
    )


if __name__ == "__main__":
    main()