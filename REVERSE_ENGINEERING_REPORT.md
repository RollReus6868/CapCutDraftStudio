# Reverse engineering report — CapCut Draft Tool v1.2.2

## 1. Phạm vi và phương pháp

Phân tích này là **static analysis**. File EXE không được chạy. Quy trình gồm:

1. Giải nén `capcut-tool-v1.2.2.zip`.
2. Xác định `CapCut Draft Tool.exe` là PyInstaller one-folder, Python 3.12.
3. Đọc CArchive/TOC và trích `PYZ.pyz`.
4. Trích bytecode các module Python tự viết.
5. Load code object tĩnh để thu thập function/class, arguments, local variables, constants và global-name references.
6. Đối chiếu API với `pycapcut 0.0.3` công khai.
7. Viết lại một implementation mới từ hành vi quan sát được; không nhúng bytecode/source gốc vào tool mới.

SHA-256:

- ZIP: `c51ecd16a562592493ec2c639af9094bda522b119572263f373d66b324d37f00`
- EXE: `16e95db27298a602d943e33e530b930527e78e4dee3b1a1321124a849f0e0827`

## 2. Cấu trúc ứng dụng gốc

Ba module riêng của tác giả:

| Module | Code objects | Vai trò |
|---|---:|---|
| `capcut_tool` | 134 | Tkinter GUI, preview, form, template, update UI |
| `draft_builder` | 99 | Scan/validate/build draft, subtitle, style, SFX/BGM, registration |
| `updater` | 14 | Check version, download ZIP, swap application folder |

Ngoài ra EXE đóng gói `pycapcut 0.0.3`, `openpyxl`, `pymediainfo`, `Pillow`, `pygame`, `numpy`, `uiautomation` và Python runtime.

Danh sách function/class chi tiết nằm trong `ORIGINAL_FUNCTION_INVENTORY.json`.

## 3. Data model gốc được phục dựng

`Settings` chứa các default quan trọng sau:

```text
width                  1920
height                 1080
fps                    30
claim_dur              1.1 s
min_speed              0.75
trans_dur              0.47 s
voice_vol              3.16
bgm_intro_vol_high     1.0
bgm_intro_vol_low      0.56
bgm_body_vol           0.18
bgm_intro_high_dur     12.0 s
bgm_intro_max_dur      59.0 s
impact_vol             1.48
logo_x                 0.949
logo_y                -0.91
logo_scale             0.09
sub_max_words          12
sub_target_sec         3.0 s
crossfade_sec          1.5 s
image_anim             variety
vol_unit               percent
subtitle_source        auto
transition_type        叠化
```

Feature toggles mặc định bật: subtitle, logo, claim, BGM, impact, voice, transition, slow và cut.

`Assets` gồm:

- `audios: dict[int, Path]`
- `videos: dict[int, Path]`
- `images: dict[int, Path]`
- `texts: dict[int, Path]`
- `claim`, `logo`
- `bgm_files`, `bgm_impact`
- `sfx_items`

## 4. Luồng scan asset

`scan_assets()`:

1. Xác nhận input và channel directory tồn tại.
2. Tìm folder voice theo ưu tiên `Audio`, sau đó `voices`/`voice`.
3. Scan file có basename chỉ gồm số trong `Audio`, `Videos`, `Images`, `Texts`.
4. Nếu cùng scene có nhiều file cùng loại, chọn theo thứ tự extension/name và log warning.
5. Resolve Logo/Claim theo override → legacy → file đầu trong folder asset.
6. Resolve BGM từ override BGM directory hoặc `<channel>/BGM`.
7. Tìm `impact.*` riêng.
8. Gom SFX từ global library và `<channel>/SFX`.

## 5. Validation và scene planner

`validate()` tạo plan cho từng audio scene và phân loại visual thành:

- `CUT`
- `SLOW`
- `SPEEDUP`
- `IMAGE`

Các lỗi được gom lại thay vì crash ngay từng scene. Có fallback video lỗi sang image cùng số. `hook_overrides` cho phép một scene audio tham chiếu visual scene khác.

