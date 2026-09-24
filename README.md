# CapCut Draft Studio 0.4.2

Tool tạo draft CapCut tự động từ thư mục audio/video/ảnh đánh số — và từ bản
0.4.0 thì **render thẳng ra file mp4** luôn được, không cần mở CapCut.

Chạy trên **Windows** và **macOS**, có bộ cài riêng cho từng hệ và tự kiểm tra
bản mới qua GitHub Releases.

Bản **clean-room reimplementation**: code được viết mới dựa trên hành vi quan
sát được và API công khai của `pycapcut`, không chứa bytecode hay source trích
nguyên văn từ file gốc.

---

## Cài đặt

### Cách 1 — dùng bộ cài (khuyến nghị)

Vào tab **Releases** của repo, tải file hợp với máy bạn:

| Hệ điều hành | File | Ghi chú |
|---|---|---|
| Windows | `CapCutDraftStudio-x.y.z-windows-setup.exe` | Đã kèm sẵn ffmpeg, cài xong là dùng được ngay |
| macOS | `CapCutDraftStudio-x.y.z-macos.dmg` | Cần chạy thêm `brew install ffmpeg` một lần nếu muốn render |

Cách tạo repo và để GitHub tự build hai file này: xem
[`HUONG-DAN-GITHUB.md`](HUONG-DAN-GITHUB.md).

Hai bộ cài chưa được ký số nên Windows SmartScreen hoặc Gatekeeper của macOS sẽ
cảnh báo ở lần mở đầu tiên — đây là hiện tượng chung của mọi app không mua
chứng chỉ ký số, không phải virus.

### Cách 2 — chạy từ mã nguồn

**Windows**: cài Python 3.10–3.12 bản 64-bit (nhớ tick *Add Python to PATH* và
giữ mục *tcl/tk and IDLE*), rồi nhấp đúp `install.bat` một lần, sau đó nhấp đúp
`run.bat`.

**macOS / Linux**:

```bash
./scripts/install.sh      # tạo .venv và cài thư viện
./scripts/run.sh          # mở tool
```

### Cách 3 — tự build bộ cài trên máy Windows của bạn

