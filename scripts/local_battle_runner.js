const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const {spawn} = require("node:child_process");

const {BattleStream, Dex, Teams} = require("pokemon-showdown");

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const format = args.format || "gen9ou";
  const simulatorFormat = resolveSimulatorFormat(format);
  const teamAPath = required(args, "team-a");
  const teamBPath = required(args, "team-b");
  const seed = parseSeed(args.seed);
  const battleId = args["battle-id"] || `local-${Date.now()}`;
  const agentAName = args["agent-a"] || "pokebrain-v1";
  const agentBName = args["agent-b"] || "random";
  const maximumTurns = Number(args["maximum-turns"] || 500);
  const decisionTimeoutMs = Number(args["decision-timeout-ms"] || 10000);
  const runDir = createRunDir(battleId);
  const logger = createLogger(runDir);

  const teamA = packTeam(teamAPath, format);
  const teamB = packTeam(teamBPath, format);
  const agents = {
    p1: createAgent(agentAName, args.python || defaultPythonCommand(), seed, {
      battleId,
      format,
      runDir,
      playerId: "p1",
    }),
    p2: createAgent(agentBName, args.python || defaultPythonCommand(), seed.map((value) => value + 17), {
      battleId,
      format,
      runDir,
      playerId: "p2",
    }),
  };
  for (const agent of Object.values(agents)) {
    if (typeof agent.ready === "function") {
      await agent.ready();
    }
  }
  const battle = new BattleStream();
  const context = {
    battleId,
    format,
    generation: inferGeneration(format),
    agentAName,
    agentBName,
    maximumTurns,
    decisionTimeoutMs,
    turn: 0,
    requests: {},
    pendingPreviewChoices: {},
    previewReady: false,
    finished: false,
    winner: null,
    terminationReason: null,
    decisionErrors: {p1: 0, p2: 0},
    illegalActions: {p1: 0, p2: 0},
    decisionTimeMs: {p1: 0, p2: 0},
    decisionCounts: {p1: 0, p2: 0},
    logger,
  };

  const keepAlive = setInterval(() => {}, 1000);
  try {
    const battleLoop = consumeBattleStream(battle, context, agents);
    battle.write(`>start ${JSON.stringify({formatid: simulatorFormat, seed})}`);
    battle.write(`>player p1 ${JSON.stringify({name: "PokeBrain", team: teamA})}`);
    battle.write(`>player p2 ${JSON.stringify({name: "Opponent", team: teamB})}`);

    await battleLoop;
  } finally {
    clearInterval(keepAlive);
    for (const agent of Object.values(agents)) {
      if (typeof agent.close === "function") {
        await agent.close();
      }
    }
  }
  logger.writeResult({
    battle_id: battleId,
    format,
    seed,
    agent_a: agentAName,
    agent_b: agentBName,
    winner: context.winner,
    turns: context.turn,
    illegal_action_count_a: context.illegalActions.p1,
    illegal_action_count_b: context.illegalActions.p2,
    decision_error_count_a: context.decisionErrors.p1,
    decision_error_count_b: context.decisionErrors.p2,
    average_decision_time_ms_a: averageDecisionTime(context, "p1"),
    average_decision_time_ms_b: averageDecisionTime(context, "p2"),
    average_decision_time_ms: averageDecisionTime(context, "p1", "p2"),
    termination_reason: context.terminationReason || "stream_end",
    run_dir: runDir,
  });

  console.log("");
  console.log("Resultado:");
  if (context.winner) {
    console.log(`${context.winner} venceu em ${context.turn} turnos.`);
  } else {
    console.log(`Batalha terminou em ${context.turn} turnos.`);
  }
  console.log(`Logs: ${runDir}`);
}

