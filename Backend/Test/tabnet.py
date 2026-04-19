import numpy as np
import pandas as pd

from sklearn.metrics import classification_report, roc_auc_score    # type: ignore
from pytorch_tabnet.tab_model import TabNetClassifier               # type: ignore

import Backend.Config as config

# =========================
# 1. ĐỌC DỮ LIỆU
# =========================
# CSV ví dụ cần có các cột:
# ts, sht_temp_c, sht_hum_pct, N, P, K, ph, ec, label
# label = 0/1

df = pd.read_csv(tabnet_csv)

# Chuyển timestamp về datetime và sort theo thời gian
df["ts"] = pd.to_datetime(df["ts"], errors="coerce")  # type: ignore
df = df.sort_values("ts").reset_index(drop=True)  


# =========================
# 2. TẠO FEATURE THỜI GIAN CƠ BẢN
# =========================
# Đây là chỗ rất quan trọng:
# TabNet không tự nhớ quá khứ giữa các dòng,
# nên ta phải đưa quá khứ vào chính feature của dòng hiện tại.

base_cols = ["sht_temp_c", "sht_hum_pct", "N", "P", "K", "ph", "ec"]

# lag 1 bước và 4 bước
for col in base_cols:
    df[f"{col}_lag1"] = df[col].shift(periods=1)  # type: ignore
    df[f"{col}_lag4"] = df[col].shift(periods=4)  # type: ignore

# rolling mean 4 bước
for col in base_cols:
    df[f"{col}_mean4"] = df[col].rolling(window=4).mean()

# delta so với bước trước
for col in base_cols:
    df[f"{col}_diff1"] = df[col].diff(1)

# Thêm đặc trưng thời gian đơn giản
df["hour"] = df["ts"].dt.hour
df["dayofweek"] = df["ts"].dt.dayofweek

# Bỏ dòng đầu bị NaN do lag / rolling
df = df.dropna().reset_index(drop=True)


# =========================
# 3. CHỌN X, y
# =========================
target_col = "label"
feature_cols = [c for c in df.columns if c not in ["ts", target_col]]

X = df[feature_cols].values.astype(np.float32)
y = df[target_col].values.astype(int)


# =========================
# 4. CHIA TRAIN / VALID / TEST THEO THỜI GIAN
# =========================
# Tuyệt đối không shuffle cho time series
n = len(df)
train_end = int(n * 0.7)
valid_end = int(n * 0.85)

X_train, y_train = X[:train_end], y[:train_end]
X_valid, y_valid = X[train_end:valid_end], y[train_end:valid_end]
X_test, y_test = X[valid_end:], y[valid_end:]


# =========================
# 5. KHAI BÁO MODEL TABNET
# =========================
clf = TabNetClassifier(
    n_d=16,
    n_a=16,
    n_steps=4,
    gamma=1.5,
    lambda_sparse=1e-4,
    optimizer_params=dict(lr=2e-2),
    mask_type="entmax",   # hoặc "sparsemax"
    seed=42,
    verbose=1
)


# =========================
# 6. TRAIN
# =========================
clf.fit(
    X_train=X_train,
    y_train=y_train,
    eval_set=[(X_train, y_train), (X_valid, y_valid)],
    eval_name=["train", "valid"],
    eval_metric=["auc"],
    max_epochs=100,
    patience=20,
    batch_size=256,
    virtual_batch_size=64,
    num_workers=0,
    drop_last=False
)


# =========================
# 7. DỰ ĐOÁN
# =========================
pred_proba = clf.predict_proba(X_test)[:, 1]
pred_label = (pred_proba >= 0.5).astype(int)

print("AUC:", roc_auc_score(y_test, pred_proba))
print(classification_report(y_test, pred_label, digits=4))


# =========================
# 8. XEM FEATURE IMPORTANCE
# =========================
importance = pd.DataFrame({
    "feature": feature_cols,
    "importance": clf.feature_importances_
}).sort_values("importance", ascending=False)

print("\nTop feature importances:")
print(importance.head(20))


# =========================
# 9. GIẢI THÍCH TỪNG MẪU
# =========================
# M_explain: importance từng sample từng feature
# masks: attention masks theo decision steps
M_explain, masks = clf.explain(X_test)

print("\nExplain matrix shape:", M_explain.shape)
print("Number of decision-step masks:", len(masks))