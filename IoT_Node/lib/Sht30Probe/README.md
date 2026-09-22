# Sht30Probe

Che do probe rieng cho SHT30, khong di qua AppRuntime/SIM/Firebase.

Moi diagnostic cycle thuc hien hai lop kiem tra:

- `INIT_BURST`: ep buoc moi lan init/probe trong mot burst deu chay lai, khong bi gate retry 10 giay cua production; mac dinh 10 lan, cach nhau 300 ms.
- `RAW_BURST`: scan bus I2C, ping ca `0x44` va `0x45`, gui lenh reset/measure truc tiep, in 6 byte frame, CRC va gia tri raw/decode.

`0x44`, SDA/SCL lay tu `Config.h` (hien tai dang la 6/7 trong bai test); `0x45` chi la ung vien chan doan. Ket qua can doc nhu sau:

- `ACK=0`: khong thay thiet bi tren dia chi do.
- `ACK=1`, `crc=0`: co phan hoi nhung frame loi.
- `ACK=1`, `crc=1`, `raw_temp=0x0000`, `raw_hum=0x0000`: bus va giao thuc phan hoi, nhung cam bien dang tra mau do khong hop le.
- `primary_ready=1`: duong `Sht30Service` da co mau hop le va payload JSON duoc tao thanh cong.