async function consumeBattleStream(battle, context, agents) {
  for await (const chunk of battle) {
    context.logger.protocol(chunk);
    const message = parseStreamChunk(chunk);
    for (const line of message.lines) {
      handlePublicLine(line, context);
    }
    flushPreviewChoices(battle, context);

    if (message.kind === "sideupdate" && message.playerId) {
      await handleSideUpdate(message.playerId, message.lines, battle, context, agents);
    }

    if (context.finished) {
      battle.writeEnd();
      break;
    }
  }
  if (!context.finished) {
    context.logger.decision({
      turn: context.turn,
      event: "stream-ended-before-result",
      pending_preview_choices: context.pendingPreviewChoices,
    });
    context.terminationReason = context.terminationReason || "stream_end";
  }
}

async function handleSideUpdate(playerId, lines, battle, context, agents) {
  for (const line of lines) {
    if (line.startsWith("|error|")) {
      context.illegalActions[playerId] += 1;
      context.logger.decision({
        turn: context.turn,
        player_id: playerId,
        event: "showdown-error",
        line,
      });
      const recoveryChoice = `>${playerId} default`;
      context.logger.decision({
        turn: context.turn,
        player_id: playerId,
        event: "showdown-error-recovery",
        choice: recoveryChoice,
      });
      battle.write(recoveryChoice);
      continue;
    }
    if (!line.startsWith("|request|")) {
      continue;
    }
    const request = JSON.parse(line.slice("|request|".length));
    const normalized = normalizeRequest(playerId, request);
    context.requests[playerId] = normalized;
    context.logger.state({
      turn: context.turn,
      player_id: playerId,
      request: normalized,
    });

    if (normalized.requestType === "wait") {
      continue;
    }

    const decisionRequest = {
      type: "decision-request",
      battle_id: context.battleId,
      format_id: context.format,
      generation: context.generation,
      turn: context.turn,
      player_id: playerId,
      player: normalized,
      opponent: context.requests[playerId === "p1" ? "p2" : "p1"] || null,
      observed_opponent: sanitizeOpponentRequest(context.requests[playerId === "p1" ? "p2" : "p1"] || null),
      legal_actions: normalized.legalActions,
    };

    let decision;
    try {
      decision = await withTimeout(
        agents[playerId].decide(decisionRequest),
        context.decisionTimeoutMs,
        `Agent ${playerId} exceeded ${context.decisionTimeoutMs}ms decision timeout.`,
      );
    } catch (error) {
      context.decisionErrors[playerId] += 1;
      context.logger.decision({
        turn: context.turn,
        player_id: playerId,
        event: "decision-error",
        error: error.message,
      });
      if (error.code === "DECISION_TIMEOUT" && typeof agents[playerId].restart === "function") {
        await agents[playerId].restart();
      }
      decision = fallbackDecision(normalized.legalActions, error);
    }
    const choice = serializeChoice(playerId, decision.action);
    const decisionTimeMs = Number(decision.decision_time_ms || 0);
    if (decisionTimeMs > 0) {
      context.decisionTimeMs[playerId] += decisionTimeMs;
      context.decisionCounts[playerId] += 1;
    }

    context.logger.decision({
      turn: context.turn,
      player_id: playerId,
      legal_actions: normalized.legalActions,
      selected_action: decision.action,
      choice,
      reasons: decision.reasons || [],
      risks: decision.risks || [],
      score: decision.score ?? null,
      alternatives: decision.alternatives || [],
      metrics: decision.metrics || {},
      decision_time_ms: decision.decision_time_ms ?? null,
    });
    console.log(`Turno ${context.turn || "preview"} - ${playerId} escolheu: ${describeAction(decision.action, normalized)}`);
    if (normalized.requestType === "team-preview") {
      context.pendingPreviewChoices[playerId] = choice;
      flushPreviewChoices(battle, context);
      continue;
    }
    battle.write(choice);
  }
}

function parseStreamChunk(chunk) {
  const lines = chunk.split("\n").filter(Boolean);
  const kind = lines[0];
  if (kind === "sideupdate") {
    return {kind, playerId: lines[1], lines: lines.slice(2)};
  }
  return {kind, playerId: null, lines: lines.slice(1)};
}

