import assert from "node:assert/strict";
import test from "node:test";
import { QueryObserver } from "@tanstack/react-query";
import {
  createQueryClient,
  createWorkbenchQueries,
  workbenchKeys,
} from "./workbench/queries";
import { createProductionAPI } from "./production";
import { createLibrary } from "./library";

function snapshot(id: string) {
  return {
    schema_version: 1,
    characters: [{ id }],
    jobs: [],
    assets: [],
    approvals: [],
    poses: [],
    selections: [],
    batches: [],
    outfit_versions: [],
    reviews: [],
  };
}

test("snapshot cache isolates characters and concurrent reads share a request", async () => {
  const calls: string[] = [];
  const api = createProductionAPI((async (url) => {
    const id = new URL(String(url), "https://test.invalid").searchParams.get(
      "character_id",
    )!;
    calls.push(id);
    return Response.json(snapshot(id));
  }) as typeof fetch);
  const client = createQueryClient();
  const queries = createWorkbenchQueries(api);
  try {
    const [first, duplicate] = await Promise.all([
      client.fetchQuery(queries.snapshot("a")),
      client.fetchQuery(queries.snapshot("a")),
    ]);
    assert.deepEqual(first, duplicate);
    await client.fetchQuery(queries.snapshot("b"));
    assert.deepEqual(calls, ["a", "b"]);
    assert.equal(
      client.getQueryData<typeof first>(workbenchKeys.snapshot("a"))
        ?.characters[0].id,
      "a",
    );
  } finally {
    client.clear();
  }
});

test("switching characters aborts the previous read and cannot populate the new snapshot", async () => {
  let oldSignal: AbortSignal | null | undefined;
  const api = createProductionAPI((async (url, init) => {
    if (String(url).endsWith("character_id=a")) {
      oldSignal = init?.signal;
      return new Promise<Response>((_resolve, reject) =>
        oldSignal?.addEventListener("abort", () =>
          reject(new DOMException("Aborted", "AbortError")),
        ),
      );
    }
    return Response.json(snapshot("b"));
  }) as typeof fetch);
  const client = createQueryClient();
  const queries = createWorkbenchQueries(api);
  const observer = new QueryObserver(client, queries.snapshot("a"));
  const stop = observer.subscribe(() => {});
  try {
    observer.setOptions(queries.snapshot("b"));
    const current = await client.fetchQuery(queries.snapshot("b"));
    assert.equal(oldSignal?.aborted, true);
    assert.equal(current.characters[0].id, "b");
    assert.equal(client.getQueryData(workbenchKeys.snapshot("a")), undefined);
  } finally {
    stop();
    client.clear();
  }
});

test("catalogs stay cached until invalidation and failed writes are attempted once", async () => {
  let reads = 0;
  let writes = 0;
  const library = createLibrary((async () => {
    reads++;
    return Response.json([]);
  }) as typeof fetch);
  const queries = createWorkbenchQueries(undefined, library);
  const client = createQueryClient();
  try {
    await client.fetchQuery(queries.characters());
    await client.fetchQuery(queries.characters());
    assert.equal(reads, 1);
    await client.invalidateQueries({ queryKey: workbenchKeys.characters });
    await client.fetchQuery(queries.characters());
    assert.equal(reads, 2);
    const mutation = client.getMutationCache().build(client, {
      mutationFn: async () => {
        writes++;
        throw new Error("uncertain submission");
      },
    });
    await assert.rejects(mutation.execute(undefined), /uncertain submission/);
    assert.equal(writes, 1);
  } finally {
    client.clear();
  }
});
