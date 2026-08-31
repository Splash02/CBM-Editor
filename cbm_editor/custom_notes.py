import copy
import re
import uuid
from functools import lru_cache


CUSTOM_NOTE_TOKENS = ("lane", "time", "end")
CUSTOM_NOTE_SHAPES = ("Circle", "Square", "Triangle")
CUSTOM_NOTE_LANE_MODES = ("Middle", "Top & Bottom", "Top Only", "Bottom Only")
CUSTOM_NOTE_KINDS = ("Note", "Event")
CUSTOM_NOTE_MARKER = "CBMCustom"
_CUSTOM_NOTES = []
_CUSTOM_TOMBSTONES = []
_CUSTOM_TYPES = {}
_CUSTOM_MATCHERS = []


def new_custom_id():
    return uuid.uuid4().hex


def normalize_lane_value(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def default_custom_type(name="Type 1"):
    return {
        "id": new_custom_id(),
        "name": name,
        "kind": "Note",
        "length": False,
        "shape": "Circle",
        "lane_mode": "Top & Bottom",
        "collision": True,
        "color": "#FF4FA3",
        "connection_color": "#B52D73",
        "syntax": "255,0,{time},1,0,{lane}",
        "lane_top_value": 0,
        "lane_bottom_value": 1,
        "lane_single_value": 0,
    }


def default_custom_note(name="Custom Note"):
    return {
        "id": new_custom_id(),
        "name": name,
        "types": [default_custom_type()],
    }


def normalize_custom_type(data):
    source = dict(data or {})
    kind = source.get("kind", "Note")
    if kind not in CUSTOM_NOTE_KINDS:
        kind = "Note"
    shape = source.get("shape", "Circle")
    if shape not in CUSTOM_NOTE_SHAPES:
        shape = "Circle"
    lane_mode = source.get("lane_mode", "Top & Bottom")
    if lane_mode not in CUSTOM_NOTE_LANE_MODES:
        lane_mode = "Top & Bottom"
    color = str(source.get("color", "#FF4FA3")).upper()
    connection_color = str(source.get("connection_color", "#B52D73")).upper()
    if not re.fullmatch(r"#[0-9A-F]{6}", color):
        color = "#FF4FA3"
    if not re.fullmatch(r"#[0-9A-F]{6}", connection_color):
        connection_color = "#B52D73"
    syntax = strip_custom_marker(source.get("syntax") or "255,0,{time},1,0,{lane}")
    syntax = syntax.replace("{lane_x}", "255").replace("{lane_y}", "0").replace("{length}", "{end}")
    return {
        "id": str(source.get("id") or new_custom_id()),
        "name": str(source.get("name") or "Type").strip() or "Type",
        "kind": kind,
        "length": bool(source.get("length", False)) if kind == "Note" else False,
        "shape": shape,
        "lane_mode": lane_mode,
        "collision": bool(source.get("collision", True)),
        "color": color,
        "connection_color": connection_color,
        "syntax": syntax,
        "lane_top_value": normalize_lane_value(source.get("lane_top_value"), 0),
        "lane_bottom_value": normalize_lane_value(source.get("lane_bottom_value"), 1),
        "lane_single_value": normalize_lane_value(source.get("lane_single_value"), 0),
    }


def normalize_custom_note(data):
    source = dict(data or {})
    types = [normalize_custom_type(item) for item in source.get("types", []) if isinstance(item, dict)]
    if not types:
        types = [default_custom_type()]
    return {
        "id": str(source.get("id") or new_custom_id()),
        "name": str(source.get("name") or "Custom Note").strip() or "Custom Note",
        "types": types,
    }


def normalize_custom_notes(notes):
    return [normalize_custom_note(item) for item in notes or [] if isinstance(item, dict)]


def normalize_custom_tombstones(tombstones):
    result = []
    for item in tombstones or []:
        if not isinstance(item, dict):
            continue
        normalized = normalize_custom_type(item)
        normalized["note_id"] = str(item.get("note_id") or "")
        normalized["note_name"] = str(item.get("note_name") or "Missing")
        result.append(normalized)
    return result


def strip_custom_marker(template):
    result = str(template or "").strip()
    suffix = "," + CUSTOM_NOTE_MARKER
    while result.endswith(suffix):
        result = result[:-len(suffix)].rstrip()
    return result


def mark_custom_template(template):
    base = strip_custom_marker(template)
    return base + "," + CUSTOM_NOTE_MARKER


@lru_cache(maxsize=512)
def compile_custom_template(template):
    marked_template = mark_custom_template(template)
    fields = marked_template.split(",")
    if len(fields) < 3:
        raise ValueError("The syntax must contain standard HitObject position fields.")
    token_pattern = re.compile(r"\{([a-z_]+)\}")
    parts = []
    seen = set()
    for field_index, field in enumerate(fields):
        if field_index > 0:
            parts.append(",")
        matches = list(token_pattern.finditer(field))
        if field_index < 2 and not matches:
            group_name = "_lane_x" if field_index == 0 else "_lane_y"
            parts.append(f"(?P<{group_name}>-?\\d+)")
            continue
        position = 0
        for match in matches:
            token = match.group(1)
            if token not in CUSTOM_NOTE_TOKENS:
                raise ValueError(f"Unknown placeholder: {{{token}}}")
            parts.append(re.escape(field[position:match.start()]))
            if token in seen:
                parts.append(f"(?P={token})")
            else:
                parts.append(f"(?P<{token}>-?\\d+)")
                seen.add(token)
            position = match.end()
        parts.append(re.escape(field[position:]))
    return re.compile("^" + "".join(parts) + "$"), frozenset(seen)


def validate_custom_type(type_data):
    item = normalize_custom_type(type_data)
    try:
        pattern, tokens = compile_custom_template(item["syntax"])
    except ValueError as error:
        return False, str(error)
    if "time" not in tokens:
        return False, "The syntax must contain {time}."
    if item["length"] and "end" not in tokens:
        return False, "Length notes must contain {end}."
    if (
        "lane" in tokens
        and item["lane_mode"] == "Top & Bottom"
        and item["lane_top_value"] == item["lane_bottom_value"]
    ):
        return False, "Top and bottom lane values must be different."
    preview_lane = -2 if item["lane_mode"] == "Middle" else (1 if item["lane_mode"] == "Bottom Only" else 0)
    preview_values = {
        "time": 1000,
        "end": 1500,
        "lane": preview_lane,
    }
    preview = render_custom_template(item["syntax"], preview_values, item)
    if len(preview.split(",")) < 5:
        return False, "The syntax must be a complete HitObject line with at least five comma-separated fields."
    try:
        int(preview.split(",")[0])
        int(preview.split(",")[1])
    except (IndexError, ValueError):
        return False, "The first two HitObject fields must resolve to numeric positions."
    if pattern.fullmatch(preview) is None:
        return False, "The syntax could not be parsed."
    return True, ""


def custom_lane_token_value(type_data, lane):
    logical_lane = int(lane)
    if type_data is None:
        return logical_lane
    mode = type_data.get("lane_mode", "Top & Bottom")
    if mode == "Top & Bottom":
        if logical_lane <= 0:
            return normalize_lane_value(type_data.get("lane_top_value"), 0)
        return normalize_lane_value(type_data.get("lane_bottom_value"), 1)
    return normalize_lane_value(type_data.get("lane_single_value"), 0)


def render_custom_template(template, values, type_data=None):
    result = mark_custom_template(template)
    source_fields = result.split(",")
    for token in CUSTOM_NOTE_TOKENS:
        placeholder = "{" + token + "}"
        if placeholder in result:
            value = values[token]
            if token == "lane":
                value = custom_lane_token_value(type_data, value)
            result = result.replace(placeholder, str(int(value)))
    fields = result.split(",")
    if len(fields) >= 2 and "lane" in values:
        lane_x, lane_y = custom_lane_values(int(values["lane"]))
        token_pattern = re.compile(r"\{[a-z_]+\}")
        if not token_pattern.search(source_fields[0]):
            fields[0] = str(lane_x)
        if not token_pattern.search(source_fields[1]):
            fields[1] = str(lane_y)
        result = ",".join(fields)
    return result


def custom_lane_values(lane):
    if lane == -2:
        return 427, 0
    if lane <= 0:
        return 255, 0
    return 256, 0


def infer_custom_lane(type_data, values, line):
    mode = type_data.get("lane_mode", "Top & Bottom")
    if "lane" in values:
        lane_value = int(values["lane"])
        if mode == "Top & Bottom":
            top_value = normalize_lane_value(type_data.get("lane_top_value"), 0)
            bottom_value = normalize_lane_value(type_data.get("lane_bottom_value"), 1)
            if lane_value == top_value and lane_value != bottom_value:
                return 0
            if lane_value == bottom_value and lane_value != top_value:
                return 1
            return None
        expected_value = normalize_lane_value(type_data.get("lane_single_value"), 0)
        if lane_value != expected_value:
            return None
    if mode == "Middle":
        return -2
    if mode == "Top Only":
        return 0
    if mode == "Bottom Only":
        return 1
    try:
        fields = line.split(",")
        x_value = int(fields[0])
        y_value = int(fields[1]) if len(fields) > 1 else 0
    except (TypeError, ValueError):
        x_value = 255
        y_value = 0
    if x_value == 427:
        return -2
    if y_value in (192,):
        return 0
    if y_value in (320,):
        return 1
    return 0 if int(x_value) <= 255 else 1


def set_custom_note_registry(notes, tombstones):
    global _CUSTOM_NOTES, _CUSTOM_TOMBSTONES, _CUSTOM_TYPES, _CUSTOM_MATCHERS
    _CUSTOM_NOTES = normalize_custom_notes(notes)
    _CUSTOM_TOMBSTONES = normalize_custom_tombstones(tombstones)
    _CUSTOM_TYPES = {}
    matchers = []
    for note in _CUSTOM_NOTES:
        for type_data in note["types"]:
            item = copy.deepcopy(type_data)
            item["note_id"] = note["id"]
            item["note_name"] = note["name"]
            _CUSTOM_TYPES[item["id"]] = item
            try:
                pattern, tokens = compile_custom_template(item["syntax"])
                prefix = ""
                anchor_source = ",".join(mark_custom_template(item["syntax"]).split(",")[2:])
                anchor = max(re.split(r"\{[a-z_]+\}", anchor_source), key=len)
                matchers.append((False, prefix, anchor, pattern, tokens, item))
            except ValueError:
                pass
    for type_data in _CUSTOM_TOMBSTONES:
        try:
            pattern, tokens = compile_custom_template(type_data["syntax"])
            prefix = ""
            anchor_source = ",".join(mark_custom_template(type_data["syntax"]).split(",")[2:])
            anchor = max(re.split(r"\{[a-z_]+\}", anchor_source), key=len)
            matchers.append((True, prefix, anchor, pattern, tokens, copy.deepcopy(type_data)))
        except ValueError:
            pass
    _CUSTOM_MATCHERS = matchers
    return copy.deepcopy(_CUSTOM_NOTES), copy.deepcopy(_CUSTOM_TOMBSTONES)


def get_custom_notes():
    return copy.deepcopy(_CUSTOM_NOTES)


def get_custom_tombstones():
    return copy.deepcopy(_CUSTOM_TOMBSTONES)


def get_custom_type(type_id):
    return _CUSTOM_TYPES.get(str(type_id))


def match_custom_hitobject_line(line):
    for missing, prefix, anchor, pattern, tokens, type_data in _CUSTOM_MATCHERS:
        if prefix and not line.startswith(prefix):
            continue
        if anchor and anchor not in line:
            continue
        match = pattern.fullmatch(line)
        if match is None:
            continue
        values = {token: int(match.group(token)) for token in tokens}
        time_value = values["time"]
        if "end" in values:
            end_value = values["end"]
        else:
            end_value = time_value
        lane = infer_custom_lane(type_data, values, line)
        if lane is None:
            continue
        return copy.deepcopy(type_data), values, time_value, end_value, lane, missing
    return None


def custom_type_to_tombstone(note, type_data):
    item = normalize_custom_type(type_data)
    item["note_id"] = str(note.get("id") or "")
    item["note_name"] = str(note.get("name") or "Missing")
    return item


def custom_type_parser_key(type_data):
    item = normalize_custom_type(type_data)
    return (
        item["id"],
        item["syntax"],
        item["lane_mode"],
        item["lane_top_value"],
        item["lane_bottom_value"],
        item["lane_single_value"],
    )
