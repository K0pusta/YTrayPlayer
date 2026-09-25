YTrayPlayer — плеер для YouTube-музыки в системном трее.

УСТАНОВКА
=========
1. Распакуй архив в любую папку (например, C:\YTrayPlayer).
2. Запусти YTrayPlayer.exe.
3. Плеер появится в трее.

УПРАВЛЕНИЕ
==========
Левый клик по иконке в трее  — пауза/плей
Правый клик                  — меню

Глобальные хоткеи:
  Ctrl+Alt+P       — play/pause
  Ctrl+Alt+Right   — следующий трек
  Ctrl+Alt+Left    — предыдущий трек
  Ctrl+Alt+Up      — громче
  Ctrl+Alt+Down    — тише
  Ctrl+Alt+F       — добавить в избранное
  Ctrl+Alt+V       — играть ссылку из буфера обмена

АВТОЗАПУСК ПРИ ВХОДЕ В СИСТЕМУ
=============================
1. Нажми Win+R, введи: shell:startup
2. Положи туда ярлык на YTrayPlayer.exe
Готово — плеер будет запускаться при входе в Windows.

ОБНОВЛЕНИЕ
==========
Если YouTube перестал играть — правый клик по иконке → «Обновить yt-dlp».
Это скачает свежий yt-dlp, который умеет работать с текущим YouTube.

ДАННЫЕ
======
Все настройки, избранное и плейлисты лежат в папке data/ рядом с exe.
Удалил папку — сбросил всё.

## Лицензия

MIT

## Благодарности

- [mpv](https://mpv.io/) — воспроизведение
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — резолв YouTube
- [pystray](https://github.com/moses-palmer/pystray), [PySide6](https://www.qt.io/qt-for-python), [win11toast](https://github.com/GitHub30/win11toast)