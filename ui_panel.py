import math

import bpy
from typing import Dict, List

from bpy.props import FloatProperty, IntProperty
from geometry_connector.calculate_geometry import CalculateGeometry
from geometry_connector.connect_geometry import build_mesh_graph
from geometry_connector.graph_utils import sort_graph, build_networks, Network
from geometry_connector.build_geometry import assemble_network, TransformMatch
from geometry_connector.build_geometry import apply_transforms_to_scene
from geometry_connector.models import Mesh


class VIEW3D_PT_build_geometry_panel(bpy.types.Panel):
    bl_label = "Build Geometry"
    bl_idname = "VIEW3D_PT_build_geometry"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Geometry Resolver'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        # Configurable constants
        layout.label(text="Thresholds:")
        layout.prop(scene, "coplanar_angle_threshold")
        layout.prop(scene, "coplanar_dist_threshold")
        layout.prop(scene, "curvature_threshold")
        layout.prop(scene, "connected_edge_angle_threshold")
        layout.prop(scene, "area_threshold")
        layout.prop(scene, "edge_threshold")
        layout.separator()
        # Build button
        layout.operator(OBJECT_OT_build_geometry.bl_idname, text="Resolve")
        layout.separator()
        # Connect Variants label and counter
        layout.label(text="Connect Variants")
        row = layout.row(align=True)
        row.prop(scene, "variant_index", text="", emboss=True)


class OBJECT_OT_build_geometry(bpy.types.Operator):
    bl_idname = "geometry.build_geometry"
    bl_label = "Build Geometry"
    bl_description = "Calculate and assemble geometry fragments"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        calculator = CalculateGeometry()
        meshes_list = calculator.calculate()
        mesh_dict: Dict[str, Mesh] = {m.name: m for m in meshes_list}

        graph = build_mesh_graph(meshes_list)
        sorted_graph = sort_graph(graph)
        networks = build_networks(sorted_graph)
        if not networks:
            self.report({'WARNING'}, "No match networks found")
            return {'CANCELLED'}

        best_network: Network = networks[0]
        transforms: List[TransformMatch] = assemble_network(best_network, mesh_dict)
        if not transforms:
            self.report({'WARNING'}, "No transforms could be calculated without conflict")
            return {'CANCELLED'}

        base_name = best_network.matches[0].mesh1
        apply_transforms_to_scene(transforms, base_name)
        self.report({'INFO'}, f"Geometry built using network weight {best_network.weight:.3f}")
        return {'FINISHED'}


DEFAULT_COPLANAR_ANGLE_THRESHOLD = math.radians(2.0)
DEFAULT_COPLANAR_DIST_THRESHOLD = 0.004
DEFAULT_CURVATURE_THRESHOLD = 0.01
DEFAULT_CONNECTED_EDGE_ANGLE_THRESHOLD = math.radians(5.0)
DEFAULT_AREA_THRESHOLD = 0.015
DEFAULT_EDGE_THRESHOLD = 0.005

classes = [VIEW3D_PT_build_geometry_panel, OBJECT_OT_build_geometry]


def register():
    # Register scene properties for constants
    bpy.types.Scene.coplanar_angle_threshold = FloatProperty(
        subtype='ANGLE',
        precision=5,
        name="Coplanar Angle Threshold",
        default=DEFAULT_COPLANAR_ANGLE_THRESHOLD,
        description="Angle below which faces are considered coplanar"
    )
    bpy.types.Scene.coplanar_dist_threshold = FloatProperty(
        precision=5,
        name="Coplanar Distance Threshold",
        default=DEFAULT_COPLANAR_DIST_THRESHOLD,
        description="Distance below which faces are considered coplanar"
    )
    bpy.types.Scene.curvature_threshold = FloatProperty(
        precision=5,
        name="Curvature Threshold",
        default=DEFAULT_CURVATURE_THRESHOLD,
        description="Deviation threshold for vertex curvature classification"
    )
    bpy.types.Scene.connected_edge_angle_threshold = FloatProperty(
        subtype='ANGLE',
        precision=5,
        name="Edge Angle Threshold",
        default=DEFAULT_CONNECTED_EDGE_ANGLE_THRESHOLD,
        description="Angle threshold for connected edge matching"
    )
    bpy.types.Scene.area_threshold = FloatProperty(
        precision=5,
        name="Area Threshold",
        default=DEFAULT_AREA_THRESHOLD,
        description="Allowed area difference for face matching"
    )
    bpy.types.Scene.edge_threshold = FloatProperty(
        precision=5,
        name="Edge Length Threshold",
        default=DEFAULT_EDGE_THRESHOLD,
        description="Allowed edge length difference for edge matching"
    )
    bpy.types.Scene.variant_index = IntProperty(
        name="Variant Index",
        default=0,
        min=0,
        description="Index of shown connect variant"
    )

    # Register classes
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    # Remove scene properties
    del bpy.types.Scene.coplanar_angle_threshold
    del bpy.types.Scene.coplanar_dist_threshold
    del bpy.types.Scene.curvature_threshold
    del bpy.types.Scene.connected_edge_angle_threshold
    del bpy.types.Scene.area_threshold
    del bpy.types.Scene.edge_threshold
    del bpy.types.Scene.variant_index
