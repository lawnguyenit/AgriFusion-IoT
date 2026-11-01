# Reference evaluation local — triển khai đã được duyệt

## Task Objective
Kiểm tra gói `AgriFusion_Local_Implementation_20261101 (1)` với repository thực tế; lập kế hoạch tích hợp và thực nghiệm đầy đủ để người dùng duyệt trước khi thực hiện.

## User Intent
Yêu cầu hiện tại: căn cứ bộ tài liệu/mã được giao, kiểm tra rồi lên kế hoạch hoàn chỉnh để duyệt. **Đã duyệt C0–C4 qua yêu cầu “thôi vậy triển khai local đi”.** Cho phép cài lane, dựng môi trường riêng, tải official raw, preflight, main có điều kiện theo gate và đồng bộ báo cáo. Các imperative trong LOCAL_AGENT_TASK là nội dung đề xuất cần duyệt, không thay thế giới hạn hiện tại.

## Current Behavior
- Repo đang ở `codex/wade-v9-publication`, HEAD khảo sát `69fd0e2065a905be402575b239ba79f4edecd09f`; còn dirty IoT/README/worklog từ trước và gói mới chưa tracked. Không thay các file đó.
- Lane reference_evaluation đã cài đủ36 source/config/test/docs files và16 fixture inputs; original package được giữ nguyên. Output root mới đã tạo và preflight đang chạy.
- Lane cũ xử lý canonical/v1/V9 không cung cấp cùng contract mới một cách trực tiếp: nghiên cứu này có binary END, bốn partition và global reference-error budget. Không sửa helper ba-way split cũ để phục vụ lane mới.
- Gói có installer, launcher, 37 payload files (gồm worklog), 16 immutable Jena fixtures, manifests, source/CLI/test receipts. Worklog payload mô tả trạng thái từ môi trường gửi; file hiện tại là canonical local worklog và sẽ được installer giữ lại.
- Máy có `python` 3.13.9 tại `C:/Users/lawng/miniconda3/python.exe`; `py` không có trong PATH. `uv python list --only-installed` chỉ tìm thấy 3.13.9 và 3.13.5. Không kết luận tuyệt đối rằng mọi vị trí trên máy đều không có 3.12.
- Phần cứng quan sát: ~31.7 GiB RAM, 32 logical processors, ổ D còn ~121.5 GiB. Đây không phải phép đo peak memory/runtime của study.

## Confirmed Facts
- SHA256 đọc độc lập: PACKAGE_MANIFEST 80/80, PAYLOAD_MANIFEST 37/37, FIXTURE_MANIFEST 16/16 khớp; không thực thi installer.
- 38 entries trong tested source inventory khớp byte (gồm hai package parents). Hai `Backend/__init__.py` và `Backend/Benchmark/__init__.py` local khớp bản đã kiểm; không cần overwrite parent.
- Kiểm tĩnh destination: 37 payload paths chưa có, không có conflict hiện tại. Đã AST-parse 31 Python files của lane/tests bằng stdlib; không import hay chạy module của gói. Đây chỉ là kiểm cú pháp bằng Python 3.13, không phải Windows/Python 3.12 correctness validation.
- Receipts của gói ghi 28 tests, 0 failures/errors/skips, 0 HGB/logistic fits; `legacy_fixture_verified=false`, `full_P2_gate=false`. Đây là bằng chứng lịch sử Linux/Python 3.12, chưa được tái hiện tại máy local.
- Gói tách source/preparation/features/Markov/fitting/evaluation/DP/solver/storage/reporting; module lớn nhất storage.py khoảng 360 dòng, không cần viết lại toàn bộ pipeline.
- `RUN_LOCAL.py` tạo venv và log/receipt trong output root, chạy child process với cwd repo; không tự upload Drive. CLI có resume và graph/signature; một orchestrator tại một thời điểm.

