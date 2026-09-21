# Đưa tool lên GitHub để tự build bộ cài và tự cập nhật

Làm một lần duy nhất. Sau đó mỗi lần muốn phát hành bản mới, bạn chỉ cần gõ
đúng 3 dòng lệnh ở phần **Phát hành bản mới** cuối trang này.

Máy GitHub sẽ tự build hộ bạn:

* **Windows** — bộ cài `CapCutDraftStudio-x.y.z-windows-setup.exe` (đã kèm sẵn
  ffmpeg, người dùng không phải cài gì thêm),
* **macOS** — file `CapCutDraftStudio-x.y.z-macos.dmg`,
* **SHA256SUMS.txt** — bảng mã kiểm tra. Tool chỉ chịu tự cập nhật khi file tải
  về khớp đúng bảng này, nên đừng xoá file đó khỏi bản phát hành.

---

## Bước 1 — Cài Git (nếu máy chưa có)

Tải ở <https://git-scm.com/download/win>, cài với toàn bộ tuỳ chọn mặc định.

Mở **Command Prompt** và kiểm tra:

```
git --version
```

Hiện ra số phiên bản là được.

## Bước 2 — Tạo repo trống trên GitHub

1. Đăng nhập <https://github.com> → góc phải trên bấm **+** → **New repository**.
2. **Repository name**: `CapCutDraftStudio`
3. Chọn **Private** (chỉ mình bạn thấy) hoặc **Public** — cả hai đều dùng được.
4. **KHÔNG** tích "Add a README file", "Add .gitignore", "Choose a license".
5. Bấm **Create repository**.

Ghi lại đường dẫn repo, dạng:

```
https://github.com/<tên-tài-khoản>/CapCutDraftStudio
```

## Bước 2b — Kiểm tra không có file nặng trong thư mục tool

GitHub **chặn mọi file trên 100 MB**. Nhạc nền, video, giọng đọc của bạn
thường nặng hơn thế nhiều, và repo code cũng không phải chỗ để chứa chúng.

File `.gitignore` đi kèm đã loại sẵn các thư mục tư liệu (`BGM/`, `SFX/`,
`Audio/`, `Videos/`, `Images/`, `Texts/`, `Logo/`, `Text Claim/`, `_render/`,
`Claude outputs/`) và mọi file `.mp3 .wav .mp4 .mov …`.