function handlePublicLine(line, context) {
  if (line.startsWith("|turn|")) {
    context.turn = Number(line.split("|")[2] || context.turn);
    if (context.turn >= context.maximumTurns) {
      context.finished = true;
      context.terminationReason = "turn_limit";
      context.winner = null;
    }
  } else if (line.startsWith("|teampreview")) {
    context.previewReady = true;
  } else if (line.startsWith("|win|")) {
    context.finished = true;
    context.winner = line.split("|")[2] || null;
    context.terminationReason = "win";
  } else if (line === "|tie" || line.startsWith("|tie|")) {
    context.finished = true;
    context.winner = null;
    context.terminationReason = "tie";
  }
}

function flushPreviewChoices(battle, context) {
  if (!context.previewReady) {
    return;
  }
  for (const playerId of ["p1", "p2"]) {
    const choice = context.pendingPreviewChoices[playerId];
    if (choice) {
      context.logger.decision({
        turn: context.turn,
        player_id: playerId,
        event: "write-preview-choice",
        choice,
      });
      battle.write(choice);
      delete context.pendingPreviewChoices[playerId];
    }
  }
}

function normalizeRequest(playerId, request) {
  const requestType = getRequestType(request);
  return {
    playerId,
    requestId: request.rqid,
    requestType,
    active: normalizeActive(request.active || []),
    team: normalizeTeam(request.side?.pokemon || []),
    legalActions: getLegalActions(request),
  };
}

function getRequestType(request) {
  if (request.wait) return "wait";
  if (request.teamPreview) return "team-preview";
  if (request.forceSwitch && request.forceSwitch.some(Boolean)) return "forced-switch";
  return "move";
}

function normalizeActive(activeList) {
  return activeList.map((active) => ({
    moves: (active.moves || []).map((move, index) => ({
      slot: index + 1,
      id: move.id,
      name: move.move,
      pp: move.pp,
      maxpp: move.maxpp,
      disabled: Boolean(move.disabled),
      target: move.target || null,
    })),
    canTerastallize: active.canTerastallize || null,
  }));
}

function normalizeTeam(pokemonList) {
  return pokemonList.map((pokemon, index) => ({
    slot: index + 1,
    ident: pokemon.ident,
    speciesId: extractSpeciesId(pokemon.details || pokemon.ident || ""),
    details: pokemon.details || "",
    condition: pokemon.condition || "0 fnt",
    active: Boolean(pokemon.active),
    fainted: String(pokemon.condition || "").endsWith(" fnt"),
    stats: pokemon.stats || {},
    moves: pokemon.moves || [],
    abilityId: pokemon.baseAbility || pokemon.ability || null,
    itemId: pokemon.item || null,
    teraType: pokemon.teraType || null,
  }));
}

function sanitizeOpponentRequest(request) {
  if (!request) {
    return null;
  }
  return {
    playerId: request.playerId,
    requestId: request.requestId,
    requestType: request.requestType,
    active: [],
    legalActions: [],
    team: (request.team || []).map((pokemon) => ({
      slot: pokemon.slot,
      ident: pokemon.ident,
      speciesId: pokemon.speciesId,
      details: pokemon.details,
      condition: pokemon.condition,
      active: pokemon.active,
      fainted: pokemon.fainted,
      stats: {},
      moves: [],
      abilityId: null,
      itemId: null,
      teraType: null,
    })),
  };
}

