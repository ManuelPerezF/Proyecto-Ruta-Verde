import sys
import os

# Agregar el directorio actual al path para las importaciones
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from src.environment.garbage_environment import GarbageEnvironment
from src.utils.config import parameters


def simple_status(model):
    critical = sum(1 for c in model.containers if c.is_critical())
    overflow = sum(1 for c in model.containers if c.is_overflowing())
    total_trash = sum(c.current_fill for c in model.containers)
    total_load = sum(t.load for t in model.trucks)

    print(f"Criticos: {critical}, Desbordados: {overflow}, "
          f"Basura: {total_trash}, Carga total: {total_load}")


def show_truck_stats(model):
    print("\n--- Estadisticas por Camion ---")
    for i, truck in enumerate(model.trucks):
        efficiency = (truck.load / truck.capacity) * 100
        fuel_percent = (truck.fuel / truck.fuel_capacity) * 100
        critical_assignment = "Si" if truck.assigned_critical_container else "No"
        
        print(f"Camion {i}: Basura={truck.load}/{truck.capacity} ({efficiency:.1f}%) "
              f"| Combustible={truck.fuel}/{truck.fuel_capacity} ({fuel_percent:.1f}%) "
              f"| Critico: {critical_assignment} | Posicion={truck.position}")

    total_collected = sum(t.load for t in model.trucks)
    total_remaining = sum(c.current_fill for c in model.containers)
    overall_efficiency = (total_collected / max(1, total_collected + total_remaining)) * 100
    
    # Estadísticas adicionales
    critical_containers = len([c for c in model.containers if c.is_critical()])
    overflowing_containers = len([c for c in model.containers if c.is_overflowing()])
    
    print(f"\nEficiencia global: {overall_efficiency:.1f}%")
    print(f"Contenedores criticos: {critical_containers}")
    print(f"Contenedores desbordados: {overflowing_containers}")


def print_model_config(parameters):
    print(f"Config: {parameters['steps']} pasos, {parameters['num_trucks']} camiones, "
          f"{parameters['num_containers']} contenedores, grid {parameters['grid_size']}x{parameters['grid_size']}")


def main():    
    model = GarbageEnvironment(parameters)
    
    print_model_config(parameters)
    print("=" * 60)
    results = model.run()
    
    print("\n" + "=" * 60)
    print("RESULTADOS FINALES")
    print("=" * 60)
    simple_status(model)
    show_truck_stats(model)

if __name__ == "__main__":
    main()
