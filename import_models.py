import bpy
import os
import math

# Константы
MODEL_DIR = "C:/path/to/your/models"  # Измените на вашу директорию с моделями
COLLECTION_NAME = "Imported_Models"
SPACING = 2.0  # Расстояние между моделями при размещении на сцене
SUPPORTED_EXTENSIONS = {".fbx", ".obj", ".blend", ".glb", ".gltf", ".stl"}

# Функции импорта
IMPORT_FUNCTIONS = {
    ".fbx": lambda path: bpy.ops.import_scene.fbx(filepath=path),
    ".obj": lambda path: bpy.ops.import_scene.obj(filepath=path),
    ".glb": lambda path: bpy.ops.import_scene.gltf(filepath=path),
    ".gltf": lambda path: bpy.ops.import_scene.gltf(filepath=path),
    ".stl": lambda path: bpy.ops.import_mesh.stl(filepath=path),
}

def import_blend_file(blend_path):
    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        data_to.objects = [name for name in data_from.objects]
    return [obj for obj in data_to.objects if obj]


def clear_collection(name):
    if name in bpy.data.collections:
        coll = bpy.data.collections[name]
        # Удаляем все объекты из коллекции
        for obj in list(coll.objects):
            coll.objects.unlink(obj)
        # Удаляем коллекцию из сцены
        bpy.context.scene.collection.children.unlink(coll)
        # Удаляем саму коллекцию из данных
        bpy.data.collections.remove(coll)


def create_collection(name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def load_models_from_directory(directory):
    # Проверка директории
    if not os.path.exists(directory):
        print(f"[INFO] Директория не существует: {directory}")
        return

    # Сбор путей к поддерживаемым расширениям
    files = sorted(os.listdir(directory))
    model_paths = []
    for fname in files:
        ext = os.path.splitext(fname)[1].lower()
        if ext in SUPPORTED_EXTENSIONS:
            model_paths.append(os.path.join(directory, fname))

    if not model_paths:
        print(f"[INFO] В директории {directory} не найдено поддерживаемых моделей.")
        return

    # Подготовка коллекции
    clear_collection(COLLECTION_NAME)
    coll = create_collection(COLLECTION_NAME)

    imported_objects = []
    for path in model_paths:
        ext = os.path.splitext(path)[1].lower()
        before = set(bpy.data.objects)
        print(f"[INFO] Импорт: {os.path.basename(path)}")
        try:
            if ext == ".blend":
                new_objs = import_blend_file(path)
                # Загружаем объекты на сцену
                for obj in new_objs:
                    bpy.context.collection.objects.link(obj)
            else:
                IMPORT_FUNCTIONS[ext](path=path)
                new_objs = [obj for obj in bpy.data.objects if obj not in before]
        except Exception as e:
            print(f"[ERROR] Ошибка при импорте {path}: {e}")
            continue

        for obj in new_objs:
            # Перемещаем объект в коллекцию
            for c in obj.users_collection:
                c.objects.unlink(obj)
            coll.objects.link(obj)
            imported_objects.append(obj)

    # Размещение объектов по сетке
    count = len(imported_objects)
    cols = math.ceil(math.sqrt(count))
    for idx, obj in enumerate(imported_objects):
        row = idx // cols
        col = idx % cols
        obj.location = (col * SPACING, row * SPACING, 0)

    print(f"[INFO] Импортировано {count} объектов в коллекцию '{COLLECTION_NAME}'.")


# Запуск
if __name__ == "__main__":
    print(f"[ERROR] Ошибка при импорте")
    load_models_from_directory(MODEL_DIR)