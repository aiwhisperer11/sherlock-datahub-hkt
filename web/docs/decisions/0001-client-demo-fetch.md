# 0001: Fetch the sandbox investigation from the browser

Date: 2026-07-23

The investigation page is a client component so it can expose loading, success, and error connection states. The backend URL is public configuration because it is consumed by browser code; no credentials belong in this value.
