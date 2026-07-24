const fs = require("node:fs");
const path = require("node:path");

const DEFAULT_OUTPUT = path.join("data", "normalized", "v1");
const SCHEMA_VERSION = 1;

function main() {
  const args = parseArgs(process.argv.slice(2));

  if (args.help) {
    printHelp();
    return;
  }

  const outputDir = args.output || DEFAULT_OUTPUT;
  const Dex = loadDex(args["showdown-dir"]);
  const sourceVersion = getShowdownVersion();

  fs.mkdirSync(outputDir, { recursive: true });

  const pokemon = uniqueById(exportPokemon(Dex));
  const moves = uniqueById(exportMoves(Dex));
  const abilities = uniqueById(exportAbilities(Dex));
  const items = uniqueById(exportItems(Dex));
  const formats = uniqueById(exportFormats(Dex));
  const learnsets = exportLearnsets(Dex, new Set(pokemon.map((row) => row.id)), new Set(moves.map((row) => row.id)));
  const aliases = exportAliases(Dex);

  writeJson(outputDir, "pokemon.json", pokemon);
  writeJson(outputDir, "species.json", pokemon);
  writeJson(outputDir, "moves.json", moves);
  writeJson(outputDir, "abilities.json", abilities);
  writeJson(outputDir, "items.json", items);
  writeJson(outputDir, "formats.json", formats);
  writeJson(outputDir, "learnsets.json", learnsets);
  writeJson(outputDir, "aliases.json", aliases);
  writeJson(outputDir, "metadata.json", {
    source: "pokemon-showdown",
    source_commit: sourceVersion,
    imported_at: new Date().toISOString(),
    schema_version: SCHEMA_VERSION,
    record_counts: {
      species: pokemon.length,
      moves: moves.length,
      abilities: abilities.length,
      items: items.length,
      formats: formats.length,
      learnsets: learnsets.length,
      aliases: aliases.length,
    },
  });

  console.log(`Exported Pokemon: ${pokemon.length}`);
  console.log(`Exported Moves: ${moves.length}`);
  console.log(`Exported Abilities: ${abilities.length}`);
  console.log(`Exported Items: ${items.length}`);
  console.log(`Exported Formats: ${formats.length}`);
  console.log(`Exported Learnsets: ${learnsets.length}`);
  console.log(`Exported Aliases: ${aliases.length}`);
  console.log(`Output: ${outputDir}`);
}

function loadDex(showdownDir) {
  const errors = [];
  const candidates = [];

  if (showdownDir) {
    const absoluteDir = path.resolve(showdownDir);
    candidates.push(path.join(absoluteDir, "sim", "dex"));
    candidates.push(path.join(absoluteDir, "dist", "sim", "dex"));
  }

  candidates.push("pokemon-showdown");
  candidates.push("pokemon-showdown/dist/sim/dex");

  for (const candidate of candidates) {
    try {
      const loaded = require(candidate);
      const Dex = loaded.Dex || loaded.dex || loaded.default || loaded;
      if (Dex && Dex.species && Dex.moves && Dex.abilities && Dex.items) {
        return Dex;
      }
      errors.push(`${candidate}: module loaded, but Dex shape was not recognized`);
    } catch (error) {
      errors.push(`${candidate}: ${error.message}`);
    }
  }

  throw new Error(
    [
      "Could not load Pokemon Showdown Dex.",
      "Run `npm install` or pass --showdown-dir pointing to a built Showdown package.",
      "",
      ...errors.map((error) => `- ${error}`),
    ].join("\n")
  );
}

function exportPokemon(Dex) {
  return Dex.species.all().map((species) => ({
    id: species.id,
    name: species.name,
    national_dex: numberOrNull(species.num),
    generation: numberOrNull(species.gen),
    types: species.types || [],
    base_stats: species.baseStats || {},
    abilities: species.abilities || {},
    height_m: numberOrNull(species.heightm),
    weight_kg: numberOrNull(species.weightkg),
    base_species: species.baseSpecies && species.baseSpecies !== species.name ? toId(species.baseSpecies) : null,
    forme: species.forme || null,
  }));
}

