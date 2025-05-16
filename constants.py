import os

# Путь к JSON-файлу (относительно расположения add-on)
BASE_DIR = os.path.dirname(__file__)
JSON_FILENAME = "geometry.json"
JSON_PATH = os.path.join(BASE_DIR, "data", JSON_FILENAME)

# # Константы
# COPLANAR_ANGLE_THRESHOLD = math.radians(2.0)          # Угол, до которого грани считаются компланарными
# COPLANAR_DIST_THRESHOLD = 0.004                       # Дистанция, до которой грани считаются компланарными
# CURVATURE_THRESHOLD = 0.01                            # Величина отклонения кривизны
# CONNECTED_EDGE_ANGLE_THRESHOLD = math.radians(5.0)    # Минимальный итоговый коэффициент
#
# AREA_THRESHOLD = 0.015                                # Допустимая разница площадей для совпадения
# EDGE_THRESHOLD = 0.005                                # Допустимая разница для длин рёбер
MIN_MATCH_FACE_COEFF = 0.5                              # Минимальный итоговый коэффициент
MIN_MATCH_EDGE_COEFF = 0.995                             # Минимальный итоговый коэффициент

# Веса/штрафы для параметров
AREA_PENALTY = 0.1                                      # Штраф за несоответствие площади
EDGE_PENALTY = 0.8                                      # Штраф за несоответствие длин рёбер
NORMAL_PENALTY = 0.1                                    # Штраф за несоответствие нормалей