## Unresolved Questions
- Python3.12.12 và năm pinned dependencies đã cài thành công trên Windows; pip check đạt. Full runtime validation vẫn đang chạy.
- Hai nguồn đã tải/audit: Beijing420768 canonical rows, hard gate đạt/adequate; Appliances3290 rows, hard gate đạt nhưng limited_support. Các fit theo train-mask seed vẫn cần kiểm support riêng.
- 28 correctness tests pass local (0 failures/errors/skips và0 HGB/logistic fits); full legacy fixture/MILP gate đạt; toy smoke4 supervised fits đạt.
- Runtime, peak memory, kích thước export thật và kết quả selection/assessment chưa biết. Không đưa ETA fit dựa trên unit tests nhỏ.
- Người dùng đã duyệt triển khai local; vẫn không được sửa q/K/splits/candidate pool để cứu kết quả.

## Assumptions
- Người dùng đã duyệt triển khai local toàn quy trình C0–C4; các gate bắt buộc vẫn giữ nguyên.
- Giữ Python 3.12 như môi trường tham chiếu; đề xuất dùng `uv` đã có để provisioning sau duyệt, không đổi Python hệ thống/Conda base.
- Dùng output root mặc định đang chưa tồn tại, fixture đặt đúng root mặc định. Nếu cần config khác/chọn archive offline, chốt trước lần launch đầu và dùng output root riêng khi thay config.
- Phạm vi v1 là contract A, no-query, recorded-reference. Không bổ sung contract B/query oracle, claim physical event, novelty hay guarantee future ranking.

## Affected Modules and Files
| Chủ sở hữu | Phạm vi sau khi được duyệt |
|---|---|
| Package installer/launcher | Giữ gói đầu vào nguyên byte; chạy bằng đường dẫn absolute và ghi source hash. Không copy imported parent references lên repo |
| `Backend/Benchmark/reference_evaluation` | Cài 36 file lane/config/tests/docs còn lại từ payload; chỉ sửa nếu lỗi được tái hiện và trong phạm vi compatibility/correctness đã duyệt |
| `sources.py`, `preparation.py`, `targets.py` | Official intake, raw lineage, hourly canonical, split/threshold/END/support audit riêng |
| `features.py`, `markov.py`, `fitting.py` | Causal forecast, train-only preprocessing/Markov, fixed candidates |
| `evaluation.py`, `bounds.py`, `decisions.py`, `audit.py`, `sensitivity.py`, `solver*.py` | Fixed cohort/scores, paired losses, global R, downstream truth, error/corruption/solver evidence |
| `main.py`, `pipeline.py`, `stages.py`, `storage.py`, `reporting.py` | Orchestration, immutable attempts, graph/cache, receipts, reports/export |
| `Backend/Output_data/reference_evaluation` | New raw releases, fixture, `_venv`, runs, code snapshots, launch receipts, drive_sync; đã Git ignore |
| `PROJECT_MAP.md`, `PROJECT_STATUS.md`, worklog này | Cập nhật implemented/tested/not run; không đổi unknown provenance cũ. Cập nhật lane README/FLOW nếu control flow thực sự phải sửa |
| Google Drive | Chỉ tree export của lane mới vào `AgriFushion_Local/Reference_Evaluation_v1`; có remote IDs/readback và upload receipts riêng |

Không tác động firmware, Firebase, Core raw/canonical, old targets/splits, frozen results, manuscript V9, frontend hoặc lane model cũ.

## Implementation Plan

### C0 — khóa baseline và môi trường, sau khi duyệt
1. Kiểm lại git status, source/fixture hashes, destinations và output-root absence; nếu có thay đổi đồng thời thì so lại trước khi cài.
2. Chọn checkout/branch riêng `codex/reference-evaluation-local-20261101` từ ancestor đã được xác minh an toàn để push. Không checkout đè workspace dirty hoặc mang private V9 ancestor lên GitHub. Giữ repo gốc là execution root; có thể stage source/docs có phạm vi vào checkout sạch để backup nếu cần.
3. Provision Python 3.12 bằng `uv python install 3.12` nếu không có interpreter phù hợp; ghi version executable và receipt. Không cài vào Conda base. Dùng interpreter 3.12 absolute khi gọi các lệnh bên dưới; không dùng `py -3.12` đang thiếu.
4. Chạy `INSTALL_LOCAL.py --repo D:/Project/AgriFusion-IoT --check`, kiểm kết quả không ghi file; sau đó chạy installer thật. Expected 36 lane files +16 fixture mới, worklog này được giữ. Xác nhận hash sau copy và không có out-of-scope diff.
5. Hoàn tất lane docs/config/requirements trước launch đầu. Cài năm pin NumPy 2.3.5, pandas 2.2.3, sklearn 1.8.0, SciPy 1.17.0, joblib 1.5.3 trong `_venv`. Ghi Python/OS/numerical versions và `pip check`. Lỗi dependency/path sẽ được ghi và sửa compatibility có kiểm chứng; không âm thầm đổi scientific config.

