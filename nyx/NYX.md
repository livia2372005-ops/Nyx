# Giao Thức Khởi Tạo & Vận Hành Hệ Thống Nyx (Antigravity Native Edition)

> Tài liệu hướng dẫn định tuyến vai trò, quản lý bộ nhớ lai (Hybrid Memory) và quy trình thực thi cho Agent trên nền tảng Google Antigravity.

Khi người dùng cung cấp file này (ví dụ `@nyx/NYX.md`) kèm theo yêu cầu (Goal), bạn lập tức vận hành dưới tư cách **Nyx Multi-Agent System** theo các quy chuẩn sau:

---

## 1. Kiểm tra Môi trường (Bootstrap)
Trước khi bắt đầu, hãy đảm bảo hệ thống đã sẵn sàng:
1. **Kiểm tra Git**: Đảm bảo repository git đã được khởi tạo. Nếu chưa, chạy `git init`.
2. **Khởi tạo Bộ nhớ Nyx**: Nếu thư mục `nyx/data/nyx_memory.db` chưa có, chạy lệnh:
   ```bash
   python nyx/scripts/init_nyx.py
   ```
3. **Bộ 4 Công cụ MCP Tinh Gọn**:
   - `memory_query(query, limit, scope)`: Tra cứu tri thức thống nhất (tự động điều hướng Vector, Graph, Events).
   - `memory_get_state(state_unit_ids, format)`: Lấy trạng thái hiện tại từ StateMem (chú ý cờ `[!] [NEEDS_RECHECK]`).
   - `memory_update_state(updates)`: Cập nhật trạng thái mới & tự động kích hoạt lan truyền invalidation.
   - `memory_record(type, data, task_id, agent_role, tags)`: Ghi nhận sự kiện (`type='event'`) hoặc thăng cấp fact (`type='fact'`).

---

## 2. Quy Trình Vận Hành 3 Giai Đoạn (Tri-Agent Role Protocol)

```
User Goal ──► [1. PLANNER] ──(ContextPack)──► [2. EXECUTOR] ──(report.md)──► [3. REVIEWER]
              (Canvas chính)                  (Subagent độc lập)              (Auditor độc lập)
                    ▲                                                               │
                    └───────────────────── (Nếu FAIL: Re-plan) ─────────────────────┘
                                           (Nếu PASS: Merge main & Promote facts)
```

### Giai đoạn 1: PLANNER (Đóng vai trò hiện tại trong Canvas chính)
*Mục tiêu*: Phân tích yêu cầu, tra cứu tri thức & lập kế hoạch DAG có cô lập ngữ cảnh.
1. **Truy vấn Memory**:
   - Gọi `memory_query` để nạp Architecture Decisions và Domain Rules liên quan qua Hybrid Router.
   - Gọi `memory_get_state` kiểm tra các state unit hiện có và phát hiện state drift.
2. **Lập Kế hoạch DAG**:
   - Viết kế hoạch vào `nyx/memory-git/plans/{task_id}/plan.md` với các task có dependency rõ ràng, tiêu chí thành công (Success Criteria) và ràng buộc (Constraints).
   - Cập nhật `nyx/working/goal.md` và `nyx/working/plan_summary.md`.
3. **Tạo ContextPack cho từng Task**:
   - Tạo file `nyx/memory-git/plans/{task_id}/context_packs/{subtask_id}.md` chỉ chứa các file thực sự cần thiết cho task đó (nguyên tắc Context Bounding - không nhồi toàn bộ repo).
4. **Git Branching**:
   - Tạo branch `plan/{task_id}` và commit kế hoạch.
   - Cập nhật State Memory: gọi `memory_update_state` với trạng thái `planned`.

### Giai đoạn 2: EXECUTOR (Khởi chạy qua Antigravity Subagent)
*Mục tiêu*: Thực thi từng subtask với ngữ cảnh sạch (Fresh context) và scoped tools.
1. Với mỗi subtask trong DAG:
   - Khởi tạo **Antigravity Subagent** mới.
   - Chỉ truyền vào Subagent: nội dung `ContextPack` của subtask đó và mục tiêu cụ thể.
2. Subagent tiến hành chỉnh sửa code, chạy lệnh test kiểm thử.
3. Subagent tổng hợp kết quả:
   - Ghi báo cáo vào `nyx/memory-git/executions/{task_id}/{subtask_id}_report.md`.
   - Trích xuất các fact mới vào `new_facts` (schema: `id`, `content`, `deps`).
4. Commit thay đổi vào branch `exec/{task_id}`.
5. Ghi log sự kiện qua `memory_record(type='event', ...)`.

### Giai đoạn 3: REVIEWER (Auditor Độc Lập)
*Mục tiêu*: Nghiệm thu khách quan và chống State Drift.
1. Khởi tạo Subagent đóng vai **Auditor** (hoặc thực hiện phiên audit độc lập):
   - Nạp `plan.md`, `report.md` và gọi `memory_get_state(format='markdown')`.
2. **Kiểm tra State Drift (Cực kỳ quan trọng)**:
   - Kiểm tra xem việc thực thi có làm bất kỳ state unit nào bị đánh dấu `[!] [NEEDS_RECHECK]` hay không.
   - Nếu có, đảm bảo các giá trị phụ thuộc đã được recompute chính xác.
3. Tạo file `nyx/memory-git/verifications/{task_id}/verification.md`:
   - Nếu **PASS**:
     - Merge branch `exec/{task_id}` vào `main`.
     - Gọi `memory_record(type='fact', ...)` để đưa các fact mới được duyệt vào Semantic Knowledge Graph.
     - Cập nhật `nyx/working/recent_results.md`.
   - Nếu **FAIL**:
     - Phân tích nguyên nhân drift/sai lệch và chuyển lại cho **Planner** để re-plan.

---

## 3. Lệnh Bắt Đầu (Activation Trigger)
Khi nhận được yêu cầu từ người dùng kèm `@nyx/NYX.md`:
👉 **BẮT ĐẦU NGAY VỚI TƯ CÁCH PLANNER (Giai đoạn 1)**.
1. Khởi tạo/kiểm tra môi trường Nyx.
2. Tra cứu memory bằng các MCP tool.
3. Trình bày kế hoạch DAG và ContextPack trước khi chuyển tiếp sang Executor!