Nói cách khác: **đừng để nhạc nền và video nằm trong `D:\CapCutDraftStudio`.**
Hãy để chúng ở một thư mục kênh riêng, ví dụ `D:\Kenh\BGM\`, rồi trỏ tool vào
đó ở ô *Folder KÊNH*. Vừa gọn repo, vừa đúng cách tool được thiết kế.

## Bước 3 — Khai báo repo cho tool biết

Mở file `capcut_draft_studio/updater.py`, tìm dòng:

```python
REPO = "LEO-capcut/CapCutDraftStudio"
```

Sửa thành đúng `<tên-tài-khoản>/<tên-repo>` của bạn, ví dụ:

```python
REPO = "uzumakileo94/CapCutDraftStudio"
```

Sai dòng này thì tool sẽ báo "đang dùng bản mới nhất" mãi mãi.

## Bước 4 — Đẩy code lên

Mở **PowerShell**, vào đúng thư mục tool:

```powershell
cd D:\CapCutDraftStudio
git init
git branch -M main
git add .
git commit -m "CapCut Draft Studio 0.4.0"
git remote add origin https://github.com/<tên-tài-khoản>/CapCutDraftStudio.git
git push -u origin main
```

> PowerShell không hiểu `cd /d` của Command Prompt — chỉ cần `cd D:\...`.
>
> Dòng cảnh báo `LF will be replaced by CRLF` hiện ra rất nhiều là **bình
> thường**, không phải lỗi, cứ kệ nó.

Lần đầu Git sẽ mở cửa sổ đăng nhập GitHub — đăng nhập bằng trình duyệt là xong.

Vào lại trang repo trên GitHub, thấy đủ các thư mục `capcut_draft_studio`,
`.github`, `installer` là đúng.

## Bước 5 — Phát hành bản đầu tiên

```
git tag v0.4.0
git push origin v0.4.0
```

Vào tab **Actions** trên trang repo. Sẽ thấy một lượt chạy tên
**Build & Release** với 3 việc: Windows, macOS, rồi Phát hành.

Chờ khoảng **10–20 phút**. Xong thì sang tab **Releases**, bạn sẽ thấy bản
`v0.4.0` với 3 file đính kèm:

* `CapCutDraftStudio-0.4.0-windows-setup.exe`
* `CapCutDraftStudio-0.4.0-macos.dmg`
* `SHA256SUMS.txt`

Tải file `.exe` về, nhấp đúp để cài như mọi phần mềm Windows khác.

---

## Phát hành bản mới (các lần sau)

1. Sửa số phiên bản ở **5 chỗ** — nhờ Claude làm hộ cho chắc, hoặc tự sửa:
   `capcut_draft_studio/__init__.py`, `capcut_draft_studio/ui/app.py`
   (`APP_VERSION`), `pyproject.toml`, `version_info.txt` (2 chuỗi),
   `README.md` (dòng tiêu đề).
2. Chạy:

```
cd /d D:\CapCutDraftStudio
git add .
git commit -m "Ban 0.4.1"
git push
git tag v0.4.1
git push origin v0.4.1
```

3. Chờ Actions chạy xong. Người dùng đang mở tool sẽ được hỏi
   "Có bản mới 0.4.1 — tải về và cài ngay?" ngay lần mở tiếp theo.

Số trong tag (`v0.4.1`) **phải** lớn hơn `APP_VERSION` của bản cũ, nếu không
tool sẽ không coi đó là bản mới.

---

## Khi push bị chặn vì "File ... exceeds GitHub's file size limit of 100.00 MB"

Nghĩa là có file nặng đã bị đưa vào commit. Sửa như sau (thay `BGM` bằng
đúng thư mục GitHub kêu trong dòng báo lỗi):

```powershell
cd D:\CapCutDraftStudio
git rm -r --cached "BGM" "Claude outputs"
git commit --amend -m "CapCut Draft Studio 0.4.0"
git push -u origin main
```

`git rm --cached` chỉ gỡ file khỏi repo, **không xoá file trên ổ đĩa** — nhạc
của bạn vẫn còn nguyên. `--amend` sửa lại commit vừa rồi thay vì tạo commit mới.

Sau đó nên chuyển hẳn thư mục nhạc ra ngoài, ví dụ sang `D:\Kenh\BGM\`, để lần
sau không dính lại.

## Khi build hỏng

Vào tab **Actions** → bấm vào lượt chạy bị dấu X đỏ → bấm vào việc bị hỏng →
mở bước có dấu X để xem dòng báo lỗi. Gửi lại cho Claude nguyên đoạn đó.

Lỗi hay gặp nhất là mạng GitHub tải ffmpeg lỗi giữa chừng — bấm
**Re-run failed jobs** là chạy lại được.

---

## Vài điều nên biết

* **Bản macOS chưa được ký số.** Lần đầu mở, macOS sẽ báo "không mở được vì
  chưa rõ nhà phát triển". Cách mở: nhấp phải vào app → **Open** → **Open**.
  Muốn hết hẳn cảnh báo thì cần tài khoản Apple Developer (99 USD/năm).
* **Bản Windows cũng chưa ký số.** SmartScreen có thể hiện bảng xanh
  "Windows protected your PC" → bấm **More info** → **Run anyway**.
* **ffmpeg** chỉ được đóng gói kèm bản Windows. Trên macOS người dùng cần chạy
  `brew install ffmpeg` một lần; tool sẽ hiện đúng hướng dẫn này khi thiếu.
* ffmpeg phát hành theo giấy phép GPL — file `bin/FFMPEG-LICENSE.txt` đi kèm
  bộ cài chính là bản giấy phép đó.
* Repo để **Private** vẫn build và phát hành được, nhưng link tải trong
  Releases sẽ yêu cầu đăng nhập GitHub — muốn người khác tải tự do thì để
  **Public**.