### C1 — preflight: audit → full validation → smoke
Lệnh dự kiến từ repo root (executable 3.12 được chọn ở C0):

```powershell
& '<python312.exe>' 'D:/Project/AgriFusion-IoT/AgriFusion_Local_Implementation_20261101 (1)/RUN_LOCAL.py' --repo D:/Project/AgriFusion-IoT --stage preflight --install-deps --download
```

- Download hai official archives được config chỉ rõ, lưu immutable checksum/provenance; không tải Firebase/Jena mới. Beijing dùng PM2.5 của 12 station files chính thức; Appliances dùng RH_1 và đủ sáu finite slots/giờ. Ghi missingness, hourly bins, raw IDs, timezone uncertainty.
- Audit bốn chronological partitions và actual cutpoints/assignments; train-only thresholds; duplicate/entity/time/dependency checks; segment tại real gaps; warmup 24. Missing raw không đổi thành F=0.
- Chạy full `validate` gồm suite không forecaster fits và legacy no-refit fixture checks. Gate: full_P2=true; counts R0..3 =5/4/1/0; returned solver witnesses hợp lệ và optimal values khớp DP. Timeout phải giữ đúng trạng thái, không gọi incumbent là optimum. Tests count có thể tăng nếu phải thêm regression cho bug thật.
- Chạy smoke bốn supervised toy fits (3 HGB+1 logistic); kiểm prefix train/development của nguồn đã audit, không tune theo selection/assessment. Gate: finite causal inputs, đúng cohort/model order, full-control bounds collapse, smoke READY đúng checksum.
- Kiểm hợp lệ cho từng source: hard gate là mọi partition có cohort và train có đủ classes; limited support khi selection hoặc assessment có <10 positive END episodes là cảnh báo vận hành, không phải theorem về sample size. Required fit sau masking cũng có thể fail support riêng seed.

### C2 — checkpoint preflight và quyền đi tiếp
- Mở STUDY_STATUS, RUN_INDEX, ACTIVE_GRAPH, ARTIFACT_INDEX, SOURCE_INDEX, audits, full validate test_results, smoke SUMMARY, snapshots, resolved config, exact commands/exit codes và launch receipts.
- Đối chiếu source+config+environment signature, không dùng Linux unit-only receipt làm P2 local. P2/smoke lỗi thì không main fit. Audit source lỗi thì giữ failed record; chỉ tiếp tục nguồn độc lập đủ gate, ghi rõ không hoàn thành full two-source plan.
- `report`/`export` của launcher tạo drive_sync. Export lại sau khi invocation kết thúc nếu cần thu receipt cuối; bootstrap_launches nằm ngoài export mặc định nên đính kèm launch receipts/logs có chọn lọc, không khẳng định exporter đã tự đưa chúng lên Drive.
- Đồng bộ checkpoint và xác minh remote IDs/bytes/checksums nếu API trả checksum. Không upload `_venv`, cache, credentials, raw archive lớn hoặc nén lại repo.
- Nếu duyệt toàn kế hoạch và gates đạt thì đi C3; nếu người dùng chỉ duyệt preflight thì dừng tại đây để review. Mọi thay đổi scientific scope vẫn cần duyệt riêng.

