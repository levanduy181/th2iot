# Bài thực hành 2 Thu thập lưu trữ và tiền xử lý dữ liệu IoT

Sinh viên: **Lê Văn Duy - B23DCAT074**. Học phần INT14149.

Hệ thống chạy trực tiếp trên Windows, **không dùng Docker**. Python chạy MQTT broker aMQTT, collector, tiền xử lý và ứng dụng Streamlit. MongoDB Community là tiến trình cơ sở dữ liệu riêng, do Python khởi động; dữ liệu chính được lưu trong MongoDB Time-Series, không thay bằng CSV hay SQLite.

## Chạy trên máy này

Mở thư mục `D:\PTIT\ki_1_nam_4\iot\th\th2\iot_lab2` trong VS Code. Mở Terminal PowerShell:

```powershell
.\.venv\Scripts\python.exe run.py
```

Mở <http://127.0.0.1:8502>. Nếu báo cổng đang dùng, hệ thống có thể đang chạy từ lần trước; mở địa chỉ này trước khi khởi động thêm. Dừng bằng Ctrl+C trong terminal đã chạy `run.py`.

Nếu hệ thống đang chạy nền hoặc còn collector cũ, dừng bằng `.\.venv\Scripts\python.exe run.py --stop`. Lệnh nhận diện các dịch vụ qua thư mục làm việc và lệnh chạy của dự án, rồi dừng cả cây tiến trình, kể cả Python con do môi trường ảo Windows tạo ra. Không chỉ dựa vào file PID của lần chạy trước. Không chạy thêm `collector.py` khi đã chạy `run.py`.

`run.py` kiểm tra cả cổng đã bind nhưng chưa listen, chờ collector và dashboard khởi động trước khi báo Ready. Để kiểm tra lỗi tiến trình sót lại trên Windows, chạy `python scripts/check_lifecycle.py` khi không có phiên bài đang chạy; script khởi động/dừng toàn bộ hệ thống hai lần và kiểm tra các cổng đã được giải phóng.

Để chạy bằng lệnh `python`, chọn interpreter `.venv/Scripts/python.exe` trong VS Code rồi mở terminal mới, hoặc dùng:

```powershell
.\.venv\Scripts\Activate.ps1
python run.py
```

Nếu PowerShell chặn Activate.ps1, dùng đường dẫn `.venv\Scripts\python.exe` như trên, không cần đổi chính sách hệ thống. Menu Terminal > Run Task có sẵn các tác vụ chạy bài và kiểm thử.

## Cài trên máy khác

Dùng Windows x64, Python **3.12** và kết nối Internet cho lần cài đầu. MongoDB portable cần khoảng 756 MiB tải xuống; cài đặt giữ lại các file chạy, loại bỏ debug symbols. Không cần tài khoản cloud, token ThingsBoard hay quyền quản trị.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_local.py
.\.venv\Scripts\python.exe run.py
```

`setup_local.py` tải MongoDB 8.0.17 từ máy chủ chính thức và đối chiếu SHA256. Không cài Windows service. Dữ liệu nằm trong `data/mongo`; log ở `data/logs`. Cấu hình nằm trong `config.json`; bộ khởi động dùng cổng cố định 1884, 1885 (khóa collector), 27018 và dashboard 8502.

## Chạy bằng dữ liệu kiểm thử Python

Giữ `run.py` đang chạy. Mở terminal thứ hai:

```powershell
.\.venv\Scripts\python.exe demo.py
```

Mặc định 60 mẫu, cách nhau 5 giây. Chọn nguồn **Python kiểm thử** trên dashboard. Có thể chạy nhanh với `--count 60 --interval 1`. Đây là dữ liệu được Python sinh và gửi qua broker MQTT thật, không phải dữ liệu ESP32. Script chủ động bỏ sequence 22; gửi trùng sequence 10; cho humidity=null ở 12; temperature=78 ở 18; distance=900 ở 30; gửi 3 bản tin không hợp lệ. Mọi bản tin mang `source=test` và `boot_id` riêng.

Sau khi demo kết thúc:

```powershell
.\.venv\Scripts\python.exe verify_run.py
.\.venv\Scripts\python.exe -m pytest -q
```

Kết quả thực đo được ghi vào `output/verification.json`, `telemetry_raw.csv`, `telemetry_processed.csv`. Script kiểm chứng sẽ báo lỗi nếu số bản ghi, trùng lặp, giá trị thiếu hoặc retention không đúng. Bảng trong báo cáo lấy từ các file này.

## Chạy bằng ESP32 Wokwi

1. Chạy `run.py` và giữ nguyên cửa sổ này.
2. Mở thư mục `firmware` trong một cửa sổ VS Code khác; dùng PlatformIO Build.
3. Chạy lệnh **Wokwi: Start Simulator**. Wokwi VS Code có Private IoT Gateway; firmware kết nối `host.wokwi.internal:1884` để tới broker trên máy. Không dùng `localhost` trong firmware. Wokwi trên website với Public Gateway không truy cập được broker loopback này.
4. Serial cần có `MQTT ... OK` rồi JSON `publish=OK`. Firmware chờ NTP để có timestamp UTC. Nếu NTP chưa đồng bộ, Serial thông báo và bỏ mẫu.
5. Trên dashboard chọn nguồn **ESP32 Wokwi**. Đổi DHT22 qua 25/50, 30/70, 18/35 và HC-SR04 qua 10, 50, 100, 200 cm. Dữ liệu gửi mỗi 5 giây; dashboard làm mới mỗi 5 giây.
6. Chụp dashboard và Serial để bổ sung bằng chứng ESP32. Số liệu kiểm thử Python trong báo cáo không thay thế phép đo từ Wokwi.

Giữ chân DHT=21, TRIG=5, ECHO=18, LED=23 của bài 1. `merge_firmware.py` chỉ ghép firmware sau build. Firmware không dùng access token ThingsBoard. `PubSubClient.publish` dùng QoS 0: trả về OK không phải xác nhận đã lưu vào database. Sequence tăng theo lần lấy mẫu; mất kết nối có thể làm mất mẫu và tạo khoảng nhảy sequence. Mỗi khởi động tạo `boot_id` mới, nên không nhầm sequence reset với trùng lặp.

## Kiến trúc và schema

```text
ESP32 Wokwi hoặc demo.py
    -> aMQTT (127.0.0.1:1884)
    -> collector.py -> SQLite inbox bền vững
    -> MongoDB sensor_raw (Time-Series, retention 7 ngày)
    -> preprocess.py (mỗi 5 giây)
    -> MongoDB sensor_processed
    -> app.py / Streamlit (127.0.0.1:8502)
