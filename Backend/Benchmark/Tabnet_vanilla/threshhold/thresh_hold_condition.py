PHYT_PALMIVORA_ROOT_ROT = {
    "label_name": "phytophthora_root_rot_risk",
    "type": "ordinal_0_3",

    "strict_rule": {
        "high": {
            "soil_ph_lt": 5.0,
            "soil_hum_gt90_hours_24h_gte": 24,
            "temp_air_avg_24h_between": [20.0, 35.0]
        },
        "medium": {
            "soil_ph_between": [5.0, 5.5],
            "soil_hum_gt90_hours_24h_gte": 6
        }
    },

    "proxy_rule_v1": {
        "high": {
            "soil_ph_lt": 5.5,
            "soil_humidity_mean_24h_gte": 75.0,
            "air_rh_mean_24h_gte": 85.0
        },
        "medium": {
            "soil_humidity_mean_24h_gte": 70.0,
            "air_rh_mean_24h_gte": 80.0
        }
    }
}

FLOWER_FRUIT_ROT_PRESSURE = {
    "label_name": "flower_fruit_rot_pressure",
    "type": "ordinal_0_3",

    "strict_rule": {
        "high": {
            "air_rh_gt95_hours_72h_gte": 48,
            "growth_stage_in": ["flowering", "fruit_set", "young_fruit"]
        },
        "warning": {
            "air_rh_gt90_hours_24h_gte": 12
        }
    },

    "proxy_rule_v1": {
        "high": {
            "air_rh_mean_24h_gte": 90.0,
            "air_rh_mean_72h_gte": 88.0,
            "growth_stage_in": ["flowering", "fruit_set", "young_fruit"]
        },
        "medium": {
            "air_rh_mean_24h_gte": 85.0
        }
    }
}

DIEBACK_PRESSURE = {
    "label_name": "dieback_pressure",
    "type": "ordinal_0_3",

    "strict_rule": {
        "high": {
            "temp_air_avg_24h_between": [25.0, 30.0],
            "air_rh_mean_24h_gte": 85.0,
            "month_local_in": [11, 12, 1]
        },
        "safe": {
            "temp_air_max_24h_gt": 35.0,
            "temp_air_min_24h_lt": 10.0
        }
    },

    "proxy_rule_v1": {
        "high": {
            "temp_air_avg_24h_between": [25.0, 30.0],
            "air_rh_mean_24h_gte": 80.0
        }
    }
}

RHIZOCTONIA_LEAF_BLIGHT = {
    "label_name": "rhizoctonia_leaf_blight_pressure",
    "type": "ordinal_0_3",

    "strict_rule": {
        "high": {
            "air_rh_mean_24h_gte": 90.0,
            "rain_sum_24h_gt": 0.0,
            "growth_stage_in": ["young_flush", "nursery", "young_canopy"]
        },
        "medium": {
            "air_rh_mean_24h_gte": 85.0
        }
    },

    "proxy_rule_v1": {
        "high": {
            "air_rh_mean_24h_gte": 88.0,
            "rain_sum_24h_gt": 0.0
        }
    }
}

SALT_STRESS = {
    "label_name": "salt_stress_risk",
    "type": "ordinal_0_3",

    "strict_rule": {
        "none": {
            "soil_ec_us_cm_lt": 1000.0
        },
        "high": {
            "soil_ec_us_cm_gte": 1000.0
        }
    },

    "proxy_rule_v1": {
        "high": {
            "soil_ec_us_cm_gte": 1000.0
        },
        "medium": {
            "soil_ec_us_cm_between": [850.0, 1000.0]
        }
    }
}

PH_STRESS = {
    "label_name": "ph_stress",
    "type": "multiclass",

    "strict_rule": {
        "critical_low": {"soil_ph_lt": 4.5},
        "suboptimal_low": {"soil_ph_between": [4.5, 5.5]},
        "optimal": {"soil_ph_between": [5.5, 6.5]},
        "high": {"soil_ph_gt": 6.5}
    },

    "extended_rule": {
        "severe_alkaline": {"soil_ph_gt": 8.5}
    }
}

HEAT_DROUGHT_STRESS = {
    "label_name": "heat_drought_stress",
    "type": "multiclass_or_binary_heads",

    "strict_rule": {
        "cold_stress": {
            "temp_air_min_24h_lt": 13.0
        },
        "heat_drought_high": {
            "temp_air_max_24h_gt": 35.0,
            "soil_humidity_mean_24h_lt": 40.0
        }
    },

    "proxy_rule_v1": {
        "heat_drought_high": {
            "temp_air_max_24h_gt": 32.0,
            "soil_humidity_mean_24h_lt": 50.0
        },
        "warning": {
            "temp_air_avg_24h_gt": 30.0,
            "soil_humidity_mean_24h_lt": 55.0
        }
    }
}

UNEVEN_FRUIT_RIPENING = {
    "label_name": "uneven_fruit_ripening_risk",
    "type": "binary",

    "strict_rule": {
        "applicable_if": {
            "growth_stage_in": ["fruit_fill", "preharvest_1m"]
        },
        "risk": {
            "k_low": True,
            "OR": {
                "soil_humidity_spike_vs_prev3d_pct_gt": 15.0
            }
        }
    },

    "proxy_rule_v1": {
        "applicable_if": {
            "growth_stage_in": ["fruit_fill", "preharvest_1m"]
        },
        "risk": {
            "k_rel_lt": 0.95,
            "OR": {
                "soil_humidity_spike_vs_prev3d_pct_gt": 12.0
            }
        }
    }
}

FLOWER_INDUCTION = {
    "ready_label_name": "flower_induction_ready",
    "blocked_label_name": "blocked_flower_induction",
    "type": "binary",

    "applicable_if": {
        "growth_stage_in": ["preflower_30_40d"]
    },

    "strict_rule": {
        "ready": {
            "soil_humidity_mean_24h_between": [26.0, 30.0],
            "dry_days_consecutive_between": [7, 14],
            "npk_ratio_close_to": [1.0, 3.0, 2.0]
        },
        "blocked": {
            "soil_humidity_mean_24h_gt": 30.0,
            "OR": {
                "n_dominant_over_p_and_k": True
            }
        }
    },

    "proxy_rule_v1": {
        "ready": {
            "soil_humidity_mean_24h_between": [28.0, 35.0],
            "dry_days_consecutive_gte": 5
        },
        "blocked": {
            "soil_humidity_mean_24h_gt": 35.0,
            "OR": {
                "n_rel_gt_p_rel": True,
                "n_rel_gt_k_rel": True
            }
        }
    }
}

SPIDER_MITE_PRESSURE = {
    "label_name": "spider_mite_pressure",
    "type": "ordinal_0_3",

    "strict_rule": {
        "high": {
            "days_no_rain_gte": 3,
            "temp_air_max_24h_gt": 32.0,
            "air_rh_mean_24h_lt": 60.0
        }
    },

    "proxy_rule_v1": {
        "high": {
            "days_no_rain_gte": 2,
            "temp_air_avg_24h_gt": 31.0,
            "air_rh_mean_24h_lt": 65.0
        },
        "medium": {
            "temp_air_avg_24h_gt": 30.0,
            "air_rh_mean_24h_lt": 70.0
        }
    }
}