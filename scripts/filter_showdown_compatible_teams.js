const fs = require("node:fs");
const path = require("node:path");

const {Dex, Teams} = require("pokemon-showdown");

function main() {
  const args = parseArgs(process.argv.slice(2));
  const format = required(args, "format");
  const source = required(args, "source");
  const output = required(args, "output");
  const clean = Boolean(args.clean);
  const dex = Dex.forFormat(format);

  fs.mkdirSync(output, {recursive: true});
  if (clean) {
    for (const file of fs.readdirSync(output)) {
      if (file.endsWith(".txt")) {
        fs.rmSync(path.join(output, file));
      }
    }
  }

  const valid = [];
  const skipped = [];
  for (const filename of fs.readdirSync(source).filter((file) => file.endsWith(".txt")).sort()) {
    const sourcePath = path.join(source, filename);
    const text = fs.readFileSync(sourcePath, "utf8");
    const validation = validateTeam(dex, text);
    if (!validation.valid) {
      skipped.push({filename, reasons: validation.reasons});
      continue;
    }
    fs.copyFileSync(sourcePath, path.join(output, filename));
    valid.push(filename);
  }

  const manifest = {
    source,
    output,
    format,
    generated_at: new Date().toISOString(),
    valid_count: valid.length,
    skipped_count: skipped.length,
    valid,
    skipped,
  };
  fs.writeFileSync(
    path.join(output, "showdown_compatibility_manifest.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );

  console.log(`Source: ${source}`);
  console.log(`Output: ${output}`);
  console.log(`Format: ${format}`);
  console.log(`Compatible teams: ${valid.length}`);
  console.log(`Skipped teams: ${skipped.length}`);
  for (const entry of skipped.slice(0, 20)) {
    console.log(`- ${entry.filename}: ${entry.reasons.join("; ")}`);
  }
  if (skipped.length > 20) {
    console.log(`... ${skipped.length - 20} more skipped teams`);
  }
}

function validateTeam(dex, text) {
  const reasons = [];
  const team = Teams.import(text);
  if (!team || !team.length) {
    return {valid: false, reasons: ["Could not parse team text."]};
  }
  for (const set of team) {
    const label = set.species || set.name || "unknown";
    if (!dex.species.get(label).exists) {
      reasons.push(`Unidentified species: ${toId(label)}`);
    }
    if (set.item && !dex.items.get(set.item).exists) {
      reasons.push(`${label}: unidentified item ${toId(set.item)}`);
    }
    if (set.ability && !dex.abilities.get(set.ability).exists) {
      reasons.push(`${label}: unidentified ability ${toId(set.ability)}`);
    }
    for (const move of set.moves || []) {
      if (move && !dex.moves.get(move).exists) {
        reasons.push(`${label}: unidentified move ${toId(move)}`);
      }
    }
  }
  return {valid: reasons.length === 0, reasons};
}

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) {
      continue;
    }
    const key = arg.slice(2);
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      args[key] = true;
    } else {
      args[key] = next;
      index += 1;
    }
  }
  return args;
}

function required(args, key) {
  if (!args[key]) {
    throw new Error(`Missing --${key}.`);
  }
  return args[key];
}

function toId(value) {
  return String(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
}

main();
