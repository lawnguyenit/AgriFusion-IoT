document.getElementById('dropZone').addEventListener('click', () => document.getElementById('fileInput').click());
document.getElementById('fileInput').addEventListener('change', (e) => handleFile(e.target.files[0]));

function handleFile(file) {
    if (!file) return;
    const reader = new FileReader();
    const ext = file.name.split('.').pop().toLowerCase();

    reader.onload = (e) => {
        document.getElementById('fileInfo').innerText = `Đã tải: ${file.name}`;
        const content = e.target.result;
        const area = document.getElementById('reportArea');
        area.style.display = 'block';
        area.innerHTML = '';

        if (ext === 'csv') {
            processCSV(content, file.name, area);
        } else if (ext === 'json' || ext === 'jsonl') {
            processJSON(content, file.name, area);
        } else {
            area.innerHTML = '<div class="data-group"><h2>Lỗi</h2><p>Định dạng không được hỗ trợ.</p></div>';
        }
    };
    reader.readAsText(file);
}

// =========================================================
// BỘ XỬ LÝ 1: MA TRẬN CSV (Ép kiểu 1 dòng thành Báo Cáo như JSON)
// =========================================================
function processCSV(content, fileName, area) {
    // 1. Chẻ nhỏ tệp CSV
    const rows = content.split('\n').filter(r => r.trim());
    if(rows.length < 2) {
        area.innerHTML = '<div class="data-group"><h2>Lỗi</h2><p>Tệp CSV không có dữ liệu.</p></div>';
        return;
    }

    // 2. Chỉ lấy đúng Tiêu đề và Dòng dữ liệu ĐẦU TIÊN
    const headers = rows[0].split(',').map(h => h.trim());
    const firstRow = rows[1].split(',').map(v => v.trim()); 

    // 3. Chuẩn bị các "Túi" chứa dữ liệu
    const envData = {}; 
    const sysData = {};
    const configData = {};

    // 4. Từ khóa phân loại (Đã bổ sung actuator, pump, fan của tệp CSV đồ án m)
    const sysKeywords = ['date', 'time', 'id', 'seen', 'health', 'battery'];
    const configKeywords = ['actuator', 'pump', 'fan', 'relay', 'on', 'off', 'addr', 'sda', 'scl', 'ms', 'limit', 'count', 'streak', 'baud', 'pin', 'timeout', 'delay', 'error', 'retry', 'valid', 'ok', 'version', 'wifi', 'ready', 'rssi'];

    // 5. Băm dòng 1 và nhét vào đúng "Túi"
    headers.forEach((h, i) => {
        let val = firstRow[i] !== undefined ? firstRow[i] : '-';
        let keyLower = h.toLowerCase();

        if (configKeywords.some(kw => keyLower.includes(kw))) {
            configData[h] = val; // Trạng thái bơm, quạt, chân cắm...
        } else if (sysKeywords.some(kw => keyLower.includes(kw))) {
            sysData[h] = val; // Thời gian đo...
        } else {
            envData[h] = val; // Nhiệt độ, Độ ẩm, NPK...
        }
    });

    // 6. Vẽ giao diện y hệt JSON Layer 1
    let html = `
        <div class="data-group" style="border-left: 5px solid #10b981;">
            <h2>📄 Phân tích Bản ghi CSV Mẫu (#1)</h2>
            <p style="color: #64748b; font-size: 0.9rem; margin-top: -10px; margin-bottom: 0;">
                Tệp <strong>${fileName}</strong> có tổng cộng ${rows.length - 1} dòng. Hệ thống chỉ trích xuất dòng đầu tiên để hiển thị cấu trúc.
            </p>
        </div>

        <div class="data-group"><h2>🌍 Dữ liệu Môi trường (Cảm biến)</h2>
            <div class="kv-grid">${Object.keys(envData).length > 0 ? buildKV(envData) : '<div class="kv-item">Trống</div>'}</div>
        </div>
        
        <div class="data-group"><h2>⚙️ Thời gian & Hệ thống</h2>
            <div class="kv-grid">${Object.keys(sysData).length > 0 ? buildKV(sysData) : '<div class="kv-item">Trống</div>'}</div>
        </div>
        
        <div class="data-group"><h2>🔧 Chấp hành & Cấu hình (Actuators/Configs)</h2>
            <div class="kv-grid">${Object.keys(configData).length > 0 ? buildKV(configData, 'config-item') : '<div class="kv-item">Trống</div>'}</div>
        </div>
    `;
    
    area.innerHTML = html;
}

