---
name: nyx
description: Vận hành hệ thống Multi-Agent Nyx với bộ nhớ lai 5 tầng (StateMem, Episodic, Semantic, Working, Git). Sử dụng khi người dùng yêu cầu kích hoạt Nyx, quản lý State Drift, lập kế hoạch DAG hoặc điều phối Planner/Executor/Reviewer.
---

# Nyx Multi-Agent Workflow Skill

Skill này hướng dẫn chi tiết cách Agent trên Antigravity phối hợp với hệ thống **Nyx**.

## 1. Khởi tạo & Kiểm tra
- Chạy script kiểm tra khởi tạo nếu database chưa tồn tại:
  ```bash
  python nyx/scripts/init_nyx.py
  ```
- Kiểm tra 4 tool MCP `memory_*`:
  - `memory_query`: Tra cứu tri thức thống nhất (Vector + Graph + Events).
  - `memory_get_state`: Lấy snapshot StateMem & phát hiện cờ `[!] [NEEDS_RECHECK]`.
  - `memory_update_state`: Cập nhật trạng thái, lan truyền invalidation & phát hiện chu trình.
  - `memory_record`: Ghi nhận sự kiện (`event`) hoặc thăng cấp tri thức (`fact`).

## 2. Quy trình Lập Kế Hoạch (Planner Mode)
1. Truy vấn Memory:
   - Tra cứu qua `memory_query` để nạp Architecture Decisions (ADR) và Domain Rules.
2. Kiểm tra State Memory:
   - Lấy snapshot trạng thái hệ thống qua `memory_get_state(format='markdown')`.
3. Soạn thảo DAG:
   - Lưu kế hoạch vào `nyx/memory-git/plans/{task_id}/plan.md`.
   - Tạo `ContextPack` cho từng task trong `nyx/memory-git/plans/{task_id}/context_packs/`.
4. Git commit:
   - Tạo nhánh `plan/{task_id}` và commit kế hoạch.

## 3. Quy trình Thực Thi (Executor Mode)
1. Khởi chạy Subagent cho từng task con với chỉ `ContextPack` được cấp.
2. Thực thi công việc và trích xuất `new_facts`.
3. Ghi báo cáo `nyx/memory-git/executions/{task_id}/report.md`, commit nhánh `exec/{task_id}`, và gọi `memory_record(type='event')`.

## 4. Quy trình Kiểm Toán (Reviewer Mode)
1. Thẩm định báo cáo `report.md` đối chiếu với `plan.md`.
2. Kiểm tra State Drift trong State Memory (`memory_get_state`).
3. Nếu PASS: Merge nhánh `exec/{task_id}` vào `main` và gọi `memory_record(type='fact')` để thăng cấp tri thức.