function getLegalActions(request) {
  const sidePokemon = request.side?.pokemon || [];

  if (request.wait) {
    return [];
  }

  if (request.teamPreview) {
    return [{
      type: "team",
      slot: 1,
      order: teamPreviewOrder(sidePokemon),
    }];
  }

  const activeList = request.active || [];
  const forcedSwitch = request.forceSwitch || [];
  if (activeList.length > 1 || forcedSwitch.length > 1) {
    return withDefaultAction(getCompoundLegalActions(request, activeList, sidePokemon));
  }

  const actions = [];
  const active = request.active?.[0];
  if (active) {
    active.moves.forEach((move, index) => {
      if (!move.disabled && (move.pp === undefined || move.pp > 0)) {
        const action = {
          type: "move",
          slot: index + 1,
          moveId: move.id,
          canTerastallize: Boolean(active.canTerastallize),
        };
        actions.push(action);
        if (active.canTerastallize) {
          actions.push({...action, terastallize: true});
        }
      }
    });
  }

  const forcedSwitchAny = request.forceSwitch && request.forceSwitch.some(Boolean);
  const canSwitch = forcedSwitchAny || !active?.trapped;
  if (canSwitch) {
    sidePokemon.forEach((pokemon, index) => {
      if (!pokemon.active && !String(pokemon.condition || "").endsWith(" fnt")) {
        actions.push({
          type: "switch",
          slot: index + 1,
          switchSpeciesId: extractSpeciesId(pokemon.details || pokemon.ident || ""),
        });
      }
    });
  }

  return withDefaultAction(actions);
}

function getCompoundLegalActions(request, activeList, sidePokemon) {
  const forcedSwitch = request.forceSwitch || [];
  const activePokemon = sidePokemon.filter((pokemon) => pokemon.active);
  const slotCount = Math.max(activeList.length, forcedSwitch.length);
  const perActiveChoices = Array.from({length: slotCount}, (_value, activeIndex) => {
    const active = activeList[activeIndex] || {};
    const activeSlot = activeIndex + 1;
    const sideActive = activePokemon[activeIndex];
    if (forcedSwitch[activeIndex]) {
      const choices = switchChoices(active, activeSlot, sidePokemon);
      return choices.length ? choices : [{type: "pass", activeSlot}];
    }
    if (sideActive && String(sideActive.condition || "").endsWith(" fnt")) {
      return [{type: "pass", activeSlot}];
    }
    if (forcedSwitch.some(Boolean)) {
      return [{type: "pass", activeSlot}];
    }
    const choices = [];
    (active.moves || []).forEach((move, index) => {
      if (!move.disabled && (move.pp === undefined || move.pp > 0)) {
        const target = defaultTargetForMove(move.target, activeIndex, activePokemon);
        if (target === INVALID_TARGET) {
          return;
        }
        const choice = {
          type: "move",
          activeSlot,
          slot: index + 1,
          moveId: move.id,
          target,
          canTerastallize: Boolean(active.canTerastallize),
        };
        choices.push(choice);
        if (active.canTerastallize) {
          choices.push({...choice, terastallize: true});
        }
      }
    });
    if (!active.trapped) {
      choices.push(...switchChoices(active, activeSlot, sidePokemon));
    }
    return choices.length ? choices : [{type: "pass", activeSlot}];
  });

  return cartesian(perActiveChoices)
    .filter((choices) => !hasDuplicateSwitchTarget(choices))
    .filter((choices) => choices.filter((choice) => choice.terastallize).length <= 1)
    .map((choices) => ({type: "compound", choices}));
}

function switchChoices(_active, activeSlot, sidePokemon) {
  return sidePokemon
    .map((pokemon, index) => ({pokemon, slot: index + 1}))
    .filter(({pokemon}) => !pokemon.active && !String(pokemon.condition || "").endsWith(" fnt"))
    .map(({pokemon, slot}) => ({
      type: "switch",
      activeSlot,
      slot,
      switchSpeciesId: extractSpeciesId(pokemon.details || pokemon.ident || ""),
    }));
}

function serializeChoice(playerId, action) {
  if (action.type === "compound") {
    return `>${playerId} ${action.choices.map((choice) => serializeChoicePart(choice)).join(", ")}`;
  }
  if (action.type === "default") return `>${playerId} default`;
  if (action.type === "move") return `>${playerId} move ${action.slot}${action.terastallize ? " terastallize" : ""}`;
  if (action.type === "switch") return `>${playerId} switch ${action.slot}`;
  if (action.type === "team") return `>${playerId} team ${action.order || action.slot}`;
  throw new Error(`Unsupported action: ${JSON.stringify(action)}`);
}