Planner dựa trên duration audio/video. Nếu không thể đáp ứng duration bằng video và không có image fallback, scene bị đánh dấu lỗi.

## 6. Image animation

`_apply_image_anim()` hỗ trợ:

- `off`
- `variety`
- `zoom_in`
- `zoom_out`
- `pan_left`
- `pan_right`

`variety` luân phiên 4 kiểu. Các trị số quan sát được:

- zoom in `1.00 → 1.08`
- zoom out `1.15 → 1.00`
- pan khoảng `±0.1` theo trục X

## 7. Subtitle pipeline

Nguồn:

- `off`
- `texts`
- `manifest`
- `excel`
- `auto`

`auto` ưu tiên manifest/Excel/Texts tùy asset có sẵn.

Manifest gốc có concept `sheets`; tool cố khớp sheet theo tên folder input, sau đó đọc `scenes[].scene_id` và `scenes[].script`.

Excel:

- Tự dò sheet phù hợp tên input hoặc sheet có header thoại.
- Tự dò header row.
- Cho phép user chỉ định `script_col`, `scene_col`, `sheet_name`.
- Có heuristic cho các header tiếng Anh/Việt như script/text/content/narration/thoại/lời/nội dung và scene/stt/number/cảnh/số/index.

Text được chia bằng dấu câu rồi tiếp tục chia theo `sub_max_words`. Tool sinh `subtitles.srt`, sau đó gọi `ScriptFile.import_srt()`.

## 8. Subtitle style harvesting

Pipeline gốc:

1. Scan `*/draft_content.json` trong CapCut drafts.
2. Đọc `materials.texts`.
3. Parse content JSON để lấy fill/font/border/shadow/glow/background.
4. Đọc alignment, letter spacing, line spacing ở material root.
5. Tạo signature để deduplicate style.
6. Lưu style JSON vào `assets/sub-styles`.
7. Có preview bằng Pillow.
8. Khi build, dùng style làm template/import reference và sau đó patch trực tiếp `draft_content.json` để đồng bộ những trường pycapcut không giữ đủ.

`_inject_subtitle_styles()` chỉ sửa material thuộc text track tên `subtitles`.

## 9. Transition harvesting

`harvest_transitions_from_capcut()` quét:

```text
materials.transitions[]
```

và lưu:

- name
- effect_id
- resource_id
- default_duration (default 500000 µs)
- is_overlap

Tool gốc có adapter `CustomTransitionType` để dùng transition không có sẵn trong enum của pycapcut.

## 10. SFX harvesting

`harvest_from_capcut()`:

1. Quét `materials.audios` trong mọi draft.
2. Chỉ lấy material `type` là `sound` hoặc `music`.
3. Bỏ file tên chỉ có số.
4. Sanitize filename.
5. Nếu có ffmpeg, có thể transcode về MP3; nếu không thì copy nguyên file.
6. Đưa vào `assets/sfx-library/harvested`.

SFX role trong GUI:

- `off`
- `placed`
- `muted`

## 11. BGM logic

`music_roles` lưu theo filename và giữ thứ tự GUI. Mỗi item có:

- `intro`
- `bg`
- volume riêng

Build tạo hai track `bgm_a` / `bgm_b` để alternate các đoạn background và overlap crossfade. Intro và background có mức volume riêng, intro bị giới hạn bởi `bgm_intro_max_dur`.

## 12. Draft build

Các track quan sát được trong `build()`:

```text
main
logo
voice
bgm
bgm_a
bgm_b
sfx
sfx_kho
subtitles
```

Luồng:

1. `DraftFolder.create_draft(name, width, height, fps, allow_replace=True)`.
2. Tạo main video track.
3. Đặt voice + visual scene theo plan.
4. Với ảnh, áp Ken Burns keyframe.
5. Thêm transition vào segment trước.
6. Claim overlay đầu video.
7. Logo overlay toàn timeline bằng `ClipSettings(transform_x/y, scale_x/y)`.
8. Intro/BGM background + fade/crossfade.
9. SFX placed trên timeline; SFX muted được preload ở track mute.
10. Sinh/import SRT.
11. `script.save()`.
12. Patch subtitle JSON nếu có style.
13. Register project vào `root_meta_info.json`.

