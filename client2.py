import socket
import threading
import customtkinter as ctk
from tkinter import scrolledtext, messagebox, Toplevel


class RussianRouletteClient:
    def __init__(self):
        self.client_socket = None
        self.player_name = ""
        self.game_started = False
        self.is_my_turn = False
        self.players_list = []
        self.selection_window = None
        self.loading_label = None
        self.player_var = None

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("Русская рулетка")
        self.root.geometry("700x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.tabview = ctk.CTkTabview(self.root)
        self.tabview.pack(pady=10, padx=10, fill="both", expand=True)

        self.tabview.add("Подключение")
        self.tabview.add("Игра")
        self.tabview.add("Справка")
        self.tabview.add("О программе")

        self.create_connection_tab()
        self.create_game_tab()
        self.create_help_tab()
        self.create_about_tab()

        self.tabview.set("Подключение")

        self.root.mainloop()

    def create_connection_tab(self):
        tab = self.tabview.tab("Подключение")

        ctk.CTkLabel(tab, text="Подключение к серверу", font=("Arial", 16)).pack(pady=10)

        ctk.CTkLabel(tab, text="Адрес сервера:").pack()
        self.host_entry = ctk.CTkEntry(tab)
        self.host_entry.insert(0, "localhost")
        self.host_entry.pack(pady=5, fill="x", padx=20)

        ctk.CTkLabel(tab, text="Порт:").pack()
        self.port_entry = ctk.CTkEntry(tab)
        self.port_entry.insert(0, "12345")
        self.port_entry.pack(pady=5, fill="x", padx=20)

        ctk.CTkLabel(tab, text="Ваше имя:").pack()
        self.name_entry = ctk.CTkEntry(tab)
        self.name_entry.pack(pady=5, fill="x", padx=20)

        self.connect_button = ctk.CTkButton(tab, text="Подключиться", command=self.connect_to_server)
        self.connect_button.pack(pady=20)

        self.status_label = ctk.CTkLabel(tab, text="")
        self.status_label.pack()

    def create_game_tab(self):
        tab = self.tabview.tab("Игра")

        self.game_log = scrolledtext.ScrolledText(tab, state='disabled', height=20, wrap="word", font=("Arial", 12))
        self.game_log.pack(pady=10, padx=10, fill="both", expand=True)

        self.actions_frame = ctk.CTkFrame(tab)
        self.actions_frame.pack(pady=10, fill="x", padx=10)

        self.shoot_self_button = ctk.CTkButton(
            self.actions_frame,
            text="Выстрелить в себя",
            command=lambda: self.send_action("я"),
            width=150
        )
        self.shoot_self_button.pack(side="left", padx=5, pady=5, expand=True)

        self.shoot_player_button = ctk.CTkButton(
            self.actions_frame,
            text="Выстрелить в игрока",
            command=self.show_player_selection,
            width=150
        )
        self.shoot_player_button.pack(side="left", padx=5, pady=5, expand=True)

        self.info_button = ctk.CTkButton(
            self.actions_frame,
            text="Информация",
            command=lambda: self.send_action("инфо"),
            width=100
        )
        self.info_button.pack(side="left", padx=5, pady=5, expand=True)

        self.players_button = ctk.CTkButton(
            self.actions_frame,
            text="Список игроков",
            command=lambda: self.send_action("игроки"),
            width=120
        )
        self.players_button.pack(side="left", padx=5, pady=5, expand=True)

    def create_help_tab(self):
        tab = self.tabview.tab("Справка")
        help_text = """
        Правила игры "Русская рулетка":

        1. В игре участвует револьвер с некоторым количеством боевых и холостых патронов.
        2. В начале каждого раунда патроны случайным образом заряжаются в барабан.
        3. Когда наступает ваш ход, вы можете:
           - Выстрелить в себя (команда "я"). Если патрон холостой, вы получаете дополнительный ход.
           - Выстрелить в другого игрока (команда "игрок [имя]"). Если патрон холостой, ход переходит.
           - Посмотреть информацию о текущем количестве боевых и холостых патронов (команда "инфо").
           - Посмотреть список живых игроков и кто сейчас ходит (команда "игроки").

        4. Если выстрел боевой - игрок, в которого стреляли, выбывает из игры. Ход переходит.
        5. Игра продолжается, пока не останется один игрок.

        Управление:
        - Используйте кнопки на вкладке "Игра" для выполнения действий.
        - Следите за логом игры для получения информации от сервера.
        """
        help_label = ctk.CTkLabel(tab, text=help_text, justify="left", wraplength=600)
        help_label.pack(pady=20, padx=20, anchor="w")

    def create_about_tab(self):
        tab = self.tabview.tab("О программе")
        about_text = """
        Русская рулетка - клиент для игры по сети

        Версия: 1.2.2
        Разработчики: 
        - Мендыгалиев Д.С. 
        - Барсуков М.В.

        Под руководством: 
        - Тагирова Л.Ф.
        Особенности:
        - Подключение к серверу игры
        - Удобный графический интерфейс
        - Возможность играть с другими участниками

        Используемые технологии:
        - Python 3
        - CustomTkinter для интерфейса
        - Socket для сетевого взаимодействия
        """
        about_label = ctk.CTkLabel(tab, text=about_text, justify="left", wraplength=600)
        about_label.pack(pady=20, padx=20, anchor="w")

    def connect_to_server(self):
        host = self.host_entry.get().strip()
        port_str = self.port_entry.get().strip()
        self.player_name = self.name_entry.get().strip()

        if not self.player_name:
            messagebox.showerror("Ошибка", "Пожалуйста, введите ваше имя.")
            return

        if not host:
            messagebox.showerror("Ошибка", "Пожалуйста, введите адрес сервера.")
            return

        if not port_str:
            messagebox.showerror("Ошибка", "Пожалуйста, введите порт сервера.")
            return

        try:
            port = int(port_str)
            if not (1 <= port <= 65535):
                messagebox.showerror("Ошибка", "Порт должен быть числом от 1 до 65535.")
                return
        except ValueError:
            messagebox.showerror("Ошибка", "Порт должен быть числом.")
            return

        try:
            self.status_label.configure(text="Подключение...")
            self.root.update_idletasks()

            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.settimeout(5)
            self.client_socket.connect((host, port))
            self.client_socket.settimeout(None)

            welcome_msg_bytes = self.client_socket.recv(1024)
            welcome_msg = welcome_msg_bytes.decode('utf-8').strip()
            self.add_to_log(f"Сервер: {welcome_msg}")

            self.client_socket.send(self.player_name.encode('utf-8'))
            self.add_to_log(f"Вы: Имя '{self.player_name}' отправлено.")

            self.status_label.configure(text=f"Подключено как {self.player_name}", text_color="green")

            threading.Thread(target=self.receive_messages, daemon=True).start()

            self.tabview.set("Игра")
            self.connect_button.configure(state="disabled")

        except socket.timeout:
            messagebox.showerror("Ошибка", "Не удалось подключиться: превышено время ожидания.")
            self.status_label.configure(text="Ошибка подключения (timeout)", text_color="red")
            if self.client_socket:
                self.client_socket.close()
                self.client_socket = None
        except ConnectionRefusedError:
            messagebox.showerror("Ошибка", "Не удалось подключиться: сервер отклонил соединение.")
            self.status_label.configure(text="Ошибка подключения (refused)", text_color="red")
            if self.client_socket:
                self.client_socket.close()
                self.client_socket = None
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось подключиться: {str(e)}")
            self.status_label.configure(text=f"Ошибка: {str(e)}", text_color="red")
            if self.client_socket:
                self.client_socket.close()
                self.client_socket = None

    def receive_messages(self):
        buffer = ""
        while True:
            if not self.client_socket:
                break
            try:
                data_bytes = self.client_socket.recv(2048)
                if not data_bytes:
                    self.add_to_log("Сервер закрыл соединение.")
                    break

                buffer += data_bytes.decode('utf-8')

                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    single_message = message.strip()

                    if not single_message:
                        continue

                    self.add_to_log(f"Сервер: {single_message}")

                    # --- Новая, более строгая логика is_my_turn ---
                    if "Ваш ход!" in single_message:
                        self.is_my_turn = True
                    elif "Ход игрока " in single_message:
                        try:
                            announced_player_name = single_message.split("Ход игрока ")[1].strip()
                            if announced_player_name.lower() != self.player_name.lower():
                                self.is_my_turn = False
                        except IndexError:
                            pass
                    elif ("выбывает из игры!" in single_message and self.player_name in single_message) or \
                            ("=== ИГРА ОКОНЧЕНА ===" in single_message) or \
                            (
                                    "побеждает!" in single_message and self.player_name not in single_message and "Никто не" not in single_message):
                        self.is_my_turn = False
                    # Не сбрасываем is_my_turn по "=== ИГРА НАЧИНАЕТСЯ ===" без дополнительной проверки,
                    # так как "Ваш ход!" может прийти чуть позже или в том же блоке данных.
                    # Флаг is_my_turn должен меняться только при явном указании смены хода.

                    # --- Остальная логика ---
                    if "Живые игроки:" in single_message or "Доступные цели для 'игрок [имя]':" in single_message:
                        self.parse_players_list_from_full_message(message)

                    if "=== ИГРА НАЧИНАЕТСЯ ===" in single_message:
                        self.game_started = True
                    elif "=== ИГРА ОКОНЧЕНА ===" in single_message or "побеждает!" in single_message:
                        self.game_started = False

            except ConnectionResetError:
                self.add_to_log("Соединение с сервером сброшено.")
                break
            except ConnectionAbortedError:
                self.add_to_log("Соединение с сервером прервано.")
                break
            except socket.error as e:
                self.add_to_log(f"Ошибка сокета: {e}")
                break
            except Exception as e:
                self.add_to_log(f"Ошибка получения сообщения: {str(e)}")
                break

        self.handle_disconnect()

    def handle_disconnect(self):
        self.add_to_log("Отключено от сервера.")
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
        self.client_socket = None
        self.is_my_turn = False
        self.game_started = False
        if hasattr(self, 'connect_button'):
            self.connect_button.configure(state="normal")
        if hasattr(self, 'status_label'):
            self.status_label.configure(text="Отключено", text_color="orange")

    def parse_players_list_from_full_message(self, full_server_message):
        lines = full_server_message.split('\n')

        targets_for_shot = []
        all_live_players = []

        parsing_mode = None

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            if "Доступные цели для 'игрок [имя]':" in line_stripped:
                parsing_mode = "targets"
                continue
            elif "Живые игроки:" in line_stripped:
                parsing_mode = "live"
                continue

            if line_stripped.startswith('- '):
                player_name_part = line_stripped[2:]
                if "(ходит)" in player_name_part:
                    player_name_part = player_name_part.replace("(ходит)", "").strip()

                if parsing_mode == "targets":
                    targets_for_shot.append(player_name_part)
                elif parsing_mode == "live":
                    all_live_players.append(player_name_part)

        if targets_for_shot:
            self.players_list = targets_for_shot
        elif all_live_players:
            self.players_list = [p for p in all_live_players if p.lower() != self.player_name.lower()]
        else:
            self.players_list = []

        if self.selection_window and self.selection_window.winfo_exists():
            self.update_selection_window_content()

    def show_player_selection(self):
        if not self.is_my_turn:
            self.add_to_log("Сейчас не ваш ход!")
            return
        if not self.game_started:
            self.add_to_log("Игра еще не началась!")
            return
        if not self.client_socket:
            self.add_to_log("Нет подключения к серверу.")
            return

        if self.selection_window and self.selection_window.winfo_exists():
            self.selection_window.destroy()

        self.selection_window = ctk.CTkToplevel(self.root)
        self.selection_window.title("Выберите игрока")
        self.selection_window.geometry("300x250")
        self.selection_window.transient(self.root)
        self.selection_window.grab_set()
        self.selection_window.attributes("-topmost", True)

        self.loading_label = ctk.CTkLabel(self.selection_window, text="Загрузка списка игроков...")
        self.loading_label.pack(pady=20, padx=10)

        self.send_action("игроки")

    def update_selection_window_content(self):
        if not (self.selection_window and self.selection_window.winfo_exists()):
            return

        for widget in self.selection_window.winfo_children():
            widget.destroy()

        available_targets = self.players_list

        if not available_targets:
            ctk.CTkLabel(self.selection_window, text="Нет доступных целей!").pack(pady=20, padx=10)
            ctk.CTkButton(self.selection_window, text="Закрыть", command=self.selection_window.destroy).pack(pady=10)
            return

        ctk.CTkLabel(self.selection_window, text="Выберите игрока для выстрела:").pack(pady=10)

        self.player_var = ctk.StringVar(value=available_targets[0] if available_targets else "")
        player_menu = ctk.CTkOptionMenu(
            self.selection_window,
            values=available_targets if available_targets else ["Нет целей"],
            variable=self.player_var,
            width=200,
            state="normal" if available_targets else "disabled"
        )
        player_menu.pack(pady=10)

        confirm_button = ctk.CTkButton(
            self.selection_window,
            text="Выстрелить",
            command=self.confirm_player_shot,
            state="normal" if available_targets else "disabled"
        )
        confirm_button.pack(pady=10)

        cancel_button = ctk.CTkButton(
            self.selection_window,
            text="Отмена",
            command=self.selection_window.destroy,
            fg_color="gray"
        )
        cancel_button.pack(pady=5)

    def confirm_player_shot(self):
        if self.player_var:
            selected_player = self.player_var.get()
            if selected_player and selected_player != "Нет целей":
                self.send_action(f"игрок {selected_player}")
        if self.selection_window and self.selection_window.winfo_exists():
            self.selection_window.destroy()
            self.selection_window = None

    def add_to_log(self, message):
        if self.root and hasattr(self, 'game_log') and self.game_log:
            try:
                # Выполняем обновление GUI в основном потоке
                self.root.after(0, self._add_to_log_threadsafe, message)
            except Exception as e:
                print(f"Ошибка планирования добавления в лог GUI: {e}")

    def _add_to_log_threadsafe(self, message):
        """Этот метод будет вызван в основном потоке GUI."""
        try:
            self.game_log.configure(state='normal')
            self.game_log.insert('end', message + '\n')
            self.game_log.configure(state='disabled')
            self.game_log.see('end')
        except Exception as e:
            print(f"Ошибка добавления в лог GUI (threadsafe): {e}")

    def send_action(self, action):
        if not self.client_socket:
            self.add_to_log("Ошибка: нет подключения к серверу.")
            messagebox.showerror("Ошибка", "Нет подключения к серверу. Пожалуйста, подключитесь снова.")
            return

        if action == "я" or action.startswith("игрок "):
            if not self.is_my_turn:
                self.add_to_log("Сейчас не ваш ход!")
                messagebox.showwarning("Внимание", "Сейчас не ваш ход!")
                return
            if not self.game_started:
                self.add_to_log("Игра еще не началась!")
                messagebox.showwarning("Внимание", "Игра еще не началась!")
                return

        try:
            self.client_socket.send(action.encode('utf-8'))
            self.add_to_log(f"Вы: {action}")
        except Exception as e:
            self.add_to_log(f"Ошибка отправки действия: {str(e)}")
            self.handle_disconnect()

    def on_closing(self):
        if self.client_socket:
            try:
                self.client_socket.close()
            except Exception as e:
                print(f"Ошибка при закрытии сокета: {e}")
        self.root.destroy()


if __name__ == "__main__":
    client_app = RussianRouletteClient()