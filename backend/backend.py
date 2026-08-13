from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from collections import deque
import threading, time
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from src.environment.garbage_environment import GarbageEnvironment
from src.utils.config import parameters

model = GarbageEnvironment(parameters)
model.setup()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Variables de la simulacion
step_queues = {}
_t_counter = 0
_stop_event = threading.Event()
_step_lock = threading.Lock()
_producer_thread = None
_producer_delay = 0.5

# Funciones de producción de pasos
def _enqueue_step_for_truck(truck_id: int, done: bool = False):
    global _t_counter
    truck = model.trucks[truck_id]
    step = {
        "t": _t_counter,
        "x": int(truck.position[0]),
        "y": int(truck.position[1]),
        "carrying": int(truck.load),
        "capacity": int(truck.capacity),
        "fuel": float(truck.fuel),
        "fuel_capacity": float(truck.fuel_capacity),
        "has_critical_assignment": truck.assigned_critical_container is not None,
        "action": "",
        "done": done
    }
    step_queues.setdefault(truck_id, deque()).append(step)

# Genera los pasos automaticamente
def _auto_producer():
    global _t_counter
    for i, _ in enumerate(model.trucks):
        step_queues[i] = deque()
    while not _stop_event.is_set():
        with _step_lock:
            if _t_counter >= parameters['steps']:
                for i, _ in enumerate(model.trucks):
                    _enqueue_step_for_truck(i, done=True)
                break
            model.step() # Avanza la simulación un paso
            _t_counter += 1
            for i, _ in enumerate(model.trucks):
                _enqueue_step_for_truck(i, done=False)
        time.sleep(_producer_delay)


@app.on_event("startup")
def startup_event():
    global _producer_thread, _stop_event
    _stop_event = threading.Event()
    _producer_thread = threading.Thread(target=_auto_producer, daemon=True)
    _producer_thread.start()


@app.on_event("shutdown")
def shutdown_event():
    global _stop_event
    _stop_event.set()
    if _producer_thread and _producer_thread.is_alive():
        _producer_thread.join()

# Endpoint para obtener el resumen de la simulacion
@app.get("/session")
def get_session():
    # Calcula estadisticas
    critical_containers = sum(1 for c in model.containers if c.is_critical())
    overflowing_containers = sum(1 for c in model.containers if c.is_overflowing())
    total_trash = sum(c.current_fill for c in model.containers)
    total_load = sum(t.load for t in model.trucks)
    overall_efficiency = (total_load / max(1, total_load + total_trash)) * 100
    
    return {
        "gridX": parameters.get("grid_size", 8),
        "gridY": parameters.get("grid_size", 8),
        "totalSteps": parameters['steps'],
        "currentStep": _t_counter,
        "trucks": [
            {
                "id": i, 
                "pos": [int(t.position[0]), int(t.position[1])], 
                "load": int(t.load),
                "capacity": int(t.capacity),
                "fuel": float(t.fuel),
                "fuel_capacity": float(t.fuel_capacity),
                "has_critical_assignment": t.assigned_critical_container is not None,
                "critical_assignment_pos": list(t.assigned_critical_container) if t.assigned_critical_container else None
            } 
            for i, t in enumerate(model.trucks)
        ],
        "containers": [
            {
                "pos": [int(c.position[0]), int(c.position[1])], 
                "fill": int(c.current_fill),
                "capacity": int(c.capacity),
                "fill_percentage": float((c.current_fill / c.capacity) * 100),
                "is_critical": c.is_critical(),
                "is_overflowing": c.is_overflowing(),
                "last_emptied_by": c.last_emptied_by,
                "last_emptied_step": c.last_emptied_step
            } 
            for c in model.containers
        ],
        "dumps": [{"pos": [int(p[0]), int(p[1])]} for p in model.get_dump_points()],
        "statistics": {
            "critical_containers": critical_containers,
            "overflowing_containers": overflowing_containers,
            "total_trash_remaining": total_trash,
            "total_load_collected": total_load,
            "overall_efficiency": float(overall_efficiency)
        }
    }

# Endpoint para obtener el siguiente paso
@app.get("/step/next")
def get_step(robot_id: int = 0):
    q = step_queues.setdefault(robot_id, deque())
    if not q:
        return Response(status_code=204)
    return q.popleft()

# Endpoint para reiniciar la simulacion
@app.post("/simulation/reset")
async def reset_simulation(request: Request):
    global model, parameters, _t_counter, _stop_event, _producer_thread
    _stop_event.set()

    body = await request.json()
    # Actualiza los parametros en base a unity
    parameters.update(body)

    model = GarbageEnvironment(parameters)
    model.setup()
    _t_counter = 0

    _stop_event = threading.Event()
    _producer_thread = threading.Thread(target=_auto_producer, daemon=True)
    _producer_thread.start()

    return {"ok": True, "parameters": parameters}

# Endpoint para pausar/reanudar la simulacion
@app.post("/simulation/pause")
async def pause_simulation():
    global _stop_event
    _stop_event.set()
    return {"ok": True, "status": "paused"}

@app.post("/simulation/resume")  
async def resume_simulation():
    global _stop_event, _producer_thread
    if _stop_event.is_set():
        _stop_event = threading.Event()
        _producer_thread = threading.Thread(target=_auto_producer, daemon=True)
        _producer_thread.start()
    return {"ok": True, "status": "resumed"}

# Endpoint para obtener parametros
@app.get("/parameters")
def get_parameters():
    return parameters
