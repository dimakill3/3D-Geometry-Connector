import math
import bpy
from typing import Dict
from bpy.props import FloatProperty, IntProperty
from geometry_connector.calculate_geometry import GeometryCalculator
from geometry_connector.connect_geometry import GeometryConnector
from geometry_connector.constants import BATCH_SIZE
from geometry_connector.graph_utils import sort_graph, Network, generate_networks
from geometry_connector.build_geometry import GeometryBuilder
from geometry_connector.models import Mesh, MeshGraph
from geometry_connector.writer import Writer
from mathutils import Matrix

_cached_networks : list[Network] = None
_cached_meshes_dictionary : Dict[str, Mesh] = None
_cached_sorted_graph : MeshGraph = None
_generated_networks = None


class GeometryResolverNPanelBuilder(bpy.types.Panel):
    bl_label = "Geometry Resolver"
    bl_idname = "GEOMETRY_RESOLVER_PT_N_PANEL"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Geometry Resolver'

    def draw(self, context):
        global _cached_networks
        layout = self.layout
        scene = context.scene

        if _cached_networks is None:
            # Выводим константы
            layout.label(text="Thresholds:")
            layout.prop(scene, "coplanar_angle_threshold")
            layout.prop(scene, "coplanar_distance_threshold")
            layout.prop(scene, "curvature_threshold")
            layout.prop(scene, "connected_edge_angle_threshold")
            layout.prop(scene, "face_area_threshold")
            layout.prop(scene, "edge_length_threshold")
            layout.separator()

            # Кнопка запуска соединения
            layout.operator(ResolveGeometryButton.bl_idname, text="Connect Fragments", icon='PLAY')
            layout.separator()
        else:
            # Переключение возможных вариантов соединений
            row = layout.row(align=True)
            row.operator(PreviousVariant.bl_idname, text="", icon='TRIA_LEFT')
            row.prop(scene, "network_variant_index", text="")
            row.operator(NextVariant.bl_idname, text="", icon='TRIA_RIGHT')
            layout.operator(StopResolveButton.bl_idname, text="Stop", icon='PAUSE')


class ResolveGeometryButton(bpy.types.Operator):
    bl_idname = "geometry_resolver_n_panel.resolve_geometry"
    bl_label = "Build Geometry"
    bl_description = "Calculate and Assemble geometry fragments"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        global _cached_networks, _cached_meshes_dictionary, _generated_networks, _cached_sorted_graph
        scene = context.scene

        meshes_list = GeometryCalculator().calculate()
        meshes_dictionary: Dict[str, Mesh] = {m.name: m for m in meshes_list}
        _cached_meshes_dictionary = meshes_dictionary

        graph = GeometryConnector().build_mesh_graph(meshes_list)
        sorted_graph = sort_graph(graph)
        _cached_sorted_graph = sorted_graph
        Writer.print_graph(sorted_graph)
        # Writer.draw_graph(sorted_graph)

        _generated_networks = generate_networks(sorted_graph)

        _cached_networks = []
        for _ in range(BATCH_SIZE):
            try:
                net = next(_generated_networks)
            except StopIteration:
                break
            _cached_networks.append(net)

        if not _cached_networks:
            self.report({'WARNING'}, "No match networks found")
            return {'CANCELLED'}

        scene.network_variant_index = 0

        result = show_another_network(scene.network_variant_index)

        if result:
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Check logs for more information")
            return {'CANCELLED'}


class PreviousVariant(bpy.types.Operator):
    bl_idname = "geometry_resolver_n_panel.prev_variant"
    bl_label = "←"

    def execute(self, context):
        scene = context.scene

        previous_index = scene.network_variant_index
        new_idx = max(0, scene.network_variant_index - 1)
        if previous_index != new_idx:
            result = show_another_network(scene.network_variant_index - 1)
            scene.network_variant_index = new_idx if result else previous_index

        return {'FINISHED'}


class NextVariant(bpy.types.Operator):
    bl_idname = "geometry_resolver_n_panel.next_variant"
    bl_label = "→"

    def execute(self, context):
        global _cached_networks
        scene = context.scene

        previous_index = scene.network_variant_index
        new_idx = context.scene.network_variant_index + 1

        result = show_another_network(scene.network_variant_index - 1)
        scene.network_variant_index = new_idx if result else previous_index

        return {'FINISHED'}


