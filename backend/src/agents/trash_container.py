import agentpy as ap
import random

class TrashContainerAgent(ap.Agent):
    def setup(self):
        self.position = None
        self.capacity = self.p.container_limit
        self.current_fill = 0
        self.last_emptied_by = None  # id del camion que lo vacio
        self.last_emptied_step = -1  # rastrea cuando fue vaciado

    def step(self):
        if random.uniform(0, 1) < self.p.population_density:
            if self.p.population_density >= 0.3:
                basura_generada = random.randint(2, 5)
            else:
                basura_generada = random.randint(1, 3)
            self.current_fill = min(self.current_fill + basura_generada, self.capacity * 2)

    def collect_trash(self, amount, truck_id=None):
        # Si no se especifica un camión, no permitir recolección
        if truck_id is None:
            return 0
            
        # Verificar si hay un camión en la misma posicion
        truck_at_position = False
        for truck in self.model.trucks:
            if truck.truck_id == truck_id and truck.position == self.position:
                truck_at_position = True
                break
                
        if not truck_at_position:
            return 0  # No permitir recolección si no hay un camión en la posicion
        
        # Proceder con la recolección normal
        collected = min(self.current_fill, amount)
        self.current_fill -= collected
        self.last_emptied_by = truck_id
        self.last_emptied_step = self.model.t
        return collected

    def is_critical(self):
        return self.current_fill >= 0.9 * self.capacity

    def is_overflowing(self):
        return self.current_fill >= self.capacity
    
    def was_recently_emptied(self, current_step, cooldown_steps=10):
        # Verificacion para saber si fue vaciado recientemente
        if self.last_emptied_step == -1:
            return False
        return (current_step - self.last_emptied_step) <= cooldown_steps
    
    def is_worth_visiting(self, current_step, min_fill_threshold=8):
        # No vale la pena si fue vaciado recientemente
        if self.was_recently_emptied(current_step):
            return False
        # No vale la pena si tiene muy poca basura
        if self.current_fill < min_fill_threshold:
            return False
        return True
