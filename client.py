import socket
import threading
import customtkinter as ctk
from tkinter import scrolledtext, messagebox, simpledialog


class RussianRouletteClient:
    def __init__(self):
        self.client_socket = None
        self.player_name = ""
        self.game_started = False
        self.is_my_turn = False
        self.players_list = []

        # Настройка графического интерфейса
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("Русская рулетка")
        self.root.geometry("700x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Создаем вкладки
        self.tabview = ctk.CTkTabview(self.root)
        self.tabview.pack(pady=10, padx=10, fill="both", expand=True)

        # Добавляем вкладки
        self.tabview.add("Подключение")
        self.tabview.add("Игра")
        self.tabview.add("Справка")
        self.tabview.add("О программе")

        # Инициализируем вкладки
        self.create_connection_tab()
        self.create_game_tab()
        self.create_help_tab()
        self.create_about_tab()

        # По умолчанию показываем вкладку подключения
        self.tabview.set("Подключение")

        self.root.mainloop()

    def create_connection_tab(self):
        """Создает вкладку для подключения к серверу"""
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
        """Создает вкладку для игрового процесса"""
        tab = self.tabview.tab("Игра")

        # Чат/лог игры
        self.game_log = scrolledtext.ScrolledText(tab, state='disabled', height=20, wrap="word", font=("Arial", 12))
        self.game_log.pack(pady=10, padx=10, fill="both", expand=True)

        # Фрейм для кнопок действий
        self.actions_frame = ctk.CTkFrame(tab)
        self.actions_frame.pack(pady=10, fill="x", padx=10)

        self.shoot_self_button = ctk.CTkButton(
            self.actions_frame,
            text="Выстрелить в себя",
            command=lambda: self.send_action("я"),
            width=150
        )
        self.shoot_self_button.pack(side="left", padx=5, expand=True)

        self.shoot_player_button = ctk.CTkButton(
            self.actions_frame,
            text="Выстрелить в игрока",
            command=self.show_player_selection,
            width=150
        )
        self.shoot_player_button.pack(side="left", padx=5, expand=True)

        self.info_button = ctk.CTkButton(
            self.actions_frame,
            text="Информация",
            command=lambda: self.send_action("инфо"),
            width=100
        )
        self.info_button.pack(side="left", padx=5, expand=True)

        self.players_button = ctk.CTkButton(
            self.actions_frame,
            text="Список игроков",
            command=lambda: self.send_action("игроки"),
            width=120
        )
        self.players_button.pack(side="left", padx=5, expand=True)

    def create_help_tab(self):
        """Создает вкладку справки"""
        tab = self.tabview.tab("Справка")

        help_text = """
        Правила игры "Русская рулетка":

        1. В игре участвует револьвер с 6 патронами (боевые и холостые)
        2. В начале игры патроны случайным образом распределяются в барабане
        3. Когда наступает ваш ход, вы можете:
           - Выстрелить в себя (кнопка "Выстрелить в себя")
           - Выстрелить в другого игрока (кнопка "Выстрелить в игрока")
           - Посмотреть информацию о патронах (кнопка "Информация")
           - Посмотреть список живых игроков (кнопка "Список игроков")

        4. Если выстрел боевой - игрок выбывает из игры
        5. Если выстрел холостой - ход переходит следующему игроку
        6. Игра продолжается, пока не останется один игрок

        Управление:
        - Используйте кнопки для выполнения действий
        - Сервер автоматически уведомит вас, когда наступит ваш ход
        """

        help_label = ctk.CTkLabel(tab, text=help_text, justify="left")
        help_label.pack(pady=20, padx=20, anchor="w")

    def create_about_tab(self):
        """Создает вкладку о программе"""
        tab = self.tabview.tab("О программе")

        about_text = """
        Русская рулетка - клиент для игры по сети

        Версия: 1.0
        Разработчик: Ваше имя

        Особенности:
        - Подключение к серверу игры
        - Удобный графический интерфейс
        - Возможность играть с другими участниками

        Используемые технологии:
        - Python 3
        - CustomTkinter для интерфейса
        - Socket для сетевого взаимодействия
        """

        about_label = ctk.CTkLabel(tab, text=about_text, justify="left")
        about_label.pack(pady=20, padx=20, anchor="w")

    def connect_to_server(self):
        """Подключение к серверу"""
        host = self.host_entry.get()
        port = int(self.port_entry.get())
        self.player_name = self.name_entry.get().strip()

        if not self.player_name:
            messagebox.showerror("Ошибка", "Введите ваше имя")
            return

        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((host, port))

            # Получаем приветственное сообщение
            welcome_msg = self.client_socket.recv(1024).decode()
            if "игрок" in welcome_msg:
                # Отправляем имя серверу
                self.client_socket.send(self.player_name.encode())

                # Запускаем поток для получения сообщений
                threading.Thread(target=self.receive_messages, daemon=True).start()

                # Переключаемся на игровую вкладку
                self.tabview.set("Игра")
                self.add_to_log(welcome_msg)
            else:
                messagebox.showerror("Ошибка", welcome_msg)
                self.client_socket.close()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось подключиться: {str(e)}")
            if self.client_socket:
                self.client_socket.close()

    def receive_messages(self):
        """Получение сообщений от сервера"""
        while True:
            try:
                message = self.client_socket.recv(1024).decode()
                if not message:
                    break

                # Проверяем, наш ли это ход
                if "Ваш ход" in message:
                    self.is_my_turn = True
                else:
                    self.is_my_turn = False

                # Сохраняем список игроков, если он пришел
                if "Доступные цели:" in message:
                    self.parse_players_list(message)

                self.add_to_log(message)

                # Проверяем начало игры
                if "=== ИГРА НАЧИНАЕТСЯ ===" in message:
                    self.game_started = True
                elif "=== ИГРА ОКОНЧЕНА ===" in message:
                    self.game_started = False

            except ConnectionAbortedError:
                break
            except Exception as e:
                self.add_to_log(f"Ошибка соединения: {str(e)}")
                break

        self.client_socket.close()
        self.add_to_log("Соединение с сервером потеряно")

    def parse_players_list(self, message):
        """Извлекает список игроков из сообщения сервера"""
        lines = message.split('\n')
        players = []
        for line in lines:
            if line.startswith('- '):
                players.append(line[2:].strip())
        self.players_list = players
        self.add_to_log("Список игроков обновлен")

    def show_player_selection(self):
        """Показывает диалог выбора игрока для выстрела"""
        #if not self.is_my_turn:
        #    self.add_to_log("Сейчас не ваш ход!")
        #    return

        if not self.game_started:
            self.add_to_log("Игра еще не началась!")
            return

        if not self.players_list:
            self.send_action("игроки")
            self.add_to_log("Запрошен список игроков... Попробуйте снова через секунду")
            return

        # Создаем новое окно для выбора игрока
        selection_window = ctk.CTkToplevel(self.root)
        selection_window.title("Выберите игрока")
        selection_window.geometry("300x200")
        selection_window.transient(self.root)  # Делаем окно модальным
        selection_window.grab_set()  # Захватываем фокус

        ctk.CTkLabel(selection_window, text="Выберите игрока:").pack(pady=10)

        # Удаляем текущего игрока из списка целей
        available_players = [p for p in self.players_list if p != self.player_name]
        if not available_players:
            ctk.CTkLabel(selection_window, text="Нет других игроков!").pack(pady=10)
            ctk.CTkButton(selection_window, text="Закрыть", command=selection_window.destroy).pack(pady=10)
            return

        player_var = ctk.StringVar(value=available_players[0])
        player_menu = ctk.CTkOptionMenu(selection_window, values=available_players, variable=player_var)
        player_menu.pack(pady=10)

        def confirm_shot():
            selected_player = player_var.get()
            if selected_player:
                self.send_action(f"игрок {selected_player}")
            selection_window.destroy()

        ctk.CTkButton(
            selection_window,
            text="Выстрелить",
            command=confirm_shot
        ).pack(pady=10)

        ctk.CTkButton(
            selection_window,
            text="Отмена",
            command=selection_window.destroy
        ).pack(pady=5)

    def add_to_log(self, message):
        """Добавление сообщения в лог"""
        self.game_log.configure(state='normal')
        self.game_log.insert('end', message + '\n')
        self.game_log.configure(state='disabled')
        self.game_log.see('end')

    def send_action(self, action):
    #    """Отправка действия на сервер"""
    #    if not self.is_my_turn and self.game_started:
    #       self.add_to_log("Сейчас не ваш ход!")
    #        return

        try:
            self.client_socket.send(action.encode())
        except Exception as e:
            self.add_to_log(f"Ошибка отправки: {str(e)}")

    def on_closing(self):
        """Обработка закрытия окна"""
        if self.client_socket:
            self.client_socket.close()
        self.root.destroy()


if __name__ == "__main__":
    RussianRouletteClient()