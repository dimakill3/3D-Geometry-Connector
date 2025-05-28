import os

# Путь к JSON-файлу (относительно расположения add-on)
BASE_DIR = os.path.dirname(__file__)
JSON_FILENAME = "geometry.json"
JSON_PATH = os.path.join(BASE_DIR, "data", JSON_FILENAME)

# # Константы
BATCH_SIZE = 100

MIN_MATCH_FACE_COEFF = 0.6                              # Минимальный итоговый коэффициент
MIN_MATCH_EDGE_COEFF = 0.999                            # Минимальный итоговый коэффициент
ORIG_INDICES = "orig_indices"                           # Метка для int слоя граней и рёбер
ORIG_INDEX = "orig_index"                               # Метка для str слоя граней

# Веса/штрафы для параметров
AREA_PENALTY = 0.1                                      # Штраф за несоответствие площади
EDGE_PENALTY = 0.8                                      # Штраф за несоответствие длин рёбер
NORMAL_PENALTY = 0.1                                    # Штраф за несоответствие нормалей
COMPARE_OTHER_MATCHES_PENALTY = 0.1                     # Штраф за несовпадение по другим соединениям