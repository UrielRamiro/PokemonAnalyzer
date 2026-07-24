const fs = require("node:fs");

const {Dex, TeamValidator, Teams} = require("pokemon-showdown");
const {
  calculate,
  Field,
  Generations,
  Move,
  Pokemon,
} = require("@smogon/calc");

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const command = args._[0];

  try {
    if (command === "resolve") {
      writeJson(resolve(args));
    } else if (command === "validate-team") {
      writeJson(await validateTeam(args));
    } else if (command === "list-formats") {
      writeJson(listFormats());
    } else if (command === "calculate-damage") {
      writeJson(await calculateDamageCommand());
    } else if (command === "calculate-damage-batch") {
      writeJson(await calculateDamageBatchCommand());
    } else {
      throw new Error("Expected command: resolve, validate-team, list-formats, calculate-damage, or calculate-damage-batch.");
    }
  } catch (error) {
    writeJson({ok: false, error: error.message});
    process.exit(1);
  }
}

async function calculateDamageCommand() {
  const input = await readStdin();
  const request = JSON.parse(input);
  return calculateDamage(request);
}

async function calculateDamageBatchCommand() {
  const input = await readStdin();
  const request = JSON.parse(input);
  return {
    ok: true,
    type: "damage-batch-result",
    results: request.requests.map((entry) => ({
      requestId: entry.requestId,
      result: calculateDamage(entry.calculation),
    })),
  };
}

function calculateDamage(request) {
  const generationNumber = Number(request.generation);
  const generation = Generations.get(generationNumber);
  const attacker = buildCalcPokemon(generation, request.attacker);
  const defender = buildCalcPokemon(generation, request.defender);
  const move = new Move(generation, resolveCalcName(generation, "move", request.move));
  const field = buildField(request.field || {});
  const result = calculate(generation, attacker, defender, move, field);
  const damageRolls = normalizeDamageRolls(result.damage);
  const minimumDamage = damageRolls.length ? Math.min(...damageRolls) : 0;
  const maximumDamage = damageRolls.length ? Math.max(...damageRolls) : 0;
  const defenderMaxHp = defender.stats.hp || defender.curHP();

  return {
    ok: true,
    generation: generationNumber,
    attacker: attacker.name,
    defender: defender.name,
    move: move.name,
    damageRolls,
    minimumDamage,
    maximumDamage,
    defenderMaxHp,
    minimumPercent: percent(minimumDamage, defenderMaxHp),
    maximumPercent: percent(maximumDamage, defenderMaxHp),
    description: describeDamage(result, attacker, defender, move, maximumDamage),
  };
}

function describeDamage(result, attacker, defender, move, maximumDamage) {
  if (maximumDamage === 0) {
    return `${attacker.name} ${move.name} does no damage to ${defender.name}.`;
  }
  try {
    return result.desc();
  } catch (_error) {
    return `${attacker.name} ${move.name} vs. ${defender.name}: damage calculated.`;
  }
}

function buildCalcPokemon(generation, input) {
  return new Pokemon(generation, resolveCalcName(generation, "species", input.species), {
    level: input.level || 100,
    ability: input.ability ? resolveCalcName(generation, "ability", input.ability) : undefined,
    item: input.item ? resolveCalcName(generation, "item", input.item) : undefined,
    nature: input.nature,
    evs: input.evs,
    ivs: input.ivs,
    boosts: input.boosts,
    status: input.status,
    teraType: input.teraType,
    curHP: input.currentHp,
  });
}

function resolveCalcName(generation, kind, value) {
  if (!value) {
    return value;
  }
  const collection = {
    species: generation.species,
    move: generation.moves,
    ability: generation.abilities,
    item: generation.items,
  }[kind];
  const resolved = collection && collection.get(String(value));
  return resolved && resolved.name ? resolved.name : value;
}

function buildField(input) {
  const field = new Field({
    gameType: input.isDoubles ? "Doubles" : "Singles",
    weather: input.weather || undefined,
    terrain: input.terrain || undefined,
  });
  field.defenderSide.isReflect = Boolean(input.reflect);
  field.defenderSide.isLightScreen = Boolean(input.lightScreen);
  field.defenderSide.isAuroraVeil = Boolean(input.auroraVeil);
  field.attackerSide.isTailwind = Boolean(input.attackerTailwind);
  field.defenderSide.isTailwind = Boolean(input.defenderTailwind);
  field.attackerSide.isHelpingHand = Boolean(input.helpingHand);
  field.defenderSide.isFriendGuard = Boolean(input.friendGuard);
  return field;
}

function normalizeDamageRolls(damage) {
  if (Array.isArray(damage)) {
    if (Array.isArray(damage[0])) {
      return damage.flat().map(Number);
    }
    return damage.map(Number);
  }
  return [Number(damage)];
}

