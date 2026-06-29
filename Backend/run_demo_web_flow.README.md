# Demo Web Flow Script

## Muc dich

`run_demo_web_flow.ps1` dong goi chuoi lenh demo web thanh 1 file PowerShell de ban khong can tim lai tung dong command trong file note.

Hien tai pha full-history cham da duoc tach rieng ra khoi flow demo nhanh.

- pha 2: bootstrap baseline demo ngay `2026-05-20`, snapshot lai len `result`
- pha 3: inject scenario demo va append dong len `result` de chart di dong

Neu can quay clip pha lich su that, dung script rieng `prepare_historical_result_snapshot.ps1`.

## Input

- `Backend/main.py`
- cau hinh Firebase trong `Backend/Services/.env`
- quyen doc/ghi Firebase RTDB
- Python environment da cai du package can thiet

## Output

- du lieu local Layer0 / Layer1 / Result_publish
- nhanh `result/*` tren Firebase RTDB
- terminal log theo tung pha de ban theo doi khi demo

## Script cho pha lich su that

```powershell
cd Backend
powershell -ExecutionPolicy Bypass -File .\prepare_historical_result_snapshot.ps1
```

Script nay thuc hien rieng:

- `--only-layer0 --full-history --start-date 2026-04-01 --end-date 2026-05-19`
- `--only-layer1`
- `--only-result --publish-result --result-mode snapshot --result-payload-scope full --result-runtime-experiment auto`

No nen duoc chay truoc va chi can chay 1 lan khi can chuan bi bo lich su that cho web.

## Command chay

### Chay mac dinh

```powershell
cd Backend
powershell -ExecutionPolicy Bypass -File .\run_demo_web_flow.ps1
```

### Tam dung giua cac pha de mo web va trinh bay

```powershell
cd Backend
powershell -ExecutionPolicy Bypass -File .\run_demo_web_flow.ps1 -PauseBetweenPhases
```

### Chay demo xong roi tu dong xoa `result` va du lieu demo `2026-05-20`

```powershell
cd Backend
powershell -ExecutionPolicy Bypass -File .\run_demo_web_flow.ps1 -PauseBetweenPhases -CleanupAfterDemo
```

### Dry-run de kiem tra chuoi lenh ma chua chay that

```powershell
cd Backend
powershell -ExecutionPolicy Bypass -File .\run_demo_web_flow.ps1 -DryRun
```

### Chi chay rieng pha cleanup

```powershell
cd Backend
powershell -ExecutionPolicy Bypass -File .\run_demo_web_flow.ps1 -CleanupOnly
```

### Chay truc tiep utility cleanup

```powershell
cd Backend
python cleanup_demo_state.py --demo-date-key 2026-05-20 --restore-latest-date-key 2026-05-19
```

### Doi tham so demo

```powershell
cd Backend
powershell -ExecutionPolicy Bypass -File .\run_demo_web_flow.ps1 `
  -DemoDateKey 2026-05-20 `
  -RestoreLatestDateKey 2026-05-19 `
  -TemplateId 2 `
  -PacketGapMinutes 64 `
  -PauseBetweenPhases `
  -CleanupAfterDemo
```

## Gia dinh xu ly

- local workspace cho phep ghi `Backend/Output_data/**`
- lich su that da duoc chuan bi truoc bang `prepare_historical_result_snapshot.ps1` neu ban muon web hien du full chart
- `TemplateId` map dung theo runtime simulator hien tai
- `RestoreLatestDateKey` phai la ngay con telemetry that de utility co the phuc hoi `latest/current`, `latest/meta`, `live`

## Rui ro va gioi han

- script nay ghi du lieu that len Firebase RTDB, khong phai dry-run neu khong truyen `-DryRun`
- pha 2 dung `snapshot`, nen se ghi de nhanh `result/*`
- neu local artifact khong dung hoac Firebase khong san sang, script dung ngay tai buoc loi dau tien
- cleanup se goi xoa truc tiep tren Firebase cho `result`, `Node1/telemetry/2026-05-20`, `Node1/status_events/*_demo`, va phuc hoi `latest/current`, `latest/meta`, `live` ve ngay `RestoreLatestDateKey`