// =========================================================
// BỘ XỬ LÝ 2: JSON LAYER 1 & LAYER 2 (Giữ nguyên độ sắc bén)
// =========================================================
function processJSON(content, fileName, area) {
    try {
        let jsonContent = fileName.endsWith('.jsonl') ? content.split('\n')[0] : content;
        const json = JSON.parse(jsonContent);

        if (json.record) {
            renderLayer1(json, area);
        } else if (json.layer === "layer2" || json.schema_version) {
            renderLayer2(json, area);
        } else {
            area.innerHTML = '<div class="data-group"><h2>Lỗi cấu trúc</h2><p>Không nhận diện được định dạng tệp Layer 1 hay Layer 2.</p></div>';
        }
    } catch (err) {
        area.innerHTML = '<div class="data-group"><h2>Lỗi đọc tệp JSON!</h2></div>';
        console.error(err);
    }
}

function renderLayer1(json, area) {
    const dataNode = json.record.payload || json.record;
    const health = json.record.health || {};
    const sysData = dataNode.system_data || dataNode.system || {};

    const envData = {}; const configData = {};
    const configKeywords = ['addr', 'sda', 'scl', 'ms', 'limit', 'count', 'streak', 'baud', 'pin', 'timeout', 'delay', 'error', 'retry', 'valid', 'ok', 'version', 'wifi', 'ready', 'rssi'];

    Object.keys(dataNode).forEach(key => {
        if (['_meta_seed', 'event_meta', 'health', 'fallback_used', 'payload', 'system_data', 'system'].includes(key)) return;

        const val = dataNode[key];
        if (typeof val === 'object' && val !== null) {
            for (let [k, v] of Object.entries(val)) {
                if (configKeywords.some(kw => k.toLowerCase().includes(kw))) configData[k] = v; else envData[k] = v;
            }
        } else {
            if (configKeywords.some(kw => key.toLowerCase().includes(kw))) configData[key] = val; else envData[key] = val;
        }
    });

    area.innerHTML = `
        <div class="data-group"><h2>🌍 Dữ liệu Môi trường (Layer 1 - Thô)</h2>
            <div class="kv-grid">${Object.keys(envData).length > 0 ? buildKV(envData) : '<div class="kv-item">Chưa có thông số môi trường</div>'}</div>
        </div>
        <div class="data-group"><h2>⚙️ Trạng thái Hệ thống & Sức khỏe</h2>
            <div class="kv-grid">${buildKV(sysData)}${buildKV(health.overall || health.npk || {})}</div>
        </div>
        <div class="data-group"><h2>🔧 Cấu hình Phần cứng (Configs)</h2>
            <div class="kv-grid">${buildKV(configData, 'config-item')}</div>
        </div>
    `;
}

function renderLayer2(json, area) {
    let html = `
        <div class="data-group"><h2>📡 Thông tin Định danh (${json.sensor_type || json.agent_name})</h2>
            <div class="kv-grid">${buildKV({"Thời gian": json.source?.date_key, "Agent": json.agent_name, "Health Status": json.health?.status, "AI Summary": json.inference_hints?.summary})}</div>
        </div>
        <div class="data-group"><h2>🌱 Dữ liệu Tức thời (Perception)</h2>
            <div class="kv-grid">${buildKV(json.perception || {})}</div>
        </div>
    `;

    const windows = json.memory?.windows;
    if (windows) {
        html += `<div class="data-group"><h2>🕒 Phân tích Lát cắt Thời gian (Window Slices)</h2>`;
        for (let [winName, metrics] of Object.entries(windows)) {
            html += `<h3 style="color:#0f172a; margin-top: 25px; border-left: 4px solid #2563eb; padding-left: 10px;">Lát cắt ${winName.toUpperCase()}</h3>
            <div class="table-responsive" style="max-height: unset; overflow-x: auto;">
                <table style="min-width: 600px;">
                    <thead><tr><th>Đại lượng</th><th>Hiện tại</th><th>Trung bình</th><th>Thấp nhất</th><th>Cao nhất</th><th>Xu hướng</th></tr></thead><tbody>`;
            for (let [metricName, stats] of Object.entries(metrics)) {
                html += `<tr><td style="font-weight:bold; color:#2563eb; position:static;">${metricName}</td>
                            <td>${stats.current !== undefined ? stats.current : '-'}</td><td>${stats.avg !== undefined ? stats.avg : '-'}</td>
                            <td>${stats.min !== undefined ? stats.min : '-'}</td><td>${stats.max !== undefined ? stats.max : '-'}</td>
                            <td>${stats.trend === 'rising' ? '📈 Tăng' : stats.trend === 'falling' ? '📉 Giảm' : '➖ Ngang'} <br><small style="color:#64748b">(${stats.delta_from_start > 0 ? '+' : ''}${stats.delta_from_start || 0})</small></td></tr>`;
            }
            html += `</tbody></table></div>`;
        }
        html += `</div>`;
    }
    area.innerHTML = html;
}

function buildKV(obj, extraClass = '') {
    if (!obj) return '';
    return Object.entries(obj).map(([k, v]) => `<div class="kv-item ${extraClass}"><span class="kv-key">${k.replace(/_/g, ' ')}</span><span class="kv-val">${typeof v === 'object' ? JSON.stringify(v) : v}</span></div>`).join('');
}