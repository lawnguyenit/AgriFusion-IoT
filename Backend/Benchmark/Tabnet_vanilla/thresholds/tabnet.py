# Tá»ˆ Lá»† CHIA Dá»® LIá»†U 
from pathlib import Path

# CÃC Tá»ˆ Lá»† CHIA Dá»® LIá»†U CHO TRAIN, VALID, TEST. PHáº¢I Cá»˜NG Láº I Báº°NG 1.0
TRAIN_RATIO = 0.70
VALID_RATIO = 0.15
TEST_RATIO = 0.15

#ÄÆ¯á»œNG DáºªN Äáº¾N FILE CSV Äáº¦U VÃ€O CHO BÆ¯á»šC CHUáº¨N Bá»Š Dá»® LIá»†U
CSV_PATH = Path(__file__).parent.parent / "Input" / "fushion.csv"
OUT_DIR = CSV_PATH.parent / "Prepared"

if OUT_DIR.exists():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

# CÃC Cá»˜T Dá»® LIá»†U Tá»ª 3 Nguá»“n NPK, SHT, METEO ÄÆ¯A VÃ€O MODEL
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

# CÃC Cá»˜T ÄÆ¯á»¢C Sá»¬ Dá»¤NG LÃ€M FEATURE CHO MODEL, CÃ“ THá»‚ KHÃ”NG PHáº¢I LÃ€ Táº¤T Cáº¢ CÃC Cá»˜T á»ž TRÃŠN
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


# CÃC Cá»˜T Sáº¼ Bá»Š LOáº I Bá»Ž Náº¾U Tá»’N Táº I, THÆ¯á»œNG LÃ€ CÃC Cá»˜T THá»œI GIAN ÄÆ¯á»¢C Äá»”I TÃŠN THEO SPEC
DROP_COLS_IF_EXIST = [
    "npk_observed_at_local",
    "sht_observed_at_local",
    "meteo_observed_at_local",
    "npk_present",    
    "sht_present",     
    "meteo_present",
]

DERIVED_FEATURES = [
    "soil_humidity_mean_24h",                           # Ä‘á»™ áº©m Ä‘áº¥t trung bÃ¬nh trong 24h
    "soil_humidity_mean_72h",                           # Ä‘á»™ áº©m Ä‘áº¥t trung bÃ¬nh trong 24h, 72h
    "soil_humidity_delta_24h",                          # chÃªnh lá»‡ch Ä‘á»™ áº©m Ä‘áº¥t hiá»‡n táº¡i so vá»›i 24h trÆ°á»›c Ä‘Ã³
    "soil_humidity_spike_vs_prev3d_pct",                # % chÃªnh lá»‡ch Ä‘á»™ áº©m Ä‘áº¥t hiá»‡n táº¡i so vá»›i trung bÃ¬nh 3 ngÃ y trÆ°á»›c Ä‘Ã³

    "soil_hum_gt90_hours_24h",                          # sá»‘ giá» cÃ³ Ä‘á»™ áº©m Ä‘áº¥t > 90% trong 24h
    "soil_hum_gt85_hours_24h",                          # sá»‘ giá» cÃ³ Ä‘á»™ áº©m Ä‘áº¥t > 90%, > 85% trong 24h
    "soil_hum_lt40_hours_24h",                          # sá»‘ giá» cÃ³ Ä‘á»™ áº©m Ä‘áº¥t > 90%, > 85%, < 40% trong 24h

    "air_rh_mean_24h",                                  # Ä‘á»™ áº©m khÃ´ng khÃ­ trung bÃ¬nh trong 24h
    "air_rh_mean_72h",                                  # Ä‘á»™ áº©m khÃ´ng khÃ­ trung bÃ¬nh trong 24h, 72h
    "air_rh_gt90_hours_24h",                            # sá»‘ giá» cÃ³ Ä‘á»™ áº©m khÃ´ng khÃ­ > 90% trong 24h
    "air_rh_gt95_hours_72h",                            # sá»‘ giá» cÃ³ Ä‘á»™ áº©m khÃ´ng khÃ­ > 90% trong 24h, 95% trong 72h
    "air_rh_lt60_hours_24h",                            # sá»‘ giá» cÃ³ Ä‘á»™ áº©m khÃ´ng khÃ­ < 60% trong 24h

    "temp_air_avg_24h",                                 # nhiá»‡t Ä‘á»™ trung bÃ¬nh, max, min trong 24h
    "temp_air_max_24h",                                 # nhiá»‡t Ä‘á»™ trung bÃ¬nh, max, min trong 24h
    "temp_air_min_24h",                                 # nhiá»‡t Ä‘á»™ trung bÃ¬nh, max, min trong 24h

    "rain_sum_24h",                                     # lÆ°á»£ng mÆ°a tÃ­ch lÅ©y trong 24h
    "rain_sum_72h",                                     # lÆ°á»£ng mÆ°a tÃ­ch lÅ©y trong 24h, 72h
    "days_no_rain",                                     # sá»‘ ngÃ y liÃªn tiáº¿p khÃ´ng cÃ³ mÆ°a

    "ec_mean_24h",                                      # giÃ¡ trá»‹ ec trung bÃ¬nh trong 24h
    "ec_gt1000_hours_24h",                              # sá»‘ giá» cÃ³ ec > 1000 us/cm trong 24h

    "n_rel", "p_rel", "k_rel",                          # cÃ¡c tá»· lá»‡ giá»¯a n, p, k vá»›i giÃ¡ trá»‹ trung vá»‹ cá»§a chÃºng trong táº­p huáº¥n luyá»‡n
    "npk_ratio_n", "npk_ratio_p", "npk_ratio_k",        # cÃ¡c tá»· lá»‡ giá»¯a n, p, k vá»›i nhau

    "growth_stage",                                     # báº¯t buá»™c cho cÃ¡c nhÃ£n cÃ³ phase
    "month_local"                                       # báº¯t buá»™c cho cÃ¡c nhÃ£n cÃ³ seasonal pattern
]