function percent(damage, hp) {
  if (!hp) {
    return 0;
  }
  return Math.round((damage / hp) * 1000) / 10;
}

function resolve(args) {
  const mod = required(args, "mod");
  const kind = required(args, "kind");
  const id = required(args, "id");
  const dex = Dex.mod(mod);

  if (kind === "species") {
    const species = dex.species.get(id);
    return {
      ok: true,
      kind,
      mod,
      found: Boolean(species.exists),
      data: species.exists ? serializeSpecies(species) : null,
    };
  }

  if (kind === "move") {
    const move = dex.moves.get(id);
    return {
      ok: true,
      kind,
      mod,
      found: Boolean(move.exists),
      data: move.exists ? serializeMove(move) : null,
    };
  }

  if (kind === "ability") {
    const ability = dex.abilities.get(id);
    return {
      ok: true,
      kind,
      mod,
      found: Boolean(ability.exists),
      data: ability.exists ? serializeAbility(ability) : null,
    };
  }

  if (kind === "item") {
    const item = dex.items.get(id);
    return {
      ok: true,
      kind,
      mod,
      found: Boolean(item.exists),
      data: item.exists ? serializeItem(item) : null,
    };
  }

  throw new Error(`Unsupported resolve kind: ${kind}.`);
}

async function validateTeam(args) {
  const format = required(args, "format");
  const teamText = await readTeamText(args);
  const team = teamText.includes("|") ? Teams.unpack(teamText) : Teams.import(teamText);

  if (!team) {
    return {
      ok: true,
      format,
      valid: false,
      problems: ["Could not parse team."],
    };
  }

  const validator = TeamValidator.get(format);
  const problems = validator.validateTeam(team) || [];

  return {
    ok: true,
    format,
    valid: problems.length === 0,
    problems,
  };
}

function listFormats() {
  const formats = Dex.formats.all().map((format) => ({
    id: format.id,
    name: format.name,
    generation: numberOrNull(format.gen) || inferGeneration(format.id, format.name),
    game_type: format.gameType || null,
    team: format.team || null,
    search_show: Boolean(format.searchShow),
    challenge_show: Boolean(format.challengeShow),
    ruleset: format.ruleset || [],
    banlist: format.banlist || [],
  }));

  return {
    ok: true,
    formats,
  };
}

function serializeSpecies(species) {
  return {
    id: species.id,
    name: species.name,
    national_dex: numberOrNull(species.num),
    generation: numberOrNull(species.gen),
    types: species.types || [],
    base_stats: species.baseStats || {},
    abilities: species.abilities || {},
    height_m: numberOrNull(species.heightm),
    weight_kg: numberOrNull(species.weightkg),
    base_species: species.baseSpecies || null,
    forme: species.forme || null,
  };
}

function serializeMove(move) {
  return {
    id: move.id,
    name: move.name,
    generation: numberOrNull(move.gen),
    type: move.type || null,
    category: move.category || null,
    power: numberOrNull(move.basePower),
    accuracy: move.accuracy === true ? null : numberOrNull(move.accuracy),
    pp: numberOrNull(move.pp),
  };
}

function serializeAbility(ability) {
  return {
    id: ability.id,
    name: ability.name,
    generation: numberOrNull(ability.gen),
    description: ability.shortDesc || ability.desc || null,
  };
}

function serializeItem(item) {
  return {
    id: item.id,
    name: item.name,
    generation: numberOrNull(item.gen),
    description: item.shortDesc || item.desc || null,
  };
}

async function readTeamText(args) {
  if (args["team-file"]) {
    return fs.readFileSync(args["team-file"], "utf8");
  }

  if (args.team) {
    return args.team;
  }

  return readStdin();
}

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => {
      resolve(data);
    });
    process.stdin.on("error", reject);
  });
}

function numberOrNull(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function inferGeneration(id, name) {
  const text = `${id || ""} ${name || ""}`;
  const match = text.match(/gen([0-9])/i);
  return match ? Number(match[1]) : null;
}

function required(args, key) {
  if (!args[key]) {
    throw new Error(`Missing --${key}.`);
  }
  return args[key];
}

function parseArgs(argv) {
  const args = {_: []};

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];

    if (arg.startsWith("--")) {
      const key = arg.slice(2);
      const next = argv[index + 1];
      if (!next || next.startsWith("--")) {
        args[key] = true;
      } else {
        args[key] = next;
        index += 1;
      }
    } else {
      args._.push(arg);
    }
  }

  return args;
}

function writeJson(data) {
  process.stdout.write(`${JSON.stringify(data, null, 2)}\n`);
}

main();
