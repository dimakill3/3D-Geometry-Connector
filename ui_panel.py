import math
import bpy
from typing import Dict, List
from bpy.props import FloatProperty, IntProperty
from geometry_connector.calculate_geometry import GeometryCalculator
from geometry_connector.connect_geometry import GeometryConnector
from geometry_connector.graph_utils import sort_graph, build_networks, Network, generate_networks
from geometry_connector.build_geometry import assemble_network, TransformMatch
from geometry_connector.build_geometry import apply_transforms_to_scene
from geometry_connector.models import Mesh
from geometry_connector.writer import Writer

_cached_networks : list[Network] = None
_cached_mesh_dict : Dict[str, Mesh] = None
_network_gen = None

BATCH_SIZE = 100


class GeometryResolverNPanelBuilder(bpy.types.Panel):
    bl_label = "Geometry Resolver"
    bl_idname = "geometry_resolver_n_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Geometry Resolver'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        global _cached_networks

        if _cached_networks is None:

            # Настраиваемые константы
            layout.label(text="Thresholds:")
            layout.prop(scene, "coplanar_angle_threshold")
            layout.prop(scene, "coplanar_dist_threshold")
            layout.prop(scene, "curvature_threshold")
            layout.prop(scene, "connected_edge_angle_threshold")
            layout.prop(scene, "area_threshold")
            layout.prop(scene, "edge_threshold")
            layout.separator()

            # Кнопка запуска соединения
            layout.operator(ResolveGeometryButton.bl_idname, text="Connect Fragments", icon='PLAY')
            layout.separator()

        else:
            # Переключение возможных вариантов соединения
            row = layout.row(align=True)
            row.operator(PrevVariant.bl_idname, text="", icon='TRIA_LEFT')
            row.prop(scene, "variant_index", text="")
            row.operator(NextVariant.bl_idname, text="", icon='TRIA_RIGHT')
            layout.operator(StopResolve.bl_idname, text="Stop", icon='PAUSE')


class ResolveGeometryButton(bpy.types.Operator):
    bl_idname = "geometry_resolver_n_panel.resolve_geometry"
    bl_label = "Build Geometry"
    bl_description = "Calculate and Assemble geometry fragments"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        global _cached_networks, _cached_mesh_dict, _network_gen
        scene = context.scene

        meshes_list = GeometryCalculator().calculate()

        mesh_dict: Dict[str, Mesh] = {m.name: m for m in meshes_list}

        graph = GeometryConnector().build_mesh_graph(meshes_list)
        sorted_graph = sort_graph(graph)

        _network_gen = generate_networks(sorted_graph)

        _cached_networks = []
        for _ in range(BATCH_SIZE):
            try:
                net = next(_network_gen)
            except StopIteration:
                break
            _cached_networks.append(net)

        if not _cached_networks:
            self.report({'WARNING'}, "No match networks found")
            return {'CANCELLED'}

        _cached_mesh_dict = mesh_dict

        scene.variant_index = 0
        best_network: Network = _cached_networks[scene.variant_index]
        transforms: List[TransformMatch] = assemble_network(best_network, mesh_dict)
        if not transforms:
            self.report({'WARNING'}, "No transforms could be calculated without conflict")
            return {'CANCELLED'}

        apply_transforms_to_scene(transforms)
        self.report({'INFO'}, f"Geometry built using network:")
        Writer.print_networks([best_network])
        return {'FINISHED'}


class PrevVariant(bpy.types.Operator):
    bl_idname = "geometry_resolver_n_panel.prev_variant"
    bl_label = "←"

    def execute(self, context):
        scene = context.scene

        prev_index = scene.variant_index
        new_idx = max(0, scene.variant_index - 1)
        if prev_index != new_idx:
            res = show_another_network(scene.variant_index - 1)
            scene.variant_index = new_idx if res else prev_index

        return {'FINISHED'}


