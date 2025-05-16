bl_info = {
    "name": "Geometry Resolver",
    "author": "Me",
    "version": (0, 0, 1),
    "blender": (4, 4, 0),
    "location": "View3D",
    "description": "Later",
    "category": "Development",
}


from . import ui_panel


def register():
    ui_panel.register()


def unregister():
    ui_panel.unregister()


if __name__ == "__main__":
    register()