function serializeChoicePart(action) {
  if (action.type === "move") {
    const target = action.target === null || action.target === undefined ? "" : ` ${action.target}`;
    const tera = action.terastallize ? " terastallize" : "";
    return `move ${action.slot}${target}${tera}`;
  }
  if (action.type === "switch") return `switch ${action.slot}`;
  if (action.type === "pass") return "pass";
  throw new Error(`Unsupported compound action part: ${JSON.stringify(action)}`);
}

function describeAction(action, request) {
  if (action.type === "compound") {
    return action.choices.map((choice) => describeAction(choice, request)).join(" + ");
  }
  if (action.type === "move") {
    const activeIndex = Math.max(0, Number(action.activeSlot || 1) - 1);
    const move = request.active[activeIndex]?.moves?.find((candidate) => candidate.slot === action.slot);
    const name = move ? move.name : `move ${action.slot}`;
    return action.terastallize ? `${name} + Tera` : name;
  }
  if (action.type === "switch") {
    const pokemon = request.team.find((candidate) => candidate.slot === action.slot);
    return pokemon ? `trocar para ${pokemon.speciesId}` : `switch ${action.slot}`;
  }
  if (action.type === "pass") return "pass";
  if (action.type === "default") return "default";
  return `team ${action.order || action.slot}`;
}

class PythonAgent {
  constructor(command, metadata) {
    this.command = command;
    this.metadata = metadata;
    this.start();
  }

  start() {
    const child = spawn(this.command, ["-m", "pokebrain.local_agent"], {
      cwd: process.cwd(),
      stdio: ["pipe", "pipe", "inherit"],
    });
    this.process = child;
    this.pending = [];
    this.readyPromise = new Promise((resolve) => {
      this._resolveReady = resolve;
    });
    this.readline = readline.createInterface({input: child.stdout});
    this.readline.on("line", (line) => this.handleLine(line));
    child.on("exit", (code) => {
      if (this.process !== child) {
        return;
      }
      while (this.pending.length) {
        this.pending.shift().reject(new Error(`Python agent exited with code ${code}.`));
      }
    });
    this.send({type: "hello", ...this.metadata}).then(() => this._resolveReady());
  }

  handleLine(line) {
    const next = this.pending.shift();
    if (!next) return;
    try {
      next.resolve(JSON.parse(line));
    } catch (error) {
      next.reject(error);
    }
  }

  ready() {
    return this.readyPromise;
  }

  async decide(request) {
    await this.readyPromise;
    const response = await this.send(request);
    if (response.type !== "decision") {
      throw new Error(`Unexpected agent response: ${JSON.stringify(response)}`);
    }
    return response;
  }

  send(payload) {
    return new Promise((resolve, reject) => {
      this.pending.push({resolve, reject});
      this.process.stdin.write(`${JSON.stringify(payload)}\n`);
    });
  }

  async close() {
    try {
      await this.send({type: "shutdown"});
    } catch (_error) {
      // Process may already be gone after a battle error.
    }
    this.process.stdin.end();
  }

  async restart() {
    this.kill();
    this.start();
    await this.ready();
  }

  kill() {
    this.pending = [];
    try {
      this.readline.close();
    } catch (_error) {
      // Readline may already be closed.
    }
    try {
      this.process.kill();
    } catch (_error) {
      // Process may already be gone.
    }
  }
}

class RandomAgent {
  constructor(seed) {
    this.state = seed.reduce((sum, value) => sum + Number(value), 1) || 1;
  }

  decide(request) {
    const actions = request.legal_actions || [];
    if (!actions.length) {
      return {type: "decision", action: {type: "team", slot: 1, order: "1"}};
    }
    const index = Math.floor(this.random() * actions.length);
    return {
      type: "decision",
      action: actions[index],
      reasons: ["RandomAgent picked a legal action."],
    };
  }

