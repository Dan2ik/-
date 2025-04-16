import socket
import threading
import tkinter as tk
from tkinter import messagebox

class RussianRouletteClient:
    def __init__(self, host='localhost', port=12345):
        self.host = host
        self.port = port
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.root = tk.Tk()
        self.root.title("Russian Roulette Client")

        self.chat_box = tk.Text(self.root, state=tk.DISABLED)
        self.chat_box.pack(padx=10, pady=10)

        self.input_box = tk.Entry(self.root)
        self.input_box.pack(padx=10, pady=10)
        self.input_box.bind("<Return>", self.send_message)

        self.send_button = tk.Button(self.root, text="Send", command=self.send_message)
        self.send_button.pack(padx=10, pady=10)

    def connect(self):
        try:
            self.client_socket.connect((self.host, self.port))
            self.append_message("Подключение к серверу установлено")

            # Получаем номер игрока
            self.append_message(self.client_socket.recv(1024).decode())
            name = self.input_box.get()
            self.client_socket.send(name.encode())

            # Поток для получения сообщений от сервера
            threading.Thread(target=self.receive_messages, daemon=True).start()

        except Exception as e:
            self.append_message(f"Ошибка: {e}")
        finally:
            self.root.mainloop()

    def receive_messages(self):
        while True:
            try:
                message = self.client_socket.recv(1024).decode()
                if not message:
                    self.append_message("Соединение с сервером разорвано")
                    break
                self.append_message(message)
            except:
                self.append_message("Соединение с сервером разорвано")
                break

    def send_message(self, event=None):
        message = self.input_box.get()
        if message.lower() == 'exit':
            self.client_socket.close()
            self.root.quit()
        else:
            self.client_socket.send(message.encode())
            self.input_box.delete(0, tk.END)

    def append_message(self, message):
        self.chat_box.config(state=tk.NORMAL)
        self.chat_box.insert(tk.END, message + "\n")
        self.chat_box.config(state=tk.DISABLED)
        self.chat_box.yview(tk.END)

if __name__ == "__main__":
    client = RussianRouletteClient()
    client.connect()