class NextVariant(bpy.types.Operator):
    bl_idname = "geometry_resolver_n_panel.next_variant"
    bl_label = "→"

    def execute(self, context):
        global _cached_networks
        scene = context.scene

        prev_index = scene.variant_index
        new_idx = context.scene.variant_index + 1

        res = show_another_network(scene.variant_index - 1)
        scene.variant_index = new_idx if res else prev_index

        return {'FINISHED'}


class StopResolve(bpy.types.Operator):
    bl_idname = "geometry_resolver_n_panel.stop"
    bl_label = "Stop"
    bl_description = "Exit change mode"

    def execute(self, context):
        global _cached_networks, _cached_mesh_dict, _network_gen
        _cached_networks = None
        _cached_mesh_dict = None
        _network_gen = None
        _cached_networks = None
        context.scene.variant_index = 0
        return {'FINISHED'}


def show_another_network(idx : int) -> bool:
    global _cached_networks, _cached_mesh_dict, _network_gen

    if not _cached_networks:
        return False

    if idx >= len(_cached_networks):
        for _ in range(BATCH_SIZE):
            try:
                net = next(_network_gen)
            except StopIteration:
                break
            _cached_networks.append(net)

    if idx >= len(_cached_networks):
        return False

    network_to_show: Network = _cached_networks[idx]

    transforms: List[TransformMatch] = assemble_network(network_to_show, _cached_mesh_dict)
    if not transforms:
        return False

    apply_transforms_to_scene(transforms)

    return True


# Значения по умолчанию
DEFAULT_COPLANAR_ANGLE_THRESHOLD = math.radians(2.0)  # Угол, до которого грани считаются компланарными
DEFAULT_COPLANAR_DIST_THRESHOLD = 0.004  # Дистанция, до которой грани считаются компланарными
DEFAULT_CURVATURE_THRESHOLD = 0.01  # Величина отклонения кривизны
DEFAULT_CONNECTED_EDGE_ANGLE_THRESHOLD = math.radians(5.0)  # Минимальный итоговый коэффициент
DEFAULT_AREA_THRESHOLD = 0.015  # Допустимая разница площадей для совпадения
DEFAULT_EDGE_THRESHOLD = 0.005  # Допустимая разница для длин рёбер

classes = [GeometryResolverNPanelBuilder, ResolveGeometryButton, PrevVariant, NextVariant, StopResolve]


def register():
    sc = bpy.types.Scene

    # Регистрация параметров панели
    sc.coplanar_angle_threshold = FloatProperty(
        subtype='ANGLE',
        name="Coplanar Angle Threshold",
        default=DEFAULT_COPLANAR_ANGLE_THRESHOLD,
        description="Angle below which faces are considered coplanar"
    )
    sc.coplanar_dist_threshold = FloatProperty(
        precision=5,
        name="Coplanar Distance Threshold",
        default=DEFAULT_COPLANAR_DIST_THRESHOLD,
        description="Distance below which faces are considered coplanar"
    )
    sc.curvature_threshold = FloatProperty(
        precision=5,
        name="Curvature Threshold",
        default=DEFAULT_CURVATURE_THRESHOLD,
        description="Deviation threshold for vertex curvature classification"
    )
    sc.connected_edge_angle_threshold = FloatProperty(
        subtype='ANGLE',
        precision=5,
        name="Edge Angle Threshold",
        default=DEFAULT_CONNECTED_EDGE_ANGLE_THRESHOLD,
        description="Angle threshold for connected edge matching"
    )
    sc.area_threshold = FloatProperty(
        precision=5,
        name="Area Threshold",
        default=DEFAULT_AREA_THRESHOLD,
        description="Allowed area difference for face matching"
    )
    sc.edge_threshold = FloatProperty(
        precision=5,
        name="Edge Length Threshold",
        default=DEFAULT_EDGE_THRESHOLD,
        description="Allowed edge length difference for edge matching"
    )
    sc.variant_index = IntProperty(
        name="Variant Index",
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

    sc = bpy.types.Scene

    # Выгрузка параметров панели
    for p in ("coplanar_angle_threshold", "coplanar_dist_threshold",
              "curvature_threshold", "connected_edge_angle_threshold",
              "area_threshold", "edge_threshold", "variant_index"):
        delattr(sc, p)