  random() {
    this.state = (this.state * 1664525 + 1013904223) >>> 0;
    return this.state / 0x100000000;
  }
}

class MaxDamageAgent {
  constructor(seed) {
    this.randomAgent = new RandomAgent(seed);
  }

  decide(request) {
    const actions = request.legal_actions || [];
    if (!actions.length) {
      return this.randomAgent.decide(request);
    }

    const moveActions = actions.filter((action) => action.type === "move");
    if (!moveActions.length) {
      return this.randomAgent.decide(request);
    }

    const best = moveActions
      .map((action) => ({action, score: moveScore(action.moveId)}))
      .sort((left, right) => right.score - left.score)[0];
    return {
      type: "decision",
      action: best.action,
      reasons: [`MaxDamageAgent selected highest base-power move (${best.score}).`],
      score: best.score,
    };
  }
}

function moveScore(moveId) {
  const move = Dex.moves.get(moveId);
  if (!move.exists || move.category === "Status") {
    return 0;
  }
  const accuracy = move.accuracy === true ? 100 : Number(move.accuracy || 100);
  return Number(move.basePower || 0) * (accuracy / 100);
}

function createAgent(name, pythonCommand, seed, metadata) {
  if (name === "previous-version" && process.env.POKEBRAIN_PREVIOUS_AGENT_COMMAND) {
    return new PythonAgent(process.env.POKEBRAIN_PREVIOUS_AGENT_COMMAND, {...metadata, agentName: "pokebrain-v1", seed});
  }
  if (["pokebrain-v1", "pokebrain", "previous-version", "pokebrain-previous", "max-damage", "search-v1", "search-v1-cache", "search-v2-belief", "search-v2-belief-shared", "search-v2-belief-layered", "search-v3-policy", "search-v3-policy-calibrated-shadow", "search-v4-policy-calibrated"].includes(name)) {
    return new PythonAgent(pythonCommand, {...metadata, agentName: name, seed});
  }
  if (name === "random") {
    return new RandomAgent(seed);
  }
  if (name === "max-damage") {
    return new MaxDamageAgent(seed);
  }
  throw new Error(`Unknown agent: ${name}`);
}

function averageDecisionTime(context, ...playerIds) {
  const totalMs = playerIds.reduce((sum, playerId) => sum + context.decisionTimeMs[playerId], 0);
  const totalCount = playerIds.reduce((sum, playerId) => sum + context.decisionCounts[playerId], 0);
  return totalCount ? totalMs / totalCount : 0;
}

function fallbackDecision(legalActions, error) {
  const action = legalActions.find((candidate) => candidate.type === "compound")
    || legalActions.find((candidate) => candidate.type === "default")
    || legalActions.find((candidate) => candidate.type === "move")
    || legalActions.find((candidate) => candidate.type === "switch")
    || legalActions[0]
    || {type: "team", slot: 1, order: "1"};
  return {
    type: "decision",
    action,
    reasons: [`Fallback after decision error: ${error.message}`],
  };
}

function withTimeout(promise, timeoutMs, message) {
  if (!timeoutMs || timeoutMs <= 0) {
    return promise;
  }
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      const error = new Error(message);
      error.code = "DECISION_TIMEOUT";
      reject(error);
    }, timeoutMs);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function packTeam(teamPath, format) {
  const text = fs.readFileSync(teamPath, "utf8");
  const team = Teams.import(text);
  if (!team) throw new Error(`Could not parse team: ${teamPath}`);
  return Teams.pack(team);
}

function resolveSimulatorFormat(format) {
  if (isChampionsFormat(format)) {
    const resolved = Dex.formats.get(format);
    if (!resolved.exists || resolved.mod !== "champions") {
      throw new Error(
        `Champions format ${format} is not available in the installed Pokemon Showdown. ` +
        "Install a current Showdown build with data/mods/champions.",
      );
    }
  }
  return format;
}

