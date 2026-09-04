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
- Kiểm tra các tool MCP `memory_*`:
  - `memory_get_state`
  - `memory_update_state`
  - `memory_render_state_block`
  - `memory_query_semantic`
  - `memory_query_episodic`
  - `memory_promote_to_semantic`

## 2. Quy trình Lập Kế Hoạch (Planner Mode)
1. Truy vấn Semantic Memory:
   - Tra cứu các Architecture Decisions (ADR) và Domain Rules hiện có.
2. Kiểm tra State Memory:
   - Lấy snapshot trạng thái hệ thống và render prompt block qua `memory_render_state_block`.
3. Soạn thảo DAG:
   - Lưu kế hoạch vào `nyx/memory-git/plans/{task_id}/plan.md`.
   - Tạo `ContextPack` cho từng task trong `nyx/memory-git/plans/{task_id}/context_packs/`.
4. Git commit:
   - Tạo nhánh `plan/{task_id}` và commit kế hoạch.

## 3. Quy trình Thực Thi (Executor Mode)
1. Khởi chạy Subagent cho từng task con với chỉ `ContextPack` được cấp.
2. Thực thi công việc và trích xuất `new_facts`.
3. Ghi báo cáo `nyx/memory-git/executions/{task_id}/report.md` và commit vào nhánh `exec/{task_id}`.

## 4. Quy trình Kiểm Toán (Reviewer Mode)
1. Thẩm định báo cáo `report.md` đối chiếu với `plan.md`.
2. Kiểm tra State Drift trong State Memory.
3. Nếu PASS: Merge nhánh `exec/{task_id}` vào `main` và gọi `memory_promote_to_semantic`.
