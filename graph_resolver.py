from geometry_connector.connect_geometry import build_mesh_graph
from geometry_connector.calculate_geometry import CalculateGeometry
from geometry_connector.graph_utils import sort_graph


if __name__ == "__main__":
    calculator = CalculateGeometry()
    data = calculator.calculate()
    graph = build_mesh_graph(data)
    sorted_graph = sort_graph(graph)
