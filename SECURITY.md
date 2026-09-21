# Security notes

- Không tự động tải/chạy executable từ server.
- Nếu tích hợp updater, `verify_package()` yêu cầu SHA-256 64 ký tự và phải khớp package đã tải.
- `root_meta_info.json` được backup một lần thành `root_meta_info.json.bak-capcut-draft-studio` trước khi ghi.
- Nên đóng CapCut trong lúc build để tránh ghi đồng thời metadata.
- Không đọc browser cookies, credential stores, clipboard, startup registry hay scheduled tasks.
