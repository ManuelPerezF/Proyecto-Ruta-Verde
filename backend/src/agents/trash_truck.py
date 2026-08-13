import agentpy as ap
import random
import pickle
import os

class TrashTruckAgent(ap.Agent):
    def setup(self):
        self.capacity = self.p.capacity
        self.load = 0
        self.position = (0, 0)
        self.q_table = {}
        self.epsilon = self.p.epsilon
        self.alpha = self.p.alpha
        self.gamma = self.p.gamma
        self.truck_id = 0
        # Sistema de combustible
        self.fuel = self.p.fuel_capacity  # Combustible actual
        self.fuel_capacity = self.p.fuel_capacity  # Capacidad máxima de combustible
        self.fuel_consumption = self.p.fuel_consumption  # Consumo por movimiento
        # Para el protocolo Contract Net
        self.current_bid = None
        self.assigned_critical_container = None
        self.load_q_table()

    def load_q_table(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        data_dir = os.path.join(project_root, 'data')
        filename = os.path.join(data_dir, f"q_table_truck_{self.truck_id}.pkl")
        
        if os.path.exists(filename):
            try:
                with open(filename, 'rb') as f:
                    saved_data = pickle.load(f)
                    self.q_table = saved_data['q_table']
                    self.epsilon = max(0.2, saved_data.get('epsilon', self.epsilon) * 0.98)
            except Exception as e:
                print(f"Error cargando Q-table para camión {self.truck_id}: {e}")

    def save_q_table(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        data_dir = os.path.join(project_root, 'data')
        
        # Crear directorio data si no existe
        os.makedirs(data_dir, exist_ok=True)
        filename = os.path.join(data_dir, f"q_table_truck_{self.truck_id}.pkl")
        
        try:
            training_runs = 1
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    old_data = pickle.load(f)
                    training_runs = old_data.get('training_runs', 0) + 1
            with open(filename, 'wb') as f:
                pickle.dump({
                    'q_table': self.q_table,
                    'epsilon': self.epsilon,
                    'training_runs': training_runs
                }, f)
        except Exception as e:
            print(f"Error guardando Q-table para camion {self.truck_id}: {e}")

    def state(self):
        # Estados del camion: posicion, carga, nivel de combustible
        fuel_level = "low" if self.fuel <= self.fuel_capacity * 0.3 else "medium" if self.fuel <= self.fuel_capacity * 0.7 else "high"
        return (self.position, self.load, fuel_level)

    def possible_actions(self):
        return ["up", "down", "left", "right", "collect", "change_route", "refuel"]

    def choose_action(self, state):
        # 1. Verificar combustible crítico y si estamos en un dump
        if self.fuel <= self.fuel_capacity * 0.2:  # Combustible bajo 20%
            if self.position in self.model.dump_points:
                return "refuel"
            else:
                # Ir al dump cercano para recargar
                return self.move_to_dump()
        
        # 2. Si estamos en un dump y tenemos basura, descargar
        if self.position in self.model.dump_points and self.load > 0:
            return "collect"  # En dump, "collect" significa descargar
        
        # 3. Verificar si hay contenedores críticos y usar Contract Net
        critical_containers = self.model.get_critical_containers()
        current_target = self.model.get_target_for_truck(self.truck_id)
        
        # Si hay contenedores críticos y no tenemos asignación crítica, participar en Contract Net
        if critical_containers and self.assigned_critical_container is None:
            pass
        
        # 4. Si tenemos asignación crítica, ir hacia ella
        if self.assigned_critical_container:
            tx, ty = self.assigned_critical_container
            x, y = self.position
            if x < tx: return "right"
            elif x > tx: return "left"
            elif y < ty: return "up"
            elif y > ty: return "down"
            else: 
                # Estamos en el contenedor crítico
                container_here = self.model.get_container_at_position(self.position)
                if container_here and container_here.current_fill > 0 and self.load < self.capacity:
                    return "collect"
                else:
                    self.assigned_critical_container = None  # Completar tarea
                    return "change_route"
        
        # 5. Verificar posicion para recoger basura
        container_at_position = self.model.get_container_at_position(self.position)
        if (container_at_position and 
            container_at_position.current_fill > 0 and 
            self.load < self.capacity):
            return "collect"

        # 6. Si estamos casi llenos, ir al vertedero
        if self.load >= self.capacity * 0.8:
            return self.move_to_dump()

        # 7. Si tenemos un objetivo, movernos hacia él
        if current_target:
            tx, ty = current_target
            x, y = self.position
            if x < tx: return "right"
            elif x > tx: return "left"
            elif y < ty: return "up"
            elif y > ty: return "down"
            else: 
                # Verificar si hay basura para recoger
                container_here = self.model.get_container_at_position(self.position)
                if container_here and container_here.current_fill > 0:
                    return "collect"
                else:
                    return "change_route"  
        
        # 8. Si no hay objetivo, explorar aleatoriamente
        return random.choice(["up", "down", "left", "right"])

    def move_to_dump(self):
        x, y = self.position
        dump_points = self.model.dump_points
        closest_dump = min(dump_points, key=lambda p: abs(x - p[0]) + abs(y - p[1]))
        tx, ty = closest_dump
        if x < tx: return "right"
        elif x > tx: return "left"
        elif y < ty: return "up"
        elif y > ty: return "down"
        else:
            self.load = 0
            return "collect"
    
    # Métodos para el protocolo Contract Net
    def calculate_bid(self, container_position):
        if self.fuel <= self.fuel_capacity * 0.3:  # Si tiene poco combustible, no puede ofertar
            return float('inf')  # Bid infinito = no puede hacerlo
        
        # Distancia al contenedor
        distance = abs(self.position[0] - container_position[0]) + abs(self.position[1] - container_position[1])
        
        # Factor de carga (camiones menos cargados son preferidos)
        load_factor = self.load / self.capacity
        
        # Factor de combustible (camiones con mas combustible son preferidos)
        fuel_factor = 1.0 - (self.fuel / self.fuel_capacity)
        
        # Calcular bid (menor es mejor)
        bid = distance + (load_factor * 10) + (fuel_factor * 5)
        
        return bid
    
    def submit_bid(self, container_position):
        self.current_bid = self.calculate_bid(container_position)
        return self.current_bid
    
    def accept_assignment(self, container_position):
        self.assigned_critical_container = container_position
        self.current_bid = None
        # Limpiar asignación regular si existe
        if self.truck_id in self.model.assignments:
            self.model.assignments.pop(self.truck_id)
    
    def reject_assignment(self):
        self.current_bid = None

    def update_q(self, state, action, reward, next_state):
        if state not in self.q_table:
            self.q_table[state] = {a: 0 for a in self.possible_actions()}
        if next_state not in self.q_table:
            self.q_table[next_state] = {a: 0 for a in self.possible_actions()}
        old_value = self.q_table[state][action]
        next_max = max(self.q_table[next_state].values())
        self.q_table[state][action] = old_value + self.alpha * (reward + self.gamma * next_max - old_value)

    def step(self):
        state = self.state()
        action = self.choose_action(state)
        reward, next_state = self.execute(action)
        self.update_q(state, action, reward, next_state)

    def execute(self, action):
        x, y = self.position
        next_pos = self.position
        reward = 0
        fuel_consumed = 0

        if action == "up" and y < 7:
            next_pos = (x, y + 1)
            fuel_consumed = self.fuel_consumption
        elif action == "down" and y > 0:
            next_pos = (x, y - 1)
            fuel_consumed = self.fuel_consumption
        elif action == "left" and x > 0:
            next_pos = (x - 1, y)
            fuel_consumed = self.fuel_consumption
        elif action == "right" and x < 7:
            next_pos = (x + 1, y)
            fuel_consumed = self.fuel_consumption
        elif action == "change_route":
            # Liberar la asignación actual para que se busque un nuevo objetivo
            if self.truck_id in self.model.assignments:
                self.model.assignments.pop(self.truck_id)
                
            possible_moves = []
            if x > 0: possible_moves.append((x-1, y))
            if x < 7: possible_moves.append((x+1, y))
            if y > 0: possible_moves.append((x, y-1))
            if y < 7: possible_moves.append((x, y+1))
            
            if possible_moves:
                next_pos = random.choice(possible_moves)
                fuel_consumed = self.fuel_consumption

            # Penalización por tener que cambiar de ruta
            reward -= 5  
        
        elif action == "refuel":
            # Solo se puede recargar en los dumps
            if self.position in self.model.dump_points:
                self.fuel = self.fuel_capacity
                reward += 20  # Recompensa por recargar combustible
            else:
                reward -= 10  # Penalización por intentar recargar fuera de un dump

        elif action == "collect":
            # Si estamos en un dump, descargar basura
            if self.position in self.model.dump_points:
                if self.load > 0:
                    reward += 50 * (self.load / 100)  # Recompensa + 50 por cada 100 unidades descargadas
                    self.load = 0
                    # Liberar asignacion crítica si estaba completada
                    if self.assigned_critical_container:
                        self.assigned_critical_container = None
                else:
                    reward -= 2  # Penalizacion -2 por intentar descargar sin carga
            else:
                # Recoger basura de contenedor
                container_at_position = self.model.get_container_at_position(self.position)
                if container_at_position and self.load < self.capacity:
                    if container_at_position.current_fill > 0:
                        truck_space = self.capacity - self.load
                        amount_to_collect = min(container_at_position.current_fill, truck_space, 10)
                        collected = container_at_position.collect_trash(amount_to_collect, self.truck_id)
                        reward += 30 * collected # Recompensa +30 por cada 10 unidades recogidas
                        if container_at_position.is_critical():
                        # Recompensa adicional por recoger de un contenedor crítico
                            reward += 100 * collected # Recompensa +100 por cada 10 unidades recogidas de un contenedor crítico
                        self.load += collected
                    else:
                        # Penalización por intentar recoger de un contenedor vacío
                        reward -= 2

                    # liberar asignacion si ya está vacío
                    if container_at_position.current_fill <= 0:
                        self.model.assignments.pop(self.truck_id, None)
                        # Si era una asignacion crítica, liberarla también
                        if self.assigned_critical_container == self.position:
                            self.assigned_critical_container = None
                else:
                    # Penalizacion por intentar recoger con camión lleno
                    reward -= 2

        # Consumir combustible si hubo movimiento
        if fuel_consumed > 0:
            self.fuel = max(0, self.fuel - fuel_consumed)
            # Penalización por quedarse sin combustible
            if self.fuel <= 0:
                reward -= 50 # Penalizacion -50 por quedarse sin combustible

        overflowing_containers = self.model.get_overflowing_containers()
        # Penalización por contenedores desbordados
        reward -= 30 * len(overflowing_containers) # Penalización -30 por cada contenedor desbordado

        self.position = next_pos
        return reward, self.state()
