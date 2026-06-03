
import os
import glob
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, colorchooser
import ttkbootstrap
import vlc
import time
import sys
import subprocess
import json

class StaroeRadioPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("StaroeRadio Player")
        self.root.geometry("900x700")
        self.root.resizable(True, True)

        # VLC
        self.instance = vlc.Instance(
            "--network-caching=5000",
            "--file-caching=5000",
            "--live-caching=5000",
            "--http-reconnect",
            "--no-video"
        )

        self.player = self.instance.media_player_new()

        # Привязка события окончания трека для автоперехода
        self.event_manager = self.player.event_manager()
        self.event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_track_end)

        # Переменные
        self.current_results = []
        self.current_index = -1
        self.is_playing = False
        self.user_seeking = False
        self.auto_play_enabled = True

        if getattr(sys, 'frozen', False):
            self.script_dir = os.path.dirname(sys.executable)
        else:
            self.script_dir = os.path.dirname(os.path.abspath(__file__))

        self.state_file = os.path.join(self.script_dir, "player_state.json")
        self.colors_file = os.path.join(self.script_dir, "colors_config.json")
        self.history_dir = os.path.join(self.script_dir, "History")
        self._ensure_history_dir()

        # Загрузка конфига цветов
        self.load_colors_config()

        # UI
        self.setup_ui()

        # Загрузка файлов
        self.refresh_files()

        # Загрузка сохранённого состояния
        self.load_state()

        # Таймер обновления
        self.update_position()

    def setup_ui(self):
        # ========= PanedWindow для изменяемых границ =========
        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg="#212121", sashwidth=5)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Левая часть - результаты поиска (включая поисковую строку)
        list_frame = ttk.LabelFrame(paned_window, text="Результаты поиска", padding="5")
        paned_window.add(list_frame, width=400)

        # === ПАНЕЛЬ ПОИСКА (ПЕРЕНЕСЕНА СЮДА) ===
        search_frame = ttk.Frame(list_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(search_frame, text="Поисковый запрос:").pack(side=tk.LEFT, padx=(0, 5))

        self.search_entry = ttk.Entry(search_frame, width=40)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.search_entry.bind("<Return>", lambda e: self.search())
        self.search_entry.bind("<Control-v>", self.paste)
        self.search_entry.bind("<Control-V>", self.paste)
        self.root.bind("<Control-v>", self.paste_root)
        self.root.bind("<Control-V>", self.paste_root)

        ttk.Button(search_frame, text="📋 Вставить", command=self.paste).pack(side=tk.LEFT, padx=(0, 5))
        # ttk.Button(search_frame, text="🔍 Найти", command=self.search).pack(side=tk.LEFT, padx=(0, 5))
        # ttk.Button(search_frame, text="📁 Обновить файлы", command=self.refresh_files).pack(side=tk.LEFT)

        self.file_count_label = ttk.Label(search_frame, text="")
        self.file_count_label.pack(side=tk.RIGHT, padx=(10, 0))
        # ====================================

        # Список результатов
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.results_listbox = tk.Text(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 10),
            height=15,
            width=50
        )
        self.results_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.results_listbox.yview)

        # Конфигурируем теги для результатов поиска из конфига
        results_tags = self.log_colors.get("results_tags", {})
        for tag_name, tag_config in results_tags.items():
            fg = tag_config.get("foreground", "#FFFFFF")
            bg = tag_config.get("background")
            if bg:
                self.results_listbox.tag_config(tag_name, foreground=fg, background=bg)
            else:
                self.results_listbox.tag_config(tag_name, foreground=fg)

        # Привязываем клик мышью для выбора трека
        self.results_listbox.bind("<Button-1>", self.on_listbox_click)

        # Кнопки управления списком
        list_btn_frame = ttk.Frame(list_frame)
        list_btn_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Button(
            list_btn_frame,
            text="💾 Сохранить M3U",
            command=self.save_m3u
        ).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(
            list_btn_frame,
            text="💿 Скачать выбранное",
            command=self.download_selected_mp3
        ).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(
            list_btn_frame,
            text="💿 Скачать все",
            command=self.download_all_mp3
        ).pack(side=tk.LEFT)

        # Второе PanedWindow для плеера и лога (вертикальное)
        right_paned = tk.PanedWindow(paned_window, orient=tk.VERTICAL, bg="#212121", sashwidth=5)
        paned_window.add(right_paned, width=400)

        # ========= Плеер =========
        control_frame = ttk.LabelFrame(right_paned, text="Плеер", padding="5")
        right_paned.add(control_frame, height=250)

        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(pady=5)

        ttk.Button(btn_frame, text="⏮ Пред.", command=self.prev_track).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="▶ Play", command=self.play_current).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="⏸ Pause", command=self.pause).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="⏹ Stop", command=self.stop).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="⏭ След.", command=self.next_track).pack(side=tk.LEFT, padx=2)

        # Громкость
        vol_frame = ttk.Frame(control_frame)
        vol_frame.pack(pady=10, fill=tk.X)

        ttk.Label(vol_frame, text="Громкость:").pack(side=tk.LEFT, padx=(0, 5))

        self.volume_var = tk.IntVar(value=80)

        self.volume_slider = ttk.Scale(
            vol_frame,
            from_=0,
            to=100,
            variable=self.volume_var,
            orient=tk.HORIZONTAL,
            command=self.set_volume
        )
        self.volume_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.volume_label = ttk.Label(vol_frame, text="80%", width=5)
        self.volume_label.pack(side=tk.LEFT, padx=(5, 0))

        # Прогресс
        progress_frame = ttk.Frame(control_frame)
        progress_frame.pack(fill=tk.X, pady=10)

        self.time_current = ttk.Label(progress_frame, text="00:00")
        self.time_current.pack(side=tk.LEFT, padx=(0, 5))

        self.progress_slider = ttk.Scale(
            progress_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL
        )
        self.progress_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.progress_slider.bind("<Button-1>", self.start_seek)
        self.progress_slider.bind("<ButtonRelease-1>", self.end_seek)

        self.time_total = ttk.Label(progress_frame, text="00:00")
        self.time_total.pack(side=tk.RIGHT, padx=(5, 0))

        # Текущий трек (цвета из конфига)
        player_colors = self.log_colors.get("player_labels", {}).get("current_track", {})
        self.current_label = tk.Label(
            control_frame,
            text="Нет трека",
            wraplength=250,
            fg=player_colors.get("foreground", "#072DA9"),
            bg=player_colors.get("background", "#212121")
        )
        self.current_label.pack(pady=10)

        # ========= Лог =========
        log_frame = ttk.LabelFrame(right_paned, text="Лог", padding="5")
        right_paned.add(log_frame, height=200)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=6,
            font=("Consolas", 9)
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Конфигурируем теги для лога из конфига
        log_tags = self.log_colors.get("log_tags", {})
        for tag_name, tag_config in log_tags.items():
            fg = tag_config.get("foreground", "#FFFFFF")
            bg = tag_config.get("background")
            if bg:
                self.log_text.tag_config(tag_name, foreground=fg, background=bg)
            else:
                self.log_text.tag_config(tag_name, foreground=fg)

        # Сохраняем ссылку на PanedWindow для сохранения позиций
        self.paned_window = paned_window
        self.right_paned = right_paned

    def refresh_files(self):
        txt_files = glob.glob(os.path.join(self.script_dir, "*.txt"))
        self.txt_files = txt_files

        if txt_files:
            self.log(f"📁 Найдено файлов: {len(txt_files)}")
            # self.file_count_label.config(text=f"Файлов: {len(txt_files)}")
        else:
            self.log("❌ TXT файлы не найдены!")
            self.file_count_label.config(text="Нет TXT файлов")

    def search(self):
        query = self.search_entry.get().strip()

        if not query:
            messagebox.showwarning("Ошибка", "Введите поисковый запрос!")
            return

        if not self.txt_files:
            messagebox.showwarning("Ошибка", "Нет TXT файлов для поиска!")
            return

        self.log(f"🔍 Поиск: '{query}'")

        search_words = query.lower().split()
        results = []

        for file_path in self.txt_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    for line in file:
                        line = line.strip()

                        if not line:
                            continue

                        line_lower = line.lower()

                        if all(word in line_lower for word in search_words):

                            if '\t' in line:
                                parts = line.split('\t', 1)
                                audio_id = parts[0]
                                title = parts[1]
                            else:
                                parts = line.split(None, 1)
                                audio_id = parts[0] if parts else ""
                                title = parts[1] if len(parts) > 1 else line

                            results.append({
                                'id': audio_id,
                                'title': title
                            })

            except Exception as e:
                self.log(f"❌ Ошибка чтения {file_path}: {e}")

        self.current_results = results
        self.update_results_list()

        if results:
            self.log(f"✅ Найдено: {len(results)} треков")
        else:
            self.log("❌ Совпадений не найдено")

    def update_results_list(self):
        self.results_listbox.config(state=tk.NORMAL)
        self.results_listbox.delete(1.0, tk.END)

        for i, item in enumerate(self.current_results, 1):
            # Номер (красный)
            num_text = f"{i:3}. "
            self.results_listbox.insert(tk.END, num_text, "number")
            
            # ID (голубой)
            id_text = f"{item['id']} | "
            self.results_listbox.insert(tk.END, id_text, "id")
            
            # Название (зелёный)
            self.results_listbox.insert(tk.END, item['title'] + "\n", "title")

        self.results_listbox.config(state=tk.DISABLED)

    def on_listbox_click(self, event):
        """Обработка клика мышью по окну результатов"""
        # Получаем позицию клика
        pos = self.results_listbox.index(f"@{event.x},{event.y}")
        line_num = int(pos.split('.')[0]) - 1
        
        if 0 <= line_num < len(self.current_results):
            self.current_index = line_num
            self.highlight_selected_line()
            self.play_current()

    def highlight_selected_line(self):
        """Выделить текущую строку цветом"""
        # Удаляем старое выделение
        self.results_listbox.tag_remove("selected", "1.0", tk.END)
        
        # Выделяем новую строку
        if 0 <= self.current_index < len(self.current_results):
            line_start = f"{self.current_index + 1}.0"
            line_end = f"{self.current_index + 1}.end"
            self.results_listbox.tag_add("selected", line_start, line_end)

    def play_selected(self):
        # Получаем текущую строку в Text виджете
        try:
            cursor_pos = self.results_listbox.index(tk.INSERT)
            line_num = int(cursor_pos.split('.')[0]) - 1
            
            if 0 <= line_num < len(self.current_results):
                self.current_index = line_num
                self.highlight_selected_line()
                self.play_current()
            else:
                messagebox.showwarning("Ошибка", "Выберите трек из списка!")
        except:
            messagebox.showwarning("Ошибка", "Выберите трек из списка!")

    def play_current(self):
        if self.current_index < 0 or self.current_index >= len(self.current_results):
            return
        
        self.auto_play_enabled = True # Сброс флага при новом воспроизведении

        track = self.current_results[self.current_index]

        url = f"https://staroeradio.ru/ap/get_mp3_radio_128.php?id={track['id']}"

        self.log(f"▶ Воспроизведение: {track['title']}")

        self._log_to_history(track)

        self.current_label.config(
            text=f"Сейчас: {track['title']}"
        )

        media = self.instance.media_new(url)

        media.add_option(":http-user-agent=Mozilla/5.0")

        self.player.stop()

        self.player.set_media(media)

        time.sleep(0.1)

        self.player.play()

        self.player.audio_set_volume(self.volume_var.get())

        self.is_playing = True

    def pause(self):
        if self.player.is_playing():
            self.player.pause()
            self.is_playing = False
            self.log("⏸ Пауза")

        elif self.player.get_state() == vlc.State.Paused:
            self.player.play()
            self.is_playing = True
            self.log("▶ Возобновлено")

    def stop(self):
        self.player.stop()
        self.is_playing = False
        self.auto_play_enabled = False  # Отключаем автовоспроизведение при ручной остановке
        self.current_label.config(text="Нет трека")
        self.progress_slider.set(0)
        self.time_current.config(text="00:00")
        self.time_total.config(text="00:00")
        self.log("⏹ Остановлено")
        # Включаем обратно через небольшую задержку, чтобы событие окончания не сработало
        self.root.after(500, lambda: setattr(self, 'auto_play_enabled', True))  

    def next_track(self):
        if self.current_results and self.current_index + 1 < len(self.current_results):
            self.current_index += 1
            self.play_current()
        else:
            self.log("📋 Это последний трек в списке")

    def on_track_end(self, event):
        """Автоматический переход к следующему треку при окончании текущего"""
        if self.auto_play_enabled:
            self.root.after(0, self.auto_next_track)   

    def auto_next_track(self):
        """Автоматическое воспроизведение следующего трека"""
        if self.current_results and self.current_index + 1 < len(self.current_results):
            self.current_index += 1
            self.highlight_selected_line()  # Обновляем выделение в списке
            self.play_current()
            self.log(f"⏭ Автопереход к следующему треку")
        elif self.current_results and self.current_index + 1 >= len(self.current_results):
            self.log("📋 Достигнут конец плейлиста")
            # Опционально: остановить плеер и сбросить выделение
            self.stop()

    def prev_track(self):
        if self.current_results and self.current_index > 0:
            self.current_index -= 1
            self.play_current()
        else:
            self.log("📋 Это первый трек в списке")

    def set_volume(self, *args):
        volume = int(float(self.volume_var.get()))

        self.player.audio_set_volume(volume)

        self.volume_label.config(text=f"{volume}%")

    def start_seek(self, event):
        self.user_seeking = True

    def end_seek(self, event):
        if self.player.get_length() > 0:
            position = self.progress_slider.get() / 100
            self.player.set_position(position)

        self.user_seeking = False

    def update_position(self):
        try:
            if self.player.is_playing():

                current_time = self.player.get_time() // 1000
                total_time = self.player.get_length() // 1000

                if total_time > 0:
                    position = (current_time / total_time) * 100

                    if not self.user_seeking:
                        self.progress_slider.set(position)

                self.time_current.config(
                    text=self.format_time(current_time)
                )

                self.time_total.config(
                    text=self.format_time(total_time)
                )

        except Exception as e:
            self.log(f"❌ Ошибка обновления позиции: {e}")

        self.root.after(1000, self.update_position)

    def format_time(self, seconds):
        if seconds < 0:
            seconds = 0

        minutes = seconds // 60
        secs = seconds % 60

        return f"{minutes:02d}:{secs:02d}"

    def save_m3u(self):
        if not self.current_results:
            messagebox.showwarning("Ошибка", "Нет результатов для сохранения!")
            return

        query = self.search_entry.get().strip()

        if not query:
            query = "search"

        safe_query = "".join(
            c for c in query
            if c.isalnum() or c in (' ', '-', '_')
        ).strip()

        safe_query = safe_query[:50]

        if not safe_query:
            safe_query = "playlist"

        m3u_filename = f"{safe_query}.m3u"

        m3u_filepath = os.path.join(
            self.script_dir,
            m3u_filename
        )

        try:
            with open(m3u_filepath, 'w', encoding='utf-8') as f:

                f.write("#EXTM3U\n")
                f.write(f"#PLAYLIST:{query}\n\n")

                for item in self.current_results:

                    url = (
                        "https://staroeradio.ru/ap/"
                        f"get_mp3_radio_128.php?id={item['id']}"
                    )

                    f.write(f"#EXTINF:-1,{item['title']}\n")
                    f.write(f"{url}\n\n")

            self.log(
                f"✅ Плейлист сохранен: "
                f"{m3u_filename} "
                f"({len(self.current_results)} треков)"
            )

            messagebox.showinfo(
                "Успех",
                f"Плейлист сохранен:\n{m3u_filename}"
            )

        except Exception as e:
            self.log(f"❌ Ошибка сохранения: {e}")

            messagebox.showerror(
                "Ошибка",
                f"Не удалось сохранить плейлист:\n{e}"
            )

    def smart_truncate(self, text, max_length=50):
        """
        Умная обрезка текста до max_length символов.
        Если последнее слово не вмещается целиком, обрезает до предпоследнего целого слова.
        """
        if len(text) <= max_length:
            return text

        # Обрезаем до max_length
        truncated = text[:max_length]

        # Ищем последний пробел
        last_space = truncated.rfind(' ')

        if last_space > 0:
            # Обрезаем до последнего пробела
            return truncated[:last_space]
        else:
            # Если пробелов нет, просто обрезаем до max_length
            return truncated

    def download_selected_mp3(self):
        """Скачать только выбранный трек"""
        # Получаем позицию курсора в Text виджете
        try:
            cursor_pos = self.results_listbox.index(tk.INSERT)
            line_num = int(cursor_pos.split('.')[0]) - 1
            
            if 0 <= line_num < len(self.current_results):
                selected_item = self.current_results[line_num]
                self._download_mp3([selected_item])
            else:
                messagebox.showwarning("Ошибка", "Выберите трек из списка!")
        except:
            messagebox.showwarning("Ошибка", "Выберите трек из списка!")

    def download_all_mp3(self):
        """Скачать все треки из результатов поиска"""
        if not self.current_results:
            messagebox.showwarning("Ошибка", "Нет результатов для скачивания!")
            return

        self._download_mp3(self.current_results)

    def _download_mp3(self, items):
        """Внутренняя функция для скачивания MP3 файлов"""
        query = self.search_entry.get().strip()

        if not query:
            query = "search"

        # Создаем безопасное имя папки
        safe_query = "".join(
            c for c in query
            if c.isalnum() or c in (' ', '-', '_')
        ).strip()

        safe_query = safe_query[:50]

        if not safe_query:
            safe_query = "downloads"

        # Создаем папку
        download_dir = os.path.join(self.script_dir, safe_query)

        try:
            os.makedirs(download_dir, exist_ok=True)
        except Exception as e:
            self.log(f"❌ Ошибка создания папки: {e}")
            messagebox.showerror("Ошибка", f"Не удалось создать папку:\n{e}")
            return

        # Проверяем наличие mutagen
        try:
            from mutagen.mp3 import MP3
            from mutagen.id3 import TIT2
        except ImportError:
            self.log("⚠️  Mutagen не установлен, теги не будут добавлены")
            has_mutagen = False
        else:
            has_mutagen = True

        # Скачиваем файлы
        saved_count = 0
        error_count = 0

        for item in items:
            try:
                # Создаем имя файла: ID_название (умная обрезка до 50 символов)
                title_short = self.smart_truncate(item['title'], max_length=50)
                # Очищаем неподходящие символы
                title_short = "".join(
                    c for c in title_short
                    if c.isalnum() or c in (' ', '-', '_', '.')
                ).strip()

                filename = f"{item['id']}_{title_short}.mp3"
                filepath = os.path.join(download_dir, filename)

                # Пропускаем, если файл уже существует
                if os.path.exists(filepath):
                    self.log(f"⏭️  Файл уже существует: {filename}")
                    saved_count += 1
                    continue

                # Скачиваем файл
                url = f"https://staroeradio.ru/ap/get_mp3_radio_128.php?id={item['id']}"

                import urllib.request
                import urllib.error

                try:
                    urllib.request.urlretrieve(url, filepath)
                except (urllib.error.HTTPError, urllib.error.URLError) as e:
                    self.log(f"⚠️  Не удалось скачать {filename}: {e}")
                    error_count += 1
                    continue

                # Добавляем теги ID3
                if has_mutagen:
                    try:
                        audio = MP3(filepath)
                        if audio.tags is None:
                            audio.add_tags()

                        audio.tags["TIT2"] = TIT2(encoding=3, text=[item['title']])
                        audio.save()
                    except Exception as e:
                        self.log(f"⚠️  Ошибка добавления тега для {filename}: {e}")

                saved_count += 1
                self.log(f"✅ Сохранен: {filename}")

            except Exception as e:
                self.log(f"❌ Ошибка при обработке {item['id']}: {e}")
                error_count += 1

        # Итоговое сообщение
        message = (
            f"Сохранено файлов: {saved_count}\n"
            f"Ошибок: {error_count}\n"
            f"Папка: {safe_query}"
        )

        self.log(f"📁 Скачивание завершено: {message.replace(chr(10), ' | ')}")

        messagebox.showinfo("Успех", message)

    def paste(self, event=None):
        """Вставка из буфера обмена через Windows API"""
        try:
            # Используем PowerShell для получения текста из буфера
            result = subprocess.run(
                ['powershell', '-Command', 'Get-Clipboard'],
                capture_output=True,
                text=True,
                timeout=2
            )
            text = result.stdout.strip()
            
            if text:
                self.search_entry.delete(0, tk.END)
                self.search_entry.insert(0, text)
                self.search_entry.focus()
        except Exception as e:
            # Резервный способ - встроенный clipboard_get
            try:
                text = self.root.clipboard_get()
                self.search_entry.delete(0, tk.END)
                self.search_entry.insert(0, text)
                self.search_entry.focus()
            except:
                pass
        
        if event:
            return "break"

    def paste_root(self, event=None):
        """Глобальная вставка из буфера"""
        self.paste(event)
        if event:
            return "break"

    def save_state(self):
        """Сохранить состояние приложения перед выходом"""
        try:
            # Получаем текущую позицию плеера (в миллисекундах)
            player_time = self.player.get_time()
            player_position = player_time if player_time > 0 else -1

            # Получаем ID трека, который сейчас воспроизводится или был выбран
            current_track_id = None
            if 0 <= self.current_index < len(self.current_results):
                current_track_id = self.current_results[self.current_index]['id']

            # Получаем размер и позицию окна
            window_geometry = self.root.geometry()

            # Получаем позиции разделителей PanedWindow
            paned_sash_pos = self.paned_window.sash_coord(0)[0] if self.paned_window.sash_coord(0) else 400
            right_paned_sash_pos = self.right_paned.sash_coord(0)[1] if self.right_paned.sash_coord(0) else 250

            state = {
                "search_query": self.search_entry.get(),
                "current_results": self.current_results,
                "current_index": self.current_index,
                "player_position": player_position,
                "current_track_id": current_track_id,
                "volume": self.volume_var.get(),
                "window_geometry": window_geometry,
                "paned_sash_position": paned_sash_pos,
                "right_paned_sash_position": right_paned_sash_pos
            }

            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            self.log(f"💾 Состояние сохранено (позиция: {player_position}мс, громкость: {self.volume_var.get()}%)")

        except Exception as e:
            self.log(f"⚠️  Ошибка сохранения состояния: {e}")

    def load_state(self):
        """Загрузить сохранённое состояние приложения"""
        try:
            if not os.path.exists(self.state_file):
                return

            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            # Восстанавливаем размер и позицию окна
            window_geometry = state.get("window_geometry")
            if window_geometry:
                try:
                    self.root.geometry(window_geometry)
                    self.log(f"🪟 Размер окна восстановлен")
                except:
                    self.log(f"⚠️  Не удалось восстановить размер окна")

            # Восстанавливаем позиции разделителей PanedWindow
            paned_sash_pos = state.get("paned_sash_position")
            right_paned_sash_pos = state.get("right_paned_sash_position")

            if paned_sash_pos:
                try:
                    self.root.after(100, lambda: self.paned_window.sash_place(0, int(paned_sash_pos), 1))
                except:
                    pass

            if right_paned_sash_pos:
                try:
                    self.root.after(100, lambda: self.right_paned.sash_place(0, 1, int(right_paned_sash_pos)))
                except:
                    pass

            # Восстанавливаем поисковый запрос
            search_query = state.get("search_query", "")
            if search_query:
                self.search_entry.insert(0, search_query)

            # Восстанавливаем результаты поиска
            self.current_results = state.get("current_results", [])
            self.current_index = state.get("current_index", -1)

            if self.current_results:
                self.update_results_list()
                self.log(f"✅ Восстановлены результаты поиска: {len(self.current_results)} треков")

                # Восстанавливаем название трека в плеере
                if self.current_index >= 0 and self.current_index < len(self.current_results):
                    track_title = self.current_results[self.current_index]['title']
                    self.current_label.config(text=f"Сейчас: {track_title}")
                # ================================

            # Восстанавливаем громкость
            volume = state.get("volume", 80)
            self.volume_var.set(volume)
            self.set_volume(volume)
            self.log(f"🔊 Громкость восстановлена: {volume}%")

            # Восстанавливаем позицию плеера
            player_position = state.get("player_position", -1)
            current_track_id = state.get("current_track_id")

            if player_position > 0 and current_track_id and 0 <= self.current_index < len(self.current_results):
                # Запускаем трек и устанавливаем позицию
                self.root.after(500, lambda: self._restore_playback(player_position))

        except Exception as e:
            self.log(f"⚠️  Ошибка загрузки состояния: {e}")

    def _restore_playback(self, position):
        """Восстановить воспроизведение с сохранённой позиции"""
        try:
            if 0 <= self.current_index < len(self.current_results):
                track = self.current_results[self.current_index]
                url = f"https://staroeradio.ru/ap/get_mp3_radio_128.php?id={track['id']}"

                media = self.instance.media_list_new()
                media.add_media(self.instance.media_new(url))
                self.player.set_media(media[0])
                self.player.play()

                # Даём плееру время на загрузку, затем устанавливаем позицию
                self.root.after(1000, lambda: self.player.set_time(int(position)))
                self.log(f"▶ Воспроизведение восстановлено с позиции {position}мс")
        except Exception as e:
            self.log(f"⚠️  Ошибка восстановления воспроизведения: {e}")

    def log(self, message):
        from datetime import datetime

        timestamp = datetime.now().strftime("%H:%M:%S")

        # Вставляем временную метку (серый цвет)
        self.log_text.insert(
            tk.END,
            f"[{timestamp}] ",
            "timestamp"
        )

        # Определяем цвет в зависимости от типа сообщения
        if message.startswith("✅"):
            tag = "success"
        elif message.startswith("❌"):
            tag = "error"
        elif message.startswith("⚠️"):
            tag = "warning"
        else:
            tag = "info"

        # Вставляем само сообщение с тегом
        self.log_text.insert(
            tk.END,
            f"{message}\n",
            tag
        )

        self.log_text.see(tk.END)

    def load_colors_config(self):
        """Загрузить конфиг цветов, создать если не существует"""
        default_colors = {
            "results_tags": {
                "number": {
                    "foreground": "#FF6B6B",
                    "description": "Номер трека (красный)"
                },
                "id": {
                    "foreground": "#4ECDC4",
                    "description": "ID трека (голубой)"
                },
                "title": {
                    "foreground": "#A159F9",
                    "description": "Название трека (фиолетовый)"
                },
                "selected": {
                    "background": "#1E3A8A",
                    "foreground": "#FFFFFF",
                    "description": "Выбранная строка (синий фон)"
                }
            },
            "log_tags": {
                "timestamp": {
                    "foreground": "#B0BEC5",
                    "description": "Временная метка (серый)"
                },
                "success": {
                    "foreground": "#81C784",
                    "description": "Успех (зелёный)"
                },
                "error": {
                    "foreground": "#E57373",
                    "description": "Ошибка (красный)"
                },
                "warning": {
                    "foreground": "#FFB74D",
                    "description": "Предупреждение (оранжевый)"
                },
                "info": {
                    "foreground": "#64B5F6",
                    "description": "Информация (синий)"
                }
            },
            "player_labels": {
                "current_track": {
                    "foreground": "#1A48DD",
                    "background": "#212121",
                    "description": "Текущий трек в плеере"
                }
            }
        }

        # Если конфиг не существует, создаём его
        if not os.path.exists(self.colors_file):
            try:
                with open(self.colors_file, 'w', encoding='utf-8') as f:
                    json.dump(default_colors, f, ensure_ascii=False, indent=2)
                self.log_colors = default_colors
                print(f"✅ Создан конфиг цветов: {self.colors_file}")
            except Exception as e:
                print(f"❌ Ошибка создания конфига: {e}")
                self.log_colors = default_colors
        else:
            # Загружаем существующий конфиг
            try:
                with open(self.colors_file, 'r', encoding='utf-8') as f:
                    self.log_colors = json.load(f)
                print(f"✅ Загружен конфиг цветов: {self.colors_file}")
            except Exception as e:
                print(f"⚠️  Ошибка загрузки конфига, используются стандартные цвета: {e}")
                self.log_colors = default_colors
    
    def _ensure_history_dir(self):
        """Создать папку History если не существует"""
        if not os.path.exists(self.history_dir):
            os.makedirs(self.history_dir)
            self.log("📁 Создана папка History")

    def _log_to_history(self, track):
        """Записать проигранный трек в историю"""
        from datetime import datetime
    
        today = datetime.now().strftime("%d.%m.%Y")
        history_file = os.path.join(self.history_dir, f"{today}.txt")
    
        time_str = datetime.now().strftime("%H:%M:%S")
    
        with open(history_file, 'a', encoding='utf-8') as f:
            f.write(f"{time_str}\n")
            f.write(f"{track['id']} -- {track['title']}\n")
            f.write("\n")
    
        self.log(f"📝 Записано в историю: {track['title'][:40]}...")

    def on_closing(self):
        self.save_state()
        self.player.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = ttkbootstrap.Window(themename="darkly")

    app = StaroeRadioPlayer(root)

    root.protocol("WM_DELETE_WINDOW", app.on_closing)

    root.mainloop()
