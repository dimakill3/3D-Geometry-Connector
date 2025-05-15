import bpy
import bmesh
import time

class ModalFaceHighlighter(bpy.types.Operator):
    bl_idname = "object.highlight_faces"
    bl_label = "Highlight Faces One by One (Accurate Time)"
    bl_options = {'REGISTER'}

    _timer = None
    _obj = None
    _bm = None
    _face_indices = []
    _original_indices = {}
    _current_index = 0
    _highlight_mat_index = -1
    _highlight_mat_name = "Highlight_Mat"
    _created_material = False
    _prev_face_index = None
    _last_change_time = 0.0
    _interval = 10.0  # В секундах

    def modal(self, context, event):
        if event.type == 'TIMER':
            now = time.perf_counter()

            if self._current_index >= len(self._face_indices):
                self.restore_materials()
                self.finish(context)
                print("Завершено.")
                return {'FINISHED'}

            if now - self._last_change_time >= self._interval:
                self._bm.faces.ensure_lookup_table()

                # Сброс предыдущей грани
                if self._prev_face_index is not None:
                    prev_face = self._bm.faces[self._prev_face_index]
                    prev_face.material_index = self._original_indices.get(prev_face.index, 0)

                # Подсветка текущей грани
                face_index = self._face_indices[self._current_index]
                face = self._bm.faces[face_index]
                self._prev_face_index = face.index
                face.material_index = self._highlight_mat_index

                print(f"Подсвечивается грань: {face.index}")

                self._bm.to_mesh(self._obj.data)
                self._obj.data.update()

                self._current_index += 1
                self._last_change_time = now

        return {'PASS_THROUGH'}

    def execute(self, context):
        self._obj = self.find_first_visible_mesh()
        if not self._obj:
            self.report({'WARNING'}, "Нет видимого mesh-объекта")
            return {'CANCELLED'}

        self._prepare_materials()
        self._prepare_bmesh()

        self._last_change_time = time.perf_counter()

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)  # Проверяем 10 раз в секунду
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def finish(self, context):
        if self._bm:
            self._bm.free()
        context.window_manager.event_timer_remove(self._timer)

        if self._created_material:
            mat = bpy.data.materials.get(self._highlight_mat_name)
            if mat:
                self._obj.data.materials.pop(index=self._highlight_mat_index)
                bpy.data.materials.remove(mat)

    def find_first_visible_mesh(self):
        for obj in bpy.context.visible_objects:
            if obj.type == 'MESH':
                return obj
        return None

    def _prepare_materials(self):
        if len(self._obj.data.materials) == 0:
            self._obj.data.materials.append(None)

        mat = bpy.data.materials.get(self._highlight_mat_name)
        if not mat:
            mat = bpy.data.materials.new(name=self._highlight_mat_name)
            mat.diffuse_color = (1, 0, 0, 1)  # Красный
            self._created_material = True
        else:
            self._created_material = False

        if mat.name not in [m.name for m in self._obj.data.materials]:
            self._obj.data.materials.append(mat)

        self._highlight_mat_index = self._obj.data.materials.find(mat.name)

    def _prepare_bmesh(self):
        bpy.ops.object.mode_set(mode='OBJECT')
        me = self._obj.data
        self._bm = bmesh.new()
        self._bm.from_mesh(me)
        self._bm.faces.ensure_lookup_table()

        self._face_indices = [f.index for f in self._bm.faces]
        self._original_indices = {f.index: f.material_index for f in self._bm.faces}
        self._current_index = 0
        self._prev_face_index = None

    def restore_materials(self):
        self._bm = bmesh.new()
        self._bm.from_mesh(self._obj.data)
        self._bm.faces.ensure_lookup_table()

        for face in self._bm.faces:
            face.material_index = self._original_indices.get(face.index, 0)

        self._bm.to_mesh(self._obj.data)
        self._obj.data.update()
        self._bm.free()

def register():
    bpy.utils.register_class(ModalFaceHighlighter)

def unregister():
    bpy.utils.unregister_class(ModalFaceHighlighter)

if __name__ == "__main__":
    register()
    bpy.ops.object.highlight_faces()
