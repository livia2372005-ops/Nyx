# Nyx Multi-Agent System: Project Operating Mandate

Tất cả các phiên làm việc và yêu cầu nhiệm vụ trong workspace này đều tuân thủ và vận hành theo kiến trúc **Nyx Hybrid Memory Multi-Agent System**. Người dùng **không cần gõ `@nyx` hay `@nyx/NYX.md`**, hệ thống luôn tự động kích hoạt các quy chuẩn sau:

---

## 1. Nguyên Tắc Vận Hành Mặc Định (Always-On Tri-Agent Flow)

Khi người dùng đưa ra một yêu cầu công việc (feature, refactor, bugfix, architecture update), Agent tự động chia thành 3 giai đoạn:

### Giai đoạn 1: PLANNER (Canvas chính)
- **Truy vấn Memory**:
  - Gọi công cụ MCP `memory_get_state` để lấy trạng thái hệ thống và kiểm tra các cờ `[!] [NEEDS_RECHECK]`.
  - Gọi `memory_query` để nạp Architecture Decisions (ADR), Domain Rules và bài học từ các task liên quan qua Hybrid Router.
- **Lập kế hoạch DAG**:
  - Soạn thảo kế hoạch tại `nyx/memory-git/plans/{task_id}/plan.md` với các task có dependency, tiêu chí nghiệm thu rõ ràng.
  - Cập nhật scratchpad: `nyx/working/goal.md` và `nyx/working/plan_summary.md`.
- **Đóng gói ContextPack (Context Bounding)**:
  - Tạo `nyx/memory-git/plans/{task_id}/context_packs/{subtask_id}.md` chỉ chứa các file thực sự cần thiết cho subtask đó (không nhồi toàn bộ repo).
- **Tạo nhánh Git**: Tạo branch `plan/{task_id}` và commit kế hoạch.

### Giai đoạn 2: EXECUTOR (Subagent cô lập)
- Khởi chạy Antigravity Subagent riêng cho từng subtask với ngữ cảnh sạch (Fresh Context).
- Chỉ nạp nội dung của `ContextPack` tương ứng.
- Subagent thực thi công việc, chạy test và ghi báo cáo vào `nyx/memory-git/executions/{task_id}/{subtask_id}_report.md`.
- Trích xuất `new_facts` và commit vào nhánh `exec/{task_id}`.
- Ghi nhận sự kiện vào Event Store qua `memory_record(type='event', ...)`.

### Giai đoạn 3: REVIEWER (Auditor độc lập)
- Khởi chạy Subagent kiểm toán độc lập đối soát `report.md` với `plan.md`.
- **Kiểm soát State Drift**: Gọi `memory_get_state` để xác minh không có node nào còn cờ `[!] [NEEDS_RECHECK]` chưa được giải quyết.
- Lập biên bản nghiệm thu `nyx/memory-git/verifications/{task_id}/verification.md`.
- Nếu PASS: Merge nhánh `exec/{task_id}` vào `main` và gọi `memory_record(type='fact', ...)` để thăng cấp các fact mới vào Semantic Memory.
- Nếu FAIL: Báo cáo drift analysis về cho Planner để re-plan.

---

## 2. Đường Đi Nhanh (Fast Path cho câu hỏi đơn giản)
- Đối với các câu hỏi giải thích mã nguồn, tra cứu định nghĩa, hướng dẫn thao tác thông thường không làm thay đổi state/codebase: Agent trả lời trực tiếp mà không cần tạo nhánh Git hoặc phân rã DAG phức tạp.

---

## 3. Bộ 4 Công Cụ MCP Tinh Gọn Của Nyx
Agent có toàn quyền sử dụng 4 công cụ MCP chuẩn hóa:
1. `memory_query(query, limit, scope)`: Tra cứu tri thức thống nhất (tự động điều hướng Vector, Graph, Events).
2. `memory_get_state(state_unit_ids, format)`: Lấy snapshot đồ thị trạng thái $G=(U,E)$ và kiểm tra State Drift.
3. `memory_update_state(updates)`: Cập nhật StateMem, tự động lan truyền cờ `[!] [NEEDS_RECHECK]` & phát hiện chu trình.
4. `memory_record(type, data, task_id, agent_role, tags)`: Ghi nhận sự kiện thực thi (`type='event'`) hoặc thăng cấp fact (`type='fact'`).
