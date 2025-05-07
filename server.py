import socket
import threading
import random
import time
import queue  # Для потокобезопасного обмена данными
import tkinter.messagebox # Для всплывающих окон с ошибками

import customtkinter as ctk

# --- Модифицированный класс RussianRouletteServer ---

class RussianRouletteServer:
    def __init__(self, host='localhost', port=12345, gui_queue=None):
        self.host = host
        self.port = port
        self.server_socket = None # Инициализируем позже
        self.clients = []
        self.client_threads = [] # Отслеживаем потоки клиентов
        self.player_names = {}  # {socket: name}
        self.name_to_socket = {}  # {name: socket}
        self.bullets = 6 # Всего слотов в барабане по умолчанию
        self.chamber = [] # Текущий барабан
        self.current_player = 0 # Индекс текущего игрока в self.clients
        self.game_started = False # Флаг, идет ли игра
        self.players_alive = [] # Список сокетов живых игроков
        self.live_bullets = 0 # Количество боевых патронов
        self.blank_bullets = 0 # Количество холостых патронов
        self.running = False # Флаг для управления основным циклом сервера
        self.gui_queue = gui_queue # Очередь для отправки сообщений в GUI

    def log(self, message_type, data):
        """Отправляет данные в очередь GUI."""
        if self.gui_queue:
            try:
                # Помещаем кортеж (тип_сообщения, данные) в очередь
                self.gui_queue.put((message_type, data), block=False)
            except queue.Full:
                # Резервное логирование в консоль, если очередь переполнена
                print("Внимание: Очередь GUI переполнена!")

    def update_status(self):
        """Отправляет текущий статус игры в GUI."""
        # Определяем имя текущего игрока, если игра идет
        current_turn_name = "N/A" # Not Applicable / Не применимо
        if self.game_started and self.clients and 0 <= self.current_player < len(self.clients):
             current_socket = self.clients[self.current_player]
             current_turn_name = self.player_names.get(current_socket, "ОшибкаИмени")

        status = {
            "connected": len(self.clients),
            "alive": len(self.players_alive) if self.game_started else 0,
            "live_bullets": self.live_bullets if self.game_started else 0,
            "blank_bullets": self.blank_bullets if self.game_started else 0,
            "turn": current_turn_name,
            "game_running": self.game_started
        }
        self.log("status_update", status) # Отправляем статус в GUI

    def start(self):
        """Основной метод запуска сервера."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Позволяет повторно использовать адрес сразу после остановки сервера
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5) # Максимум 5 ожидающих подключений
            # Устанавливаем таймаут, чтобы accept не блокировал навечно,
            # и мы могли проверять флаг self.running
            self.server_socket.settimeout(1.0)
            self.running = True
            self.log("log", f"Сервер запущен на {self.host}:{self.port}. Ожидание игроков...")
            self.update_status() # Обновляем статус в GUI

            # Главный цикл ожидания подключений
            while self.running:
                try:
                    # Ожидаем подключение с таймаутом
                    client_socket, addr = self.server_socket.accept()
                    # Проверяем флаг еще раз после accept, т.к. могли остановить сервер пока ждали
                    if not self.running:
                        client_socket.close()
                        break

                    # Ограничение на количество игроков
                    if len(self.clients) < 6:
                        self.clients.append(client_socket)
                        player_num = len(self.clients)
                        self.log("log", f"Новое подключение от {addr}. Игрок {player_num}.")
                        # Запускаем поток для обработки клиента
                        thread = threading.Thread(target=self.handle_client, args=(client_socket, player_num), daemon=True)
                        self.client_threads.append(thread)
                        thread.start()
                        self.update_status() # Обновляем GUI о новом подключении
                    else:
                        # Сервер полон
                        self.log("log", f"Отклонено подключение от {addr}: Сервер переполнен.")
                        client_socket.send("Сервер переполнен".encode())
                        client_socket.close()
                except socket.timeout:
                    # Таймаут сработал, подключений не было. Просто продолжаем цикл, чтобы проверить self.running.
                    continue
                except Exception as e:
                    # Логируем другие ошибки, если сервер еще должен работать
                    if self.running:
                         self.log("log", f"Ошибка в главном цикле приема подключений: {e}")
                    break # Выходим из цикла при других ошибках

        except OSError as e:
             # Ошибка привязки сокета (часто - порт занят)
             self.log("log", f"Ошибка запуска сервера (возможно, порт {self.port} занят): {e}")
             # Сообщаем GUI, что сервер не запустился и остановился
             if self.gui_queue:
                self.gui_queue.put(("server_stopped", None), block=False)
        finally:
            # Этот блок выполняется всегда: при нормальном выходе или из-за ошибки
            self.log("log", "Сервер останавливается...")
            self.running = False # Убеждаемся, что флаг остановлен
            if self.server_socket:
                self.server_socket.close()
                self.server_socket = None
            self._cleanup_clients() # Закрываем соединения клиентов
            self.reset_game_state() # Сбрасываем состояние игры
            self.update_status() # Обновляем статус в GUI последний раз
            self.log("log", "Сервер остановлен.")
            # Сообщаем GUI, что сервер точно остановился (если еще не сделано)
            if self.gui_queue:
                 try: self.gui_queue.put(("server_stopped", None), block=False)
                 except queue.Full: pass


    def stop(self):
        """Сигнализирует серверу о необходимости остановиться."""
        if not self.running:
            return # Уже остановлен
        self.log("log", "Получен сигнал остановки...")
        self.running = False
        # Попытка разблокировать server_socket.accept(), подключившись к самому себе.
        # Это не всегда работает надежно, но часто помогает.
        try:
            # Создаем временное соединение к своему же серверу
            with socket.create_connection((self.host, self.port), timeout=0.5) as sock:
                pass # Просто подключаемся и сразу закрываем
        except Exception:
             # Игнорируем ошибки здесь, т.к. главная цель - разбудить accept()
            pass

    def _cleanup_clients(self):
         """Закрывает все сокеты клиентов и очищает списки."""
         self.log("log", "Закрытие клиентских соединений...")
         # Создаем копии списков, чтобы безопасно удалять элементы во время итерации
         clients_copy = self.clients[:]
         names_copy = list(self.player_names.values()) # Получаем список имен для лога

         for client_socket in clients_copy:
             try:
                 # Пытаемся уведомить клиента об отключении
                 client_socket.send("Сервер отключается.".encode())
                 client_socket.shutdown(socket.SHUT_RDWR) # Сигнализируем о закрытии
                 client_socket.close()
             except Exception as e:
                 # Логируем ошибку, но продолжаем закрывать остальные
                 self.log("log", f"Ошибка при закрытии сокета клиента: {e}")
             # Удаляем клиента из внутренних структур данных (даже если была ошибка закрытия)
             self._remove_client(client_socket, notify_others=False) # Не уведомляем других, т.к. все отключаются

         # Принудительно завершаем потоки клиентов (опционально, может замедлить остановку)
         # for thread in self.client_threads:
         #     thread.join(timeout=0.5)
         self.client_threads.clear() # Очищаем список потоков
         self.log("log", f"Удалены игроки: {', '.join(names_copy) if names_copy else 'Нет'}")


    def _remove_client(self, client_socket, notify_others=True):
        """Удаляет клиента и связанные с ним данные."""
        was_in_game = client_socket in self.players_alive
        name = self.player_names.pop(client_socket, None) # Удаляем из словаря имен, получаем имя

        if client_socket in self.clients:
            try:
                # Запоминаем индекс перед удалением, если это был текущий игрок
                 original_index = self.clients.index(client_socket)
                 is_current = self.game_started and self.current_player == original_index
            except ValueError:
                 original_index = -1
                 is_current = False
            self.clients.remove(client_socket) # Удаляем из основного списка
        else:
             original_index = -1
             is_current = False


        if name:
            self.name_to_socket.pop(name.lower(), None) # Удаляем из словаря имя->сокет
            if notify_others:
                self.log("log", f"Игрок {name} отключился или удален.")
                self.broadcast(f"{name} покинул игру.")
        if client_socket in self.players_alive:
            self.players_alive.remove(client_socket) # Удаляем из списка живых

        # Логика после удаления клиента (если игра шла)
        if self.game_started and was_in_game:
            # Проверяем, не закончилась ли игра
            if len(self.players_alive) <= 1:
                 if len(self.players_alive) == 1:
                     winner_name = self.player_names.get(self.players_alive[0], "Неизвестный")
                     self.broadcast(f"\n=== ИГРА ОКОНЧЕНА ===\n{winner_name} побеждает!")
                 else:
                     self.broadcast("\n=== ИГРА ОКОНЧЕНА ===\nВсе игроки выбыли!")
                 self.reset_game()
            # Если удалили текущего игрока, нужно передать ход
            elif is_current and self.players_alive:
                 self.log("log", f"Текущий игрок {name} отключился, передаем ход.")
                 # Индекс current_player может стать невалидным после удаления.
                 # Pass_turn сам найдет следующего живого.
                 # Но т.к. current_player уже указывает на "несуществующего"
                 # или следующего игрока (из-за self.clients.remove),
                 # надо аккуратно передать ход.
                 # Безопаснее всего просто пересчитать с нуля.
                 if self.clients: # Если еще остались клиенты
                     # Устанавливаем current_player на валидный индекс или 0
                     self.current_player = original_index % len(self.clients) if len(self.clients) > 0 else 0
                     self.pass_turn(notify=True) # Передаем ход и уведомляем
                 else:
                     self.reset_game() # Клиентов не осталось

            # Если удалили не текущего, но игроков стало меньше 2
            elif len(self.clients) < 2 and self.game_started:
                  self.broadcast("Недостаточно игроков для продолжения.")
                  self.reset_game()
            # Если удалили не текущего, но current_player теперь указывает за пределы списка
            elif self.current_player >= len(self.clients) and self.clients:
                 self.current_player = 0 # Возвращаем на начало списка


        self.update_status() # Обновляем статус в GUI


    def handle_client(self, client_socket, player_num):
        """Обрабатывает сообщения от одного клиента."""
        name = f"Игрок_{player_num}" # Имя по умолчанию
        try:
            # Запрос имени
            client_socket.send(f"Добро пожаловать! Вы игрок {player_num}\nВведите ваше имя:".encode())
            name_bytes = client_socket.recv(1024)
            if not name_bytes: # Если клиент сразу отключился
                raise ConnectionResetError("Клиент отключился при запросе имени")
            name_input = name_bytes.decode().strip()

            if not name_input:
                # Имя не введено, используем имя по умолчанию
                pass # name уже = f"Игрок_{player_num}"
            else:
                 name = name_input

            # Проверка на уникальность имени
            original_name = name
            count = 1
            # Преобразуем имя к нижнему регистру для проверки уникальности
            while name.lower() in self.name_to_socket:
                 name = f"{original_name}_{count}"
                 count += 1
                 if count > 10: # Предохранитель от бесконечного цикла, если что-то пошло не так
                      name = f"Игрок_{random.randint(1000,9999)}" # Генерируем случайное имя
                      break

            # Сохраняем имя и сокет
            self.player_names[client_socket] = name
            self.name_to_socket[name.lower()] = client_socket
            self.log("log", f"Игрок {player_num} теперь '{name}'.")
            # Уведомляем всех о новом игроке
            self.broadcast(f"{name} присоединился к игре! Всего игроков: {len(self.clients)}")
            self.update_status() # Обновляем статус в GUI

            # Проверка на начало игры
            # Используем блокировку для предотвращения гонки состояний при старте игры
            # (Хотя в данном случае это менее критично, т.к. start_game проверяет внутри)
            if len(self.clients) >= 2 and not self.game_started:
                self.start_game()

            # Цикл обработки сообщений от клиента
            while self.running: # Проверяем флаг работы сервера
                try:
                    data_bytes = client_socket.recv(1024)
                    if not data_bytes:
                        # Клиент отправил пустые данные (обычно означает отключение)
                        self.log("log", f"{name} отключился (пустые данные).")
                        break # Выходим из цикла обработки сообщений
                    data = data_bytes.decode().strip().lower()
                except ConnectionResetError:
                    self.log("log", f"Соединение с {name} сброшено.")
                    break
                except Exception as e:
                    self.log("log", f"Ошибка при получении данных от {name}: {e}")
                    break


                # Обработка команд
                if not self.game_started:
                    client_socket.send("Игра еще не началась. Ожидание игроков...".encode())
                    continue # Игнорируем команды, если игра не идет

                if client_socket not in self.players_alive:
                     client_socket.send("Вы выбыли из игры.".encode())
                     continue # Игнорируем команды, если игрок мертв

                # Обработка команд 'инфо' и 'игроки' доступна всегда
                if data == "инфо":
                    self.send_bullet_info(client_socket)
                elif data == "игроки":
                    self.send_player_list(client_socket)
                # Проверяем, ход ли этого игрока
                elif self.clients[self.current_player] == client_socket:
                    if data == "я":
                        self.process_shot(client_socket, target="self")
                    elif data.startswith("игрок "):
                        # Извлекаем имя цели
                        target_name = data[len("игрок "):].strip()
                        self.process_player_target(client_socket, target_name)
                    else:
                        client_socket.send("Ваш ход. Используйте: 'я', 'игрок [имя]', 'инфо' или 'игроки'".encode())
                else:
                    # Не ход этого игрока
                    current_turn_name = "???"
                    # Проверяем, действителен ли индекс current_player
                    if 0 <= self.current_player < len(self.clients):
                        current_turn_socket = self.clients[self.current_player]
                        current_turn_name = self.player_names.get(current_turn_socket, "???")

                    client_socket.send(f"Сейчас не ваш ход. Ходит {current_turn_name}.".encode())

        except ConnectionResetError:
            # Это нормальное явление, если клиент просто закрыл соединение
            self.log("log", f"Соединение с {name} было сброшено.")
        except Exception as e:
            # Логируем другие ошибки, если сервер работает
            if self.running:
                self.log("log", f"Ошибка в handle_client ({name}): {e}")
        finally:
            # Этот блок выполняется всегда при выходе из try (нормальном или из-за ошибки)
            # или при разрыве соединения
            self.log("log", f"Завершение обработки клиента {name}.")
            # Удаляем клиента из системы
            self._remove_client(client_socket, notify_others=True) # Уведомляем остальных

            # Закрываем сокет клиента (на всякий случай, если еще не закрыт)
            if client_socket:
                try:
                    client_socket.close()
                except Exception: pass # Игнорируем ошибки при закрытии

    def process_player_target(self, shooter_socket, target_name):
        """Обрабатывает попытку выстрелить в другого игрока."""
        shooter_name = self.player_names.get(shooter_socket, "Неизвестный")
        if not target_name:
            shooter_socket.send("Укажите имя игрока после 'игрок '".encode())
            return

        # Нельзя стрелять в самого себя через команду 'игрок [свое_имя]'
        if target_name.lower() == shooter_name.lower():
            # shooter_socket.send("Чтобы выстрелить в себя, используйте команду 'я'".encode())
            # Или просто выполняем выстрел в себя:
             self.process_shot(shooter_socket, target="self")
             return

        # Ищем сокет цели по имени
        target_socket = self.name_to_socket.get(target_name.lower())

        if target_socket:
            # Проверяем, жив ли игрок-цель
            if target_socket in self.players_alive:
                self.process_shot(shooter_socket, target=target_socket)
            else:
                # Цель найдена, но уже выбыла
                target_real_name = self.player_names.get(target_socket, target_name) # Получаем реальное имя
                shooter_socket.send(f"Игрок {target_real_name} уже выбыл!".encode())
        else:
            # Игрок с таким именем не найден
            shooter_socket.send("Игрок с таким именем не найден или не в игре. Используйте 'игроки' чтобы увидеть список.".encode())

    def send_player_list(self, client_socket):
        """Отправляет клиенту список живых игроков."""
        alive_players_info = []
        current_name = "" # Имя того, чей сейчас ход

        # Получаем имя текущего игрока, если игра идет
        if self.game_started and self.clients and self.players_alive:
             # Проверка валидности индекса current_player
             if 0 <= self.current_player < len(self.clients):
                 current_socket = self.clients[self.current_player]
                 current_name = self.player_names.get(current_socket,"??") # Получаем имя по сокету

        # Формируем список живых игроков
        for client in self.players_alive:
            name = self.player_names.get(client, "Неизвестный")
            # Отмечаем, чей сейчас ход
            is_current = " (ходит)" if name == current_name and name != "Неизвестный" else ""
            alive_players_info.append(f"- {name}{is_current}")

        if alive_players_info:
            message = "Живые игроки:\n" + "\n".join(alive_players_info)
        else:
            message = "Нет живых игроков."

        # Добавляем список доступных целей, если это ход запрашивающего игрока
        # и есть другие живые игроки
        is_requester_turn = False
        if self.game_started and self.clients and 0 <= self.current_player < len(self.clients):
            is_requester_turn = (client_socket == self.clients[self.current_player])

        if is_requester_turn:
             targets = [self.player_names.get(p) for p in self.players_alive if p != client_socket and p in self.player_names]
             targets = [name for name in targets if name] # Убираем None если имя не нашлось
             if targets:
                  message += "\n\nДоступные цели для 'игрок [имя]':\n" + "\n".join([f"- {name}" for name in targets])
             elif len(self.players_alive) > 1: # Если есть другие игроки, но что-то пошло не так с именами
                  message += "\n\nНе удалось определить доступные цели."
             else: # Если остался только один игрок (запрашивающий)
                  message += "\n\nНет других игроков для выбора!"

        client_socket.send(message.encode())

    def start_game(self):
        """Начинает новый раунд игры."""
        # Еще раз проверяем количество игроков на случай, если кто-то отключился
        if len(self.clients) < 2:
             self.broadcast("Нужно минимум 2 игрока для старта.")
             self.game_started = False # Убеждаемся, что флаг сброшен
             self.update_status()
             return

        self.game_started = True
        # Копируем текущих клиентов в список живых
        self.players_alive = self.clients.copy()
        # Заряжаем барабан
        self.load_chamber()
        # Выбираем случайного игрока для первого хода
        self.current_player = random.randrange(len(self.clients))
        self.broadcast("\n=== ИГРА НАЧИНАЕТСЯ ===")
        self.broadcast(f"Патроны в барабане: {self.live_bullets} боевых и {self.blank_bullets} холостых")
        self.broadcast(
            "Правила:\n"
            "'я' - выстрелить в себя\n"
            "'игрок [имя]' - выстрелить в другого игрока\n"
            "'инфо' - информация о патронах\n"
            "'игроки' - список живых игроков")
        # Уведомляем, чей ход
        self.notify_turn()
        self.update_status() # Обновляем статус в GUI

    def load_chamber(self):
        """Заряжает барабан случайным количеством боевых и холостых патронов."""
        # self.bullets = 6 # Можно сделать разное кол-во слотов, но пока фиксировано
        self.live_bullets = random.randint(1, 3) # От 1 до 3 боевых
        self.blank_bullets = self.bullets - self.live_bullets # Остальные - холостые
        # Создаем список патронов (True - боевой, False - холостой)
        bullets_list = [True] * self.live_bullets + [False] * self.blank_bullets
        # Перемешиваем патроны в барабане
        random.shuffle(bullets_list)
        self.chamber = bullets_list
        self.log("log", f"Барабан заряжен: {self.live_bullets} боевых, {self.blank_bullets} холостых. Порядок: {''.join(['Б' if b else 'Х' for b in self.chamber])}")
        self.update_status() # Обновляем GUI

    def process_shot(self, shooter_socket, target):
        """Обрабатывает выстрел."""
        # Проверка на пустой барабан (на всякий случай)
        if not self.chamber:
             self.broadcast("Ошибка: Барабан пуст, но выстрел произведен? Перезарядка...")
             self.load_chamber()
             # Возможно, стоит просто пропустить ход или выдать ошибку клиенту
             if not self.chamber: # Если и после перезарядки пусто (маловероятно)
                 self.broadcast("Критическая ошибка: не удалось зарядить барабан.")
                 self.reset_game()
                 return
             # Повторная попытка выстрела не нужна, т.к. ход уже сделан.
             # Передаем ход следующему.
             self.pass_turn(notify=True)
             return

        # Получаем имена стрелка и цели
        shooter_name = self.player_names.get(shooter_socket, "Неизвестный")
        is_self_shot = (target == "self" or target == shooter_socket)

        if is_self_shot:
            target_socket = shooter_socket
            target_name = shooter_name
            action_verb = "стреляет в себя"
        else:
            target_socket = target
            target_name = self.player_names.get(target_socket, "Неизвестный")
            action_verb = f"стреляет в {target_name}"

        # Извлекаем первый патрон из барабана
        current_bullet = self.chamber.pop(0) # Используем и удаляем патрон
        shot_type = "БОЕВОЙ" if current_bullet else "ХОЛОСТОЙ"

        # Уведомляем всех о выстреле
        self.broadcast(f"\n{shooter_name} {action_verb}... {shot_type}!")

        notify_next_turn = True # Флаг, нужно ли уведомлять о следующем ходе

        if current_bullet: # --- Боевой патрон ---
            self.live_bullets -= 1
            # Проверяем, была ли цель жива
            if target_socket in self.players_alive:
                self.players_alive.remove(target_socket) # Удаляем из живых
                self.broadcast(f"{target_name} выбывает из игры!")
                # Передаем ход следующему игроку (т.к. этот ход закончен)
                self.pass_turn(notify=False) # Передаем ход, но пока не уведомляем
            else:
                 # Странная ситуация: стреляли в уже выбывшего игрока?
                 self.broadcast(f"Странно, {target_name} уже был вне игры...")
                 self.pass_turn(notify=False) # Все равно передаем ход

        else: # --- Холостой патрон ---
            self.blank_bullets -= 1
            self.broadcast(f"{shooter_name} в безопасности (пока что).")
            if is_self_shot:
                # Выстрелил в себя холостым -> получает доп. ход
                 self.broadcast(f"{shooter_name} получает дополнительный ход!")
                 # notify_turn() будет вызван ниже автоматически, т.к. ход не передается
                 notify_next_turn = True # Нужно уведомить этого же игрока еще раз
            else:
                # Выстрелил в другого холостым -> ход переходит
                self.pass_turn(notify=False) # Передаем ход, но пока не уведомляем

        self.update_status() # Обновляем статус в GUI

        # --- Проверки после выстрела ---

        # 1. Проверка на конец игры
        if len(self.players_alive) == 1:
            winner_socket = self.players_alive[0]
            winner_name = self.player_names.get(winner_socket, "Неизвестный")
            self.broadcast(f"\n=== ИГРА ОКОНЧЕНА ===\n{winner_name} побеждает!")
            self.reset_game()
            return # Игра окончена, выходим из метода
        elif len(self.players_alive) == 0:
             self.broadcast("\n=== ИГРА ОКОНЧЕНА ===\nНикто не выжил!")
             self.reset_game()
             return # Игра окончена

        # 2. Проверка на пустой барабан
        if not self.chamber:
            self.broadcast("\nБарабан пуст! Производится перезарядка...")
            self.load_chamber()
            self.broadcast(f"Новые патроны: {self.live_bullets} боевых и {self.blank_bullets} холостых")
            # После перезарядки ход НЕ передается дополнительно, он уже был передан (или не передан при доп. ходе)

        # 3. Уведомление о следующем ходе (если он был передан или это доп. ход)
        if notify_next_turn:
             # Небольшая задержка перед уведомлением для лучшего восприятия лога
             # time.sleep(0.5) # Раскомментировать для паузы
             self.notify_turn()


    def pass_turn(self, notify=True):
        """Передает ход следующему живому игроку."""
        if not self.players_alive:
             # Некому передавать ход
             self.log("log", "pass_turn вызван без живых игроков.")
             if self.game_started: # Если игра шла, завершаем ее
                self.broadcast("\n=== ИГРА ОКОНЧЕНА ===\nНе осталось живых игроков.")
                self.reset_game()
             return

        if not self.clients:
             self.log("log", "pass_turn вызван без подключенных клиентов.")
             if self.game_started: self.reset_game()
             return

        num_clients = len(self.clients)
        # Начинаем поиск со следующего индекса
        next_player_index = (self.current_player + 1) % num_clients

        # Ищем следующего игрока, который есть в списке живых
        for i in range(num_clients): # Проходим не более одного круга
            check_index = (next_player_index + i) % num_clients
            potential_next_socket = self.clients[check_index]
            if potential_next_socket in self.players_alive:
                # Нашли следующего живого игрока
                self.current_player = check_index
                if notify:
                    self.notify_turn() # Уведомляем его о ходе
                return # Выход из функции

        # Если цикл завершился, а мы никого не нашли (очень странно, если players_alive не пуст)
        self.log("log", "Ошибка: Не удалось найти следующего живого игрока в pass_turn, хотя список живых не пуст.")
        # В качестве запасного варианта, выберем первого живого из списка живых
        if self.players_alive:
            first_alive_socket = self.players_alive[0]
            try:
                self.current_player = self.clients.index(first_alive_socket)
                self.log("log", f"Аварийное переключение хода на первого живого: {self.player_names.get(first_alive_socket, '?')}")
                if notify: self.notify_turn()
            except ValueError:
                 self.log("log", "Критическая ошибка: Первый живой игрок не найден в общем списке клиентов.")
                 self.reset_game()
        else:
             # Сюда не должны были попасть из-за проверки в начале, но на всякий случай
             self.reset_game()


    def send_bullet_info(self, client_socket):
        """Отправляет клиенту информацию о патронах."""
        if self.game_started:
            message = f"Патроны: {self.live_bullets} боев., {self.blank_bullets} хол. (Всего в барабане: {len(self.chamber)})".encode()
            client_socket.send(message)
        else:
            client_socket.send("Игра еще не началась.".encode())

    def notify_turn(self):
        """Уведомляет текущего игрока о его ходе."""
        # Проверки на валидность состояния игры
        if not self.game_started or not self.players_alive or not self.clients:
            return

        # Проверка валидности индекса current_player
        if not (0 <= self.current_player < len(self.clients)):
             self.log("log", f"Ошибка: неверный индекс current_player ({self.current_player}) при уведомлении о ходе. Список клиентов: {len(self.clients)}. Сброс игры.")
             self.reset_game()
             return

        current_player_socket = self.clients[self.current_player]

        # Дополнительная проверка: действительно ли этот игрок жив?
        if current_player_socket not in self.players_alive:
            self.log("log", f"Уведомление о ходе для игрока {self.current_player}, но он не найден в списке живых. Передаем ход.")
            self.pass_turn(notify=True) # Передаем ход следующему
            return

        # Получаем имя текущего игрока
        current_name = self.player_names.get(current_player_socket, None)

        if current_name:
            # Уведомляем всех
            self.broadcast(f"\nХод игрока {current_name}")
            # Отправляем личное сообщение текущему игроку
            try:
                current_player_socket.send("Ваш ход! (я / игрок [имя] / инфо / игроки): ".encode())
                self.update_status() # Обновляем статус в GUI (чей ход)
            except Exception as e:
                # Ошибка при отправке сообщения (вероятно, клиент отключился)
                self.log(f"Не удалось уведомить {current_name} о его ходе (возможно, отключился): {e}")
                # Обрабатываем отключение этого клиента
                self._remove_client(current_player_socket, notify_others=True)
                # Передавать ход не нужно здесь, т.к. _remove_client это сделает, если нужно
        else:
             # Не смогли найти имя для текущего сокета (очень странно)
             self.log("log", f"Ошибка: Не удалось найти имя для сокета игрока с индексом {self.current_player}. Передача хода.")
             self.pass_turn(notify=True)


    def reset_game_state(self):
         """Сбрасывает только переменные состояния игры, не трогая соединения."""
         self.chamber = []
         self.current_player = 0
         self.game_started = False
         self.players_alive = []
         self.live_bullets = 0
         self.blank_bullets = 0
         # self.clients, self.player_names, self.name_to_socket остаются

    def reset_game(self):
        """Сбрасывает состояние игры и уведомляет игроков."""
        # Уведомляем только если игра действительно шла
        if self.game_started:
            self.log("log", "Игра сбрасывается.")
            self.broadcast("\nОжидание новых игроков или начала новой игры... (нужно минимум 2)")
        # Сбрасываем переменные игры
        self.reset_game_state()
        self.update_status() # Обновляем GUI

        # Проверяем, можно ли сразу начать новую игру
        if len(self.clients) >= 2:
             self.log("log", "Достаточно игроков для новой игры. Запуск...")
             # Можно добавить небольшую паузу перед авто-стартом
             # time.sleep(2)
             self.start_game() # Начинаем новую игру


    def broadcast(self, message):
        """Отправляет сообщение всем подключенным клиентам."""
        # Сначала логируем сообщение в GUI
        self.log("broadcast", message)
        message_encoded = f"{message}\n".encode() # Добавляем перевод строки для читаемости у клиента
        # Создаем копию списка клиентов, чтобы избежать проблем при удалении клиента во время итерации
        clients_copy = self.clients[:]
        for client in clients_copy:
            try:
                client.send(message_encoded)
            except Exception as e:
                # Ошибка при отправке -> считаем, что клиент отключился
                client_name = self.player_names.get(client, 'Неизвестный')
                self.log("log", f"Ошибка отправки сообщения игроку {client_name}: {e}. Удаление.")
                # Удаляем клиента из системы
                self._remove_client(client, notify_others=False) # Не уведомляем других, т.к. это broadcast
                # Закрываем сокет на всякий случай
                try: client.close()
                except Exception: pass


# --- Класс GUI ---

class RussianRouletteServerGUI(ctk.CTk):
    def __init__(self, host='localhost', port=12345):
        super().__init__()

        self.title("Сервер Русской Рулетки")
        self.geometry("750x600") # Немного увеличим размер
        ctk.set_appearance_mode("Light") # System, Dark, Light
        ctk.set_default_color_theme("blue") # blue, green, dark-blue

        # --- Переменные состояния ---
        self.server_running = False
        self.server_thread = None
        self.gui_queue = queue.Queue() # Очередь для получения сообщений от сервера
        self.server_instance = None # Храним экземпляр сервера здесь

        # --- Макет окна ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1) # Строка с логом будет растягиваться

        # --- Фрейм настроек (IP, Порт) ---
        self.settings_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.settings_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        self.ip_label = ctk.CTkLabel(self.settings_frame, text="IP Адрес:")
        self.ip_label.grid(row=0, column=0, padx=(5, 2), pady=5, sticky="w")
        self.ip_entry = ctk.CTkEntry(self.settings_frame, placeholder_text="localhost или 0.0.0.0")
        self.ip_entry.grid(row=0, column=1, padx=(0, 10), pady=5, sticky="ew")
        self.ip_entry.insert(0, host) # Устанавливаем значение по умолчанию

        self.port_label = ctk.CTkLabel(self.settings_frame, text="Порт:")
        self.port_label.grid(row=0, column=2, padx=(10, 2), pady=5, sticky="w")
        self.port_entry = ctk.CTkEntry(self.settings_frame, width=70)
        self.port_entry.grid(row=0, column=3, padx=(0, 10), pady=5, sticky="w")
        self.port_entry.insert(0, str(port)) # Устанавливаем значение по умолчанию

        # Расширяем колонку с IP адресом
        self.settings_frame.grid_columnconfigure(1, weight=1)

        # --- Фрейм управления и статуса ---
        self.control_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.control_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.control_frame.grid_columnconfigure(3, weight=1) # Колонка с информацией будет растягиваться

        self.start_button = ctk.CTkButton(self.control_frame, text="Запустить Сервер", command=self.start_server_thread)
        self.start_button.grid(row=0, column=0, padx=5, pady=5)

        self.stop_button = ctk.CTkButton(self.control_frame, text="Остановить Сервер", command=self.stop_server_thread, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=5, pady=5)

        # Статус (Запущен/Остановлен)
        self.status_label = ctk.CTkLabel(self.control_frame, text="Статус: Остановлен", text_color="red", anchor="w")
        self.status_label.grid(row=0, column=2, padx=(20, 5), pady=5, sticky="w")

        # Подробная информация о состоянии игры
        self.info_label = ctk.CTkLabel(self.control_frame, text="", anchor="w")
        self.info_label.grid(row=0, column=3, padx=5, pady=5, sticky="ew")


        # --- Текстовое поле для логов ---
        self.log_textbox = ctk.CTkTextbox(self, wrap="word", state="disabled") # wrap=word переносит слова целиком
        self.log_textbox.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="nsew") # Растягиваем во все стороны

        # --- Настройка поведения при закрытии окна ---
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- Запуск проверки очереди ---
        self.check_queue()

    def log_message(self, message):
        """Потокобезопасно добавляет сообщение в текстовое поле лога."""
        try:
            self.log_textbox.configure(state="normal") # Включаем редактирование
            timestamp = time.strftime("%H:%M:%S") # Добавляем временную метку
            self.log_textbox.insert("end", f"[{timestamp}] {message}\n")
            self.log_textbox.configure(state="disabled") # Выключаем редактирование
            self.log_textbox.see("end") # Прокручиваем вниз
        except Exception as e:
            print(f"Ошибка при логировании в GUI: {e}") # Резервный вывод в консоль

    def update_status_display(self, status_data):
         """Обновляет метки статуса на основе данных от сервера."""
         # Извлекаем данные из словаря, используя .get() для безопасности
         connected = status_data.get("connected", 0)
         alive = status_data.get("alive", 0)
         live = status_data.get("live_bullets", 0)
         blank = status_data.get("blank_bullets", 0)
         turn = status_data.get("turn", "N/A")
         game_running = status_data.get("game_running", False)

         game_state = "В игре" if game_running else "Ожидание"
         info_text = f"Подкл: {connected} | Живых: {alive} | {game_state} | Патроны: {live}б/{blank}х | Ход: {turn}"
         self.info_label.configure(text=info_text) # Обновляем метку с информацией

    def check_queue(self):
        """Периодически проверяет очередь на наличие сообщений от потока сервера."""
        try:
            # Обрабатываем все сообщения, которые есть в очереди на данный момент
            while True:
                message_type, data = self.gui_queue.get_nowait() # Получаем без блокировки

                if message_type == "log":
                    self.log_message(f"[Сервер] {data}")
                elif message_type == "broadcast":
                     # Убираем лишние переводы строк для лога GUI
                     self.log_message(f"[Всем] {data.strip()}")
                elif message_type == "status_update":
                     self.update_status_display(data) # Обновляем строку статуса
                elif message_type == "server_stopped":
                     # Это сообщение сервер отправляет, когда его основной цикл завершен
                     self.server_stopped_actions()

        except queue.Empty:
            # Очередь пуста, ничего не делаем
            pass
        except Exception as e:
             # Логируем неожиданные ошибки при обработке очереди
             self.log_message(f"[GUI Ошибка] Ошибка обработки очереди: {e}")

        # Планируем следующую проверку очереди через 100 миллисекунд
        self.after(100, self.check_queue)


    def start_server_thread(self):
        """Запускает сервер в отдельном потоке."""
        if self.server_running:
            self.log_message("Сервер уже запущен.")
            return

        # --- Получаем IP и Порт из полей ввода ---
        host = self.ip_entry.get().strip()
        port_str = self.port_entry.get().strip()

        # --- Валидация порта ---
        try:
            port = int(port_str)
            if not (1 <= port <= 65535):
                # Вызываем стандартное окно с ошибкой
                tkinter.messagebox.showerror("Ошибка Ввода", f"Неверный порт: {port}.\nПорт должен быть числом от 1 до 65535.")
                return # Не запускаем сервер
        except ValueError:
            tkinter.messagebox.showerror("Ошибка Ввода", f"Неверный формат порта: '{port_str}'.\nВведите число от 1 до 65535.")
            return # Не запускаем сервер

        # --- Валидация IP (простая) ---
        if not host:
             host = 'localhost' # Если пусто, используем localhost по умолчанию
             self.ip_entry.delete(0, "end")
             self.ip_entry.insert(0, host)
             self.log_message("IP адрес не указан, используется 'localhost'.")
        # Можно добавить более сложную валидацию IP, если нужно

        # --- Запуск сервера ---
        self.log_message(f"Запуск сервера на {host}:{port}...")

        # Создаем новый экземпляр сервера с актуальными host и port
        self.server_instance = RussianRouletteServer(host=host, port=port, gui_queue=self.gui_queue)

        # Создаем и запускаем поток сервера
        self.server_thread = threading.Thread(target=self.server_instance.start, daemon=True)
        self.server_thread.start()

        # --- Обновляем состояние GUI ---
        self.server_running = True
        self.start_button.configure(state="disabled") # Блокируем кнопку "Запустить"
        self.stop_button.configure(state="normal")   # Разблокируем кнопку "Остановить"
        self.ip_entry.configure(state="disabled")    # Блокируем поле IP
        self.port_entry.configure(state="disabled")  # Блокируем поле Порт
        self.status_label.configure(text="Статус: Запущен", text_color="green") # Обновляем метку статуса

    def stop_server_thread(self):
        """Останавливает поток сервера."""
        if self.server_running and self.server_instance:
            self.log_message("Остановка сервера...")
            self.server_instance.stop() # Посылаем сигнал остановки серверу
            # Не ждем здесь завершения потока, т.к. он сам сообщит через очередь
            # Блокируем кнопку "Остановить" сразу для предотвращения повторных нажатий
            self.stop_button.configure(state="disabled")
        elif not self.server_instance:
             self.log_message("Сервер не был инициализирован.")
        else:
            self.log_message("Сервер не запущен.")

    def server_stopped_actions(self):
         """Действия, выполняемые после подтверждения остановки сервера (через очередь)."""
         self.log_message("Сервер подтвердил остановку.")
         self.server_running = False
         # Поток должен завершиться сам, но на всякий случай можно подождать
         if self.server_thread and self.server_thread.is_alive():
              # self.server_thread.join(timeout=1.0) # Ждем недолго (опционально)
              pass
         self.server_thread = None
         self.server_instance = None # Сбрасываем экземпляр сервера

         # --- Обновляем состояние GUI ---
         self.start_button.configure(state="normal")  # Разблокируем кнопку "Запустить"
         self.stop_button.configure(state="disabled") # Оставляем "Остановить" заблокированной
         self.ip_entry.configure(state="normal")      # Разблокируем поле IP
         self.port_entry.configure(state="normal")    # Разблокируем поле Порт
         self.status_label.configure(text="Статус: Остановлен", text_color="red") # Обновляем метку статуса
         # Можно сбросить информационную метку или оставить последнее состояние
         # self.info_label.configure(text="")


    def on_closing(self):
        """Обрабатывает событие закрытия окна."""
        if self.server_running:
            # Если сервер работает, пытаемся его остановить перед закрытием
            self.log_message("Окно закрывается, останавливаем сервер...")
            # Показываем диалог подтверждения
            if tkinter.messagebox.askyesno("Подтверждение", "Сервер запущен. Остановить сервер и закрыть окно?"):
                 self.stop_server_thread()
                 # Даем серверу немного времени на остановку.
                 # Это не идеальное решение, т.к. GUI может подвиснуть.
                 # Более сложный вариант - ждать сигнала от сервера в цикле с update().
                 self.log_message("Попытка дождаться остановки сервера (до 2 секунд)...")
                 max_wait_ms = 2000
                 wait_interval_ms = 100
                 elapsed_ms = 0
                 while self.server_running and elapsed_ms < max_wait_ms:
                     self.update() # Обрабатываем события GUI, включая check_queue
                     time.sleep(wait_interval_ms / 1000.0)
                     elapsed_ms += wait_interval_ms

                 if self.server_running:
                      self.log_message("Сервер не остановился вовремя, окно будет закрыто принудительно.")
                 else:
                      self.log_message("Сервер успешно остановлен.")
                 self.destroy() # Закрываем окно
            else:
                 # Пользователь отменил закрытие
                 return
        else:
            # Если сервер не запущен, просто закрываем окно
            self.destroy()

# --- Точка входа ---

if __name__ == "__main__":
    # Настройки по умолчанию (можно изменить)
    DEFAULT_HOST = 'localhost' # '0.0.0.0' для прослушивания на всех интерфейсах
    DEFAULT_PORT = 12345

    # Создаем и запускаем GUI
    app = RussianRouletteServerGUI(host=DEFAULT_HOST, port=DEFAULT_PORT)
    app.mainloop()