## 13. Registration vào CapCut home

`register_draft_in_root_meta()` đọc `draft_meta_info.json`, set:

- `draft_json_file`
- `streaming_edit_draft_ready = true`

sau đó insert/update entry trong `root_meta_info.json -> all_draft_store` theo `draft_id`.

Điểm rủi ro: file metadata này là internal format của CapCut và có thể thay đổi theo version.

## 14. GUI gốc

Tabs:

- Chính
- Nhạc
- SFX
- Phụ đề
- Nâng cao
- Hướng dẫn

Các chức năng UI đáng chú ý:

- Save/load template cấu hình.
- Aspect 16:9 / 9:16.
- Volume unit percent/dB.
- Music role per file.
- SFX role per file + bulk actions.
- Preview audio qua pygame.
- Excel sheet/column picker.
- Harvest subtitle style/transition/SFX từ CapCut.
- Logo drag/scale preview.
- Channel settings persistence.
- Background worker + Queue để GUI không freeze.

## 15. Updater gốc

`API_BASE` được hard-code tới Cloudflare Worker. `check_update()` gọi endpoint `/version?app=capcut-tool` và kỳ vọng `version`, `download_url`, `changelog`.

`apply_update()`:

1. Chỉ chạy khi app frozen.
2. Download ZIP vào temp.
3. Extract.
4. Tìm app folder/EXE mới.
5. Copy user data `assets/sfx-library` và `tool-config.json` vào bản mới.
6. Sinh `updater.ps1`; fallback `updater.bat`.
7. Chờ process cũ exit.
8. Rename folder cũ thành `.old`.
9. Move bản mới vào.
10. Rollback nếu move fail.
11. Start EXE mới.
12. Xóa backup/temp.

PowerShell được launch với `-ExecutionPolicy Bypass`.

Không quan sát thấy bước bắt buộc xác minh SHA-256 hoặc chữ ký package trong bytecode updater.

## 16. Những gì tool mới đã implement

Project `capcut_clone_tool` là implementation mới, gồm:

- `models.py`: Settings/Assets/ScenePlan.
- `config.py`: config/channel settings + detect CapCut drafts.
- `media.py`: scan, duration, planner, SFX harvesting, CapCut process warning.
- `subtitles.py`: manifest/Excel/Texts, sentence splitting, SRT.
- `styles.py`: harvest/inject subtitle style cơ bản.
- `capcut_engine.py`: pycapcut draft builder, BGM, SFX, overlays, subtitles, registration.
- `app.py`: Tkinter GUI 6 tabs.
- `updater.py`: updater helper chỉ verify package khi có SHA-256.

## 17. Khác biệt có chủ đích

Bản clean-room hiện tại **không cố sao chép từng dòng/bytecode**. Một số chi tiết được thiết kế lại:

- Không hard-code update server.
- Không tự chạy package update chưa xác minh.
- Backup `root_meta_info.json` trước khi patch.
- Warning nếu CapCut.exe đang chạy.
- Planner/SFX placement được viết lại rõ ràng, dễ sửa.
- Subtitle manifest parser chấp nhận nhiều shape hơn.

Chưa đạt parity tuyệt đối ở:

- audio preview pygame;
- logo drag preview;
- custom transition adapter từ harvested resource ID;
- preview hình subtitle style;
- exact SFX impact-window algorithm của bản gốc;
- exact low-level `draft_meta_info.json` material repair cho mọi phiên bản CapCut.

## 18. Kết luận

Có đủ bằng chứng tĩnh để mô tả gần như toàn bộ kiến trúc và hành vi của tool gốc mà không cần chạy EXE. Phần khó nhất không phải GUI mà là compatibility layer với schema CapCut thay đổi theo version. Tool mới tách phần đó khỏi UI để có thể thay adapter khi CapCut cập nhật.
