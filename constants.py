import math
import os

# Путь к JSON-файлу (относительно расположения add-on)
BASE_DIR = os.path.dirname(__file__)
JSON_FILENAME = "geometry.json"
GRAPH_FILENAME = "graph.png"
JSON_PATH = os.path.join(BASE_DIR, "data", JSON_FILENAME)
GRAPH_PATH = os.path.join(BASE_DIR, "data", GRAPH_FILENAME)

# # Константы
BATCH_SIZE = 100

MIN_MATCH_FACE_COEFF = 0.65                              # Минимальный итоговый коэффициент
MIN_MATCH_EDGE_COEFF = 0.99999                          # Минимальный итоговый коэффициент
ORIG_INDICES = "orig_indices"                           # Метка для int слоя граней и рёбер
ORIG_INDEX = "orig_index"                               # Метка для str слоя граней

# Веса/штрафы для параметров
AREA_PENALTY = 0.1                                      # Штраф за несоответствие площади
EDGE_PENALTY = 0.8                                      # Штраф за несоответствие длин рёбер
NORMAL_PENALTY = 0.1                                    # Штраф за несоответствие нормалей

NORMAL_ANGLE_THRESHOLD = math.radians(2)                # Порог для конечной проверки правильного поворота мэшей относительно соединений
MAX_DISTANCE_BETWEEN_MESHES = 0.01                      # Максиамльная конечная дистанция между мэшами (для минимизации зазоров)