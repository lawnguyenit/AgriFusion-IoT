# Frontend Dashboard

## 1. Muc dich

`Frontend/` la dashboard tinh dung de doc nhanh `result/*` tu Firebase RTDB va hien thi:

- lich su du lieu
- snapshot hien tai
- ket qua phan tich runtime
- anomaly va recommendation do backend publish

## 2. Kien truc xu ly

```text
Frontend/public/config.js
-> nap config.local.json neu co
-> ket noi Firebase RTDB
-> subscribe result/*
-> normalize payload
-> render chart + side views + prediction card
```

File chinh:

- `public/index.html`
- `public/style.css`
- `public/app.js`
- `public/config.js`
- `public/config.local.example.json`
- `firebase.json`

## 3. Input

Frontend ky vong cac node:

- `result/meta`
- `result/pipeline`
- `result/latest`
- `result/history/air`
- `result/history/soil`
- `result/history/npk`
- `result/history/weather` neu backend co publish meteo
- `result/analysis`
- `result/analysis/diagnosis`
- `result/analysis/forecast/{air,soil,npk,weather}`
- `result/analysis/anomalies`
- `result/analysis/recommendations`

## 4. Output

Dashboard hien thi:

- bieu do chinh
- card trang thai pipeline
- card snapshot
- card prediction
- recommendation
- anomaly marker

## 5. Contract diagnosis hien tai

Frontend ho tro hai contract:

### 5.1. Contract runtime uu tien hien tai

- `label = normal_context | packet_loss_outage | water_deficit | rain_or_fertigation_context`
- `model.family = xgboost` hoac model runtime tuong thich
- `model.labelScheme = four_class`

### 5.2. Contract nhi phan fallback

- `label = normal | abnormal`
- `model.family = xgboost`
- `model.labelScheme = binary`

Frontend se tu phan biet hai contract nay de khong hieu sai `abnormal` thanh `packet_loss_outage`.

## 6. Vi du ket qua

### 6.1. Vi du diagnosis doc duoc

```json
{
  "label": "packet_loss_outage",
  "displayLabel": "Packet loss outage",
  "abnormalProbability": 0.96,
  "model": {
    "family": "xgboost",
    "labelScheme": "four_class"
  }
}
```

### 6.2. Vi du config local

```json
{
  "mode": "auto",
  "resultPath": "result",
  "firebase": {
    "apiKey": "...",
    "authDomain": "...",
    "databaseURL": "...",
    "projectId": "...",
    "appId": "..."
  }
}
```

## 7. Cache va deploy

Frontend hien tai da duoc them hai lop chong cache cu:

- `index.html` nap `app.js`, `config.js`, `style.css` kem query version
- `firebase.json` gan header `Cache-Control: no-cache, no-store, must-revalidate` cho `index.html`, `app.js`, `config.js`, `style.css`

Dieu nay tranh truong hop backend da publish payload moi nhung browser van giu `app.js` cu, dan toi UI hien sai contract diagnosis.

## 8. Cach tai lap

### 8.1. Chay local preview

```powershell
python -m http.server 4173 -d Frontend/public
```

### 8.2. Dung Firebase that

```powershell
Copy-Item Frontend/public/config.local.example.json Frontend/public/config.local.json
```

Sau do sua `config.local.json` theo project Firebase that.

### 8.3. Deploy lai hosting sau khi sua UI

```powershell
cd Frontend
firebase deploy --only hosting
```

Sau deploy, neu browser van giu giao dien cu thi hard refresh `Ctrl + F5`.

## 9. Thu vien can cai

- khong can `npm install` cho ban public tinh hien tai
- Firebase SDK duoc tai tu CDN trong trinh duyet
- can Firebase CLI neu muon deploy hosting

## 10. Gia dinh xu ly

- backend da publish contract `result/*` dung schema
- neu thieu config local hoac thieu du lieu that, frontend se fallback sang demo mode

## 11. Rui ro va gioi han

- frontend khong chay model cuc bo
- prediction card phu thuoc hoan toan vao payload backend
- diagnosis nhi phan chi cho biet `normal/abnormal`, nguoi doc van can xem chart va anomaly de dien giai nguyen nhan
