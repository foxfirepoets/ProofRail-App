import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { InMemoryProofRailRepository } from "../src/proofrail/repository.js";
import { derivePhaseFromProject } from "../src/proofrail/qbo.js";

// Real Class list, verified against qbo Source Files/8_Classes_REALM_A_API_SEED.csv +
// 9_Classes_REALM_B_API_SEED.csv, seeded identically into Supabase's proofrail_class_mapping.
function seedRealClassList(repo: InMemoryProofRailRepository) {
  repo.seedClassMapping({ context: "Acquisition", qboClass: "00 Acquisition" });
  repo.seedClassMapping({ context: "Sitework", qboClass: "20 Sitework" });
  repo.seedClassMapping({ context: "Vertical", qboClass: "40 Vertical" });
  repo.seedClassMapping({ context: "Disposition", qboClass: "80 Disposition" });
  repo.seedClassMapping({ context: "Operations", qboClass: "90 Operations" });
  repo.seedClassMapping({ context: "REALM_B", qboClass: "90 Parent Overhead" });
}

describe("Phase derivation + real Class list resolution", () => {
  it("derives the phase suffix from a project:phase string", () => {
    assert.equal(derivePhaseFromProject("Madison Park:Vertical"), "Vertical");
    assert.equal(derivePhaseFromProject("12SB Hunters Landing:Acquisition"), "Acquisition");
    assert.equal(derivePhaseFromProject("Dominus:Operations"), "Operations");
  });

  it("returns undefined (never guesses) when the project has no ':phase' suffix", () => {
    assert.equal(derivePhaseFromProject("Madison Park"), undefined);
    assert.equal(derivePhaseFromProject("Madison Park:"), undefined);
  });

  it("resolves the real Class for every documented phase", async () => {
    const repo = new InMemoryProofRailRepository();
    seedRealClassList(repo);

    for (const [phase, expected] of [
      ["Acquisition", "00 Acquisition"],
      ["Sitework", "20 Sitework"],
      ["Vertical", "40 Vertical"],
      ["Disposition", "80 Disposition"],
      ["Operations", "90 Operations"],
    ] as const) {
      const result = await repo.resolveQboClass({ entity: "Madison", project: `Madison Park:${phase}`, item: "003 Concrete", vendor: "GC - Elite", context: phase });
      assert.equal(result, expected, `phase ${phase} should resolve to ${expected}`);
    }
  });

  it("halts (undefined) on an undocumented phase name - never guesses a new Class", async () => {
    const repo = new InMemoryProofRailRepository();
    seedRealClassList(repo);
    const result = await repo.resolveQboClass({ entity: "Madison", project: "Madison Park:MadeUpPhase", item: "003 Concrete", vendor: "GC - Elite", context: "MadeUpPhase" });
    assert.equal(result, undefined);
  });
});

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
