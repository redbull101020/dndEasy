"""Read-only validation of a fresh v3 campaign and its linked documents."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import stat
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


class ValidationError(Exception):
    pass


STAGES = (
    "new", "await-lore", "await-characters", "await-story",
    "await-final-settings", "playable", "playing", "between-adventures", "complete",
)
CHARACTER_ID = re.compile(r"pc-[a-z0-9](?:[a-z0-9-]{0,27}[a-z0-9])?")
ADVENTURE_ID = re.compile(r"[0-9]{4}")
CAMPAIGN_ID = re.compile(r"[0-9a-f]{32}")
DIGEST = re.compile(r"[0-9a-f]{64}")
MAX_TEXT_BYTES = 2 * 1024 * 1024
REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
BASE_FILES = ("CAMPAIGN.md", "SAVE.md", "AGENTS.md", "PROJECT_INSTRUCTIONS.md")
BASE_DIRS = ("characters", "adventures", "transactions", "workshops", "references", "journal", "backups", "tools")
REVIEWED_OPERATIONAL_SHA256 = {
    "AGENTS.md": "f362a6f99970d4b5f3d74f35cbb6f08ef4e7ca7dfde0e321114b5d5dcfe272b6",
    "PROJECT_INSTRUCTIONS.md": "d4693ec0d87267da9dc8c5920eac921659d4cb7d29e2642155acb8f9f5111d00",
    "workshops/COORDINATOR_GUIDE.md": "3703277fdcb368a276eea2647110438cc7b09fa36b31c42dfa14c7304a43bfcf",
    "workshops/LORE_GUIDE.md": "40c82257e8a13d8c7c3c4661adf2baa00e35d59bce721a07c1bcd9e6cd6678f2",
    "workshops/CHARACTER_GUIDE.md": "504fe7d703d23ef054c8f3a332b033b61e67ca093eb34e3114651b5b385cde79",
    "workshops/NARRATIVE_GUIDE.md": "bcba3783123c035a9b9adc80dcfc45f2c9d151a7ff39e816520ec099903ea551",
    "workshops/LORE_TEMPLATE.md": "f80da94e41d64eccc8f457343554e563d6907c73745132fda6b92d374e0b0169",
    "workshops/CHARACTER_TEMPLATE.md": "d76c77b0c842d237fefe8f84d40250b6af9694bf45ea6b6eaa5e605f87335838",
    "workshops/STORY_TEMPLATE.md": "c50768404115d0fbceb833d17b6103218124c8d920883ef31e213f526544915f",
    "workshops/ADVENTURE_TEMPLATE.md": "1cfb7fe1f659714136415b953d8677c8a771e44264c9abef50dbe9404d9f5102",
    "tools/dice.py": "920e879c297238928edfbcf50c69be1d0bff783eb78c0ad63f5a2796648a62f8",
    "tools/state_commit.py": "9da04ede2ed0935aef93f9b7a95808d12b37ec0c7dfe07ee481090c30490ec9c",
    "tools/validate_runtime.py": "d673d26b6057d5a04cb749010df05462ec34755a71ea243a74cb9c0f3b89e89c",
}
CAMPAIGN_SECTIONS = (
    "Metadata", "Rules Baseline", "Campaign Premise", "Play Style", "Narrative Direction",
    "Party Setup", "Character Creation", "World and Rules Tracking", "Roll Policy",
    "House Rules", "Persistent Rulings", "Player Preferences", "Content Boundaries",
)
SAVE_SECTIONS = (
    "Metadata", "Player Characters", "Current Scenes", "Adventure Ledger", "Active Combat",
    "Active Quests", "Active World State", "DM Private State",
)
CHARACTER_SECTIONS = (
    "Metadata", "Identity", "Goals", "Abilities and Proficiencies", "Combat", "Resources",
    "Conditions and Effects", "Equipment", "Inventory", "Currency", "Currency Events", "Awards", "Features",
    "Actions and Attacks", "Spells", "Relationships",
)
LORE_SECTIONS = ("Metadata", "Player Introduction", "World Constants", "History and Factions", "Locations and Hooks", "DM Spoilers")
STORY_SECTIONS = ("Metadata", "Player Introduction", "Campaign Goal", "Flexible Beats", "Possible Endings", "DM Spoilers")
ADVENTURE_SECTIONS = ("Metadata", "Player Introduction", "Objective and Pressure", "Closure", "Rewards", "DM Scenario")
REWARD_ID = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
EVENT_KIND = {"ordinary", "origin-reversal", "reroll-fee", "reroll-outcome", "adventure-reward"}


def id_list(value: str, relative: str) -> tuple[str, ...]:
    if value == "none":
        return ()
    values = tuple(value.split(","))
    require(bool(values) and len(values) == len(set(values)) and
            all(REWARD_ID.fullmatch(item) is not None for item in values), f"Invalid reward IDs: {relative}")
    return values


def currency_events(section: str, relative: str) -> tuple[int | None, list[tuple[str, str, int]]]:
    opening_value = field(section, "Opening GP", relative)
    opening = None if opening_value == "not-set" else canonical_number(opening_value, "Opening GP", relative, maximum=1_000_000_000)
    history = field(section, "Event history", relative)
    require(history in {"none", "listed"}, f"Invalid currency event history: {relative}")
    lines = re.findall(r"(?m)^- Event: (.+)$", section)
    require((history == "none") == (not lines), f"Currency event history mismatch: {relative}")
    events: list[tuple[str, str, int]] = []
    for line in lines:
        match = re.fullmatch(r"tx=([0-9]{8}); kind=([a-z-]+); gp=([+-](?:0|[1-9][0-9]*))", line)
        require(match is not None and match.group(2) in EVENT_KIND, f"Invalid currency event: {relative}")
        amount = int(match.group(3))
        require(abs(amount) <= 1_000_000_000, f"Excessive currency event: {relative}")
        events.append((match.group(1), match.group(2), amount))
    require(len({(item[0], item[1]) for item in events}) == len(events), f"Duplicate currency event: {relative}")
    return opening, events


def reward_grants(section: str, participants: list[str], relative: str) -> dict[tuple[str, str], dict[str, object]]:
    grants: dict[tuple[str, str], dict[str, object]] = {}
    for raw in re.findall(r"(?m)^- Grant: (.+)$", section):
        match = re.fullmatch(r"(success|failure|abandon) \| (pc-[a-z0-9-]+) \| gp=(0|[1-9][0-9]*) \| xp=(0|[1-9][0-9]*) \| items=([a-z0-9,-]+) \| markers=([a-z0-9,-]+)", raw)
        require(match is not None, f"Invalid structured grant: {relative}")
        outcome, character_id, gold, xp, items, markers = match.groups()
        require(character_id in participants and (outcome, character_id) not in grants, f"Duplicate/unknown reward recipient: {relative}")
        grants[(outcome, character_id)] = {
            "gp": canonical_number(gold, "Reward GP", relative, maximum=1_000_000_000),
            "xp": canonical_number(xp, "Reward XP", relative, maximum=1_000_000_000),
            "items": id_list(items, relative), "markers": id_list(markers, relative),
        }
    require(set(grants) == {(outcome, participant) for outcome in ("success", "failure", "abandon")
                            for participant in participants}, f"Incomplete structured reward roster: {relative}")
    return grants


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _safe_path(root: Path, relative: str, *, directory: bool = False, allow_missing: bool = False) -> Path:
    require(relative == relative.replace("\\", "/"), "Unsafe path separator")
    parts = Path(relative).parts
    require(parts and not any(part in {"", ".", ".."} for part in parts), f"Unsafe path: {relative}")
    current = root
    for part in parts:
        current = current / part
        if current.exists() or current.is_symlink():
            require(not current.is_symlink(), f"Symlink is forbidden: {relative}")
            require(not current.stat().st_file_attributes & REPARSE if hasattr(current.stat(), "st_file_attributes") else True,
                    f"Reparse point is forbidden: {relative}")
    resolved = current.resolve(strict=False)
    require(resolved == root or root in resolved.parents, f"Path escapes project: {relative}")
    if not allow_missing:
        require(current.is_dir() if directory else current.is_file(), f"Missing {'directory' if directory else 'file'}: {relative}")
    return current


def allowed_target(relative: str) -> bool:
    if relative in {"CAMPAIGN.md", "SAVE.md", "LORE.md", "CAMPAIGN_STORY.md"}:
        return True
    if relative.startswith("characters/") and relative.endswith(".md"):
        return CHARACTER_ID.fullmatch(relative[11:-3]) is not None
    return re.fullmatch(r"adventures/(?!0000)[0-9]{4}\.md", relative) is not None


def _read(root: Path, relative: str, overrides: dict[str, bytes], *, required: bool = True) -> bytes | None:
    if relative in overrides:
        _safe_path(root, relative, allow_missing=True)
        data = overrides[relative]
    else:
        path = _safe_path(root, relative, allow_missing=not required)
        if not path.is_file():
            return None
        require(path.stat().st_size <= MAX_TEXT_BYTES, f"File too large: {relative}")
        data = path.read_bytes()
    require(0 < len(data) <= MAX_TEXT_BYTES, f"Empty or oversized document: {relative}")
    require(not data.startswith(b"\xef\xbb\xbf"), f"UTF-8 BOM is forbidden: {relative}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError(f"Invalid UTF-8: {relative}") from error
    require(not any((ord(character) < 32 and character not in {"\n", "\t"}) or ord(character) == 127 or
                    character in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u200b\u200c\u200d\ufeff"
                    for character in text) and "\r" not in text, f"Unsafe control/invisible character: {relative}")
    return data


def _text(root: Path, relative: str, overrides: dict[str, bytes], *, required: bool = True) -> str | None:
    data = _read(root, relative, overrides, required=required)
    return data.decode("utf-8") if data is not None else None


def _sections(text: str, title: str, headings: tuple[str, ...], relative: str) -> dict[str, str]:
    require(text.startswith(f"# {title}\n"), f"Invalid title: {relative}")
    found = re.findall(r"(?m)^## ([^\n]+)$", text)
    require(found == list(headings), f"Invalid section order: {relative}")
    result: dict[str, str] = {}
    for index, heading in enumerate(headings):
        start = text.index(f"## {heading}\n") + len(f"## {heading}\n")
        end = text.index(f"## {headings[index + 1]}\n", start) if index + 1 < len(headings) else len(text)
        result[heading] = text[start:end].strip()
        require(result[heading] != "", f"Empty section {heading}: {relative}")
    return result


def field(text: str, key: str, relative: str) -> str:
    values = re.findall(rf"(?m)^- {re.escape(key)}:[ \t]*(.*)$", text)
    require(len(values) == 1, f"Field {key} occurs {len(values)} times: {relative}")
    value = values[0].strip()
    require(value != "" and len(value) <= 8192, f"Empty or oversized {key}: {relative}")
    return value


def canonical_number(value: str, key: str, relative: str, *, maximum: int = 2_147_483_647) -> int:
    require(re.fullmatch(r"0|[1-9][0-9]*", value) is not None, f"Invalid {key}: {relative}")
    number = int(value)
    require(number <= maximum, f"Excessive {key}: {relative}")
    return number


def timestamp(value: str, key: str, relative: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValidationError(f"Invalid {key}: {relative}") from error
    require(parsed.tzinfo is not None, f"Timezone missing in {key}: {relative}")


def _validate_source(root: Path, campaign: dict[str, str], turn: bool) -> None:
    section = campaign["Rules Baseline"]
    access = field(section, "Baseline reference access", "CAMPAIGN.md")
    digest = field(section, "Baseline reference SHA-256", "CAMPAIGN.md")
    if access == "not-set":
        require(digest == "not-set", "Unset source must have unset digest")
        return
    if access == "model-knowledge-only (degraded)":
        require(digest == "not-applicable", "Degraded source digest must be not-applicable")
        return
    if access.startswith("local: references/"):
        relative = access.removeprefix("local: ")
        require(DIGEST.fullmatch(digest) is not None, "Local reference needs SHA-256")
        path = _safe_path(root, relative)
        require(0 < path.stat().st_size <= 256 * 1024 * 1024, "Local reference has invalid size")
        if not turn:
            require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, "Local reference SHA-256 mismatch")
        return
    if access.startswith("remote: "):
        url = access.removeprefix("remote: ")
        parsed = urlsplit(url)
        require(parsed.scheme == "https" and parsed.hostname is not None and parsed.port in {None, 443}, "Unsafe source URL")
        require(parsed.username is None and parsed.password is None and "\\" not in url, "Unsafe source URL")
        hostname = parsed.hostname.rstrip(".").lower()
        require(not hostname.endswith((".local", ".internal", ".localhost")) and hostname != "localhost", "Local host forbidden")
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            require("." in hostname and re.fullmatch(r"[a-z0-9.-]+", hostname) is not None, "Invalid source hostname")
        else:
            require(ip.is_global, "Private IP source forbidden")
        require(digest == "remote-unpinned", "Remote source digest must be remote-unpinned")
        return
    raise ValidationError("Invalid baseline reference access")


def _validate_character(text: str, character_id: str, campaign_id: str, revision: int) -> dict[str, object]:
    relative = f"characters/{character_id}.md"
    sections = _sections(text, f"Character {character_id}", CHARACTER_SECTIONS, relative)
    metadata = sections["Metadata"]
    require(field(metadata, "Format version", relative) == "3", f"Invalid character format: {relative}")
    require(field(metadata, "Campaign ID", relative) == campaign_id, f"Character Campaign ID mismatch: {relative}")
    require(field(metadata, "Character ID", relative) == character_id, f"Character ID mismatch: {relative}")
    require(canonical_number(field(metadata, "Character revision", relative), "Character revision", relative) == revision,
            f"Character revision mismatch: {relative}")
    timestamp(field(metadata, "Updated at", relative), "Updated at", relative)
    status = field(metadata, "Character status", relative)
    require(status in {"creating", "ready", "dead", "retired"}, f"Invalid character status: {relative}")
    identity = sections["Identity"]
    controller = field(identity, "Controller", relative)
    name = field(identity, "Name", relative)
    xp_value = field(identity, "XP", relative)
    xp = None if xp_value in {"not-set", "not-applicable"} else canonical_number(xp_value, "XP", relative, maximum=1_000_000_000)
    level_match = re.search(r"(?:^|\s)([1-9][0-9]*)$", field(identity, "Class and level", relative))
    level = int(level_match.group(1)) if level_match else None
    if status != "creating":
        require(controller != "not-set" and name != "not-set" and level is not None and level <= 20,
                f"Incomplete ready character identity: {relative}")
        for key in ("Ancestry/species", "Background"):
            require(field(identity, key, relative) != "not-set", f"Missing {key}: {relative}")
        abilities = sections["Abilities and Proficiencies"]
        for key in ("Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma"):
            score = canonical_number(field(abilities, key, relative), key, relative, maximum=30)
            require(1 <= score <= 30, f"Invalid ability score {key}: {relative}")
        bonus = canonical_number(field(abilities, "Proficiency bonus", relative), "Proficiency bonus", relative, maximum=9)
        require(2 <= bonus <= 9, f"Invalid proficiency bonus: {relative}")
        canonical_number(field(abilities, "Passive Perception", relative), "Passive Perception", relative, maximum=50)
        for key in ("Saving throws", "Skills", "Languages", "Other proficiencies"):
            require(field(abilities, key, relative) != "not-set", f"Missing {key}: {relative}")
    combat = sections["Combat"]
    hp = field(combat, "HP (current / max)", relative)
    hp_match = re.fullmatch(r"(0|[1-9][0-9]*) / ([1-9][0-9]*)", hp)
    if status != "creating":
        require(hp_match is not None, f"Invalid HP: {relative}")
        require(int(hp_match.group(1)) <= int(hp_match.group(2)), f"HP exceeds maximum: {relative}")
        require(status != "dead" or int(hp_match.group(1)) == 0, f"Dead character has HP: {relative}")
        for key in ("AC", "Temporary HP", "Exhaustion"):
            canonical_number(field(combat, key, relative), key, relative, maximum=1_000_000)
        require(re.fullmatch(r"[+-]?(0|[1-9][0-9]*)", field(combat, "Initiative modifier", relative)) is not None,
                f"Invalid initiative modifier: {relative}")
        canonical_number(field(combat, "Speed", relative), "Speed", relative, maximum=10000)
        require(re.fullmatch(r"(0|[1-9][0-9]*) / ([1-9][0-9]*)d(4|6|8|10|12)", field(combat, "Hit Dice (current / max)", relative)) is not None,
                f"Invalid Hit Dice: {relative}")
    currency = sections["Currency"]
    gold = 0
    if currency != "none":
        order = ("CP", "SP", "EP", "GP", "PP")
        found: list[str] = []
        for line in currency.splitlines():
            match = re.fullmatch(r"- (CP|SP|EP|GP|PP): (0|[1-9][0-9]*)", line)
            require(match is not None, f"Invalid currency: {relative}")
            found.append(match.group(1))
            canonical_number(match.group(2), "Currency", relative, maximum=1_000_000_000)
            if match.group(1) == "GP":
                gold = int(match.group(2))
        require(len(found) == len(set(found)) and found == sorted(found, key=order.index), f"Currency order/duplicate: {relative}")
    opening_gp, events = currency_events(sections["Currency Events"], relative)
    awards: dict[str, dict[str, object]] = {}
    if sections["Awards"] != "none":
        for award_line in sections["Awards"].splitlines():
            match = re.fullmatch(r"- Award: adventure=([0-9]{4}); result=(success|failure|abandon); gp=(0|[1-9][0-9]*); xp=(0|[1-9][0-9]*); items=([a-z0-9,-]+); markers=([a-z0-9,-]+)", award_line)
            require(match is not None, f"Invalid award event: {relative}")
            adventure, result, award_gp, award_xp, items, markers = match.groups()
            require(adventure not in awards, f"Duplicate adventure award: {relative}")
            awards[adventure] = {"result": result, "gp": int(award_gp), "xp": int(award_xp),
                                 "items": id_list(items, relative), "markers": id_list(markers, relative)}
    if status != "creating":
        for section_name in ("Goals", "Abilities and Proficiencies", "Actions and Attacks", "Spells"):
            require("not-set" not in sections[section_name], f"Incomplete {section_name}: {relative}")
        for key in ("CP", "SP", "EP", "GP", "PP"):
            require(re.search(rf"(?m)^- {key}: (0|[1-9][0-9]*)$", currency) is not None,
                    f"Missing currency {key}: {relative}")
        require(opening_gp is not None and opening_gp + sum(item[2] for item in events) == gold,
                f"Currency event balance mismatch: {relative}")
        require(xp_value != "not-set", f"XP method unresolved: {relative}")
    return {"id": character_id, "status": status, "name": name, "controller": controller,
            "level": level, "gp": gold, "xp": xp, "opening_gp": opening_gp,
            "currency_events": events, "awards": awards}


def _validate_lore(text: str, campaign_id: str) -> None:
    sections = _sections(text, "Lore", LORE_SECTIONS, "LORE.md")
    metadata = sections["Metadata"]
    require(field(metadata, "Format version", "LORE.md") == "3", "Invalid lore format")
    require(field(metadata, "Campaign ID", "LORE.md") == campaign_id, "Lore Campaign ID mismatch")
    require(field(metadata, "Document status", "LORE.md") == "ready", "Lore not approved")
    require(canonical_number(field(metadata, "Lore revision", "LORE.md"), "Lore revision", "LORE.md") > 0, "Lore revision must be positive")
    timestamp(field(metadata, "Updated at", "LORE.md"), "Updated at", "LORE.md")
    for name in LORE_SECTIONS[1:]:
        require(sections[name] not in {"", "not-set"}, f"Missing lore {name}")


def _validate_story(text: str, campaign_id: str) -> None:
    sections = _sections(text, "Campaign Story", STORY_SECTIONS, "CAMPAIGN_STORY.md")
    metadata = sections["Metadata"]
    require(field(metadata, "Format version", "CAMPAIGN_STORY.md") == "3", "Invalid story format")
    require(field(metadata, "Campaign ID", "CAMPAIGN_STORY.md") == campaign_id, "Story Campaign ID mismatch")
    require(field(metadata, "Document status", "CAMPAIGN_STORY.md") == "ready", "Story not approved")
    require(canonical_number(field(metadata, "Story revision", "CAMPAIGN_STORY.md"), "Story revision", "CAMPAIGN_STORY.md") > 0, "Story revision must be positive")
    timestamp(field(metadata, "Updated at", "CAMPAIGN_STORY.md"), "Updated at", "CAMPAIGN_STORY.md")
    start = canonical_number(field(metadata, "Starting level", "CAMPAIGN_STORY.md"), "Starting level", "CAMPAIGN_STORY.md", maximum=20)
    target = canonical_number(field(metadata, "Target ending level", "CAMPAIGN_STORY.md"), "Target ending level", "CAMPAIGN_STORY.md", maximum=20)
    require(1 <= start <= target, "Invalid story level progression")
    count = canonical_number(field(metadata, "Planned adventures", "CAMPAIGN_STORY.md"), "Planned adventures", "CAMPAIGN_STORY.md", maximum=10)
    require(5 <= count <= 10, "Campaign needs 5-10 planned adventures")
    beats = re.findall(r"(?m)^- Beat: (.+)$", sections["Flexible Beats"])
    require(len(beats) == count and all(beat != "not-set" for beat in beats), "Story beat count mismatch")
    for name in ("Player Introduction", "Campaign Goal", "Possible Endings"):
        require(sections[name] not in {"", "not-set"}, f"Missing story {name}")


def _validate_adventure(text: str, adventure_id: str, campaign_id: str, characters: dict[str, dict[str, object]], save_revision: int) -> dict[str, object]:
    relative = f"adventures/{adventure_id}.md"
    sections = _sections(text, f"Adventure {adventure_id}", ADVENTURE_SECTIONS, relative)
    metadata = sections["Metadata"]
    require(field(metadata, "Format version", relative) == "3", f"Invalid adventure format: {relative}")
    require(field(metadata, "Campaign ID", relative) == campaign_id, f"Adventure Campaign ID mismatch: {relative}")
    require(field(metadata, "Adventure ID", relative) == adventure_id, f"Adventure ID mismatch: {relative}")
    require(field(metadata, "Document status", relative) == "ready", f"Adventure not approved: {relative}")
    require(canonical_number(field(metadata, "Adventure revision", relative), "Adventure revision", relative) > 0, f"Adventure revision must be positive: {relative}")
    timestamp(field(metadata, "Updated at", relative), "Updated at", relative)
    participants = [item.strip() for item in field(metadata, "Participants", relative).split(",")]
    require(participants and len(participants) == len(set(participants)), f"Invalid participants: {relative}")
    require(all(item in characters and characters[item]["status"] == "ready" for item in participants), f"Unknown participant: {relative}")
    levels = field(metadata, "Participant levels at draft", relative)
    level_entries = re.findall(r"(pc-[a-z0-9-]+)=([1-9][0-9]*)", levels)
    require(", ".join(f"{item}={number}" for item, number in level_entries) == levels,
            f"Invalid participant levels: {relative}")
    require([item for item, _number in level_entries] == participants, f"Participant level roster mismatch: {relative}")
    for name in ("Player Introduction", "Objective and Pressure", "Closure", "Rewards", "DM Scenario"):
        require(sections[name] not in {"", "not-set"}, f"Missing adventure {name}: {relative}")
    for key in ("Objective", "Pressure", "Difficulty rationale"):
        require(field(sections["Objective and Pressure"], key, relative) != "not-set", f"Missing {key}: {relative}")
    for key in ("Success", "Failure", "Abandon"):
        require(field(sections["Closure"], key, relative) != "not-set", f"Missing closure {key}: {relative}")
        reward = field(sections["Rewards"], key, relative)
        entries = [entry.strip() for entry in reward.split(";")]
        pairs = [entry.split("=", 1) for entry in entries]
        require(all(len(pair) == 2 and pair[1].strip() not in {"", "not-set"} for pair in pairs) and
                [pair[0].strip() for pair in pairs] == participants,
                f"Missing/order-mismatched per-character reward {key}: {relative}")
    grants = reward_grants(sections["Rewards"], participants, relative)
    drafted_at = canonical_number(field(metadata, "Save revision at draft", relative), "Save revision at draft", relative)
    require(drafted_at <= save_revision, f"Adventure draft is newer than state: {relative}")
    return {"id": adventure_id, "participants": participants, "levels": {item: int(number) for item, number in level_entries}, "grants": grants}


def _validate_scenes(section: str, characters: dict[str, dict[str, object]], stage: str) -> None:
    focus = field(section, "Focus scene", "SAVE.md")
    scene_headers = re.findall(r"(?m)^### Scene ([a-z0-9-]+)$", section)
    require(1 <= len(scene_headers) <= 24 and len(scene_headers) == len(set(scene_headers)), "Invalid scene roster")
    require(focus in scene_headers, "Focus scene is missing")
    memberships: list[str] = []
    for scene_id in scene_headers:
        start = section.index(f"### Scene {scene_id}\n")
        next_scene = re.search(r"(?m)^### Scene ", section[start + 1:])
        block = section[start: start + 1 + next_scene.start()] if next_scene else section[start:]
        pc_value = field(block, "Player characters", "SAVE.md")
        if pc_value != "none":
            members = [item.strip() for item in pc_value.split(",")]
            require(all(member in characters for member in members), "Scene references unknown character")
            memberships.extend(members)
        for key in ("Location", "Situation", "Visible entities", "Immediate dangers", "Recent context"):
            field(block, key, "SAVE.md")
    require(len(memberships) == len(set(memberships)), "Character appears in multiple scenes")
    if stage in {"playable", "playing", "between-adventures", "complete"}:
        required = {key for key, value in characters.items() if value["status"] in {"ready", "dead"}}
        require(set(memberships) == required, "Ready/dead characters must each have one scene")


def _check_unfinished_transactions(root: Path) -> None:
    folder = _safe_path(root, "transactions", directory=True)
    for candidate in folder.iterdir():
        if candidate.is_dir() and re.fullmatch(r"[0-9]{8}", candidate.name):
            status = candidate / "status"
            if status.exists() or (candidate / "rolls.json").exists():
                require(status.is_file() and status.read_text(encoding="ascii").strip() in {"committed", "aborted"},
                        f"Unfinished transaction: {candidate.name}")
                if status.read_text(encoding="ascii").strip() == "aborted":
                    require((candidate / "abort.json").is_file(), f"Aborted transaction has no reason: {candidate.name}")


def _linked_document(root: Path, relative: str, overlay: dict[str, bytes], metadata: str,
                     revision_key: str, digest_key: str) -> str | None:
    revision = canonical_number(field(metadata, revision_key, "SAVE.md"), revision_key, "SAVE.md")
    expected_hash = field(metadata, digest_key, "SAVE.md")
    data = _read(root, relative, overlay, required=False)
    if data is None:
        require(revision == 0 and expected_hash == "none", f"Missing linked document metadata mismatch: {relative}")
        return None
    require(revision > 0 and DIGEST.fullmatch(expected_hash) is not None, f"Missing linked revision/hash: {relative}")
    require(hashlib.sha256(data).hexdigest() == expected_hash, f"Linked SHA-256 mismatch: {relative}")
    revision_match = re.search(rf"(?m)^- {re.escape(revision_key)}: (0|[1-9][0-9]*)$", data.decode("utf-8"))
    require(revision_match is not None and int(revision_match.group(1)) == revision, f"Linked revision mismatch: {relative}")
    return data.decode("utf-8")


def validate(root: Path, *, turn: bool = False, overrides: dict[str, bytes] | None = None,
             check_transactions: bool = True) -> dict[str, object]:
    root = root.resolve(strict=True)
    overlay = overrides or {}
    require(all(allowed_target(name) for name in overlay), "Overlay contains forbidden target")
    for relative in BASE_DIRS:
        _safe_path(root, relative, directory=True)
    for relative in BASE_FILES:
        _safe_path(root, relative)
    if not turn:
        for relative, expected in REVIEWED_OPERATIONAL_SHA256.items():
            data = _read(root, relative, {})
            assert data is not None
            require(hashlib.sha256(data).hexdigest() == expected, f"Reviewed operational fingerprint mismatch: {relative}")
    if check_transactions:
        _check_unfinished_transactions(root)
    campaign_text = _text(root, "CAMPAIGN.md", overlay)
    save_text = _text(root, "SAVE.md", overlay)
    assert campaign_text is not None and save_text is not None
    campaign = _sections(campaign_text, "Campaign", CAMPAIGN_SECTIONS, "CAMPAIGN.md")
    save = _sections(save_text, "Save", SAVE_SECTIONS, "SAVE.md")
    cmeta, smeta = campaign["Metadata"], save["Metadata"]
    require(field(cmeta, "Format version", "CAMPAIGN.md") == "3", "Campaign is not v3")
    require(field(smeta, "Format version", "SAVE.md") == "3", "Save is not v3")
    campaign_id = field(cmeta, "Campaign ID", "CAMPAIGN.md")
    require(field(smeta, "Campaign ID", "SAVE.md") == campaign_id, "Campaign ID mismatch")
    config_rev = canonical_number(field(cmeta, "Configuration revision", "CAMPAIGN.md"), "Configuration revision", "CAMPAIGN.md")
    save_rev = canonical_number(field(smeta, "Save revision", "SAVE.md"), "Save revision", "SAVE.md")
    applied_rev = canonical_number(field(smeta, "Campaign configuration revision", "SAVE.md"), "Campaign configuration revision", "SAVE.md")
    require(applied_rev <= config_rev, "Save applies future configuration")
    stage = field(smeta, "Workflow stage", "SAVE.md")
    require(stage in STAGES, "Invalid workflow stage")
    if turn:
        require(stage in {"playable", "playing"}, "Turn validator is only for an ordinary active adventure")
    config_status = field(cmeta, "Configuration status", "CAMPAIGN.md")
    campaign_status = field(smeta, "Campaign status", "SAVE.md")
    require(config_status in {"setup-required", "ready"} and campaign_status in {"setup-required", "active", "paused", "ended"}, "Invalid status")
    if stage == "new":
        require(config_rev == save_rev == applied_rev == 0 and campaign_id == "not-set", "New stage must be pristine")
        require(field(cmeta, "Updated at", "CAMPAIGN.md") == field(smeta, "Updated at", "SAVE.md") == "not-set", "Pristine timestamp mismatch")
    else:
        require(CAMPAIGN_ID.fullmatch(campaign_id) is not None and config_rev > 0 and save_rev > 0, "Campaign not initialized")
        timestamp(field(cmeta, "Updated at", "CAMPAIGN.md"), "Updated at", "CAMPAIGN.md")
        timestamp(field(smeta, "Updated at", "SAVE.md"), "Updated at", "SAVE.md")
        require(applied_rev == config_rev, "Configuration/save revision mismatch")
    _validate_source(root, campaign, turn)
    if stage not in {"new"}:
        upstream = (
            (campaign["Rules Baseline"], ("Rules edition", "Baseline reference", "Baseline reference access")),
            (campaign["Party Setup"], ("Control mode", "Target party size")),
            (campaign["Character Creation"], ("Starting level", "Ability score method", "HP method", "Allowed character sources")),
            (campaign["Content Boundaries"], ("Lines", "Veils", "Ask-before topics", "Stop/pause signal")),
        )
        for section, keys in upstream:
            for key in keys:
                require(field(section, key, "CAMPAIGN.md") != "not-set", f"Missing prerequisite {key}")
        require(field(campaign["Rules Baseline"], "Rules edition", "CAMPAIGN.md") in {"dnd-5e-2014", "dnd-5e-2024"}, "Unsupported rules edition")
        target_size = canonical_number(field(campaign["Party Setup"], "Target party size", "CAMPAIGN.md"), "Target party size", "CAMPAIGN.md", maximum=12)
        require(1 <= target_size <= 12, "Target party size must be 1-12")
        method = field(campaign["Character Creation"], "Ability score method", "CAMPAIGN.md").lower()
        if any(token in method for token in ("roll", "брос", "куб")):
            require(field(campaign["Roll Policy"], "Roll authority", "CAMPAIGN.md") != "not-set", "Random abilities need roll authority before creation")
    roster_section = save["Player Characters"]
    characters: dict[str, dict[str, object]] = {}
    if roster_section != "none":
        lines = roster_section.splitlines()
        require(1 <= len(lines) <= 12, "Invalid character count")
        for line in lines:
            match = re.fullmatch(r"- Character: (pc-[a-z0-9-]+) \| revision: (0|[1-9][0-9]*) \| sha256: ([0-9a-f]{64})", line)
            require(match is not None, "Invalid character roster line")
            character_id, revision_text, expected_hash = match.groups()
            require(CHARACTER_ID.fullmatch(character_id) is not None and character_id not in characters, "Invalid/duplicate Character ID")
            revision = canonical_number(revision_text, "Character revision", "SAVE.md")
            require(revision <= save_rev, "Character revision exceeds Save revision")
            relative = f"characters/{character_id}.md"
            data = _read(root, relative, overlay)
            assert data is not None
            require(hashlib.sha256(data).hexdigest() == expected_hash, f"Character SHA-256 mismatch: {character_id}")
            characters[character_id] = _validate_character(data.decode("utf-8"), character_id, campaign_id, revision)
    _validate_scenes(save["Current Scenes"], characters, stage)
    if turn:
        for revision_key, digest_key in (("Lore revision", "Lore sha256"), ("Story revision", "Story sha256")):
            require(canonical_number(field(smeta, revision_key, "SAVE.md"), revision_key, "SAVE.md") > 0 and
                    DIGEST.fullmatch(field(smeta, digest_key, "SAVE.md")) is not None,
                    f"Missing linked {revision_key} metadata")
        lore = story = None
    else:
        lore = _linked_document(root, "LORE.md", overlay, smeta, "Lore revision", "Lore sha256")
        story = _linked_document(root, "CAMPAIGN_STORY.md", overlay, smeta, "Story revision", "Story sha256")
    if stage in {"await-characters", "await-story", "await-final-settings", "playable", "playing", "between-adventures", "complete"}:
        if not turn:
            require(lore is not None, "Lore is missing")
            _validate_lore(lore, campaign_id)
    if stage in {"await-story", "await-final-settings", "playable", "playing", "between-adventures", "complete"}:
        target = canonical_number(field(campaign["Party Setup"], "Target party size", "CAMPAIGN.md"), "Target party size", "CAMPAIGN.md", maximum=12)
        require(sum(item["status"] == "ready" for item in characters.values()) == target, "Party is not ready")
    if stage == "new":
        require(not characters and lore is None and story is None, "Pristine project contains campaign material")
        require(config_status == campaign_status == "setup-required", "New campaign status mismatch")
    if stage == "await-lore":
        require(lore is None and not characters, "Lore stage has later material")
    if stage == "await-characters":
        require(story is None, "Character stage has story material")
    if stage in {"await-final-settings", "playable", "playing", "between-adventures", "complete"}:
        if not turn:
            require(story is not None, "Campaign story is missing")
            _validate_story(story, campaign_id)
            campaign_start = canonical_number(field(campaign["Character Creation"], "Starting level", "CAMPAIGN.md"), "Starting level", "CAMPAIGN.md", maximum=20)
            require(field(_sections(story, "Campaign Story", STORY_SECTIONS, "CAMPAIGN_STORY.md")["Metadata"],
                          "Starting level", "CAMPAIGN_STORY.md") == str(campaign_start), "Story/campaign starting level mismatch")
    candidate = field(smeta, "Adventure candidate", "SAVE.md")
    active = field(smeta, "Active adventure", "SAVE.md")
    adventure_details: dict[str, dict[str, object]] = {}
    for label, adventure_id in (("Adventure candidate", candidate), ("Active adventure", active)):
        hash_value = field(smeta, f"{label} sha256", "SAVE.md")
        if adventure_id == "none":
            require(hash_value == "none", f"Unused {label} has hash")
        else:
            require(ADVENTURE_ID.fullmatch(adventure_id) is not None and adventure_id != "0000", "Invalid adventure ID")
            require(DIGEST.fullmatch(hash_value) is not None, f"Missing {label} hash")
            if not turn:
                data = _read(root, f"adventures/{adventure_id}.md", overlay)
                assert data is not None
                require(hashlib.sha256(data).hexdigest() == hash_value, f"{label} SHA-256 mismatch")
                adventure_details[adventure_id] = _validate_adventure(data.decode("utf-8"), adventure_id, campaign_id, characters, save_rev)
    if candidate != "none" and not turn:
        require(all(adventure_details[candidate]["levels"][item] == characters[item]["level"]
                    for item in adventure_details[candidate]["participants"]), "Candidate levels differ from current character sheets")
    require(candidate == "none" or active == "none", "Candidate and active adventure overlap")
    if stage == "await-final-settings":
        require(candidate != "none" and active == "none", "Final settings need one adventure candidate")
    if stage in {"playable", "playing"}:
        require(active != "none" and candidate == "none", "Playable stage needs active adventure")
    if stage in {"between-adventures", "complete"}:
        require(active == "none", "Closed stage must not have active adventure")
        if stage == "complete":
            require(candidate == "none", "Completed campaign cannot have new adventure candidate")
    if stage in {"playable", "playing", "between-adventures", "complete"}:
        require(config_status == "ready" and campaign_status in {"active", "paused", "ended"}, "Campaign not configured")
        require("not-set" not in campaign_text, "Ready campaign retains not-set setting")
    else:
        require(config_status == campaign_status == "setup-required", "Setup stage status mismatch")
        require(active == "none", "Setup stage cannot have active adventure")
    ledger = save["Adventure Ledger"]
    completed: set[str] = set()
    if ledger != "none":
        for line in ledger.splitlines():
            match = re.fullmatch(r"- Adventure: ([0-9]{4}) \| result: (success|failure|abandon) \| reward: granted \| save-revision: ([1-9][0-9]*) \| sha256: ([0-9a-f]{64})", line)
            require(match is not None, "Invalid adventure ledger line")
            adventure_id = match.group(1)
            require(adventure_id not in completed and int(match.group(3)) <= save_rev, "Duplicate or future adventure reward")
            if not turn:
                previous = _read(root, f"adventures/{adventure_id}.md", overlay)
                assert previous is not None
                require(hashlib.sha256(previous).hexdigest() == match.group(4), "Completed adventure hash mismatch")
                previous_sections = _sections(previous.decode("utf-8"), f"Adventure {adventure_id}",
                                              ADVENTURE_SECTIONS, f"adventures/{adventure_id}.md")
                previous_participants = [item.strip() for item in field(previous_sections["Metadata"], "Participants",
                                               f"adventures/{adventure_id}.md").split(",")]
                previous_grants = reward_grants(previous_sections["Rewards"], previous_participants,
                                                f"adventures/{adventure_id}.md")
                for character_id in previous_participants:
                    require(character_id in characters and characters[character_id]["awards"].get(adventure_id) ==
                            {"result": match.group(2), **previous_grants[(match.group(2), character_id)]},
                            f"Completed adventure award missing/mismatched: {adventure_id}/{character_id}")
            completed.add(adventure_id)
        require(active not in completed and candidate not in completed, "Closed adventure cannot be reactivated")
    if not turn:
        for character_id, character in characters.items():
            require(set(character["awards"]) <= completed,
                    f"Character has an award absent from adventure ledger: {character_id}")
    if stage in {"between-adventures", "complete"}:
        require(bool(completed), "No completed adventure in closed stage")
    if candidate != "none":
        require(int(candidate) == len(completed) + 1, "Candidate adventure number must follow completed adventures")
    if active != "none":
        require(int(active) == len(completed) + 1, "Active adventure number must follow completed adventures")
    if stage == "playable":
        require(campaign_status == "active", "Playable adventure must be active")
    if stage == "playing":
        require(campaign_status in {"active", "paused"}, "Playing campaign status mismatch")
    require(save["Active Combat"].startswith("- Status: "), "Combat status missing")
    if stage not in {"playable", "playing"}:
        require(save["Active Combat"] == "- Status: inactive", "Combat may not run during setup/between adventures")
    return {
        "status": "PASS", "scope": "turn" if turn else "full", "format_version": 3,
        "campaign_id": campaign_id, "configuration_revision": config_rev,
        "save_revision": save_rev, "workflow_stage": stage, "configuration_status": config_status,
        "campaign_status": campaign_status, "character_count": len(characters),
        "active_adventure": active, "adventure_candidate": candidate,
        "completed_adventures": len(completed), "local_reference_hashes_verified": not turn,
        "operational_fingerprints_verified": not turn,
    }
