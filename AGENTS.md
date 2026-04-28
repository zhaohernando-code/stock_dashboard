# Stock Dashboard Agent Rules

- Treat `/Users/hernando_zhao/codex/projects/stock_dashboard` as the editable source of truth and `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard` as the live runtime copy.
- Do not edit files under the runtime copy unless the task is explicitly about debugging runtime drift or launch behavior. Publish into runtime by syncing from the repo.
- If a task changes anything that can affect the live service or a user-visible validation result, do not stop at repo edits. Before concluding, run `scripts/publish-local-runtime.sh`, verify local runtime health, and then verify the remote-facing entry in a real browser.
- A live-facing task is not complete until `scripts/publish-local-runtime.sh` succeeds, both `http://127.0.0.1:8000/health` and `http://127.0.0.1:5173/` pass their checks, and the published result is rechecked on the user-facing remote route such as `https://hernando-zhao.cn/stocks` or `https://hernando-zhao.cn/projects/ashare-dashboard/`.
- When validating the frontend, verify the served frontend matches the repo build on the actual remote-facing page rather than assuming a successful `npm run build` implies runtime parity.
- If remote publish or browser acceptance cannot be completed in the current turn, report that explicitly and do not describe the fix as finished.
- If runtime drift is found, record the cause and prevention in `PROCESS.md` before finishing.
