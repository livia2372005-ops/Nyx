# Nyx System Operating Rules

Khi làm việc trong workspace kích hoạt Nyx, Agent cần tuân thủ nghiêm ngặt các quy tắc sau:

1. **Chống State Drift (State Drift Guardrail)**:
   - Trước khi báo cáo hoàn thành bất kỳ task nào, luôn kiểm tra State Memory (`memory_get_state`).
   - Nếu phát hiện bất kỳ state unit nào có cờ `[NEEDS_RECHECK]`, không được phép bỏ qua hoặc giả định. Phải tính toán lại (recompute) hoặc yêu cầu xác nhận.

2. **Nguyên tắc Cô lập Ngữ cảnh (Context Bounding)**:
   - Khi chuyển giao công việc cho Executor (Subagent), chỉ đóng gói các file và thông tin liên quan trực tiếp trong `ContextPack`.
   - Tránh nạp toàn bộ cây thư mục hoặc toàn bộ lịch sử hội thoại để tránh hiện tượng Context Bloat và giảm thiểu hallucination.

3. **Tính Toàn Vẹn Của Git Audit Trail**:
   - Mọi thay đổi mã nguồn phải được thực hiện trên nhánh `exec/{task_id}`.
   - Nhánh `main` chỉ được phép cập nhật thông qua merge sau khi Reviewer đã kiểm toán và tạo file `verification.md` đạt yêu cầu.