class StopResolveButton(bpy.types.Operator):
    bl_idname = "geometry_resolver_n_panel.stop"
    bl_label = "Stop"
    bl_description = "Exit change mode"

    def execute(self, context):
        global _cached_networks, _cached_meshes_dictionary, _generated_networks, _cached_meshes_dictionary
        _cached_networks = None
        _cached_meshes_dictionary = None
        _generated_networks = None
        _cached_networks = None
        _cached_meshes_dictionary = None
        context.scene.network_variant_index = 0
        return {'FINISHED'}


def show_another_network(idx : int) -> bool:
    global _cached_networks, _cached_meshes_dictionary, _generated_networks, _cached_sorted_graph

    if not _cached_networks:
        return False

    if idx >= len(_cached_networks):
        for _ in range(BATCH_SIZE):
            try:
                net = next(_generated_networks)
            except StopIteration:
                break
            _cached_networks.append(net)

    if idx >= len(_cached_networks):
        print("WARNING: Trying to select network out of bounds")
        return False

    network_to_show: Network = _cached_networks[idx]

    Writer.print_networks([network_to_show])
    transforms: Dict[str, Matrix] = GeometryBuilder().assemble_network(network_to_show, _cached_meshes_dictionary, _cached_sorted_graph)
    if not transforms:
        print("WARNING: No transforms could be calculated without conflict")
        return False

    GeometryBuilder().apply_transforms_to_scene(transforms)
    print("INFO: Geometry built using network:")

    return True


# Значения по умолчанию
DEFAULT_COPLANAR_ANGLE_THRESHOLD = math.radians(1)  # Угол, до которого грани считаются компланарными
DEFAULT_COPLANAR_DISTANCE_THRESHOLD = 0.0001  # Дистанция, до которой грани считаются компланарными
DEFAULT_CURVATURE_THRESHOLD = 0.01  # Величина отклонения кривизны
DEFAULT_CONNECTED_ANGLE_THRESHOLD = math.radians(1)  # Минимальный итоговый коэффициент
DEFAULT_FACE_AREA_THRESHOLD = 0.00001  # Допустимая разница площадей граней для совпадения
DEFAULT_EDGE_LENGTH_THRESHOLD = 0.00130  # Допустимая разница длин рёбер

classes = [GeometryResolverNPanelBuilder, ResolveGeometryButton, PreviousVariant, NextVariant, StopResolveButton]


def register():
    scene = bpy.types.Scene

    # Регистрация параметров панели
    scene.coplanar_angle_threshold = FloatProperty(
        subtype='ANGLE',
        name="Coplanar Angle Threshold",
        default=DEFAULT_COPLANAR_ANGLE_THRESHOLD,
        min=0,
        description="Angle below which faces are considered coplanar"
    )
    scene.coplanar_distance_threshold = FloatProperty(
        precision=5,
        name="Coplanar Distance Threshold",
        default=DEFAULT_COPLANAR_DISTANCE_THRESHOLD,
        min=0,
        description="Distance below which faces are considered coplanar"
    )
    scene.curvature_threshold = FloatProperty(
        precision=5,
        name="Curvature Threshold",
        default=DEFAULT_CURVATURE_THRESHOLD,
        min=0,
        description="Deviation threshold for vertex curvature classification"
    )
    scene.connected_angle_threshold = FloatProperty(
        subtype='ANGLE',
        precision=5,
        name="Connected Angle Threshold",
        default=DEFAULT_CONNECTED_ANGLE_THRESHOLD,
        min=0,
        description="Angle threshold for connected elements (face/edge) matching"
    )
    scene.face_area_threshold = FloatProperty(
        precision=5,
        name="Area Threshold",
        default=DEFAULT_FACE_AREA_THRESHOLD,
        min=0,
        description="Allowed area difference for face matching"
    )
    scene.edge_length_threshold = FloatProperty(
        precision=5,
        name="Edge Length Threshold",
        default=DEFAULT_EDGE_LENGTH_THRESHOLD,
        min=0,
        description="Allowed edge length difference for edge matching"
    )
    scene.network_variant_index = IntProperty(
        name="Network Variant Index",
        default=0,
        min=0,
        description="Index of shown connect variant"
    )

    # Регистрация классов
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    # Выгрузка зарегистрированных классов
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    scene = bpy.types.Scene

    # Выгрузка параметров панели
    for param in ("coplanar_angle_threshold", "coplanar_dist_threshold",
              "curvature_threshold", "connected_angle_threshold",
              "area_threshold", "edge_threshold", "variant_index"):
        delattr(scene, param)