Nhấp đúp `BUILD_EXE.bat`, đợi 1–3 phút, kết quả nằm ở `dist\`. Build lỗi thì
mọi chi tiết được ghi vào `build.log` cạnh nó.

---

## Giao diện

Cột trái là thanh điều hướng 5 trang; thanh dưới cùng luôn hiển thị tiến trình
và hai nút **KIỂM TRA** / **TẠO PROJECT**.

| Trang | Nội dung |
|---|---|
| **Tổng quan** | 3 đường dẫn bắt buộc (có huy hiệu báo hợp lệ), tên project, khung hình, FPS, hiệu ứng ảnh, bật/tắt từng chức năng, nhật ký tô màu theo mức |
| **Cài đặt** | Một trang, năm tab: *Cảnh quay*, *Nhạc nền*, *Hiệu ứng SFX*, *Phụ đề*, *Nâng cao* |
| **Render video** | Cài đặt xuất, hàng đợi render nhiều project, phần trăm và thời gian còn lại |
| **Preset kênh** | Lưu nhiều bộ cài đặt kênh; danh sách project gần đây |
| **Hướng dẫn** | Cấu trúc thư mục và quy trình, đọc được ngay trong app |

### Quy trình

1. Chọn **Folder VIDEO**, **Folder KÊNH**, **Folder CapCut Drafts**, đặt tên project.
2. Sang **Cài đặt** gán vai trò nhạc và SFX, chọn nguồn phụ đề, chỉnh khoảng nghỉ.
3. Bấm **KIỂM TRA** → mở *Cài đặt → Cảnh quay* soát lại từng cảnh.
4. Hết cảnh lỗi thì bấm **TẠO PROJECT**. Có thể bấm **Dừng** giữa chừng.
5. Mở CapCut Desktop (draft đã nằm sẵn trong danh sách), hoặc sang **Render
   video** để lấy luôn file mp4.

---

## Mới ở 0.4.0

### Khoảng nghỉ giữa các cảnh

*Cài đặt → Nâng cao → Nhịp hội thoại*. Mặc định **0.40 giây**.

Trước đây các file audio nối liền nhau làm lời thoại nghe như máy đọc. Giờ sau
mỗi cảnh có một quãng lặng, và **hình của cảnh đó được kéo dài để lấp chỗ
trống** nên không bao giờ bị đen màn.

Đặt về `0.00` là quay lại đúng cách dựng của các bản trước.

Lưu ý: khoảng nghỉ làm mỗi ô thời gian dài thêm, nên một video vốn vừa khít có
thể phải làm chậm hơn, hoặc rơi sang dùng ảnh. Cột **Nghỉ** trong bảng *Cảnh
quay* cho biết từng cảnh nghỉ bao lâu.

### Âm lượng tiếng gốc của video

*Cài đặt → Nâng cao*. Hệ số nhân, mặc định `1.00` (giữ nguyên như bản cũ),
đặt `0.00` để tắt hẳn tiếng của file video.

### Bóng đổ phụ đề

*Cài đặt → Phụ đề → Bóng đổ chữ*. Mặc định **bật, độ mờ 90%**, đổ chéo xuống
phải. Tool ghi bóng theo **cả hai schema** mà các bản CapCut khác nhau đang đọc
(`shadow_*` ở cấp material và `content.styles[0].shadows`) nên bản nào cũng
hiện. Bản render mp4 cũng có bóng tương ứng.

### Render video ngay trong tool

Trang **Render video**, chọn một trong hai engine:

| Engine | Ưu | Nhược |
|---|---|---|
| **ffmpeg** (mặc định) | Không cần mở CapCut, chạy hàng loạt, % và thời gian còn lại thật, chạy cả Windows lẫn macOS | Chuyển cảnh và kiểu chữ là bản mô phỏng, không giống CapCut 100% |
| **CapCut** | File ra đúng y CapCut xuất | Chỉ Windows, không được đụng chuột trong lúc chạy, và tool phải đóng CapCut rồi mở lại để nó thấy draft mới |

Engine CapCut tự tìm `CapCut.exe`, tự đóng và mở lại CapCut, tự chọn project,
bấm Export và chờ xong. Nhận diện cửa sổ dựa vào **tên lớp cửa sổ + tên tiến
trình**, không dựa vào tiêu đề — bản `pycapcut` gốc so tiêu đề đúng bằng chuỗi
tiếng Trung `"CapCut专业版"` nên không bao giờ chạy được với CapCut quốc tế.

Khi không chạy, bấm **Chẩn đoán CapCut** ở trang Render: tool liệt kê CapCut.exe
tìm thấy ở đâu, tiến trình nào đang chạy và mọi cửa sổ đang mở, rồi chép vào
clipboard để gửi đi nhờ sửa.

Render hàng loạt: bấm **Thêm nhiều folder…** rồi chọn thư mục **cha** chứa
nhiều folder VIDEO — mỗi thư mục con có `Audio/` thành một việc trong hàng đợi.

Cách engine ffmpeg dựng lại video, theo đúng thứ tự:

1. render từng cảnh (scale, tốc độ, Ken Burns) ra clip tạm;
2. ghép các clip bằng `xfade` — phần đuôi thêm ở bước 1 vừa đúng bằng thời
   lượng chuyển cảnh nên **tổng thời lượng không đổi**, tiếng và hình không lệch;
3. dựng riêng từng đường tiếng: giọng đọc, tiếng gốc video, nhạc nền, SFX;
4. trộn lại, chèn claim + logo, ghi phụ đề lên hình.

### Tự cập nhật

Tool kiểm tra bản mới trên GitHub Releases khi mở (tắt được ở *Cài đặt → Nâng
cao*). File tải về **chỉ được chạy khi SHA-256 khớp đúng** bảng băm
`SHA256SUMS.txt` công bố kèm bản phát hành — không khớp thì tool tự xoá file.
Bản phát hành thiếu bảng băm bị coi như không có bản cập nhật.

---

## Cấu trúc thư mục đầu vào

```text
VIDEO_FOLDER/
  Audio/     1.mp3, 2.mp3, …     ← bắt buộc, quyết định số cảnh
  Videos/    1.mp4, 2.mp4, …     ← tùy chọn
  Images/    1.jpg, 2.jpg, …     ← ảnh dự phòng khi video lỗi / quá ngắn
  Texts/     1.txt, 2.txt, …     ← lời thoại từng cảnh
  _manifest.json                 ← tùy chọn, ưu tiên cao nhất cho phụ đề

CHANNEL_FOLDER/
  Logo/                          ← logo.png
  Text Claim/                    ← claim.png hoặc "text claim.png"
  BGM/                           ← nhạc nền; file tên impact.* dùng làm impact
  SFX/                           ← hiệu ứng riêng của kênh
  channel-settings.json          ← tạo khi bấm "Lưu cài đặt kênh"