```

`sensor_raw` có `timeField=timestamp`, `metaField=meta`, `granularity=seconds`, `expireAfterSeconds=604800`. Metadata gồm `device_id`, `boot_id`, `source`; fields gồm các cảm biến, RSSI, sequence, uptime và thời điểm nhận. MongoDB tự tạo chỉ mục metadata/thời gian; chương trình thêm chỉ mục `event_id` để tìm lại bản tin. MongoDB Time-Series không hỗ trợ unique index: collector duy nhất được khóa bằng socket, dùng SQLite khóa chính event_id và kiểm tra MongoDB trước khi thử ghi lại. Lớp đọc cũng loại trùng event_id để phòng ghi mơ hồ; không tuyên bố bảo đảm exactly-once phân tán.

`sensor_processed` là collection thường có `_id` xác định từ phiên và mốc cửa sổ, ghi bằng upsert. Thiết kế này cho phép cập nhật kết quả khi nội suy có thêm mẫu và không nhân đôi khi chạy lại. Collection này cũng có TTL 7 ngày. SQLite là bộ đệm và sổ nhận, không phải database time-series chính. Dữ liệu đã ghi trong inbox và sự kiện được dọn sau 7 ngày; bản tin đang chờ chưa bị xóa tự động. File SQLite có thể cần VACUUM khi muốn thu hồi dung lượng vật lý. MQTT broker trong RAM không có lưu hàng đợi bền vững sau khi broker khởi động lại.

JSON: `device_id`, `boot_id`, `source`, `timestamp_ms` (UTC epoch ms), `sequence`, `uptime_s`, `rssi`, `temperature`, `humidity`, `distance_cm`. Cảm biến bị lỗi gửi `null`; chuỗi "NaN", infinity, JSON sai, thông tin nhận dạng sai bị từ chối. Giá trị số hữu hạn ngoài miền được giữ trong raw và gắn cờ khi xử lý để còn bằng chứng outlier.

## Tiền xử lý

- Chia theo thiết bị, nguồn và phiên khởi động để không nội suy xuyên lần reset.
- Gắn cờ ngoài miền: nhiệt độ [-40,80], độ ẩm [0,100], khoảng cách [2,400].
- IQR với hệ số 1.5, ít nhất 8 mẫu và IQR khác 0. IQR tính theo phiên trong khoảng đọc; có thể đánh dấu nhầm biến đổi thật và cần điều chỉnh theo ứng dụng.
- Resampling trung bình mỗi 10 giây. Giữ sample_count và cờ chất lượng.
- Chỉ nội suy các khoảng thiếu nằm giữa dữ liệu, dài tối đa 2 cửa sổ. Giữ NaN ở đầu/cuối và khoảng thiếu dài.
- Rolling mean 3 cửa sổ, delta giữa 2 cửa sổ liên tiếp, chuẩn hóa Min-Max bằng miền vật lý cố định.
- Lưu kết quả vào collection mới, không ghi đè dữ liệu gốc. Job mặc định xử lý lại 60 phút gần nhất; dùng `--minutes` để backfill lâu hơn, tránh coi cửa sổ ở biên truy vấn là kết quả ổn định vĩnh viễn.

## Độ trễ và giới hạn

Độ trễ nhận đến lưu = thời điểm nhận ACK thành công từ MongoDB trừ thời điểm Python nhận MQTT. Độ trễ publisher đến lưu dùng timestamp của bản tin; chỉ đáng tin khi đồng hồ đồng bộ. Kiểm thử Python dùng chung đồng hồ máy nên tránh sai lệch giữa thiết bị. Wokwi/NTP có thể lệch hoặc chạy chậm hơn thời gian thực, nên cần kiểm tra riêng. Dashboard còn có độ trễ làm mới và truy vấn, không nằm trong chỉ số publisher-to-DB.

Các cổng chỉ mở loopback cho bài thực hành. Không có TLS/auth tại broker và MongoDB cục bộ; không đổi sang 0.0.0.0 để công khai. Khi triển khai thật cần xác thực, TLS, hàng đợi MQTT bền vững và theo dõi dung lượng inbox.

## Nộp bài

Nộp firmware, các script Python, requirements, cấu hình, README, báo cáo Word trong `output`, CSV và ảnh kết quả. Không đưa `.venv`, `.runtime`, `data`, `.pio` lên GitHub. Chưa tự đẩy GitHub vì chưa có repository đích. Có thể giải nén gói mã nguồn được cung cấp rồi đưa vào repository của bạn.

## Tài liệu tham khảo

- Đề Bài thực hành số 2 IoT, mục 3–7.
- MongoDB Time-Series: https://www.mongodb.com/docs/manual/core/timeseries-collections/
- MongoDB Time-Series limitations: https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/
- aMQTT: https://amqtt.io/
- Paho MQTT Python: https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html
- Wokwi VS Code: https://docs.wokwi.com/vscode/project-config
