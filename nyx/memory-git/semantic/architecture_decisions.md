# Architecture Decisions (Nyx Semantic Mirror)

Tài liệu này phản ánh các quyết định kiến trúc cốt lõi đã được Reviewer nghiệm thu và thăng cấp vào Semantic Memory.

---

## ADR-001: Tri-Agent Role Isolation
- **Status**: Accepted
- **Context**: Tránh context bloat, ảo giác công cụ và lỗi tự nghiệm thu sai lệch.
- **Decision**: Chia tách tuyệt đối 3 vai trò:
  - **Planner**: Lập kế hoạch DAG, tạo ContextPack, commit branch `plan/*`.
  - **Executor**: Chạy trong isolated context, chỉ nhận ContextPack và scoped tools, sinh `report.md` + `new_facts.json`, commit branch `exec/*`.
  - **Reviewer**: Độc lập kiểm toán, kiểm tra State Drift, nghiệm thu merge vào `main` và thăng cấp fact.

## ADR-002: StateMem Invalidation via Dependency Graph
- **Status**: Accepted
- **Context**: State Drift là nguyên nhân hàng đầu khiến Agent dùng lại thông tin cũ dù đã có fact mới.
- **Decision**: Quản lý trạng thái dưới dạng đồ thị phụ thuộc $G=(U,E)$. Khi một node bị thay thế (`superseded`), cờ `needs_recheck` được lan truyền tất định qua các node phụ thuộc mà không cần tốn LLM calls.
