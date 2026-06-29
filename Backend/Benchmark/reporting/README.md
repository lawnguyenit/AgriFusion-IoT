# Reporting

## Mục đích

`Backend/Benchmark/reporting` là namespace active cho phần tổng hợp artifact, biểu đồ và báo cáo benchmark.

Kiến trúc active hiện tại lấy `tabular_benchmark` làm family train real-only duy nhất, nên report active cũng bám theo 3 lane nhãn:

- `binary`
- `tri_class`
- `four_class`

## Input

- training artifact đã hoàn tất từ `tabular_benchmark`
- `training_report.json`
- `aggregate_model_metrics.csv`
- build manifest liên quan nếu cần truy vết dataset nguồn

## Output

Report active được chuẩn hóa theo:

- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\artifacts\binary\reports\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\artifacts\tri_class\reports\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\artifacts\four_class\reports\<run_id>\`
- `D:\AgriFusion-IoT\Backend\Benchmark\reporting\artifacts\chapter5_visual_reports\<run_id>\`

Artifact chính:

- `combined_model_metrics.csv`
- `summary_model_metrics.csv`
- `report_summary.md`
- `chart_test_macro_f1.png`
- `chart_test_accuracy.png`
- `report_manifest.json`

Artifact bổ sung cho Chương 5:

- `5_3_pipeline_counts\raw_source_counts.csv`
- `5_3_pipeline_counts\pipeline_overview_counts.csv`
- `5_3_pipeline_counts\chart_raw_source_counts.png`
- `5_3_pipeline_counts\chart_processed_stage_rows.png`
- `5_3_pipeline_counts\chart_pipeline_overview_infographic.png`
- `5_3_pipeline_counts\chart_prepared_rows_heatmap.png`
- `5_4_label_distributions\label_distribution_counts.csv`
- `5_4_label_distributions\chart_label_distribution_panels.png`
- `5_5_split_results\split_counts_focus_versions.csv`
- `5_5_split_results\chart_split_counts_focus_versions.png`
- `5_5_split_results\chart_excluded_gap_focus_versions.png`
- `5_5_split_results\chart_validation_test_class_support.png`
- `5_7_feature_source_analysis\feature_source_registry.csv`
- `5_7_feature_source_analysis\chart_feature_source_matrix.png`
- `5_7_feature_source_analysis\chart_test_macro_f1_v0_to_v3.png`
- `5_7_feature_source_analysis\chart_test_balanced_accuracy_v0_to_v3.png`
- `chapter5_visual_summary.md`
- `manifest.json`

## Command

Sinh report cho một training run theo lane:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\report.py --label-mode tri_class
```

Hoặc chỉ định thẳng training run:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\report.py --label-mode four_class --run-dir <training_run_dir>
```

Sinh visual pack riêng cho Chương 5:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\reporting\chapter5_visual_report.py
```

## Giả định

- chỉ artifact active từ `tabular_benchmark` mới tiếp tục được ghi report mới
- `context_benchmark` khong con la lane train active chinh, nhung van la family retained vi runtime FT va simulator sizing con doc artifact tu day
- mỗi lane nhãn có report root riêng để dễ so sánh `binary`, `tri_class`, `four_class`
- chapter5 visual pack đọc thêm artifact từ `benchmark_dataset/dataset` để dựng biểu đồ pipeline counts, label distributions và split coverage
- section `5.3` có thêm infographic overview để kể chuyện theo flow `Firebase raw -> aligned -> labeled -> binary collapse`, bên cạnh các chart cột/heatmap chi tiết
- các chart của chapter5 visual pack được tối ưu lại theo kiểu dễ đọc khi chèn vào Word: tiêu đề ngắn hơn, nhãn lớn hơn, ít nhiễu hơn và ưu tiên mạch kể chuyện của dữ liệu thực
- riêng `5.4` đang khóa theo snapshot báo cáo `01/04/2026-10/05/2026` để đồng nhất với số liệu đã chốt trong bản thảo Word, không bám trực tiếp artifact labeling mới hơn
- riêng `5.5` hiện chỉ hiển thị `v1-v2` để khớp với phạm vi benchmark đang giữ trong phần trình bày
- phần metric chính cho benchmark vẫn ưu tiên `test_macro_f1` và `test_balanced_accuracy`
- trong chapter5 visual pack, nhánh `binary` được hiển thị theo quy ước báo cáo `normal_context` / `non_normal_context`
- riêng `5.7`, chart chính hiện chỉ giữ `v1-v2` theo đúng phạm vi so sánh đặc trưng cửa sổ đã chốt; `v0` và `v3-v5` không còn xuất hiện trong hình metric chính

## Rủi ro / giới hạn hiện tại

- `generate_direct_profile_report.py` vẫn còn nằm trong `tabular_benchmark/` vì nó là profile report chuyên biệt cho evidence pack, chưa được gom hẳn về namespace này
- historical runs theo layout cũ vẫn cần fallback nếu có consumer đọc đối chiếu
- dữ liệu `tri_class` và `four_class` real-only đang lệch lớp mạnh, nên report cần được đọc cùng với phân bố lớp trong build/training artifact
- chapter5 visual pack hiện phải chịu thêm độ lệch tên file lịch sử giữa contract `benchmark_input_*` và artifact thực tế kiểu `flb_*`; script mới tự đọc qua manifest/report để giảm phụ thuộc vào tên file cứng