# Má»¤C TIÃŠU Dá»° ÄOÃN
TRAIN_NOW = [
    "phytophthora_root_rot_risk",       # nguy cÆ¡ bá»‡nh thá»‘i rá»… phytophthora dá»±a trÃªn Ä‘iá»u kiá»‡n mÃ´i trÆ°á»ng hiá»‡n táº¡i vÃ  proxy cá»§a nÃ³
    "uneven_fruit_ripening_risk",       # nguy cÆ¡ trÃ¡i chÃ­n khÃ´ng Ä‘á»u dá»±a trÃªn Ä‘iá»u kiá»‡n mÃ´i trÆ°á»ng hiá»‡n táº¡i vÃ  proxy cá»§a nÃ³
    "flower_induction_ready",           # cÃ¢y Ä‘Ã£ sáºµn sÃ ng cho giai Ä‘oáº¡n hoa chÆ°a dá»±a trÃªn Ä‘iá»u kiá»‡n mÃ´i trÆ°á»ng hiá»‡n táº¡i vÃ  proxy cá»§a nÃ³
    "blocked_flower_induction",         # cÃ¢y cÃ³ bá»‹ cháº·n quÃ¡ trÃ¬nh ra hoa khÃ´ng dá»±a trÃªn Ä‘iá»u kiá»‡n mÃ´i trÆ°á»ng hiá»‡n táº¡i vÃ  proxy cá»§a nÃ³
    "flower_fruit_rot_pressure",        # Ã¡p lá»±c bá»‡nh thá»‘i hoa quáº£ dá»±a trÃªn Ä‘iá»u kiá»‡n mÃ´i trÆ°á»ng hiá»‡n táº¡i vÃ  proxy cá»§a nÃ³
    "salt_stress_risk",                 # nguy cÆ¡ cÃ¢y bá»‹ stress do Ä‘á»™ máº·n cao dá»±a trÃªn Ä‘iá»u kiá»‡n mÃ´i trÆ°á»ng hiá»‡n táº¡i vÃ  proxy cá»§a nÃ³
    "ph_stress",                        # nguy cÆ¡ cÃ¢y bá»‹ stress do pH Ä‘áº¥t khÃ´ng phÃ¹ há»£p dá»±a trÃªn Ä‘iá»u kiá»‡n mÃ´i trÆ°á»ng hiá»‡n táº¡i vÃ  proxy cá»§a nÃ³
    "heat_drought_stress",              # nguy cÆ¡ cÃ¢y bá»‹ stress do nhiá»‡t Ä‘á»™ cao vÃ  háº¡n hÃ¡n dá»±a trÃªn Ä‘iá»u kiá»‡n mÃ´i trÆ°á»ng hiá»‡n táº¡i vÃ  proxy cá»§a nÃ³
    "spider_mite_pressure"              # Ã¡p lá»±c rá»‡p Ä‘á» dá»±a trÃªn Ä‘iá»u kiá»‡n mÃ´i trÆ°á»ng hiá»‡n táº¡i vÃ  proxy cá»§a nÃ³
]

TRAIN_WITH_STAGE = [
    "uneven_fruit_ripening_risk",       # nguy cÆ¡ trÃ¡i chÃ­n khÃ´ng Ä‘á»u dá»±a trÃªn Ä‘iá»u kiá»‡n mÃ´i trÆ°á»ng hiá»‡n táº¡i vÃ  proxy cá»§a nÃ³
    "flower_induction_ready",           # cÃ¢y Ä‘Ã£ sáºµn sÃ ng cho giai Ä‘oáº¡n hoa chÆ°a dá»±a trÃªn Ä‘iá»u kiá»‡n mÃ´i trÆ°á»ng hiá»‡n táº¡i vÃ  proxy cá»§a nÃ³
    "blocked_flower_induction"          # cÃ¢y cÃ³ bá»‹ cháº·n quÃ¡ trÃ¬nh ra hoa khÃ´ng dá»±a trÃªn Ä‘iá»u kiá»‡n mÃ´i trÆ°á»ng hiá»‡n táº¡i vÃ  proxy cá»§a nÃ³
]

EXPERIMENTAL = [
    "dieback_pressure",                 # Ã¡p lá»±c bá»‡nh chÃ¡y lÃ¡ dá»±a trÃªn Ä‘iá»u kiá»‡n mÃ´i trÆ°á»ng hiá»‡n táº¡i vÃ  proxy cá»§a nÃ³
    "rhizoctonia_leaf_blight_pressure"  # Ã¡p lá»±c bá»‡nh thá»‘i lÃ¡ rhizoctonia dá»±a trÃªn Ä‘iá»u kiá»‡n mÃ´i trÆ°á»ng hiá»‡n táº¡i vÃ  proxy cá»§a nÃ³
]