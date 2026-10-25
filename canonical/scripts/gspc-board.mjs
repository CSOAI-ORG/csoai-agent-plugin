#!/usr/bin/env node
/**
 * Fetch the live GSPC board and print an honest summary.
 *
 * Never fills UNMEASURED as 0. A fetch failure is UNREACHABLE, not a cached score. Slot count and
 * measured count are two labelled numbers and are never summed. SEPARATED / TIE / UNTESTED are three
 * states and none is folded into another.
 *
 * This is measurement, not certification.
 *
 * MODES
 *   node gspc-board.mjs                 the board, once
 *   node gspc-board.mjs --axis=governance
 *                                        one axis, with the numbers that say how much to trust
 *                                        it: resolution (MDE), interval, separation test and p,
 *                                        fleet context, and the caveats the board already carries
 *   node gspc-board.mjs --watch[=10]    live: re-read the board and print ONLY what changed
 *   node gspc-board.mjs --json          the same payload as JSON, for scripts
 *
 * The --watch mode is the point: a board you read once is a snapshot, and a snapshot hides the
 * thing a measurement body exists to show — that the record moves, and how.
 */
"use strict";

const ORIGIN = process.env.GSPC_ORIGIN || "https://councilof.ai";
const URL = `${ORIGIN.replace(/\/$/, "")}/api/gspc`;

const argv = process.argv.slice(2);
const flag = (name) => argv.find((a) => a === `--${name}` || a.startsWith(`--${name}=`));
const value = (name) => {
  const found = flag(name);
  if (!found) return undefined;
  return found.includes("=") ? found.split("=").slice(1).join("=") : true;
};

function pad(value, width) {
  return String(value === null || value === undefined ? "—" : value).padEnd(width);
}

