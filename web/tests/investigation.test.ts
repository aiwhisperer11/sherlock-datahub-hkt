import { describe, expect, it, vi } from "vitest";
import { apiUrl, fetchStalePipeline } from "../src/lib/investigation";

describe("Sherlock Engine client", () => {
  it("uses the local engine URL by default", () => {
    expect(apiUrl).toBe("http://localhost:8000");
  });

  it("returns the investigation response", async () => {
    const payload = { id: "demo", title: "The Case of the Stale Pipeline" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => payload }));

    await expect(fetchStalePipeline()).resolves.toEqual(payload);
  });
});
