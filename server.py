import socket
import threading
import random
import time
import queue  # Для потокобезопасного обмена данными
import tkinter.messagebox  # Для всплывающих окон с ошибками

import customtkinter as ctk


# --- Модифицированный класс RussianRouletteServer ---

class RussianRouletteServer:
    def __init__(self, host='localhost', port=12345, gui_queue=None):
        self.host = host
        self.port = port
        self.server_socket = None  # Инициализируем позже
        self.clients = []  # Список сокетов всех подключенных клиентов
        self.client_threads = []  # Отслеживаем потоки клиентов
        self.player_names = {}  # {socket: name}
        self.name_to_socket = {}  # {name: socket}
        self.bullets = 6  # Всего слотов в барабане по умолчанию
        self.chamber = []  # Текущий барабан
        self.current_player = 0  # Индекс текущего игрока в self.clients
        self.game_started = False  # Флаг, идет ли игра
        self.players_alive = []  # Список сокетов живых игроков
        self.live_bullets = 0  # Количество боевых патронов
        self.blank_bullets = 0  # Количество холостых патронов
        self.running = False  # Флаг для управления основным циклом сервера
        self.gui_queue = gui_queue  # Очередь для отправки сообщений в GUI

    def log(self, message_type, data):
        if self.gui_queue:
            try:
                self.gui_queue.put((message_type, data), block=False)
            except queue.Full:
                print("Внимание: Очередь GUI переполнена!")

    def update_status(self):
        current_turn_name = "N/A"
        if self.game_started and self.clients and 0 <= self.current_player < len(self.clients):
            current_socket = self.clients[self.current_player]
            if current_socket in self.players_alive:  # Убедимся, что игрок еще жив
                current_turn_name = self.player_names.get(current_socket, "ОшибкаИмени")
            else:  # Если текущий игрок по индексу мертв, отобразим N/A
                current_turn_name = "N/A (ожид. передачи)"

        status = {
            "connected": len(self.clients),
            "alive": len(self.players_alive) if self.game_started else 0,
            "live_bullets": self.live_bullets if self.game_started else 0,
            "blank_bullets": self.blank_bullets if self.game_started else 0,
            "turn": current_turn_name,
            "game_running": self.game_started
        }
        self.log("status_update", status)

    def start(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)
            self.running = True
            self.log("log", f"Сервер запущен на {self.host}:{self.port}. Ожидание игроков...")
            self.update_status()

            while self.running:
                try:
                    client_socket, addr = self.server_socket.accept()
                    if not self.running:
                        client_socket.close()
                        break

                    if len(self.clients) < 6:
                        player_num_temp = len(self.clients) + 1  # Временный номер для лога
                        self.log("log", f"Новое подключение от {addr}. Попытка регистрации игрока {player_num_temp}.")
                        thread = threading.Thread(target=self.handle_client, args=(client_socket, player_num_temp),
                                                  daemon=True)
                        self.client_threads.append(thread)
                        thread.start()
                    else:
                        self.log("log", f"Отклонено подключение от {addr}: Сервер переполнен.")
                        try:
                            client_socket.send("Сервер переполнен".encode())
                        except Exception:
                            pass  # Клиент мог уже отключиться
                        client_socket.close()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.log("log", f"Ошибка в главном цикле приема подключений: {e}")
                    break
        except OSError as e:
            self.log("log", f"Ошибка запуска сервера (возможно, порт {self.port} занят): {e}")
            if self.gui_queue:
                self.gui_queue.put(("server_stopped", None), block=False)
        finally:
            self.log("log", "Сервер останавливается...")
            self.running = False
            if self.server_socket:
                self.server_socket.close()
                self.server_socket = None
            self._cleanup_clients()
            if self.game_started:
                self.reset_game_state()

            self.update_status()
            self.log("log", "Сервер остановлен.")
            if self.gui_queue:
                try:
                    self.gui_queue.put(("server_stopped", None), block=False)
                except queue.Full:
                    pass

    def stop(self):
        if not self.running:
            return
        self.log("log", "Получен сигнал остановки...")
        self.running = False
        try:
            with socket.create_connection((self.host, self.port), timeout=0.5) as sock:
                pass
        except Exception:
            pass

    def _cleanup_clients(self):
        self.log("log", "Закрытие клиентских соединений...")
        clients_copy = self.clients[:]

        for client_socket in clients_copy:
            player_name = self.player_names.get(client_socket, "Неизвестный (уже удален?)")
            self.log("log", f"Принудительное отключение клиента {player_name}...")
            try:
                client_socket.send("Сервер отключается.".encode())
                client_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                client_socket.close()
            except Exception as e:
                self.log("log", f"Ошибка при закрытии сокета клиента {player_name}: {e}")
            self._remove_client(client_socket, notify_others=False, reason="server_shutdown")

        if self.game_started:
            self.log("log", "Игра прервана из-за остановки сервера.")
            self.reset_game_state()

        self.log("log", "Все клиентские соединения обработаны для закрытия.")

    def _remove_client(self, client_socket, notify_others=True, reason="disconnect"):
        name = self.player_names.pop(client_socket, None)
        player_log_name = name if name else "Неизвестный"

        player_socket_that_was_current = None
        original_current_player_index = self.current_player

        if self.game_started and self.clients and 0 <= self.current_player < len(self.clients):
            player_socket_that_was_current = self.clients[self.current_player]

        original_index_of_removed_player = -1
        if client_socket in self.clients:
            try:
                original_index_of_removed_player = self.clients.index(client_socket)
            except ValueError:
                pass
            self.clients.remove(client_socket)

        if name:
            self.name_to_socket.pop(name.lower(), None)
            if notify_others:
                self.log("log", f"Игрок {name} ({reason}) покинул игру.")
                self.broadcast(f"{name} покинул игру.")
        else:
            self.log("log", f"Неименованный игрок ({reason}) отключился/удален.")

        was_in_players_alive = client_socket in self.players_alive
        if was_in_players_alive:
            self.players_alive.remove(client_socket)

        if self.game_started and was_in_players_alive:
            if len(self.players_alive) <= 1 and reason != "server_shutdown":
                winner_name = "Никто не"
                if len(self.players_alive) == 1:
                    winner_name = self.player_names.get(self.players_alive[0], "Неизвестный")
                self.broadcast(f"\n=== ИГРА ОКОНЧЕНА ===\n{winner_name} побеждает!")
                self.reset_game()

            elif client_socket == player_socket_that_was_current:
                self.log("log", f"Текущий игрок {player_log_name} отключился. Передача хода.")
                if self.players_alive:
                    if len(self.clients) > 0:
                        self.current_player = (original_index_of_removed_player - 1 + len(self.clients)) % len(
                            self.clients)
                    else:
                        self.current_player = 0
                    self.pass_turn(notify=True)
                else:
                    if reason != "server_shutdown": self.reset_game()

            elif player_socket_that_was_current and self.clients:
                try:
                    new_idx = self.clients.index(player_socket_that_was_current)
                    self.current_player = new_idx
                    self.log("log",
                             f"Игрок {player_log_name} отключился. Ход остается у {self.player_names.get(player_socket_that_was_current, 'ТЕКУЩИЙ')}, новый индекс {self.current_player}.")
                    if player_socket_that_was_current not in self.players_alive:
                        self.log("log",
                                 f"Ход был у {self.player_names.get(player_socket_that_was_current)}, но он выбыл. Передача хода.")
                        self.pass_turn(notify=True)
                except ValueError:
                    self.log("log",
                             f"КРИТИЧЕСКАЯ ОШИБКА: Ожидаемый текущий игрок {self.player_names.get(player_socket_that_was_current)} не найден после удаления {player_log_name}. Текущий индекс был {original_current_player_index}.")
                    if self.players_alive:
                        self.current_player = 0
                        self.pass_turn(notify=True)
                    elif reason != "server_shutdown":
                        self.reset_game()
            elif not self.players_alive and reason != "server_shutdown":
                self.reset_game()

        elif len(self.clients) < 2 and self.game_started and reason != "server_shutdown":
            self.broadcast("Недостаточно игроков для продолжения.")
            self.reset_game()

        if reason != "server_shutdown":
            self.update_status()

    def handle_client(self, client_socket, player_num_temp):
        name = None
        peer_address = None # Инициализируем здесь
        try:
            peer_address = client_socket.getpeername()
            self.log("log", f"DEBUG: Запрос имени у клиента {peer_address}")
            client_socket.send(f"Добро пожаловать! Введите ваше имя:".encode())

            name_bytes = client_socket.recv(1024)
            self.log("log", f"DEBUG: От {peer_address} получено name_bytes: {name_bytes!r} (длина: {len(name_bytes)})")

            if not name_bytes:
                self.log("log", f"DEBUG: name_bytes от {peer_address} пусто. Клиент, вероятно, отключился.")
                raise ConnectionResetError("Клиент отключился при запросе имени")

            try:
                name_input_decoded = name_bytes.decode('utf-8')
                self.log("log",
                         f"DEBUG: Для {peer_address} декодированное имя: '{name_input_decoded}' (длина: {len(name_input_decoded)})")
            except UnicodeDecodeError as ude:
                self.log("log",
                         f"ОШИБКА: Для {peer_address} НЕ УДАЛОСЬ декодировать name_bytes: {name_bytes!r}. Ошибка: {ude}")
                name = f"Игрок_{player_num_temp}_ОшибкаКодировки"
                self.log("log", f"DEBUG: Присвоено имя по умолчанию '{name}' из-за ошибки декодирования.")
            else:
                name_input = name_input_decoded.strip()
                self.log("log",
                         f"DEBUG: Для {peer_address} имя после strip(): '{name_input}' (длина: {len(name_input)})")

                if not name_input:
                    self.log("log",
                             f"DEBUG: Для {peer_address} имя name_input пустое после strip(). Используется имя по умолчанию.")
                    name = f"Игрок_{player_num_temp}"
                else:
                    name = name_input

            original_name = name
            count = 1
            # Преобразуем имя к нижнему регистру для проверки уникальности
            while name.lower() in self.name_to_socket:
                 name = f"{original_name}_{count}"
                 count += 1
                 if count > 10: # Предохранитель от бесконечного цикла
                      name = f"Игрок_{random.randint(1000,9999)}" # Генерируем случайное имя
                      break

            self.clients.append(client_socket)
            self.player_names[client_socket] = name
            self.name_to_socket[name.lower()] = client_socket # Сохраняем в нижнем регистре для поиска

            actual_player_num = self.clients.index(client_socket) + 1
            self.log("log", f"Игрок '{name}' (№{actual_player_num}) успешно зарегистрирован.")
            self.broadcast(f"{name} присоединился к игре! Всего игроков: {len(self.clients)}")
            self.update_status()

            if len(self.clients) >= 2 and not self.game_started:
                self.start_game()

            while self.running:
                try:
                    data_bytes = client_socket.recv(1024)
                    if not data_bytes:
                        self.log("log", f"{name} отключился (пустые данные).")
                        break
                    data = data_bytes.decode().strip().lower()
                except ConnectionResetError:
                    self.log("log", f"Соединение с {name} сброшено (ConnectionResetError).")
                    break
                except socket.error as e:
                    if not self.running and e.errno == 10004:
                        self.log("log", f"Операция recv для {name} прервана (остановка сервера).")
                    else:
                        self.log("log", f"Ошибка сокета при получении данных от {name}: {e}")
                    break
                except Exception as e:
                    self.log("log", f"Ошибка при получении данных от {name}: {e}")
                    break

                if not self.game_started:
                    client_socket.send("Игра еще не началась. Ожидание игроков...".encode())
                    continue

                if client_socket not in self.players_alive:
                    client_socket.send("Вы выбыли из игры.".encode())
                    continue

                current_player_socket_check = None
                if 0 <= self.current_player < len(self.clients):
                    current_player_socket_check = self.clients[self.current_player]
                else:
                    self.log("log",
                             f"ОШИБКА: self.current_player ({self.current_player}) вне диапазона self.clients ({len(self.clients)}) в handle_client для {name}.")
                    if self.players_alive:
                        self.pass_turn(notify=True)
                        if 0 <= self.current_player < len(self.clients):
                            current_player_socket_check = self.clients[self.current_player]
                        else:
                            client_socket.send(
                                "Ошибка сервера: не удалось определить текущего игрока. Попробуйте позже.".encode())
                            self.log("log", "КРИТИЧЕСКАЯ ОШИБКА: Не удалось восстановить current_player.")
                            continue
                    else:
                        client_socket.send("Нет живых игроков для хода.".encode())
                        if self.game_started: self.reset_game()
                        continue

                if data == "инфо":
                    self.send_bullet_info(client_socket)
                elif data == "игроки":
                    self.send_player_list(client_socket)
                elif current_player_socket_check == client_socket:
                    if data == "я":
                        self.process_shot(client_socket, target="self")
                    elif data.startswith("игрок "):
                        target_name_cmd = data[len("игрок "):].strip() # переименовал, чтобы не конфликтовать с переменной name
                        self.process_player_target(client_socket, target_name_cmd)
                    else:
                        client_socket.send("Ваш ход. Используйте: 'я', 'игрок [имя]', 'инфо' или 'игроки'".encode())
                else:
                    current_turn_name = "???"
                    if current_player_socket_check:
                        current_turn_name = self.player_names.get(current_player_socket_check, "???")
                    client_socket.send(f"Сейчас не ваш ход. Ходит {current_turn_name}.".encode())

        except ConnectionResetError:
            log_name_cr = name if name else f"клиент ({peer_address})" if peer_address else "неименованный клиент"
            self.log("log", f"Соединение с {log_name_cr} было сброшено.")
        except Exception as e:
            log_name_ex = name if name else f"клиент ({peer_address})" if peer_address else "неименованный клиент"
            if self.running:
                self.log("log", f"Непредвиденная ошибка в handle_client ({log_name_ex}): {e}")
        finally:
            log_name_final = name if name else f"клиент (сокет: {client_socket.fileno() if client_socket and client_socket.fileno() != -1 else 'N/A'}, адрес: {peer_address if peer_address else 'N/A'})"
            self.log("log", f"Завершение обработки клиента {log_name_final}.")
            self._remove_client(client_socket, notify_others=True)

            if client_socket:
                try:
                    client_socket.close()
                except Exception:
                    pass

    def process_player_target(self, shooter_socket, target_name):
        shooter_name = self.player_names.get(shooter_socket, "Неизвестный")
        if not target_name:
            shooter_socket.send("Укажите имя игрока после 'игрок '".encode())
            return

        if target_name.lower() == shooter_name.lower():
            self.process_shot(shooter_socket, target="self")
            return

        target_socket = self.name_to_socket.get(target_name.lower())

        if target_socket:
            if target_socket in self.players_alive:
                self.process_shot(shooter_socket, target=target_socket)
            else:
                target_real_name = self.player_names.get(target_socket, target_name)
                shooter_socket.send(f"Игрок {target_real_name} уже выбыл!".encode())
        else:
            shooter_socket.send(
                "Игрок с таким именем не найден или не в игре. Используйте 'игроки' чтобы увидеть список.".encode())

    def send_player_list(self, client_socket):
        alive_players_info = []
        current_name_for_list = ""

        if self.game_started and self.clients and self.players_alive:
            if 0 <= self.current_player < len(self.clients):
                current_socket_for_list = self.clients[self.current_player]
                if current_socket_for_list in self.players_alive:
                    current_name_for_list = self.player_names.get(current_socket_for_list, "??")

        for p_socket in self.players_alive:
            name = self.player_names.get(p_socket, "Неизвестный")
            is_current_marker = " (ходит)" if name == current_name_for_list and name != "??" else ""
            alive_players_info.append(f"- {name}{is_current_marker}")

        if alive_players_info:
            message = "Живые игроки:\n" + "\n".join(alive_players_info)
        else:
            message = "Нет живых игроков."

        is_requester_turn = False
        if self.game_started and self.clients and 0 <= self.current_player < len(self.clients):
            is_requester_turn = (client_socket == self.clients[self.current_player])

        if is_requester_turn:
            targets = [self.player_names.get(p) for p in self.players_alive if
                       p != client_socket and p in self.player_names]
            targets = [name for name in targets if name]
            if targets:
                message += "\n\nДоступные цели для 'игрок [имя]':\n" + "\n".join([f"- {name}" for name in targets])
            elif len(self.players_alive) > 1:
                message += "\n\nНе удалось определить доступные цели."
            else:
                message += "\n\nНет других игроков для выбора!"
        try:
            client_socket.send(message.encode())
        except Exception as e:
            self.log("log", f"Ошибка отправки списка игроков клиенту: {e}")

    def start_game(self):
        if len(self.clients) < 2:
            self.broadcast("Нужно минимум 2 игрока для старта.")
            self.game_started = False
            self.update_status()
            return

        self.game_started = True
        self.players_alive = self.clients.copy()
        self.load_chamber()
        self.current_player = random.randrange(len(self.clients))

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
        bullets_list = [True] * self.live_bullets + [False] * self.blank_bullets
        random.shuffle(bullets_list)
        self.chamber = bullets_list
        self.log("log",
                 f"Барабан заряжен: {self.live_bullets} боевых, {self.blank_bullets} холостых. Порядок: {''.join(['Б' if b else 'Х' for b in self.chamber])}")
        self.update_status()

    def process_shot(self, shooter_socket, target):
        if not self.chamber:
            self.broadcast("Ошибка: Барабан пуст! Перезарядка...")
            self.load_chamber()
            if not self.chamber:
                self.broadcast("Критическая ошибка: не удалось зарядить барабан.")
                self.reset_game()
                return
            self.notify_turn()
            return

        shooter_name = self.player_names.get(shooter_socket, "Неизвестный")
        is_self_shot = (target == "self" or target == shooter_socket)

        target_socket = shooter_socket if is_self_shot else target
        target_name = self.player_names.get(target_socket, "Неизвестный (цель)")
        action_verb = "стреляет в себя" if is_self_shot else f"стреляет в {target_name}"

        current_bullet = self.chamber.pop(0)
        shot_type = "БОЕВОЙ" if current_bullet else "ХОЛОСТОЙ"
        self.broadcast(f"\n{shooter_name} {action_verb}... {shot_type}!")

        turn_passed_or_extra = False

        if current_bullet:
            self.live_bullets -= 1
            if target_socket in self.players_alive:
                self.players_alive.remove(target_socket)
                self.broadcast(f"{target_name} выбывает из игры!")
                self.pass_turn(notify=False)
                turn_passed_or_extra = True
            else:
                self.broadcast(f"Хм, {target_name} уже был вне игры...")
                self.pass_turn(notify=False)
                turn_passed_or_extra = True
        else:
            self.blank_bullets -= 1
            self.broadcast(f"{shooter_name} в безопасности (пока что).")
            if is_self_shot:
                self.broadcast(f"{shooter_name} получает дополнительный ход!")
                turn_passed_or_extra = True
            else:
                self.pass_turn(notify=False)
                turn_passed_or_extra = True

        self.update_status()

        if len(self.players_alive) <= 1:
            winner_name = "Никто не"
            if len(self.players_alive) == 1:
                winner_name = self.player_names.get(self.players_alive[0], "Неизвестный")
            self.broadcast(f"\n=== ИГРА ОКОНЧЕНА ===\n{winner_name} побеждает!")
            self.reset_game()
            return

        if not self.chamber:
            self.broadcast("\nБарабан пуст! Производится перезарядка...")
            self.load_chamber()
            self.broadcast(f"Новые патроны: {self.live_bullets} боевых и {self.blank_bullets} холостых")
            self.notify_turn()
            return

        if turn_passed_or_extra:
            self.notify_turn()

    def pass_turn(self, notify=True):
        if not self.players_alive:
            self.log("log", "pass_turn: нет живых игроков.")
            if self.game_started:
                self.broadcast("\n=== ИГРА ОКОНЧЕНА ===\nНе осталось живых игроков.")
                self.reset_game()
            return

        if not self.clients:
            self.log("log", "pass_turn: нет подключенных клиентов.")
            if self.game_started: self.reset_game()
            return

        num_total_clients = len(self.clients)
        if num_total_clients == 0:
            if self.game_started: self.reset_game()
            return

        start_search_idx = (self.current_player + 1) % num_total_clients

        for i in range(num_total_clients):
            check_idx = (start_search_idx + i) % num_total_clients
            potential_next_socket = self.clients[check_idx]
            if potential_next_socket in self.players_alive:
                self.current_player = check_idx
                if notify:
                    self.notify_turn()
                return

        self.log("log", "Ошибка в pass_turn: не удалось найти следующего живого игрока обычным способом.")
        if self.players_alive:
            first_alive_socket = self.players_alive[0]
            try:
                self.current_player = self.clients.index(first_alive_socket)
                self.log("log",
                         f"Аварийное переключение хода на первого живого из списка players_alive: {self.player_names.get(first_alive_socket, '?')}")
                if notify: self.notify_turn()
            except ValueError:
                self.log("log", "Критическая ошибка: Первый живой игрок из players_alive не найден в self.clients.")
                self.reset_game()
        else:
            if self.game_started: self.reset_game()

    def send_bullet_info(self, client_socket):
        if self.game_started:
            message = f"Патроны: {self.live_bullets} боев., {self.blank_bullets} хол. (Всего в барабане: {len(self.chamber)})".encode()
            try:
                client_socket.send(message)
            except Exception as e:
                self.log("log", f"Ошибка отправки инфо о патронах: {e}")
        else:
            try:
                client_socket.send("Игра еще не началась.".encode())
            except Exception as e:
                self.log("log", f"Ошибка отправки 'игра не началась': {e}")

    def notify_turn(self):
        if not self.game_started or not self.players_alive or not self.clients:
            self.update_status()
            return

        if not (0 <= self.current_player < len(self.clients)):
            self.log("log",
                     f"Ошибка notify_turn: неверный индекс current_player ({self.current_player}). Клиентов: {len(self.clients)}. Попытка передать ход.")
            if self.players_alive:
                self.pass_turn(notify=True)
            else:
                self.reset_game()
            return

        current_player_socket = self.clients[self.current_player]

        if current_player_socket not in self.players_alive:
            self.log("log",
                     f"notify_turn: Игрок {self.player_names.get(current_player_socket, '??')} (индекс {self.current_player}) не найден в списке живых. Передаем ход.")
            self.pass_turn(notify=True)
            return

        current_name = self.player_names.get(current_player_socket)
        if current_name:
            self.broadcast(f"\nХод игрока {current_name}")
            try:
                current_player_socket.send("Ваш ход! (я / игрок [имя] / инфо / игроки): ".encode())
            except Exception as e:
                self.log("log", f"Не удалось уведомить {current_name} о его ходе (возможно, отключился): {e}")
        else:
            self.log("log",
                     f"Ошибка notify_turn: Не удалось найти имя для сокета игрока с индексом {self.current_player}. Передача хода.")
            self.pass_turn(notify=True)

        self.update_status()

    def reset_game_state(self):
        self.chamber = []
        self.current_player = 0
        self.game_started = False
        self.players_alive = []
        self.live_bullets = 0
        self.blank_bullets = 0

    def reset_game(self):
        if self.game_started:
            self.log("log", "Игра сбрасывается.")

        self.reset_game_state()
        self.update_status()

        if len(self.clients) >= 2:
            self.log("log", "Достаточно игроков для новой игры. Запуск...")
            self.start_game()
        else:
            self.broadcast("\nОжидание новых игроков или начала новой игры... (нужно минимум 2)")
            self.update_status()

    def broadcast(self, message):
        self.log("broadcast", message)
        message_encoded = f"{message}\n".encode()

        for client_socket in list(self.clients):
            try:
                client_socket.send(message_encoded)
            except Exception as e:
                client_name = self.player_names.get(client_socket, 'Неизвестный')
                self.log("log",
                         f"Ошибка отправки broadcast сообщения игроку {client_name} (возможно, отключается): {e}.")


