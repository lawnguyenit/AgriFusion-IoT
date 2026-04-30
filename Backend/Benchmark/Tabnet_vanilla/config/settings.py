# TỈ LỆ CHIA DỮ LIỆU 
from pathlib import Path

# CÁC TỈ LỆ CHIA DỮ LIỆU CHO TRAIN, VALID, TEST. PHẢI CỘNG LẠI BẰNG 1.0
TRAIN_RATIO = 0.70
VALID_RATIO = 0.15
TEST_RATIO = 0.15

#ĐƯỜNG DẪN ĐẾN FILE CSV ĐẦU VÀO CHO BƯỚC CHUẨN BỊ DỮ LIỆU
CSV_PATH = Path(__file__).parent.parent / "Input" / "fushion.csv"
OUT_DIR = CSV_PATH.parent / "Prepared"

if OUT_DIR.exists():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

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

]


# CÁC CỘT SẼ BỊ LOẠI BỎ NẾU TỒN TẠI, THƯỜNG LÀ CÁC CỘT THỜI GIAN ĐƯỢC ĐỔI TÊN THEO SPEC
DROP_COLS_IF_EXIST = [
    "npk_observed_at_local",
    "sht_observed_at_local",
    "meteo_observed_at_local",
    "npk_present",    
    "sht_present",     
    "meteo_present",
]

DERIVED_FEATURES = [
    "soil_humidity_mean_24h",                           # độ ẩm đất trung bình trong 24h
    "soil_humidity_mean_72h",                           # độ ẩm đất trung bình trong 24h, 72h
    "soil_humidity_delta_24h",                          # chênh lệch độ ẩm đất hiện tại so với 24h trước đó
    "soil_humidity_spike_vs_prev3d_pct",                # % chênh lệch độ ẩm đất hiện tại so với trung bình 3 ngày trước đó

    "soil_hum_gt90_hours_24h",                          # số giờ có độ ẩm đất > 90% trong 24h
    "soil_hum_gt85_hours_24h",                          # số giờ có độ ẩm đất > 90%, > 85% trong 24h
    "soil_hum_lt40_hours_24h",                          # số giờ có độ ẩm đất > 90%, > 85%, < 40% trong 24h

    "air_rh_mean_24h",                                  # độ ẩm không khí trung bình trong 24h
    "air_rh_mean_72h",                                  # độ ẩm không khí trung bình trong 24h, 72h
    "air_rh_gt90_hours_24h",                            # số giờ có độ ẩm không khí > 90% trong 24h
    "air_rh_gt95_hours_72h",                            # số giờ có độ ẩm không khí > 90% trong 24h, 95% trong 72h
    "air_rh_lt60_hours_24h",                            # số giờ có độ ẩm không khí < 60% trong 24h

    "temp_air_avg_24h",                                 # nhiệt độ trung bình, max, min trong 24h
    "temp_air_max_24h",                                 # nhiệt độ trung bình, max, min trong 24h
    "temp_air_min_24h",                                 # nhiệt độ trung bình, max, min trong 24h

    "rain_sum_24h",                                     # lượng mưa tích lũy trong 24h
    "rain_sum_72h",                                     # lượng mưa tích lũy trong 24h, 72h
    "days_no_rain",                                     # số ngày liên tiếp không có mưa

    "ec_mean_24h",                                      # giá trị ec trung bình trong 24h
    "ec_gt1000_hours_24h",                              # số giờ có ec > 1000 us/cm trong 24h

    "n_rel", "p_rel", "k_rel",                          # các tỷ lệ giữa n, p, k với giá trị trung vị của chúng trong tập huấn luyện
    "npk_ratio_n", "npk_ratio_p", "npk_ratio_k",        # các tỷ lệ giữa n, p, k với nhau

    "growth_stage",                                     # bắt buộc cho các nhãn có phase
    "month_local"                                       # bắt buộc cho các nhãn có seasonal pattern
]

# MỤC TIÊU DỰ ĐOÁN
TRAIN_NOW = [
    "phytophthora_root_rot_risk",       # nguy cơ bệnh thối rễ phytophthora dựa trên điều kiện môi trường hiện tại và proxy của nó
    "uneven_fruit_ripening_risk",       # nguy cơ trái chín không đều dựa trên điều kiện môi trường hiện tại và proxy của nó
    "flower_induction_ready",           # cây đã sẵn sàng cho giai đoạn hoa chưa dựa trên điều kiện môi trường hiện tại và proxy của nó
    "blocked_flower_induction",         # cây có bị chặn quá trình ra hoa không dựa trên điều kiện môi trường hiện tại và proxy của nó
    "flower_fruit_rot_pressure",        # áp lực bệnh thối hoa quả dựa trên điều kiện môi trường hiện tại và proxy của nó
    "salt_stress_risk",                 # nguy cơ cây bị stress do độ mặn cao dựa trên điều kiện môi trường hiện tại và proxy của nó
    "ph_stress",                        # nguy cơ cây bị stress do pH đất không phù hợp dựa trên điều kiện môi trường hiện tại và proxy của nó
    "heat_drought_stress",              # nguy cơ cây bị stress do nhiệt độ cao và hạn hán dựa trên điều kiện môi trường hiện tại và proxy của nó
    "spider_mite_pressure"              # áp lực rệp đỏ dựa trên điều kiện môi trường hiện tại và proxy của nó
]

TRAIN_WITH_STAGE = [
    "uneven_fruit_ripening_risk",       # nguy cơ trái chín không đều dựa trên điều kiện môi trường hiện tại và proxy của nó
    "flower_induction_ready",           # cây đã sẵn sàng cho giai đoạn hoa chưa dựa trên điều kiện môi trường hiện tại và proxy của nó
    "blocked_flower_induction"          # cây có bị chặn quá trình ra hoa không dựa trên điều kiện môi trường hiện tại và proxy của nó
]

EXPERIMENTAL = [
    "dieback_pressure",                 # áp lực bệnh cháy lá dựa trên điều kiện môi trường hiện tại và proxy của nó
    "rhizoctonia_leaf_blight_pressure"  # áp lực bệnh thối lá rhizoctonia dựa trên điều kiện môi trường hiện tại và proxy của nó
]