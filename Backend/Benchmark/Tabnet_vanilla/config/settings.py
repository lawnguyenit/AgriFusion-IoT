# TỈ LỆ CHIA DỮ LIỆU 
TRAIN_RATIO = 0.70
VALID_RATIO = 0.15
TEST_RATIO = 0.15


# CÁC CỘT DỮ LIỆU TỪ 3 Nguồn NPK, SHT, METEO ĐƯA VÀO MODEL
NPK_FIELDS = {
                "n_ppm": "perception.n_ppm",
                "p_ppm": "perception.p_ppm",
                "k_ppm": "perception.k_ppm",
                "soil_temp_c": "perception.soil_temp_c",
                "soil_humidity_pct": "perception.soil_humidity_pct",
                "soil_ph": "perception.soil_ph",
                "soil_ec_us_cm": "perception.soil_ec_us_cm",
            }

SHT_FIELDS = {
                "temp_air_c": "perception.temp_air_c",
                "humidity_air_pct": "perception.humidity_air_pct",
            }

METEO_FIELDS = {
            "temp_air_c": "perception.temp_air_c",
                "humidity_air_pct": "perception.humidity_air_pct",
                "rain_mm": "perception.rain_mm",
                "dew_point_c": "perception.dew_point_c",
                "cloud_cover_pct": "perception.cloud_cover_pct",
                "et0_mm": "perception.et0_mm",
                "weather_code": "perception.weather_code",
                "is_day": "perception.is_day",
}

# CÁC CỘT ĐƯỢC SỬ DỤNG LÀM FEATURE CHO MODEL, CÓ THỂ KHÔNG PHẢI LÀ TẤT CẢ CÁC CỘT Ở TRÊN
BASE_FEATURE_COLS = [
    # NPK
    "npk_n_ppm",
    "npk_p_ppm",
    "npk_k_ppm",
    "npk_soil_temp_c",
    "npk_soil_humidity_pct",
    "npk_soil_ph",
    "npk_soil_ec_us_cm",

    # SHT
    "sht_temp_air_c",
    "sht_humidity_air_pct",

    # METEO
    "meteo_rain_mm",
    "meteo_dew_point_c",
    "meteo_cloud_cover_pct",
    "meteo_et0_mm",
    "meteo_weather_code",
    "meteo_is_day",

    # presence flags
    "npk_present",
    "sht_present",
    "meteo_present",
]


# CÁC CỘT SẼ BỊ LOẠI BỎ NẾU TỒN TẠI, THƯỜNG LÀ CÁC CỘT THỜI GIAN ĐƯỢC ĐỔI TÊN THEO SPEC
DROP_COLS_IF_EXIST = [
    "npk_observed_at_local",
    "sht_observed_at_local",
    "meteo_observed_at_local",
]

