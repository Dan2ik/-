import socket
import threading
import tkinter as tk
from tkinter import simpledialog, messagebox

class RussianRouletteClient:
    def __init__(self, host='localhost', port=12345):
        self.host = host
        self.port = port
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.root = tk.Tk()
        self.root.withdraw()  # сначала скрываем окно
        self.available_targets = []

        self.name = simpledialog.askstring("Ваше имя", "Введите ваше имя:")
        if not self.name:
            messagebox.showerror("Ошибка", "Имя обязательно для входа")
            self.root.destroy()
            return

        self.root.title(f"Русская рулетка — {self.name}")

        self.chat_box = tk.Text(self.root, state=tk.DISABLED, height=20, width=60)
        self.chat_box.pack(padx=10, pady=10)

        # Кнопки
        self.button_frame = tk.Frame(self.root)
        self.button_frame.pack(pady=10)

        self.shoot_self_button = tk.Button(self.button_frame, text="Выстрелить в себя", command=self.shoot_self)
        self.shoot_self_button.grid(row=0, column=0, padx=5)

        self.shoot_player_button = tk.Button(self.button_frame, text="Выстрелить в игрока", command=self.select_target)
        self.shoot_player_button.grid(row=0, column=1, padx=5)

        self.info_button = tk.Button(self.button_frame, text="Инфо о патронах", command=self.request_info)
        self.info_button.grid(row=0, column=2, padx=5)

        self.exit_button = tk.Button(self.button_frame, text="Выйти", command=self.exit_game)
        self.exit_button.grid(row=0, column=3, padx=5)

    def connect(self):
        try:
            self.client_socket.connect((self.host, self.port))
            self.append_message("Подключение к серверу установлено")

            welcome_message = self.client_socket.recv(1024).decode()
            self.append_message(welcome_message)

            self.client_socket.send(self.name.encode())

            self.root.deiconify()

            threading.Thread(target=self.receive_messages, daemon=True).start()

        except Exception as e:
            messagebox.showerror("Ошибка подключения", str(e))
            self.root.destroy()

        self.root.mainloop()

    def receive_messages(self):
        buffer = ""
        while True:
            try:
                data = self.client_socket.recv(4096).decode()
                if not data:
                    self.append_message("Соединение с сервером разорвано")
                    break
                buffer += data

                # Обработка полного сообщения
                if "\n" in buffer:
                    lines = buffer.split('\n')
                    for line in lines[:-1]:
                        self.process_message(line.strip())
                    buffer = lines[-1]

            except:
                self.append_message("Соединение с сервером разорвано")
                break

    def process_message(self, message):
        if message.startswith("Доступные цели:"):
            self.available_targets = []
        elif message.startswith("- "):
            player_name = message[2:].strip()
            self.available_targets.append(player_name)
        else:
            self.append_message(message)

    def shoot_self(self):
        try:
            self.client_socket.send("я".encode())
        except:
            self.append_message("Ошибка отправки команды 'я'")

    def request_players(self):
        try:
            self.client_socket.send("игроки".encode())
        except:
            self.append_message("Ошибка запроса списка игроков")

    def select_target(self):
        if not self.available_targets:
            self.append_message("Нет доступных целей.")
            return

        choice = simpledialog.askstring(
            "Выберите цель",
            "Введите имя игрока:\n" + "\n".join(self.available_targets)
        )
        if choice:
            command = f"игрок {choice}"
            try:
                self.client_socket.send(command.encode())
            except:
                self.append_message("Ошибка отправки команды")

    def request_info(self):
        try:
            self.client_socket.send("инфо".encode())
        except:
            self.append_message("Ошибка запроса информации о патронах")

    def exit_game(self):
        try:
            self.client_socket.close()
        except:
            pass
        self.root.quit()

    def append_message(self, message):
        self.chat_box.config(state=tk.NORMAL)
        self.chat_box.insert(tk.END, message + "\n")
        self.chat_box.config(state=tk.DISABLED)
        self.chat_box.yview(tk.END)

if __name__ == "__main__":
    client = RussianRouletteClient()
    client.connect()
