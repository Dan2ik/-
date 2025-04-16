import socket
import threading
import random


class RussianRouletteServer:
    def __init__(self, host='localhost', port=12345):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.clients = []
        self.player_names = {}  # {socket: name}
        self.name_to_socket = {}  # {name: socket}
        self.bullets = 6
        self.chamber = []
        self.current_player = 0
        self.game_started = False
        self.players_alive = []
        self.live_bullets = 0
        self.blank_bullets = 0

    def start(self):
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"Сервер запущен на {self.host}:{self.port}. Ожидание игроков...")

        while True:
            client_socket, addr = self.server_socket.accept()
            if len(self.clients) < 6:
                self.clients.append(client_socket)
                player_num = len(self.clients)
                threading.Thread(target=self.handle_client, args=(client_socket, player_num)).start()
            else:
                client_socket.send("Сервер переполнен".encode())
                client_socket.close()

    def handle_client(self, client_socket, player_num):
        client_socket.send(f"Добро пожаловать! Вы игрок {player_num}\nВведите ваше имя:".encode())
        name = client_socket.recv(1024).decode().strip()
        self.player_names[client_socket] = name
        self.name_to_socket[name.lower()] = client_socket

        self.broadcast(f"{name} присоединился к игре! Всего игроков: {len(self.clients)}")

        if len(self.clients) >= 2 and not self.game_started:
            self.start_game()

        while True:
            try:
                data = client_socket.recv(1024).decode().strip().lower()
                if not data:
                    break

                if self.game_started and client_socket in self.players_alive:
                    player_index = self.clients.index(client_socket)
                    if player_index == self.current_player:
                        if data == "я":
                            self.process_shot(client_socket, target="self")
                        elif data.startswith("игрок "):
                            target_name = data[6:].strip()
                            self.process_player_target(client_socket, target_name)
                        elif data == "инфо":
                            self.send_bullet_info(client_socket)
                        elif data == "игроки":
                            self.send_player_list(client_socket)
                        else:
                            client_socket.send("Используйте: 'я', 'игрок [имя]', 'инфо' или 'игроки'".encode())
            except:
                break

    def process_player_target(self, shooter_socket, target_name):
        if target_name.lower() == self.player_names[shooter_socket].lower():
            self.process_shot(shooter_socket, target="self")
            return

        target_socket = self.name_to_socket.get(target_name.lower())

        if target_socket:
            if target_socket in self.players_alive:
                self.process_shot(shooter_socket, target=target_socket)
            else:
                shooter_socket.send("Этот игрок уже выбыл!".encode())
        else:
            shooter_socket.send("Игрок с таким именем не найден. Используйте 'игроки' чтобы увидеть список.".encode())

    def send_player_list(self, client_socket):
        alive_players = [self.player_names[client] for client in self.players_alive]
        current_name = self.player_names[self.clients[self.current_player]]

        # Убираем текущего игрока из списка целей
        targets = [name for name in alive_players if name != current_name]

        if targets:
            message = "Доступные цели:\n" + "\n".join([f"- {name}" for name in targets])
        else:
            message = "Нет других игроков для выбора!"

        client_socket.send(message.encode())

    def start_game(self):
        self.game_started = True
        self.players_alive = self.clients.copy()
        self.load_chamber()
        self.current_player = 0
        self.broadcast("\n=== ИГРА НАЧИНАЕТСЯ ===")
        self.broadcast(f"Патроны в барабане: {self.live_bullets} боевых и {self.blank_bullets} холостых")
        self.broadcast(
            "Правила:\n"
            "'я' - выстрелить в себя\n"
            "'игрок [имя]' - выстрелить в другого игрока\n"
            "'инфо' - информация о патронах\n"
            "'игроки' - список живых игроков")
        self.notify_turn()

    def load_chamber(self):
        self.live_bullets = random.randint(1, 3)
        self.blank_bullets = self.bullets - self.live_bullets
        bullets = [True] * self.live_bullets + [False] * self.blank_bullets
        random.shuffle(bullets)
        self.chamber = bullets

    def process_shot(self, shooter_socket, target):
        shooter_name = self.player_names[shooter_socket]

        if target == "self":
            target_name = shooter_name
            target_socket = shooter_socket
        else:
            target_name = self.player_names[target]
            target_socket = target

        current_bullet = self.chamber.pop(self.current_player)

        if current_bullet:
            self.broadcast(f"\n{shooter_name} стреляет в {target_name}... БАХ! Боевой патрон!")
            self.live_bullets -= 1

            if target_socket in self.players_alive:
                self.players_alive.remove(target_socket)
                self.broadcast(f"{target_name} выбывает из игры!")

            self.pass_turn()
        else:
            self.broadcast(f"\n{shooter_name} стреляет в {target_name}... Щелк! Холостой патрон")
            self.blank_bullets -= 1

            if target != "self":
                self.pass_turn()

        if len(self.players_alive) == 1:
            winner_name = self.player_names[self.players_alive[0]]
            self.broadcast(f"\n=== ИГРА ОКОНЧЕНА ===\n{winner_name} побеждает!")
            self.reset_game()
            return

        self.broadcast(f"Осталось патронов: {self.live_bullets} боевых и {self.blank_bullets} холостых")

        if len(self.chamber) == 0:
            self.load_chamber()
            self.broadcast("\nБарабан пуст! Производится перезарядка...")
            self.broadcast(f"Новые патроны: {self.live_bullets} боевых и {self.blank_bullets} холостых")

        self.notify_turn()

    def pass_turn(self):
        next_player = (self.current_player + 1) % len(self.clients)
        while next_player != self.current_player:
            if self.clients[next_player] in self.players_alive:
                self.current_player = next_player
                break
            next_player = (next_player + 1) % len(self.clients)
        else:
            self.broadcast("Ошибка: нет живых игроков!")
            self.reset_game()

    def send_bullet_info(self, client_socket):
        client_socket.send(
            f"Текущее состояние: {self.live_bullets} боевых и {self.blank_bullets} холостых патронов".encode())

    def notify_turn(self):
        current_name = self.player_names[self.clients[self.current_player]]
        self.broadcast(f"\nХод игрока {current_name}")
        self.clients[self.current_player].send("Ваш ход (я/игрок [имя]/инфо/игроки):".encode())

    def reset_game(self):
        self.game_started = False
        self.broadcast("\nОжидание новых игроков... (нужно минимум 2)")

    def broadcast(self, message):
        for client in self.clients:
            try:
                client.send(f"\n{message}".encode())
            except:
                if client in self.clients:
                    self.clients.remove(client)


if __name__ == "__main__":
    server = RussianRouletteServer()
    server.start()