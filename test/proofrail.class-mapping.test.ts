import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { InMemoryProofRailRepository } from "../src/proofrail/repository.js";

describe("Fail-closed QBO Class mapping (Ben's directive, 2026-07-08)", () => {
  it("returns undefined (halt, never guess) when no mapping row matches", async () => {
    const repo = new InMemoryProofRailRepository();
    const result = await repo.resolveQboClass({ entity: "Madison", project: "Madison Park:Vertical", item: "003 Concrete", vendor: "GC - Elite" });
    assert.equal(result, undefined);
  });

  it("resolves via the most specific matching row when multiple rows could match", async () => {
    const repo = new InMemoryProofRailRepository();
    repo.seedClassMapping({ entity: "Madison", qboClass: "40 Vertical - Madison Default", priority: 100 });
    repo.seedClassMapping({ entity: "Madison", project: "Madison Park:Vertical", qboClass: "40 Vertical", priority: 50 });

    const result = await repo.resolveQboClass({ entity: "Madison", project: "Madison Park:Vertical", item: "003 Concrete", vendor: "GC - Elite" });
    assert.equal(result, "40 Vertical"); // more fields matched (entity+project) beats the entity-only row
  });

  it("a wrong entity/project never falls back to an unrelated row - stays undefined", async () => {
    const repo = new InMemoryProofRailRepository();
    repo.seedClassMapping({ entity: "Madison", project: "Madison Park:Vertical", qboClass: "40 Vertical" });

    const result = await repo.resolveQboClass({ entity: "Union", project: "Union Station:Vertical", item: "003 Concrete", vendor: "GC - Elite" });
    assert.equal(result, undefined);
  });
});