# --- Класс GUI ---
class RussianRouletteServerGUI(ctk.CTk):
    def __init__(self, host='localhost', port=12345):
        super().__init__()

        self.title("Сервер Русской Рулетки")
        self.geometry("750x600")
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        self.server_running = False
        self.server_thread = None
        self.gui_queue = queue.Queue()
        self.server_instance = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.settings_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.settings_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        self.ip_label = ctk.CTkLabel(self.settings_frame, text="IP Адрес:")
        self.ip_label.grid(row=0, column=0, padx=(5, 2), pady=5, sticky="w")
        self.ip_entry = ctk.CTkEntry(self.settings_frame, placeholder_text="localhost или 0.0.0.0")
        self.ip_entry.grid(row=0, column=1, padx=(0, 10), pady=5, sticky="ew")
        self.ip_entry.insert(0, host)

        self.port_label = ctk.CTkLabel(self.settings_frame, text="Порт:")
        self.port_label.grid(row=0, column=2, padx=(10, 2), pady=5, sticky="w")
        self.port_entry = ctk.CTkEntry(self.settings_frame, width=70)
        self.port_entry.grid(row=0, column=3, padx=(0, 10), pady=5, sticky="w")
        self.port_entry.insert(0, str(port))

        self.settings_frame.grid_columnconfigure(1, weight=1)

        self.control_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.control_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.control_frame.grid_columnconfigure(3, weight=1)

        self.start_button = ctk.CTkButton(self.control_frame, text="Запустить Сервер", command=self.start_server_thread)
        self.start_button.grid(row=0, column=0, padx=5, pady=5)

        self.stop_button = ctk.CTkButton(self.control_frame, text="Остановить Сервер", command=self.stop_server_thread,
                                         state="disabled")
        self.stop_button.grid(row=0, column=1, padx=5, pady=5)

        self.status_label = ctk.CTkLabel(self.control_frame, text="Статус: Остановлен", text_color="red", anchor="w")
        self.status_label.grid(row=0, column=2, padx=(20, 5), pady=5, sticky="w")

        self.info_label = ctk.CTkLabel(self.control_frame, text="", anchor="w")
        self.info_label.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        self.log_textbox = ctk.CTkTextbox(self, wrap="word", state="disabled")
        self.log_textbox.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="nsew")

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.check_queue()

    def log_message(self, message):
        try:
            self.log_textbox.configure(state="normal")
            timestamp = time.strftime("%H:%M:%S")
            self.log_textbox.insert("end", f"[{timestamp}] {message}\n")
            self.log_textbox.configure(state="disabled")
            self.log_textbox.see("end")
        except Exception as e:
            print(f"Ошибка при логировании в GUI: {e}")

    def update_status_display(self, status_data):
        connected = status_data.get("connected", 0)
        alive = status_data.get("alive", 0)
        live = status_data.get("live_bullets", 0)
        blank = status_data.get("blank_bullets", 0)
        turn = status_data.get("turn", "N/A")
        game_running = status_data.get("game_running", False)

        game_state_str = "В игре" if game_running else "Ожидание"
        turn_str = turn
        if game_running and turn == "N/A" and alive > 0:
            turn_str = "Передача хода..."
        elif not game_running and alive == 0 and connected > 0:
            pass

        info_text = f"Подкл: {connected} | Живых: {alive} | {game_state_str} | Патроны: {live}б/{blank}х | Ход: {turn_str}"
        self.info_label.configure(text=info_text)

    def check_queue(self):
        try:
            while True:
                message_type, data = self.gui_queue.get_nowait()

                if message_type == "log":
                    self.log_message(f"[Сервер] {data}")
                elif message_type == "broadcast":
                    self.log_message(f"[Всем] {data.strip()}")
                elif message_type == "status_update":
                    self.update_status_display(data)
                elif message_type == "server_stopped":
                    self.server_stopped_actions()
        except queue.Empty:
            pass
        except Exception as e:
            self.log_message(f"[GUI Ошибка] Ошибка обработки очереди: {e}")
        self.after(100, self.check_queue)

    def start_server_thread(self):
        if self.server_running:
            self.log_message("Сервер уже запущен.")
            return

        host = self.ip_entry.get().strip()
        port_str = self.port_entry.get().strip()

        try:
            port = int(port_str)
            if not (1 <= port <= 65535):
                tkinter.messagebox.showerror("Ошибка Ввода",
                                             f"Неверный порт: {port}.\nПорт должен быть числом от 1 до 65535.")
                return
        except ValueError:
            tkinter.messagebox.showerror("Ошибка Ввода",
                                         f"Неверный формат порта: '{port_str}'.\nВведите число от 1 до 65535.")
            return

        if not host:
            host = 'localhost'
            self.ip_entry.delete(0, "end")
            self.ip_entry.insert(0, host)
            self.log_message("IP адрес не указан, используется 'localhost'.")

        self.log_message(f"Запуск сервера на {host}:{port}...")
        self.server_instance = RussianRouletteServer(host=host, port=port, gui_queue=self.gui_queue)
        self.server_thread = threading.Thread(target=self.server_instance.start, daemon=True)
        self.server_thread.start()

        self.server_running = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.ip_entry.configure(state="disabled")
        self.port_entry.configure(state="disabled")
        self.status_label.configure(text="Статус: Запущен", text_color="green")

    def stop_server_thread(self):
        if self.server_running and self.server_instance:
            self.log_message("Остановка сервера...")
            self.server_instance.stop()
            self.stop_button.configure(state="disabled")
        elif not self.server_instance:
            self.log_message("Сервер не был инициализирован.")
        else:
            self.log_message("Сервер не запущен.")

    def server_stopped_actions(self):
        if not self.server_running and not (self.server_thread and self.server_thread.is_alive()):
            self.log_message("Сервер уже был отмечен как остановленный и поток завершен.")
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.ip_entry.configure(state="normal")
            self.port_entry.configure(state="normal")
            self.status_label.configure(text="Статус: Остановлен", text_color="red")
            return

        self.log_message("Сервер подтвердил остановку.")
        self.server_running = False

        if self.server_thread and self.server_thread.is_alive():
            self.log_message("Ожидание завершения потока сервера...")
            self.server_thread.join(timeout=1.0)
            if self.server_thread.is_alive():
                self.log_message("Поток сервера не завершился вовремя.")
            else:
                self.log_message("Поток сервера успешно завершен.")

        self.server_thread = None
        self.server_instance = None

        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.ip_entry.configure(state="normal")
        self.port_entry.configure(state="normal")
        self.status_label.configure(text="Статус: Остановлен", text_color="red")

    def on_closing(self):
        if self.server_running:
            if tkinter.messagebox.askyesno("Подтверждение", "Сервер запущен. Остановить сервер и закрыть окно?"):
                self.log_message("Закрытие окна: Инициирована остановка сервера...")
                self.stop_server_thread()
                self.after(1500, self.destroy_window_force)
            else:
                return
        else:
            self.destroy()

    def destroy_window_force(self):
        if self.server_thread and self.server_thread.is_alive():
            self.log_message("Принудительное закрытие окна, сервер мог не успеть полностью остановиться.")
        self.destroy()


if __name__ == "__main__":
    DEFAULT_HOST = 'localhost'
    DEFAULT_PORT = 12345
    app = RussianRouletteServerGUI(host=DEFAULT_HOST, port=DEFAULT_PORT)
    app.mainloop()