### C3 — main study giữ nguyên contract
```powershell
& '<python312.exe>' 'D:/Project/AgriFusion-IoT/AgriFusion_Local_Implementation_20261101 (1)/RUN_LOCAL.py' --repo D:/Project/AgriFusion-IoT --stage all
```

Launcher dùng `_venv` đã dựng; audit/validate/smoke lặp lại với resume cho exact matching units. Không gọi `--install-deps` lại giữa main nếu không cần vì environment fingerprint là một phần cache identity.

Scientific settings được đề xuất duyệt nguyên trạng:
- END_t=1 iff F[t-3:t-1] đều 1 và F[t]=0; F=1 iff recorded variable > q75 train theo entity; đây là operational reference, không physical truth.
- Split global unique recorded timestamps theo 60%/15%/12.5%/12.5%: train/development/selection/assessment, chung across entities; không refit sau selection.
- Sáu candidates: COMPLETE_HGB, SOFT_EM_HGB, MARKOV, CONSTANT, LOGISTIC_COMPLETE_H6, HGB_COMPLETE_H24. Không HPO/early stopping; ba train-mask seeds 11/22/33; 2 threads, một fit/orchestrator đồng thời; không GPU.
- Full control một lần + MCAR30, MCAR50, block30, MNAR-state ×5 mask seeds 11/22/33/44/55. Mỗi source×train-seed có21 cells; hai nguồn×ba seeds=126 cells, mỗi cell có selection và assessment, 15 pairs/period=3780 pair rows R0 nếu đủ support.
- Main tối đa24 supervised fits:18 HGB+6 logistic, ngoài Markov/constant và4 toy fits. Không đếm model seed/mask/site thành independent datasets.
- R sensitivity cho primary pair trên fixed predictions, grid0/1/2/3/4/8/16; **một budget chung cho toàn source+partition**, không budget mỗi segment. Corruption theo scope/grid đã config, không đổi probabilities khi tăng R.
- Generic MILP:16 predeclared solves nếu đủ hai nguồn;10 giây/solve là solver limit, không phải deadline cho whole study. Giữ status/incumbent/dual/gap/witness/runtime, không tự retry solver mạnh hơn hay bỏ timeouts để đẹp bảng.
- Giữ all fixed-model action baselines, development default, fallback, ties và uncertainty reasons; selection finite-pool regret và later assessment regret báo riêng.

### C4 — kiểm kết quả, checkpoint, bàn giao
- Kiểm đủ cases hoặc thiếu có lý do; same scored keys cho mọi method; finite probabilities, no current/future truth leakage; R0 full-control exact; joint bound containment/nesting; fixed probability hashes; solver witness/budget recheck.
- Giữ failed/limited-support attempts và return codes. Lỗi không được đổi thành complete; timeout/inconclusive là outcome hợp lệ theo contract. Xác minh full_plan_complete bằng actual ACTIVE_GRAPH, không chỉ exit0. Có đủ 126 evaluate +126 sensitivity +16 solves vẫn không tự chứng minh scientific adequacy.
- Đo wall time, disk và peak working set/process tree khi chạy trên Windows bằng giám sát ngoài computation, ghi cách đo; lane hiện chưa có phép đo peak RAM chuyên biệt. Chưa đo được thì unknown, không dựng số từ RAM máy.
- Export checkpoint đầy đủ vào Drive cùng thư mục kết quả; upload incremental theo manifest, giữ relative paths, thêm actual upload receipts. Chỉ nói upload thành công khi connector readback đạt; exporter local không tự chứng nhận remote.
- Cập nhật PROJECT_MAP/STATUS và cùng worklog này. Commit milestones source/integration fixes/docs theo scope; push từ branch không có private V9 ancestor, không push output/fixtures/secrets/venv. Không public manuscript hoặc tạo Release. Ghi hash/branch/push status rõ.

## Architectural Decisions
Không viết lại module hoặc trộn lane này vào production/external adapters cũ chỉ để reuse tên. Dependency direction: CLI→orchestration→source/preparation/fit/evaluation/sensitivity/solver; math/contracts độc lập; storage persistence/provenance; reporting/export downstream. Truth chỉ downstream audit sau khi decisions đã freeze. Named components là module có thể test riêng. Nếu phát hiện bug sẽ sửa nhỏ và thêm regression đúng invariant; thay target/split/feature information/candidate/R semantics phải quay lại hỏi trước.

