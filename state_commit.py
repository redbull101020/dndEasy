"""Recoverable, revision-checked multi-document commit for a single v3 writer.

Usage: state_commit.py roll 00000001 --roll-id roll-1 --expression 1d20 --dc 12;
       state_commit.py prepare 00000001; state_commit.py apply 00000001;
       state_commit.py recover 00000001; state_commit.py abort 00000001 --reason ...
Roll writes durable rolls.json before output. Recovery never makes a new roll.
The caller supplies transactions/ID/proposal.json and new/<target> before prepare.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from dice import parse_expression, roll as dice_roll
from v3_core import (ADVENTURE_SECTIONS, CHARACTER_SECTIONS, ValidationError, _safe_path,
                     _sections, allowed_target, currency_events, field,
                     reward_grants, validate)


def digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def read_existing(root: Path, relative: str) -> bytes | None:
    path = _safe_path(root, relative, allow_missing=True)
    return path.read_bytes() if path.is_file() else None


def write_durable(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-v3")
    if temp.exists():
        raise ValidationError(f"Temporary write file already exists: {temp}")
    try:
        with temp.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def transaction_folder(root: Path, identifier: str) -> Path:
    if re.fullmatch(r"[0-9]{8}", identifier) is None:
        raise ValidationError("Transaction ID must contain exactly eight digits")
    return _safe_path(root, f"transactions/{identifier}", directory=True)


def load_proposal(root: Path, folder: Path) -> dict:
    path = _safe_path(root, f"transactions/{folder.name}/proposal.json")
    if path.stat().st_size > 1024 * 1024:
        raise ValidationError("Oversized transaction proposal")
    proposal = json.loads(path.read_text(encoding="utf-8"))
    required = {"expected_configuration_revision", "expected_save_revision", "targets", "rolls", "reason"}
    if not isinstance(proposal, dict) or not required <= set(proposal) or set(proposal) - required - {"mechanic"}:
        raise ValidationError("Invalid proposal shape")
    if type(proposal["expected_configuration_revision"]) is not int or type(proposal["expected_save_revision"]) is not int:
        raise ValidationError("Expected revisions must be integers")
    if not isinstance(proposal["targets"], list) or not proposal["targets"] or len(proposal["targets"]) > 24:
        raise ValidationError("Invalid target list")
    if not isinstance(proposal["reason"], str) or not 1 <= len(proposal["reason"]) <= 1000:
        raise ValidationError("Missing transaction reason")
    if not isinstance(proposal["rolls"], list) or len(proposal["rolls"]) > 24:
        raise ValidationError("Invalid rolls list")
    for roll in proposal["rolls"]:
        if not isinstance(roll, dict) or set(roll) != {"id", "expression", "mode", "rolls", "total", "dc"}:
            raise ValidationError("Invalid recorded roll")
        if not isinstance(roll["id"], str) or re.fullmatch(r"roll-[1-9][0-9]*", roll["id"]) is None:
            raise ValidationError("Invalid Roll ID")
        if not isinstance(roll["rolls"], list) or any(type(value) is not int for value in roll["rolls"]):
            raise ValidationError("Invalid dice values")
        if type(roll["total"]) is not int or type(roll["dc"]) is not int:
            raise ValidationError("Invalid roll total/DC")
        expression = roll["expression"]
        mode = roll["mode"]
        match = re.fullmatch(r"([1-9][0-9]*)d([1-9][0-9]*)([+-][0-9]+)?", expression) if isinstance(expression, str) else None
        if match is None or mode not in {"normal", "advantage", "disadvantage"}:
            raise ValidationError("Invalid recorded dice expression/mode")
        count, sides = int(match.group(1)), int(match.group(2))
        modifier = int(match.group(3) or "0")
        if count > 100 or sides > 10000 or abs(modifier) > 10000 or not 0 <= roll["dc"] <= 100000:
            raise ValidationError("Recorded roll exceeds dice limits")
        values = roll["rolls"]
        if mode == "normal":
            expected_count, kept = count, values
        else:
            if count != 1 or sides != 20:
                raise ValidationError("Advantage/disadvantage only apply to 1d20")
            expected_count = 2
            kept = [max(values)] if mode == "advantage" and values else [min(values)] if values else []
        if len(values) != expected_count or any(not 1 <= value <= sides for value in values) or sum(kept) + modifier != roll["total"]:
            raise ValidationError("Recorded dice values/total are inconsistent")
    if "mechanic" in proposal and not isinstance(proposal["mechanic"], dict):
        raise ValidationError("Invalid mechanic description")
    if len({item["id"] for item in proposal["rolls"]}) != len(proposal["rolls"]):
        raise ValidationError("Duplicate Roll ID")
    return proposal


def target_list(proposal: dict) -> list[str]:
    targets = proposal["targets"]
    if any(not isinstance(item, str) or not allowed_target(item) for item in targets):
        raise ValidationError("Forbidden transaction target")
    if len(targets) != len(set(targets)) or "SAVE.md" not in targets:
        raise ValidationError("SAVE.md is mandatory and targets must be unique")
    return sorted(targets, key=lambda item: item != "SAVE.md")


def value(data: bytes, key: str) -> str:
    found = re.findall(rb"(?m)^- " + re.escape(key.encode("ascii")) + rb": (.+)$", data)
    if len(found) != 1:
        raise ValidationError(f"Missing or duplicate {key} in transaction data")
    return found[0].decode("utf-8")


def gp(data: bytes) -> int:
    raw = value(data, "GP")
    if re.fullmatch(r"0|[1-9][0-9]*", raw) is None:
        raise ValidationError("Invalid GP in character sheet")
    return int(raw)


def transition(data: bytes) -> dict[str, str]:
    parts = [part.strip() for part in value(data, "Last transition").split(";")]
    pairs = [part.split("=", 1) for part in parts]
    if any(len(pair) != 2 or not pair[0] or not pair[1] for pair in pairs):
        raise ValidationError("Last transition must contain exact key=value fields")
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValidationError("Duplicate Last transition field")
    return result


def sheet_sections(data: bytes, relative: str) -> dict[str, str]:
    return _sections(data.decode("utf-8"), f"Character {Path(relative).stem}", CHARACTER_SECTIONS, relative)


def sheet_events(data: bytes, relative: str) -> tuple[int | None, list[tuple[str, str, int]]]:
    return currency_events(sheet_sections(data, relative)["Currency Events"], relative)


def precheck_reroll(root: Path, origin: str, actor: str | None, resolution: str | None) -> tuple[int, int, str]:
    if (re.fullmatch(r"[0-9]{8}", origin) is None or actor is None or
            re.fullmatch(r"pc-[a-z0-9-]+", actor) is None or resolution is None or
            re.fullmatch(r"r-[1-9][0-9]*", resolution) is None):
        raise ValidationError("Invalid reroll attribution")
    current = transition(read_existing(root, "SAVE.md"))
    if current.get("origin-tx") != origin or current.get("resolution") != resolution or current.get("paid-reroll") != "available":
        raise ValidationError("Only immediately previous available resolution may be rerolled")
    origin_folder = transaction_folder(root, origin)
    if (origin_folder / "status").read_text(encoding="ascii").strip() != "committed":
        raise ValidationError("Origin resolution was not committed")
    manifest = prepared_manifest(root, origin_folder)
    original_rolls = manifest["proposal"].get("rolls", [])
    if len(original_rolls) != 1 or current.get("roll") != original_rolls[0].get("id"):
        raise ValidationError("Origin Roll ID does not match exact transition field")
    relative = f"characters/{actor}.md"
    if relative not in manifest["files"] or manifest["files"][relative]["old"] is None:
        raise ValidationError("Origin resolution lacks an actor pre-roll sheet")
    old = (origin_folder / "old" / relative).read_bytes()
    if digest(old) != manifest["files"][relative]["old"]:
        raise ValidationError("Origin pre-roll sheet SHA-256 mismatch")
    current_sheet = read_existing(root, relative)
    if current_sheet is None:
        raise ValidationError("Reroll actor sheet is missing")
    if digest(current_sheet) != manifest["files"][relative]["new"]:
        raise ValidationError("Origin outcome sheet is not the current sheet")
    if manifest["candidate"].get("save_revision") != validate(root, turn=True, check_transactions=False)["save_revision"]:
        raise ValidationError("Origin resolution is not the immediately preceding saved transition")
    before_gp, current_gp = gp(old), gp(current_sheet)
    if before_gp < 10 or current_gp < 10:
        raise ValidationError("Hero lacks 10 GP without old outcome income")
    return before_gp, current_gp, current["roll"]


def recorded_rolls(root: Path, folder: Path) -> dict | None:
    path = _safe_path(root, f"transactions/{folder.name}/rolls.json", allow_missing=True)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def assert_recorded_rolls(root: Path, folder: Path, proposal: dict) -> None:
    record = recorded_rolls(root, folder)
    if record is None:
        if proposal["rolls"]:
            raise ValidationError("Dice rolls must first be durably recorded with the roll operation")
        return
    if not isinstance(record, dict) or set(record) != {"baseline", "configuration_revision", "save_revision", "rolls"}:
        raise ValidationError("Invalid durable roll record")
    if record["rolls"] != proposal["rolls"]:
        raise ValidationError("Proposal rolls differ from durable roll record")
    if (record["configuration_revision"] != proposal["expected_configuration_revision"] or
            record["save_revision"] != proposal["expected_save_revision"]):
        raise ValidationError("Recorded roll was made against another revision")
    if record["baseline"] != {name: digest(read_existing(root, name)) for name in ("CAMPAIGN.md", "SAVE.md")}:
        raise ValidationError("Recorded roll baseline changed")


def roll_once(root: Path, folder: Path, roll_id: str, expression: str, mode: str, dc: int,
              reroll_origin: str | None, actor: str | None, resolution: str | None) -> dict:
    if re.fullmatch(r"roll-[1-9][0-9]*", roll_id) is None or type(dc) is not int or not 0 <= dc <= 100000:
        raise ValidationError("Invalid roll ID/DC")
    parsed = parse_expression(expression)
    if mode not in {"normal", "advantage", "disadvantage"}:
        raise ValidationError("Invalid dice mode")
    if mode != "normal" and (parsed.count, parsed.sides) != (1, 20):
        raise ValidationError("Advantage/disadvantage require 1d20")
    if any((folder / name).exists() for name in ("rolls.json.tmp-v3", "status.tmp-v3")):
        raise ValidationError("Interrupted durable roll write requires inspection; never silently reroll")
    record = recorded_rolls(root, folder)
    if record is not None:
        for previous in record["rolls"]:
            if previous["id"] == roll_id:
                if (previous["expression"], previous["mode"], previous["dc"]) != (parsed.normalized, mode, dc):
                    raise ValidationError("Roll ID was already used with other parameters")
                if not (folder / "status").exists():
                    write_durable(folder / "status", b"rolled\n")
                return previous
    status = folder / "status"
    if status.exists() and status.read_text(encoding="ascii").strip() not in {"rolled"}:
        raise ValidationError("Dice roll cannot be added to this package status")
    for other in _safe_path(root, "transactions", directory=True).iterdir():
        if other != folder and other.is_dir() and re.fullmatch(r"[0-9]{8}", other.name):
            other_status = other / "status"
            if other_status.exists() and other_status.read_text(encoding="ascii").strip() not in {"committed", "aborted"}:
                raise ValidationError(f"Another unfinished transaction: {other.name}")
    baseline = validate(root, check_transactions=False)
    if record is None:
        record = {"baseline": {name: digest(read_existing(root, name)) for name in ("CAMPAIGN.md", "SAVE.md")},
                  "configuration_revision": baseline["configuration_revision"],
                  "save_revision": baseline["save_revision"], "rolls": []}
    elif (record["configuration_revision"], record["save_revision"], record["baseline"]) != (
            baseline["configuration_revision"], baseline["save_revision"],
            {name: digest(read_existing(root, name)) for name in ("CAMPAIGN.md", "SAVE.md")}):
        raise ValidationError("Roll package baseline changed")
    if reroll_origin is not None:
        precheck_reroll(root, reroll_origin, actor, resolution)
    elif actor is not None or resolution is not None:
        raise ValidationError("Reroll attribution requires origin transaction")
    if len(record["rolls"]) >= 24:
        raise ValidationError("Too many rolls in package")
    result = dice_roll(parsed, mode)
    item = {"id": roll_id, "expression": result.expression, "mode": result.mode,
            "rolls": result.rolls, "total": result.total, "dc": dc}
    record["rolls"].append(item)
    path = _safe_path(root, f"transactions/{folder.name}/rolls.json", allow_missing=True)
    write_durable(path, (json.dumps(record, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    write_durable(status, b"rolled\n")
    return item


def abort(root: Path, folder: Path, reason: str) -> dict:
    if not 1 <= len(reason) <= 1000:
        raise ValidationError("Abort requires a concrete reason")
    status = folder / "status"
    current = status.read_text(encoding="ascii").strip() if status.exists() else None
    if current not in {None, "rolled", "preparing"}:
        raise ValidationError("Prepared or partially written package can only recover forward")
    if (folder / "manifest.json").exists():
        raise ValidationError("Manifest already prepared; package can only recover forward")
    validate(root, check_transactions=False)
    record = recorded_rolls(root, folder)
    if record is not None:
        if record["baseline"] != {name: digest(read_existing(root, name)) for name in ("CAMPAIGN.md", "SAVE.md")}:
            raise ValidationError("Game files changed since recorded roll")
    proposal_path = folder / "proposal.json"
    if proposal_path.is_file():
        for target in target_list(load_proposal(root, folder)):
            copy = folder / "old" / target
            if copy.is_file() and digest(copy.read_bytes()) != digest(read_existing(root, target)):
                raise ValidationError("Game file already changed; abort forbidden")
    write_durable(folder / "abort.json", (json.dumps({"reason": reason, "rolls": record["rolls"] if record else []},
                                                      ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    write_durable(status, b"aborted\n")
    return {"status": "aborted", "reason": reason, "rolls": record["rolls"] if record else []}


def check_mechanic(root: Path, folder: Path, proposal: dict, overlays: dict[str, bytes]) -> None:
    mechanic = proposal.get("mechanic")
    if mechanic is None:
        return
    kind = mechanic.get("type")
    baseline_save = read_existing(root, "SAVE.md")
    assert baseline_save is not None
    next_save = overlays["SAVE.md"]
    if kind == "paid-reroll":
        if set(mechanic) != {"type", "origin_transaction", "actor", "resolution", "new_outcome_gp_effect", "new_outcome_gp_reason"}:
            raise ValidationError("Invalid paid-reroll mechanic fields")
        origin, actor, resolution = mechanic["origin_transaction"], mechanic["actor"], mechanic["resolution"]
        delta = mechanic["new_outcome_gp_effect"]
        if type(delta) is not int or abs(delta) > 1_000_000 or not isinstance(mechanic["new_outcome_gp_reason"], str) or not mechanic["new_outcome_gp_reason"].strip():
            raise ValidationError("New outcome GP effect needs an explicit reason")
        character = f"characters/{actor}.md"
        if character not in overlays or len(proposal["rolls"]) != 1:
            raise ValidationError("Reroll needs changed actor sheet and recorded new roll")
        before_gp, current_gp, original_roll = precheck_reroll(root, origin, actor, resolution)
        next_last = transition(next_save)
        if any(next_last.get(key) != expected for key, expected in {
                "origin-tx": origin, "resolution": resolution, "old-roll": original_roll,
                "roll": proposal["rolls"][0]["id"], "paid-reroll": "used", "reroll-cost": "10 GP"}.items()):
            raise ValidationError("New transition lacks paid-reroll audit")
        old_current = read_existing(root, character)
        assert old_current is not None
        old_opening, old_events = sheet_events(old_current, character)
        new_opening, new_events = sheet_events(overlays[character], character)
        expected = [(folder.name, "origin-reversal", before_gp - current_gp),
                    (folder.name, "reroll-fee", -10), (folder.name, "reroll-outcome", delta)]
        if new_opening != old_opening or new_events != old_events + expected:
            raise ValidationError("Reroll requires separate reversal, 10 GP fee and new effect events")
        if gp(overlays[character]) != before_gp - 10 + delta:
            raise ValidationError("Reroll final GP differs from separately logged events")
    elif kind == "adventure-close":
        if set(mechanic) != {"type", "adventure_id", "result"}:
            raise ValidationError("Invalid adventure-close mechanic fields")
        adventure_id, result = mechanic["adventure_id"], mechanic["result"]
        if result not in {"success", "failure", "abandon"} or value(baseline_save, "Active adventure") != adventure_id:
            raise ValidationError("Only active adventure may be closed")
        if value(next_save, "Active adventure") != "none" or value(next_save, "Workflow stage") not in {"between-adventures", "complete"}:
            raise ValidationError("Adventure closure did not clear active stage")
        if not re.search(rf"(?m)^- Adventure: {re.escape(adventure_id)} \| result: {result} \| reward: granted \|", next_save.decode("utf-8")):
            raise ValidationError("Adventure reward ledger missing")
        if re.search(rf"(?m)^- Adventure: {re.escape(adventure_id)} \|", baseline_save.decode("utf-8")):
            raise ValidationError("Adventure was already rewarded")
        scenario_bytes = read_existing(root, f"adventures/{adventure_id}.md")
        assert scenario_bytes is not None
        scenario = _sections(scenario_bytes.decode("utf-8"), f"Adventure {adventure_id}",
                             ADVENTURE_SECTIONS, f"adventures/{adventure_id}.md")
        participants = [item.strip() for item in field(scenario["Metadata"], "Participants", f"adventures/{adventure_id}.md").split(",")]
        grants = reward_grants(scenario["Rewards"], participants, f"adventures/{adventure_id}.md")
        for character_id in participants:
            relative = f"characters/{character_id}.md"
            if relative not in overlays:
                raise ValidationError(f"Rewarded character sheet was not changed: {character_id}")
            before = sheet_sections(read_existing(root, relative), relative)
            after = sheet_sections(overlays[relative], relative)
            grant = grants[(result, character_id)]
            award = (f"- Award: adventure={adventure_id}; result={result}; gp={grant['gp']}; xp={grant['xp']}; "
                     f"items={','.join(grant['items']) or 'none'}; markers={','.join(grant['markers']) or 'none'}")
            if award in before["Awards"] or after["Awards"].count(award) != 1:
                raise ValidationError("Reward event is missing or duplicated")
            if gp(overlays[relative]) != gp(read_existing(root, relative)) + grant["gp"]:
                raise ValidationError("Adventure GP reward was not granted exactly")
            old_opening, old_events = sheet_events(read_existing(root, relative), relative)
            new_opening, new_events = sheet_events(overlays[relative], relative)
            if new_opening != old_opening or new_events != old_events + [(folder.name, "adventure-reward", grant["gp"])]:
                raise ValidationError("Adventure GP reward needs one exact currency event")
            old_xp, new_xp = field(before["Identity"], "XP", relative), field(after["Identity"], "XP", relative)
            if old_xp == "not-applicable":
                if grant["xp"] != 0 or new_xp != old_xp:
                    raise ValidationError("Milestone level-up is a separate transition")
            elif int(new_xp) != int(old_xp) + grant["xp"]:
                raise ValidationError("Adventure XP reward was not granted exactly")
            for section_name, prefix, ids in (("Inventory", "Item ID", grant["items"]),
                                               ("Features", "Reward marker ID", grant["markers"])):
                before_ids = set(re.findall(rf"(?m)^- {prefix}: ([a-z0-9-]+)$", before[section_name]))
                after_ids = set(re.findall(rf"(?m)^- {prefix}: ([a-z0-9-]+)$", after[section_name]))
                if after_ids - before_ids != set(ids):
                    raise ValidationError(f"Adventure {section_name} reward IDs were not granted exactly")
    else:
        raise ValidationError("Unknown transaction mechanic")


def check_stage_step(before: str, after: str) -> None:
    next_stages = {
        "new": {"await-lore"},
        "await-lore": {"await-lore", "await-characters"},
        "await-characters": {"await-characters", "await-story"},
        "await-story": {"await-story", "await-final-settings"},
        "await-final-settings": {"await-final-settings", "playable"},
        "playable": {"playable", "playing"},
        "playing": {"playing", "between-adventures", "complete"},
        "between-adventures": {"between-adventures", "playable", "complete"},
        "complete": {"complete"},
    }
    if after not in next_stages.get(before, set()):
        raise ValidationError(f"Forbidden workflow stage transition: {before} -> {after}")


def prepared_manifest(root: Path, folder: Path) -> dict:
    path = _safe_path(root, f"transactions/{folder.name}/manifest.json")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != {"proposal", "files", "candidate", "baseline", "roll_sha256"}:
        raise ValidationError("Invalid prepared manifest")
    return manifest


def prepare(root: Path, folder: Path) -> dict:
    status = folder / "status"
    present_status = status.read_text(encoding="ascii").strip() if status.exists() else None
    if present_status not in {None, "rolled", "preparing"}:
        raise ValidationError("Transaction is already prepared")
    for other in _safe_path(root, "transactions", directory=True).iterdir():
        if other != folder and other.is_dir() and re.fullmatch(r"[0-9]{8}", other.name):
            other_status = other / "status"
            if other_status.exists() or (other / "proposal.json").exists():
                if not other_status.is_file() or other_status.read_text(encoding="ascii").strip() not in {"committed", "aborted"}:
                    raise ValidationError(f"Another unfinished transaction: {other.name}")
    proposal = load_proposal(root, folder)
    assert_recorded_rolls(root, folder, proposal)
    targets = target_list(proposal)
    old_save = read_existing(root, "SAVE.md")
    assert old_save is not None
    fast = (proposal.get("mechanic") is None and all(target == "SAVE.md" or target.startswith("characters/") for target in targets)
            and value(old_save, "Workflow stage") in {"playable", "playing"})
    baseline = validate(root, turn=fast, check_transactions=False)
    if baseline["configuration_revision"] != proposal["expected_configuration_revision"] or baseline["save_revision"] != proposal["expected_save_revision"]:
        raise ValidationError("Stale expected campaign/save revision")
    overlays: dict[str, bytes] = {}
    files: dict[str, dict[str, str | None]] = {}
    for target in targets:
        new_path = _safe_path(root, f"transactions/{folder.name}/new/{target}")
        new_data = new_path.read_bytes()
        old_data = read_existing(root, target)
        if not new_data or new_data == old_data:
            raise ValidationError(f"Missing change: {target}")
        if old_data is not None:
            old_path = _safe_path(root, f"transactions/{folder.name}/old/{target}", allow_missing=True)
            if old_path.is_file() and old_path.read_bytes() != old_data:
                raise ValidationError(f"Existing pre-write copy no longer matches state: {target}")
        overlays[target] = new_data
        files[target] = {"old": digest(old_data), "new": digest(new_data)}
    check_mechanic(root, folder, proposal, overlays)
    candidate = validate(root, turn=fast, overrides=overlays, check_transactions=False)
    check_stage_step(baseline["workflow_stage"], candidate["workflow_stage"])
    if candidate["save_revision"] != baseline["save_revision"] + 1:
        raise ValidationError("SAVE revision must increase exactly once")
    config_step = 1 if "CAMPAIGN.md" in targets else 0
    if candidate["configuration_revision"] != baseline["configuration_revision"] + config_step:
        raise ValidationError("Configuration revision change is invalid")
    for target in targets:
        if not target.startswith("characters/"):
            continue
        old = read_existing(root, target)
        before = re.search(rb"(?m)^- Character revision: ([0-9]+)$", old) if old else None
        after = re.search(rb"(?m)^- Character revision: ([0-9]+)$", overlays[target])
        if not after or int(after.group(1)) != (int(before.group(1)) + 1 if before else 1):
            raise ValidationError(f"Character revision must increase exactly once: {target}")
        relative = target
        if old is not None:
            old_opening, old_events = sheet_events(old, relative)
            new_opening, new_events = sheet_events(overlays[target], relative)
            if old_opening != new_opening or new_events[:len(old_events)] != old_events:
                raise ValidationError(f"Opening GP or prior currency events were rewritten: {target}")
            if any(event[0] != folder.name for event in new_events[len(old_events):]):
                raise ValidationError(f"New currency events require current transaction ID: {target}")
    if present_status in {None, "rolled"}:
        write_durable(status, b"preparing\n")
    for target in targets:
        old_data = read_existing(root, target)
        if old_data is not None:
            old_path = _safe_path(root, f"transactions/{folder.name}/old/{target}", allow_missing=True)
            if not old_path.is_file():
                write_durable(old_path, old_data)
    manifest = {"proposal": proposal, "files": files, "candidate": candidate,
                "roll_sha256": digest(read_existing(root, f"transactions/{folder.name}/rolls.json")),
                "baseline": {"CAMPAIGN.md": digest(read_existing(root, "CAMPAIGN.md")),
                             "SAVE.md": digest(read_existing(root, "SAVE.md"))}}
    manifest_path = _safe_path(root, f"transactions/{folder.name}/manifest.json", allow_missing=True)
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if manifest_path.is_file():
        if manifest_path.read_bytes() != manifest_bytes:
            raise ValidationError("Already prepared manifest differs from resumed candidate")
    else:
        write_durable(manifest_path, manifest_bytes)
    write_durable(status, b"prepared\n")
    return candidate


def apply_or_recover(root: Path, folder: Path) -> dict:
    status = _safe_path(root, f"transactions/{folder.name}/status").read_text(encoding="ascii").strip()
    if status == "preparing":
        prepare(root, folder)
        status = "prepared"
    if status == "committed":
        return validate(root)
    if status != "prepared":
        raise ValidationError("Transaction status is not prepared")
    manifest = prepared_manifest(root, folder)
    if digest(read_existing(root, f"transactions/{folder.name}/rolls.json")) != manifest["roll_sha256"]:
        raise ValidationError("Durable roll record changed after preparation")
    files = manifest["files"]
    targets = target_list(manifest["proposal"])
    fast = manifest["candidate"].get("scope") == "turn"
    if "CAMPAIGN.md" not in targets and digest(read_existing(root, "CAMPAIGN.md")) != manifest["baseline"]["CAMPAIGN.md"]:
        raise ValidationError("Campaign settings changed after transaction preparation")
    if set(files) != set(targets):
        raise ValidationError("Prepared manifest target mismatch")
    overlays: dict[str, bytes] = {}
    partially_written = False
    for target in targets:
        new_path = _safe_path(root, f"transactions/{folder.name}/new/{target}")
        new_data = new_path.read_bytes()
        old_data = read_existing(root, target)
        if digest(new_data) != files[target]["new"]:
            raise ValidationError(f"Prepared new copy changed: {target}")
        if digest(old_data) not in {files[target]["old"], files[target]["new"]}:
            raise ValidationError(f"Target changed outside transaction: {target}")
        if digest(old_data) == files[target]["new"]:
            partially_written = True
        if files[target]["old"] is not None:
            copy = _safe_path(root, f"transactions/{folder.name}/old/{target}").read_bytes()
            if digest(copy) != files[target]["old"]:
                raise ValidationError(f"Recoverable old copy changed: {target}")
        overlays[target] = new_data
    candidate = validate(root, turn=fast, overrides=overlays, check_transactions=False)
    if candidate != manifest["candidate"]:
        raise ValidationError("Prepared candidate no longer validates identically")
    for target in targets:
        if digest(read_existing(root, target)) != files[target]["new"]:
            write_durable(_safe_path(root, target, allow_missing=True), overlays[target])
    verified = validate(root, turn=fast, check_transactions=False)
    if verified != candidate:
        raise ValidationError("Written state failed verification; recover before play")
    if partially_written:
        validate(root, check_transactions=False)
    write_durable(folder / "status", b"committed\n")
    return validate(root, turn=fast)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("roll", "prepare", "apply", "recover", "abort"))
    parser.add_argument("transaction_id")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--roll-id")
    parser.add_argument("--expression")
    parser.add_argument("--mode", default="normal")
    parser.add_argument("--dc", type=int)
    parser.add_argument("--reroll-origin")
    parser.add_argument("--actor")
    parser.add_argument("--resolution")
    parser.add_argument("--reason")
    arguments = parser.parse_args()
    try:
        root = arguments.root.resolve(strict=True)
        folder = transaction_folder(root, arguments.transaction_id)
        if arguments.operation == "roll":
            if arguments.roll_id is None or arguments.expression is None or arguments.dc is None:
                raise ValidationError("Roll requires --roll-id, --expression and --dc")
            result = roll_once(root, folder, arguments.roll_id, arguments.expression, arguments.mode,
                               arguments.dc, arguments.reroll_origin, arguments.actor, arguments.resolution)
        elif arguments.operation == "abort":
            result = abort(root, folder, arguments.reason or "")
        elif arguments.operation == "prepare":
            result = prepare(root, folder)
        else:
            result = apply_or_recover(root, folder)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (ValidationError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