async function fetchBoard() {
  const response = await fetch(URL, { headers: { accept: "application/json" } });
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function summarise(board) {
  const axes = Array.isArray(board.axes) ? board.axes : [];
  const totals = board.totals || {};
  return {
    schema: board.schema || "unknown",
    slots: totals.axes ?? axes.length,
    measured: totals.measured_axes ?? null,
    public_count: totals.public_count ?? null,
    separation: totals.separation_public_count ?? null,
    measured_on: board.measured_on?.date ?? null,
    axes: axes.map((row) => ({
      axis: row.axis || row.name || "?",
      status: String(row.status || row.kind || "?").toUpperCase(),
      n: row.n ?? null,
      accuracy: row.accuracy ?? null,
      separation: row.separation ?? null,
      leader: row.leader ?? null,
    })),
  };
}

function fingerprint(summary) {
  return JSON.stringify({
    measured: summary.measured,
    public_count: summary.public_count,
    separation: summary.separation,
    axes: summary.axes.map((a) => [a.axis, a.status, a.n, a.accuracy, a.separation, a.leader]),
  });
}

function printBoard(board) {
  const axes = Array.isArray(board.axes) ? board.axes : [];
  const totals = board.totals || {};

  console.log(`GSPC board    schema=${board.schema || "unknown"}`);
  console.log(`source        ${URL}`);
  console.log(`slots         ${totals.axes ?? axes.length}  (declared positions on the board)`);
  console.log(
    `measurements  ${totals.measured_axes ?? "?"}  (real runs behind those slots)  — the two numbers are never summed`
  );
  if (totals.public_count) console.log(`public_count  ${totals.public_count}`);
  if (totals.separation_public_count) {
    console.log(`separation    ${totals.separation_public_count}`);
  }
  const stamp =
    board.living_stamp || (board.measured_on && board.measured_on.living_stamp) || null;
  if (stamp) {
    console.log(
      `stamp         updated=${stamp.updated || "?"}  signed=${stamp.signed ?? "?"}  state=${stamp.verification_state || "?"}`
    );
  }
  if (board.measured_on && board.measured_on.date) {
    console.log(`measured_on   ${board.measured_on.date}`);
  }

  const measured = [];
  const unmeasured = [];
  for (const row of axes) {
    const status = String(row.status || row.kind || "?").toUpperCase();
    if (status === "MEASURED") measured.push(row);
    else unmeasured.push(row);
  }

  console.log("");
  console.log("axis                      status     n      acc   separation   leader");
  console.log("-".repeat(86));
  for (const row of axes) {
    const status = String(row.status || row.kind || "?").toUpperCase();
    const isMeasured = status === "MEASURED";
    const n = isMeasured && row.n != null ? row.n : "—";
    const acc = isMeasured && row.accuracy != null ? Number(row.accuracy).toFixed(3) : "—";
    const sep = row.separation || "—";
    const leader = row.leader || (row.public_leader_state ? row.public_leader_state : "—");
    console.log(
      `${pad(row.axis || row.name || "?", 25)}  ${pad(status, 9)}  ${String(n).padStart(4)}  ${String(acc).padStart(6)}   ${pad(sep, 12)} ${leader}`
    );
  }

  if (unmeasured.length) {
    console.log("");
    console.log(`UNMEASURED slots (empty, and they stay empty — never 0): ${unmeasured.length}`);
    for (const row of unmeasured) console.log(`  - ${row.axis}`);
  }

  console.log("");
  console.log("Doctrine: MEASURED rows are evidence. UNMEASURED rows stay empty. Ties are not wins.");
  console.log("This is measurement, not certification. https://councilof.ai/verify");
}

/**
 * One axis, with everything that says how much to trust the number.
 *
 * The board already carries all of it; the point is to put it next to the number instead of in a
 * footnote nobody reads. A reader who sees only "accuracy 0.5865" is being asked to trust more
 * than the number can bear.
 */
function printAxis(board, wanted) {
  const axes = Array.isArray(board.axes) ? board.axes : [];
  const row = axes.find((a) => (a.axis || a.name) === wanted);
  if (!row) {
    console.log(`NOT ON THE BOARD  ${wanted}`);
    console.log(`Known axes: ${axes.map((a) => a.axis || a.name).join(", ")}`);
    process.exit(2);
  }
  const mde = row.mde || {};
  const interval = row.interval;
  const evidence = row.separation_evidence || {};

  console.log(`axis          ${row.axis || row.name}`);
  console.log(`status        ${String(row.status || "?").toUpperCase()}`);
  console.log(`n             ${row.n ?? "—"}`);
  console.log(`accuracy      ${row.accuracy ?? "—"}`);
  console.log(`separation    ${row.separation ?? "—"}`);
  console.log(`leader        ${row.leader ?? "—"}`);
  console.log("");
  console.log("-- how much to trust this number --");
  if (mde.value != null) {
    console.log(
      `resolution    ~${mde.value} ${mde.unit || ""} (alpha ${mde.alpha ?? "?"}, power ${mde.power ?? "?"})`
    );
    console.log(
      `              a smaller gap between two models would not be visible on this axis at all`
    );
  } else {
    console.log("resolution    not recorded for this axis");
  }
  console.log(
    `interval      ${Array.isArray(interval) ? `[${interval[0]}, ${interval[1]}]` : "—"}  (annotation only — never folded into separation)`
  );
  console.log(`separation    ${row.separation_sentence || row.separation || "—"}`);
  if (row.separation_p != null) console.log(`separation p  ${row.separation_p}`);
  const fleet = [];
  if (row.fleet_mean != null) fleet.push(`fleet mean ${row.fleet_mean}`);
  if (row.mean_harm != null) fleet.push(`mean harm ${row.mean_harm}`);
  if (row.cvar05_harm != null) fleet.push(`CVaR(5%) harm ${row.cvar05_harm}`);
  if (fleet.length) console.log(`fleet         ${fleet.join("; ")}`);
  console.log("");
  console.log("-- provenance --");
  console.log(`per-item rows ${row.peritem_file_sha256 || "—"}`);
  if (evidence.file) console.log(`rows file     ${evidence.file} @ ${evidence.source || ""}`);
  if (row.measurement_time) {
    console.log(
      `measured on   ${row.measurement_time.observed_on || "?"} (precision: ${row.measurement_time.precision || "?"})`
    );
  }
  if (row.leader_card_url) {
    console.log(`leader card   ${row.leader_card_url}  [${row.leader_card_state || "?"}]`);
  }
  if (row.leader_card_note) console.log(`              ${row.leader_card_note}`);
  if (row.dataset) console.log(`dataset       ${row.dataset}${row.dataset_url ? ` — ${row.dataset_url}` : ""}`);
  console.log("");
  console.log("-- caveats the board already carries --");
  const caveats = [];
  if (row.leader_card_state === "CARD_RECORDS_A_DIFFERENT_MEASUREMENT") {
    caveats.push(
      "The signed card for this leader records a DIFFERENT measurement, so it does not back the number above."
    );
  }
  if (String(row.separation || "").toUpperCase().includes("TIE")) {
    caveats.push("Nothing separated on this axis. The point-estimate lead is not a measured advantage.");
  }
  if (row.historical_measurement_record?.state) {
    caveats.push(
      `This axis carries a historical measurement record (${row.historical_measurement_record.state}); it is not the number above.`
    );
  }
  if (row.status === "UNMEASURED") caveats.push("No run sits behind this slot yet. UNMEASURED is an answer, never 0.");
  if (!caveats.length) caveats.push("No caveat is recorded against this axis.");
  for (const caveat of caveats) console.log(`  - ${caveat}`);
  console.log("");
  console.log(`Re-check: ${URL}?axis=${row.axis || row.name}`);
  console.log("Measurement, not certification. https://councilof.ai/verify");
}

async function watch(seconds) {
  let previous = null;
  let previousStamp = null;
  for (;;) {
    let summary;
    try {
      summary = summarise(await fetchBoard());
    } catch (error) {
      console.log(`UNREACHABLE  ${error.status ? `HTTP ${error.status} from ` : ""}${URL}`);
      console.log("No cached number is presented as live.");
    }
    if (summary) {
      const stamp = JSON.stringify([summary.measured, summary.public_count, summary.separation]);
      const now = new Date().toISOString();
      if (previous === null) {
        console.log(`${now}  live — first read`);
        console.log(`  slots ${summary.slots} · measured ${summary.measured} · ${summary.separation || ""}`);
        for (const axis of summary.axes) {
          if (axis.status === "MEASURED") {
            console.log(`  ${pad(axis.axis, 26)} n=${String(axis.n ?? "—").padStart(4)} acc=${axis.accuracy ?? "—"} ${axis.separation || ""}`);
          }
        }
        console.log("");
      } else if (stamp !== previousStamp) {
        const before = new Map(previous.axes.map((a) => [a.axis, a]));
        console.log(`${now}  CHANGED`);
        for (const axis of summary.axes) {
          const old = before.get(axis.axis);
          if (!old) {
            console.log(`  + ${axis.axis} ${axis.status} n=${axis.n ?? "—"} acc=${axis.accuracy ?? "—"}`);
            continue;
          }
          if (
            old.status !== axis.status ||
            old.n !== axis.n ||
            old.accuracy !== axis.accuracy ||
            old.separation !== axis.separation ||
            old.leader !== axis.leader
          ) {
            console.log(
              `  ~ ${axis.axis}: ${old.status}/${old.n ?? "—"}/${old.accuracy ?? "—"}/${old.separation || "—"} -> ${axis.status}/${axis.n ?? "—"}/${axis.accuracy ?? "—"}/${axis.separation || "—"}`
            );
          }
        }
        console.log("");
      } else {
        console.log(`${now}  no change (measured ${summary.measured}, ${summary.public_count || ""})`);
      }
      previous = summary;
      previousStamp = stamp;
    }
    await new Promise((resolve) => setTimeout(resolve, seconds * 1000));
  }
}

async function main() {
  const axis = value("axis");
  if (value("watch") !== undefined) {
    const seconds = Number(value("watch")) || 10;
    await watch(seconds);
    return;
  }

  let board;
  try {
    board = await fetchBoard();
  } catch (error) {
    console.log(`UNREACHABLE  ${error.status ? `HTTP ${error.status} from ` : "could not fetch "}${URL}`);
    console.log(String(error && error.message ? error.message : error));
    console.log("No cached number is presented as live.");
    process.exit(2);
  }

  if (value("json")) {
    console.log(JSON.stringify(board, null, 2));
    return;
  }
  if (axis) {
    printAxis(board, String(axis));
    return;
  }
  printBoard(board);
}

main();
