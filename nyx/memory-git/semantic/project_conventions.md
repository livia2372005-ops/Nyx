# Project Conventions (Nyx Semantic Mirror)

- **Coding Standard**: Giữ mã nguồn tinh gọn, tránh dependency thừa thãi.
- **Error Handling**: Luôn xử lý ngoại lệ an toàn, không để lộ crash traceback ra giao diện người dùng.
- **Git Branching**:
  - `main`: Nhánh ổn định, chỉ nhận merge từ Reviewer sau khi pass audit.
  - `plan/{task_id}`: Nhánh lưu kế hoạch do Planner tạo.
  - `exec/{task_id}`: Nhánh lưu mã nguồn thực thi do Executor tạo.
