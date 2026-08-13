import agentpy as ap
import random
import itertools
from ..agents.trash_container import TrashContainerAgent
from ..agents.trash_truck import TrashTruckAgent

class GarbageEnvironment(ap.Model):
    def setup(self):
        grid_size = self.p.get('grid_size', 8)
        self.grid = ap.Grid(self, (grid_size, grid_size), track_empty=True)
        self.dump_points = [(0, 0), (grid_size-1, 0), (0, grid_size-1), (grid_size-1, grid_size-1)]

        num_containers = self.p.get('num_containers', 8)
        num_trucks = self.p.get('num_trucks', 2)

        # Generar todas las posiciones posibles, quitando los dumps
        all_positions = set(itertools.product(range(grid_size), range(grid_size)))
        forbidden = set(self.dump_points)
        available_positions = list(all_positions - forbidden)
        random.shuffle(available_positions)

        # Asignar posiciones aleatorias a los contenedores
        container_positions = available_positions[:num_containers]
        self.containers = ap.AgentList(self, num_containers, TrashContainerAgent)
        for c, pos in zip(self.containers, container_positions):
            c.position = pos
            c.current_fill = random.randint(5, 20)

        # Quitar posiciones ya usadas por contenedores
        remaining_positions = available_positions[num_containers:]
        random.shuffle(remaining_positions)
        truck_positions = remaining_positions[:num_trucks]
        self.trucks = ap.AgentList(self, num_trucks, TrashTruckAgent)
        for i, (t, pos) in enumerate(zip(self.trucks, truck_positions)):
            t.position = pos
            t.truck_id = i

        self.assignments = {}
    
    def step(self):
        # Primero ejecutar Contract Net para contenedores críticos
        self.contract_net_protocol()
        # Luego asignar contenedores normales
        self.assign_containers_to_trucks()
        self.containers.step()
        self.trucks.step()

    def contract_net_protocol(self):
        critical_containers = [c for c in self.containers if c.is_critical()]
        
        # Obtener contenedores críticos que no están ya asignados
        assigned_critical = {truck.assigned_critical_container for truck in self.trucks 
                           if truck.assigned_critical_container is not None}
        
        unassigned_critical = [c for c in critical_containers 
                             if c.position not in assigned_critical]
        
        for container in unassigned_critical:
            # Paso 1: Solicitar bids de todos los camiones
            bids = {}
            for truck in self.trucks:
                # Solo camiones que no tienen asignación crítica actual pueden ofertar
                if truck.assigned_critical_container is None:
                    bid = truck.submit_bid(container.position)
                    if bid != float('inf'):  # Solo ofertas válidas
                        bids[truck.truck_id] = bid
            
            # Paso 2: Seleccionar el mejor camión (menor bid)
            if bids:
                winner_id = min(bids.keys(), key=lambda x: bids[x])
                winner_truck = next(truck for truck in self.trucks if truck.truck_id == winner_id)
                
                # Paso 3: Asignar al ganador y rechazar a los demás
                winner_truck.accept_assignment(container.position)
                
                for truck in self.trucks:
                    if truck.truck_id != winner_id and truck.current_bid is not None:
                        truck.reject_assignment()
                
                # Contract Net asignación completada silenciosamente
                pass

    def assign_containers_to_trucks(self):
        # Solo considerar contenedores no críticos que valgan la pena visitar
        current_step = self.t
        non_critical_containers = [c for c in self.containers 
                                 if not c.is_critical() and c.is_worth_visiting(current_step)]
        candidates = non_critical_containers
        used = set()

        # Añadir posiciones de contenedores críticos asignados a la lista de usados
        for truck in self.trucks:
            if truck.assigned_critical_container:
                used.add(truck.assigned_critical_container)

        # Añadir contenedores ya asignados a otros camiones
        assigned_positions = set(self.assignments.values())
        used.update(assigned_positions)

        # Ordenar camiones por carga, pero solo considerar los que no tienen asignación crítica
        available_trucks = [t for t in self.trucks if t.assigned_critical_container is None]
        sorted_trucks = sorted(available_trucks, key=lambda t: t.load)
        
        for truck in sorted_trucks:
            # Si ya tiene un objetivo asignado, verificar si sigue siendo válido
            if truck.truck_id in self.assignments:
                tgt = self.assignments[truck.truck_id]
                c = next((x for x in self.containers if x.position == tgt), None)
                
                # Mantener asignación solo si es válida y vale la pena
                if (c and not c.is_critical() and c.is_worth_visiting(current_step) 
                    and truck.load < truck.capacity * 0.9):
                    # Si el camión está cerca o en el objetivo, mantener la asignación
                    distance_to_target = abs(truck.position[0] - tgt[0]) + abs(truck.position[1] - tgt[1])
                    if distance_to_target <= 3:  # Mantener si está cerca del objetivo
                        continue
                
                # Liberar asignación si ya no es válida
                self.assignments.pop(truck.truck_id, None)
            
            # Buscar el contenedor más cercano y valioso para este camión
            best = None
            best_score = float('inf')
            
            for c in candidates:
                # Ignorar contenedores ya asignados
                if c.position in used:
                    continue
                    
                # Calcular distancia Manhattan
                distance = abs(truck.position[0] - c.position[0]) + abs(truck.position[1] - c.position[1])
                
                # Calcular puntuación combinada (menor es mejor)
                # Factor de llenado del contenedor (más lleno es mejor)
                fullness_factor = c.current_fill / c.capacity
                
                # Factor de tiempo desde último vaciado (más tiempo = mejor)
                time_factor = 0
                if c.last_emptied_step != -1:
                    time_since_emptied = current_step - c.last_emptied_step
                    time_factor = max(0, 1.0 - (time_since_emptied / 50.0))  # Normalizar
                
                # Puntuación combinada: distancia + penalización por bajo llenado + penalización por reciente vaciado
                score = distance + (1.0 - fullness_factor) * 5 + time_factor * 3
                
                # Bonificación para camiones con poca carga hacia contenedores llenos
                if truck.load < truck.capacity * 0.5:
                    score -= fullness_factor * 2  # Reducir score (mejorar) para contenedores llenos
                    
                if score < best_score:
                    best = c
                    best_score = score
                    
            if best:
                self.assignments[truck.truck_id] = best.position
                used.add(best.position)
                # Asignación completada silenciosamente
            
            # Si no hay contenedores disponibles, asignar un punto aleatorio para explorar
            elif truck.truck_id not in self.assignments:
                available = [(x, y) for x in range(self.p.grid_size) for y in range(self.p.grid_size) 
                        if (x, y) not in used and (x, y) != truck.position]
                if available:
                    explore_point = random.choice(available)
                    self.assignments[truck.truck_id] = explore_point
                    # Exploración asignada silenciosamente
    
    def get_target_for_truck(self, truck_id):
        return self.assignments.get(truck_id, None)

    def get_container_at_position(self, position):
        for container in self.containers:
            if container.position == position:
                return container
        return None

    def get_critical_containers(self):
        return [c.position for c in self.containers if c.is_critical()]

    def get_overflowing_containers(self):
        return [c.position for c in self.containers if c.is_overflowing()]

    def get_dump_points(self):
        return list(self.dump_points)
        
    def is_truck_near_container(self, container_pos, threshold=1.0):
        """Verifica si hay algún camión cerca del contenedor"""
        for truck in self.trucks:
            dx = abs(truck.position[0] - container_pos[0])
            dy = abs(truck.position[1] - container_pos[1])
            manhattan_distance = dx + dy
            if manhattan_distance <= threshold:
                return True, truck.truck_id
        return False, None

    def end(self):
        for truck in self.trucks:
            truck.save_q_table()
