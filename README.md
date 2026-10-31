# TroHoaLac – bản triển khai công khai

Ứng dụng này dùng **Streamlit + Python + Hard Filtering + Weighted Sum** để gợi ý Top 10 phòng từ dữ liệu do người quản trị xuất ra từ SQL Server. Bản công khai **không kết nối SQL Server trực tiếp**, do đó không yêu cầu người truy cập nhập thông tin SQL.

## Chạy trên Windows

1. `py -m pip install -r requirements_export.txt`
2. `py export_public.py --server localhost --database TroHoaLac`
3. **Kiểm tra kỹ** `data/rooms_public.json` và xóa thông tin riêng tư hoặc không được phép đăng công khai.
4. `py -m pip install -r requirements.txt`
5. `py -m streamlit run app.py` → mở `http://localhost:8501`.

Nếu dùng SQL Express, thay `localhost` thành `".\SQLEXPRESS"`. Nếu dùng SQL Server Authentication, thêm `--user TEN_DANG_NHAP` và nhập mật khẩu khi CMD hỏi.

## Đăng lên Internet

Tạo repository trên GitHub, upload code và file `data/rooms_public.json` đã rà soát; mở <https://share.streamlit.io> → Create app → chọn repo, `main`, `app.py` → Deploy. Bạn sẽ nhận được URL `https://...streamlit.app` để mọi người truy cập.

Hướng dẫn đầy đủ bằng tiếng Việt: [`HUONG_DAN_PUBLIC_WINDOWS.txt`](HUONG_DAN_PUBLIC_WINDOWS.txt).

## Các file

- `app.py`: Giao diện cho người dùng, không có ô kết nối SQL.
- `recommend.py`: Lõi tính điểm như project cũ.
- `web_logic.py`: Chuyển các lựa chọn của người dùng thành JSON nhu cầu.
- `db_live.py`: Chỉ dùng trên máy người quản trị để đọc SQL.
- `export_public.py`: Xuất file dữ liệu công khai từ SQL Server thật.
- `data/rooms_public.json`: File snapshot dữ liệu. Trong ZIP ban đầu file này **rỗng**; phải xuất từ database của bạn trước khi deploy.
- `requirements.txt`: Chỉ cần `streamlit` khi triển khai trên Community Cloud.
- `requirements_export.txt`: `pyodbc` chỉ cài trên máy xuất dữ liệu.

## Bảo vệ dữ liệu

Cảnh báo: Với GitHub repo công khai, tất cả nội dung JSON bạn upload đều có thể được người khác đọc hoặc tải xuống. Script có giới hạn trường xuất, mặc định bỏ URL bài đăng, và ẩn một số mẫu số điện thoại/email trong tên phòng. **Nó không thể tự động phát hiện mọi thông tin cá nhân, dữ liệu riêng tư hoặc vấn đề quyền chia sẻ**. Bạn phải rà soát thủ công và chỉ xuất bản những bản ghi được phép công khai. Tuyệt đối không đưa `.bak`, thông tin đăng nhập SQL hoặc `secrets.toml` vào repo.

## Độ chính xác và cập nhật

Lõi `recommend.py` không thay đổi công thức. Dữ liệu online là bản snapshot, không tự đồng bộ. Muốn cập nhật phòng mới: xuất lại trên máy có SQL Server → rà soát → upload thay file `data/rooms_public.json` trên GitHub → commit. Kết quả hiển thị chỉ mang tính hỗ trợ tìm kiếm, không đảm bảo phòng vẫn đang trống hoặc thông tin bài đăng còn hiệu lực.