```

Tên file phải là **số thuần** (`1.mp3`, `02.mp4`…). Số của audio quyết định
cảnh đó lấy video/ảnh nào.

---

## Hiệu ứng ảnh (Ken Burns)

Ô **Hiệu ứng ảnh** ở trang Tổng quan chỉ áp dụng cho các cảnh dùng **ảnh tĩnh**,
không đụng tới cảnh dùng video.

| Lựa chọn | Ý nghĩa |
|---|---|
| **Ngẫu nhiên (không lặp liền kề)** | Mỗi cảnh bốc một hiệu ứng bất kỳ, nhưng không bao giờ trùng với cảnh ngay trước đó |
| **Luân phiên theo thứ tự** | Chạy vòng lần lượt qua đủ 8 hiệu ứng |
| Một hiệu ứng cụ thể | Mọi cảnh ảnh đều dùng đúng hiệu ứng đó |
| **Tắt hiệu ứng** | Ảnh đứng yên hoàn toàn |

Kho có 8 hiệu ứng: phóng to dần, thu nhỏ dần, trượt trái, trượt phải, trượt lên,
trượt xuống, phóng to + trượt chéo, thu nhỏ + trượt chéo.

Các hiệu ứng có trượt đều được phóng nhẹ **1.12 lần** trong suốt cảnh, để ảnh
luôn dư viền mà trượt — không lộ mép đen ở rìa khung hình. Muốn đổi mức phóng
hoặc thêm hiệu ứng mới, sửa `capcut_draft_studio/animations.py`; bản render
ffmpeg tự đọc lại đúng thông số đó.

---

## Cách tool chọn chế độ cho mỗi cảnh

| Chế độ | Khi nào |
|---|---|
| **Cắt** | Video dài hơn hoặc bằng *giọng đọc + khoảng nghỉ* → cắt bớt phần thừa |
| **Chậm** | Video ngắn hơn nhưng tốc độ cần dùng vẫn ≥ *Tốc độ chậm tối thiểu* |
| **Ảnh** | Video quá ngắn hoặc lỗi → dùng ảnh cùng số + hiệu ứng Ken Burns |
| **Nhanh** | Khi tắt *Cắt video*: video dài bị tăng tốc cho vừa giọng đọc |

---

## Lưu ý tương thích

- Nên **đóng CapCut** trong lúc tool ghi draft. Tool cảnh báo nếu phát hiện
  CapCut đang chạy (kiểm tra được trên cả Windows và macOS).
- `pycapcut 0.0.3` là thư viện beta và format draft CapCut đổi theo phiên bản.
  Nếu CapCut mới báo *media inaccessible / relink*, cần cập nhật adapter
  `draft_meta_info.json` theo schema của phiên bản đang dùng.
- Engine **CapCut** của trang Render chỉ chạy trên Windows và chỉ tự động hoá
  tốt với CapCut bản 6 trở xuống.
- Bản render bằng ffmpeg là bản **dựng lại**, không phải bản CapCut xuất ra.

---

## File cấu hình tool sinh ra

Tool ghi dữ liệu vào **thư mục cài đặt** khi thư mục đó ghi được (bản portable,
chạy từ mã nguồn). Khi cài vào `C:\Program Files` hoặc `/Applications` — là nơi
Windows/macOS **cấm ghi** với tài khoản thường — tool tự chuyển sang:

| Hệ điều hành | Thư mục dữ liệu |
|---|---|
| Windows | `%LOCALAPPDATA%\CapCutDraftStudio` |
| macOS | `~/Library/Application Support/CapCutDraftStudio` |
| Linux | `~/.local/share/CapCutDraftStudio` |

Đường dẫn thật được in ra dòng đầu của nhật ký mỗi lần mở tool.

| File / thư mục | Vai trò |
|---|---|
| `tool-config.json` | Trạng thái lần dùng gần nhất (đường dẫn, theme, chức năng) |
| `presets/*.json` | Các preset kênh đã lưu |
| `recent-projects.json` | Lịch sử project gần đây |
| `assets/sfx-library/` | Thư viện SFX dùng chung |
| `assets/sub-styles/` | Style phụ đề đã nhập từ CapCut |
| `bin/` | ffmpeg + ffprobe đi kèm bộ cài Windows |
| `updates/` | Bộ cài tải về khi tự cập nhật |
| `crash.log` | Chỉ sinh ra nếu bản đóng gói lỗi lúc khởi động — gửi file này khi app không mở được |
| `build.log` | Nhật ký của `BUILD_EXE.bat` — gửi file này khi build lỗi |

---

## Chạy test

```bash
pip install -r requirements.txt pytest
pytest tests -q                 # 86 test, không cần ffmpeg

# kiểm tra render thật (cần ffmpeg):
python tests/manual_render_check.py <thư-mục-project> 0.4

# kiểm tra giao diện dựng được ở cả 2 theme (Linux, cần Xvfb):
Xvfb :99 -screen 0 1440x920x24 &
DISPLAY=:99 python tests/smoke_gui.py shots
```
