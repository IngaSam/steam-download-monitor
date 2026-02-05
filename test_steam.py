import os
from pathlib import Path

steam_path = Path("C:/Program Files (x86)/Steam")

print("=" * 60)
print("DIAGNOSTIC: Steam Download Detection")
print("=" * 60)

# Проверка 1: Существует ли папка downloading?
downloading = steam_path / "steamapps" / "downloading"
print(f"✓ Папка downloading существует: {downloading.exists()}")

if downloading.exists():
    folders = list(downloading.iterdir())
    print(f"✓ Папок в downloading: {len(folders)}")

    if folders:
        for folder in folders:
            print(f"  - Найдена папка: {folder.name}")

        # Проверка 2: Размер папки
        test_folder = folders[0]
        total_size = sum(f.stat().st_size for f in test_folder.rglob('*') if f.is_file())
        print(f"✓ Размер папки {test_folder.name}: {total_size / (1024 * 1024):.2f} MB")

        # Проверка 3: Содержимое папки
        print(f"✓ Файлов в папке {test_folder.name}:")
        files = list(test_folder.rglob('*'))
        for i, file in enumerate(files[:10]):  # Показываем первые 10 файлов
            if file.is_file():
                print(f"    {file.name} ({file.stat().st_size / 1024:.1f} KB)")
    else:
        print("✗ Папка downloading пуста")
else:
    print(f"✗ Папка downloading не найдена по пути: {downloading}")

# Проверка 4: Альтернативные пути
print("\n" + "=" * 60)
print("Проверка альтернативных путей:")
alternative_paths = [
    Path("C:/Program Files/Steam"),
    Path(os.path.expanduser("~/Steam")),
    Path("D:/Steam"),  # если у вас есть диск D
]

for alt_path in alternative_paths:
    alt_downloading = alt_path / "steamapps" / "downloading"
    if alt_downloading.exists():
        print(f"✓ Найден альтернативный путь: {alt_path}")
        break

print("=" * 60)