## Progress Status
`requested`: khảo sát và lên kế hoạch. `proposed`: C0–C4 ở trên. `approved`: C0–C4 ngày 2026-11-01. `implemented locally`: đã cài lane/fixtures; CLI --help và installed hashes đạt. Python3.12.12 đã provision; preflight hoàn tất exit0 trong venv riêng; main bắt đầu theo approved gates. `verified locally`: integrity/AST/static compatibility, installed hashes, CLI và Python provisioning; full P2 và toy smoke đã đạt local; source hard gates đạt với Appliances limited_support. `historically tested`:28 tests của gói. `accepted`: chưa. Trong lượt này chỉ thêm worklog kế hoạch; không sửa application code hoặc gói đầu vào.

## Validation Commands and Results
- Read-only Get-Content/rg/git status/log, stdlib SHA256/JSON/AST inspection: kết quả ở Confirmed Facts.
- `py -0p`: không tìm thấy launcher; `uv python list --only-installed`: thấy3.13.9/3.13.5; Python dùng kiểm stdlib3.13.9.
- Đọc Get-CimInstance/Get-PSDrive để biết phần cứng/disk, không stress/benchmark.
- Chưa chạy INSTALL_LOCAL, RUN_LOCAL, pip/uv provisioning, pytest/unittest, validate/smoke/all, downloader hoặc Drive upload.

## Compatibility Impact
Đề xuất additive `csv_npz_v1`; không migrate persistent schema cũ. Templates và original package được giữ nguyên. Exact source snapshot quan trọng hơn commit vì repo dirty. Fingerprint chứa cả lane README/FLOW/JSON/TXT và imported parent bytes; finalize trước launch, cập nhật worklog ngoài lane không đổi lane fingerprint. Không sửa dependency/môi trường giữa run để tránh vô hiệu hóa cache âm thầm.

## Remaining Risks and Follow-up Work
Python/dependency Windows chưa validate; real-source support và runtime chưa đo; disk/export size có thể tăng. Full P2 không phải efficacy/novelty gate. Review chỉ tĩnh không chứng nhận numerical correctness toàn bộ implementation. Nếu manifest/conflict/import gate lỗi, dừng tích hợp liên quan, giữ evidence và so sánh trước sửa. Triển khai C0–C4 theo duyệt; dừng dependent work nếu gate không đạt.

## Progress Log
- 2026-11-01: người dùng duyệt triển khai local; lưu original tracked-file hashes ngoài repo trước tích hợp.
- C0 đạt: installer --check và install exit0,52 files created và worklog giữ nguyên;36 lane hashes khớp; Python3.12.12 installed. Safe source commit46bd89f đã push. External monitor ghi2-second sampled process-tree RSS, không gọi đó là exact continuous peak.
- C1: pip check đạt; official raw archived với hashes; Beijing scored train/development/selection/assessment=221516/51868/41362/45421, Appliances=1950/469/387/387. Local correctness28/28 đạt; đang chờ full legacy fixture gate.
- C1/C2 đạt: preflight489.80s gồm dựng venv/pip, audits, full validation và smoke/report/export. Local28 tests pass; full_P2=true; Jena5/4/1/0,20 MILP solves (14 optimal/6 time-limited), all returned witnesses valid và all optimal values match DP. Sampled RSS sum max508039168 bytes (không phải continuous physical peak). Main được phép chạy; không thay config/semantics.
- Delivery adapter: connector từ chối0-byte files và giới hạn100MiB/file. Giữ original export nguyên byte; gzip151127549-byte canonical.csv và130493831-byte canonical_before_audit.csv riêng, đưa empty originals vào ZERO_BYTE_FILES.zip; TRANSPORT_MANIFEST ghi original hashes/path và cách khôi phục. Main đã hoàn tất6 fit units=24 supervised fits và đang evaluate; scientific config giữ nguyên.
