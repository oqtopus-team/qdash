Copilot package: what the API needs to open a chat about a task result.

The planner itself runs in the Pi Agent Runtime (`agent-runtime/`) with the
pi-qdash tools; the calibration evaluation model is pi-qcaleval's; the chat's
shell and files are the Copilot workspace (`agent-runtime/exec/`). This
package runs neither a model nor model-written code: it loads data, renders
prompts, and holds the shared contracts.

## Package Layout

- [runtime.py](runtime.py)
  `CopilotRuntime`: composes the loaders in `services/` into `build_task_context()`,
  the context and figures a chat about one task result opens with.
- [config/](config/__init__.py)
  Configuration models and the YAML loader (`config/copilot/*.yaml`).
- [contracts/](contracts/__init__.py)
  Request/response models shared with the API routers (`ChatRequest`, `TaskContext`, ...).
- [prompts/](prompts/__init__.py)
  The opening message of a task chat and the knowledge extraction prompt.
- [services/](services/__init__.py)
  Data loaders: task result, task history, neighbour and coupling parameters, figures.
- [blocks.py](blocks.py)
  Renders the chat's blocks answer as markdown for issue and forum replies.

## Flow

1. `POST /copilot/chat/stream` with `task` builds a `TaskContextBundle` through `CopilotRuntime`.
2. `api/services/pi_chat_service.py` renders it into the opening message and figures and
   proxies the turn to the Pi Agent Runtime as SSE.
3. Issue and forum AI replies and issue knowledge extraction run one planner turn the same
   way (`pi_chat_service.thread_reply`, `pi_chat_service.complete_once`).