function isChampionsFormat(format) {
  return String(format).toLowerCase().includes("championsvgc");
}

const INVALID_TARGET = Symbol("invalid-target");

function teamPreviewOrder(sidePokemon) {
  const activeSlots = sidePokemon
    .map((pokemon, index) => ({pokemon, slot: index + 1}))
    .filter(({pokemon}) => !String(pokemon.condition || "").endsWith(" fnt"))
    .slice(0, 4)
    .map(({slot}) => String(slot));
  return activeSlots.length ? activeSlots.join("") : "1234";
}

function defaultTargetForMove(targetType, activeIndex = 0, activePokemon = []) {
  if (["normal", "any", "adjacentFoe", "randomNormal"].includes(targetType)) {
    return 1;
  }
  if (targetType === "adjacentAlly") {
    return liveAllyTarget(activeIndex, activePokemon);
  }
  if (targetType === "adjacentAllyOrSelf") {
    return liveAllyTarget(activeIndex, activePokemon) === INVALID_TARGET ? null : liveAllyTarget(activeIndex, activePokemon);
  }
  return null;
}

function liveAllyTarget(activeIndex, activePokemon) {
  const allyIndex = activePokemon.findIndex((pokemon, index) => (
    index !== activeIndex && !String(pokemon.condition || "").endsWith(" fnt")
  ));
  return allyIndex === -1 ? INVALID_TARGET : -(allyIndex + 1);
}

function cartesian(groups) {
  return groups.reduce(
    (accumulator, group) => accumulator.flatMap((prefix) => group.map((item) => [...prefix, item])),
    [[]],
  );
}

function hasDuplicateSwitchTarget(choices) {
  const switchSlots = choices
    .filter((choice) => choice.type === "switch")
    .map((choice) => choice.slot);
  return new Set(switchSlots).size !== switchSlots.length;
}

function withDefaultAction(actions) {
  return actions.length ? actions : [{type: "default"}];
}

function createLogger(runDir) {
  return {
    protocol: (chunk) => fs.appendFileSync(path.join(runDir, "protocol.log"), chunk),
    decision: (entry) => fs.appendFileSync(path.join(runDir, "decisions.jsonl"), `${JSON.stringify(entry)}\n`),
    state: (entry) => fs.appendFileSync(path.join(runDir, "states.jsonl"), `${JSON.stringify(entry)}\n`),
    writeResult: (data) => fs.writeFileSync(path.join(runDir, "result.json"), `${JSON.stringify(data, null, 2)}\n`),
  };
}

function createRunDir(battleId) {
  const now = new Date();
  const date = now.toISOString().slice(0, 10);
  const runDir = path.join("runs", date, battleId);
  fs.mkdirSync(runDir, {recursive: true});
  fs.writeFileSync(path.join(runDir, "metadata.json"), `${JSON.stringify({battle_id: battleId, created_at: now.toISOString()}, null, 2)}\n`);
  return runDir;
}

function parseSeed(value) {
  if (!value) return [123, 456, 789, 101112];
  const seed = String(value).split(",").map((part) => Number(part.trim()));
  if (seed.length !== 4 || seed.some((part) => !Number.isInteger(part))) {
    throw new Error("--seed must contain four comma-separated integers.");
  }
  return seed;
}

function extractSpeciesId(details) {
  const species = String(details).split(",")[0].replace(/^p[12][a-z]?:\s*/, "");
  return toId(species);
}

function toId(value) {
  return String(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function inferGeneration(format) {
  const match = String(format).match(/gen([0-9]+)/i);
  return match ? Number(match[1]) : 9;
}

function defaultPythonCommand() {
  return process.platform === "win32" ? ".\\.venv\\bin\\python.exe" : "./.venv/bin/python";
}

function parseArgs(argv) {
  const args = {};
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
    }
  }
  return args;
}

function required(args, key) {
  if (!args[key]) throw new Error(`Missing --${key}.`);
  return args[key];
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
