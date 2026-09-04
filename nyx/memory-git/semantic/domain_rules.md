# Domain Rules (Nyx Semantic Mirror)

Các quy tắc nghiệp vụ bất biến áp dụng cho toàn bộ dự án:

1. **Rule-001 (Context Bounding)**: Executor chỉ được phép nhận danh sách file được chỉ định cụ thể trong `ContextPack`. Không nạp toàn bộ repo vào context của Executor.
2. **Rule-002 (Signed Audit Trail)**: Mỗi thay đổi phải có commit rõ ràng:
   - Planner commit: `plan: [task_id] <summary>`
   - Executor commit: `exec: [task_id] <summary>`
   - Reviewer commit: `verify: [task_id] <summary>`
3. **Rule-003 (State Drift Prohibition)**: Không được phép nghiệm thu bất kỳ task nào nếu trong State Snapshot còn tồn tại state unit có trạng thái `needs_recheck` mà chưa được recompute/validate.
