# 0001: Fetch the Frozen Dashboard investigation from the browser

Date: 2026-07-23

The investigation page is a client component so it can expose loading, success, and error connection states. It calls the Frozen Dashboard endpoint and displays simulated input separately from observed DataHub evidence and Sherlock-derived conclusions. The backend URL is public configuration because it is consumed by browser code; no credentials belong in this value.