function exportMoves(Dex) {
  return Dex.moves.all().map((move) => ({
    id: move.id,
    name: move.name,
    type: move.type || null,
    category: move.category || null,
    power: numberOrNull(move.basePower),
    accuracy: move.accuracy === true ? null : numberOrNull(move.accuracy),
    pp: numberOrNull(move.pp),
    priority: numberOrNull(move.priority) || 0,
  }));
}

function exportAbilities(Dex) {
  return Dex.abilities.all().map((ability) => ({
    id: ability.id,
    name: ability.name,
    description: ability.shortDesc || ability.desc || null,
  }));
}

function exportItems(Dex) {
  return Dex.items.all().map((item) => ({
    id: item.id,
    name: item.name,
    description: item.shortDesc || item.desc || null,
  }));
}

function exportFormats(Dex) {
  if (!Dex.formats || typeof Dex.formats.all !== "function") {
    return [];
  }

  return Dex.formats.all().map((format) => ({
    id: format.id,
    name: format.name,
    generation: numberOrNull(format.gen) || inferGeneration(format.id, format.name),
    ruleset: format.ruleset || [],
  })).filter((format) => format.generation !== null);
}

function exportLearnsets(Dex, speciesIds, moveIds) {
  const learnsets = Dex.data && Dex.data.Learnsets ? Dex.data.Learnsets : {};
  const rows = [];

  for (const [pokemonId, learnsetData] of Object.entries(learnsets)) {
    if (!speciesIds.has(pokemonId)) {
      continue;
    }
    const learnset = learnsetData.learnset || {};
    for (const [moveId, sources] of Object.entries(learnset)) {
      if (!moveIds.has(moveId)) {
        continue;
      }
      for (const generation of generationsFromSources(sources)) {
        rows.push({
          pokemon_id: pokemonId,
          move_id: moveId,
          generation,
        });
      }
    }
  }

  return rows;
}

function exportAliases(Dex) {
  const aliases = Dex.data && Dex.data.Aliases ? Dex.data.Aliases : {};
  return Object.entries(aliases).map(([alias, targetId]) => ({
    alias,
    target_id: String(targetId),
  }));
}

function generationsFromSources(sources) {
  const generations = new Set();
  if (!Array.isArray(sources)) {
    return generations;
  }

  for (const source of sources) {
    if (typeof source === "string" && /^[0-9]/.test(source)) {
      generations.add(Number(source[0]));
    }
  }

  return generations;
}

function inferGeneration(id, name) {
  const text = `${id || ""} ${name || ""}`;
  const match = text.match(/gen([0-9])/i);
  return match ? Number(match[1]) : null;
}

function numberOrNull(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function getShowdownVersion() {
  try {
    const packageJson = require("pokemon-showdown/package.json");
    return `npm:pokemon-showdown@${packageJson.version}`;
  } catch (_error) {
    return "unknown";
  }
}

function toId(value) {
  return String(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function writeJson(outputDir, filename, data) {
  const outputPath = path.join(outputDir, filename);
  fs.writeFileSync(outputPath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

function uniqueById(rows) {
  const seen = new Set();
  const uniqueRows = [];

  for (const row of rows) {
    if (seen.has(row.id)) {
      continue;
    }
    seen.add(row.id);
    uniqueRows.push(row);
  }

  return uniqueRows;
}

function parseArgs(argv) {
  const args = {};

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];

    if (arg === "--help" || arg === "-h") {
      args.help = true;
    } else if (arg.startsWith("--")) {
      const key = arg.slice(2);
      const next = argv[index + 1];
      if (!next || next.startsWith("--")) {
        args[key] = true;
      } else {
        args[key] = next;
        index += 1;
      }
    }
  }

  return args;
}

function printHelp() {
  console.log(`Usage: node scripts/export_showdown_with_node.js [options]

Options:
  --output DIR        Directory for normalized JSON. Default: ${DEFAULT_OUTPUT}
  --showdown-dir DIR  Optional local built Pokemon Showdown package/repo.
  -h, --help          Show this help.

The easiest setup is:
  npm install
  node scripts/export_showdown_with_node.js
`);
}

main();
