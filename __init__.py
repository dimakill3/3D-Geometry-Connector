from geometry_connector.calculate_geometry import CalculateGeometry
from geometry_connector.writer import Writer

bl_info = {
    "name": "Geometry Resolver",
    "author": "Me",
    "version": (0, 0, 1),
    "blender": (4, 4, 0),
    "location": "View3D",
    "description": "Later",
    "category": "Development",
}

def register():
    calculator = CalculateGeometry()
    data = calculator.calculate()
    Writer.write_meshes_to_json(data)

def unregister():
    pass

if __name__ == "__main__":
    register()