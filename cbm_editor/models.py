from .widgets import *
from .custom_notes import *

register_shared_globals(globals())

def find_linux_custom_songs_path(game_root):
    game_root = Path(game_root).expanduser().absolute()
    steamapps = game_root.parent.parent if game_root.parent.name.lower() == "common" else None
    app_id = None
    if steamapps and steamapps.name.lower() == "steamapps":
        for manifest in steamapps.glob("appmanifest_*.acf"):
            try:
                content = manifest.read_text(encoding="utf-8", errors="ignore")
                install_match = re.search(r'"installdir"\s+"([^"]+)"', content, re.IGNORECASE)
                if not install_match:
                    continue
                install_path = steamapps / "common" / install_match.group(1)
                if install_path.resolve() != game_root.resolve():
                    continue
                id_match = re.search(r'"appid"\s+"(\d+)"', content, re.IGNORECASE)
                if id_match:
                    app_id = id_match.group(1)
                    break
            except OSError:
                continue
    if steamapps and app_id:
        users_root = steamapps / "compatdata" / app_id / "pfx" / "drive_c" / "users"
        users = []
        steam_user = users_root / "steamuser"
        if steam_user.exists():
            users.append(steam_user)
        if users_root.exists():
            users.extend(path for path in users_root.iterdir() if path.is_dir() and path not in users)
        if not users:
            users.append(steam_user)
        return users[0] / "AppData" / "LocalLow" / "D-CELL GAMES" / "UNBEATABLE" / "CustomSongs"
    if steamapps:
        compatdata = steamapps / "compatdata"
        if compatdata.exists():
            candidates = list(compatdata.glob("*/pfx/drive_c/users/*/AppData/LocalLow/D-CELL GAMES/UNBEATABLE"))
            existing = next((path / "CustomSongs" for path in candidates if (path / "CustomSongs").exists()), None)
            if existing:
                return existing
            if len(candidates) == 1:
                return candidates[0] / "CustomSongs"
    config_value = os.environ.get("XDG_CONFIG_HOME")
    config_root = Path(config_value).expanduser() if config_value else Path.home() / ".config"
    return config_root / "unity3d" / "D-CELL GAMES" / "UNBEATABLE" / "CustomSongs"

def find_unbeatable_root() -> Optional[Path]:
    possible_roots = []

    if sys.platform.startswith("win"):
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam")
            steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)
            
            if steam_path:
                steam_path = Path(steam_path)
                library_vdf = steam_path / "steamapps" / "libraryfolders.vdf"
                
                paths = [steam_path]
                
                if library_vdf.exists():
                    with open(library_vdf, 'r', encoding='utf-8') as f:
                        content = f.read()
                        matches = re.findall(r'"path"\s+"(.+?)"', content)
                        for m in matches:
                            clean_path = m.replace("\\\\", "\\")
                            paths.append(Path(clean_path))
                
                for p in paths:
                    possible_roots.append(p / "steamapps" / "common" / "UNBEATABLE")
                    possible_roots.append(p / "steamapps" / "common" / "UNBEATABLE [white label]")
        except Exception as e:
            print(f"LOAD UI BG ERROR: {e}")
            import traceback
            traceback.print_exc()

        for root in possible_roots:
            if root.exists():
                return root
    else:
        try:
            steam_path = Path.home() / ".local" / "share" / "Steam"
            
            if steam_path.exists():
                library_vdf = steam_path / "steamapps" / "libraryfolders.vdf"
                
                paths = [steam_path]
                
                if library_vdf.exists():
                    with open(library_vdf, 'r', encoding='utf-8') as f:
                        content = f.read()
                        matches = re.findall(r'"path"\s+"(.+?)"', content)
                        for m in matches:
                            paths.append(Path(m))
                
                for p in paths:
                    possible_roots.append(p / "steamapps" / "common" / "UNBEATABLE")
                    possible_roots.append(p / "steamapps" / "common" / "UNBEATABLE [white label]")
        except Exception as e:
            print(f"LOAD UI BG ERROR: {e}")
            import traceback
            traceback.print_exc()

        for root in possible_roots:
            if root.exists():
                return root

    
    return None

@dataclass
class BeatmapMetadata:
    Title: str = ""
    TitleUnicode: str = ""
    Artist: str = ""
    ArtistUnicode: str = ""
    Creator: str = ""
    Version: str = "Beginner"
    AudioFilename: str = ""
    BPM: float = 120.0
    Offset: int = 0
    PreviewTime: int = -1
    Level: int = 1
    FlavorText: str = ""
    SongLength: float = 0.0
    ActualAudioLength: float = 0.0
    GridSize: int = 4
    Attributes: list = None

    def __post_init__(self):
        if self.Attributes is None:
            self.Attributes = []

_hit_object_uid_counter = 0

HITOBJECT_X_RANGES = (
    (171, 255, 255),
    (256, 341, 256),
    (342, 426, 384),
    (427, 511, 427),
)


def interpreted_hitobject_x(value):
    """Return the UNBEATABLE X category without changing the stored X value."""
    try:
        x_value = int(value)
    except (TypeError, ValueError):
        return None
    for minimum, maximum, interpreted_x in HITOBJECT_X_RANGES:
        if minimum <= x_value <= maximum:
            return interpreted_x
    return None

@dataclass(slots=True)
class CustomObjectData:
    type_id: str
    note_id: str
    lane: int
    end_time: int
    raw_line: str
    missing: bool = False
    section: str = "HitObjects"

def copy_custom_object_data(data):
    if data is None:
        return None
    return CustomObjectData(
        data.type_id,
        data.note_id,
        data.lane,
        data.end_time,
        data.raw_line,
        data.missing,
        data.section,
    )

def custom_object_data_to_tuple(data):
    if data is None:
        return None
    return (
        data.type_id,
        data.note_id,
        data.lane,
        data.end_time,
        data.raw_line,
        data.missing,
        data.section,
    )

def custom_object_data_from_tuple(data):
    if not data:
        return None
    return CustomObjectData(*data)

@dataclass(eq=False, slots=True)
class HitObject:
    x: int
    y: int
    time: int
    type: int
    hitSound: int
    objectParams: str = "0"
    hitSample: str = "0:0:0:"
    order_index: int = 0
    creation_time: float = 0.0
    last_update_time: float = 0.0
    tc_is_blue: bool = None
    uid: int = -1
    custom_data: object = None
    _cached_end_params: str = field(default=None, init=False, repr=False)
    _cached_end_value: int = field(default=0, init=False, repr=False)
    _current_visual_time: float = field(init=False, repr=False)
    _target_visual_time: float = field(init=False, repr=False)
    _current_visual_end_time: float = field(init=False, repr=False)
    _target_visual_end_time: float = field(init=False, repr=False)
    _current_visual_lane: float = field(init=False, repr=False)
    _target_visual_lane: float = field(init=False, repr=False)
    _current_visual_pair_lane: float = field(init=False, repr=False)
    _target_visual_pair_lane: float = field(init=False, repr=False)

    def __post_init__(self):
        global _hit_object_uid_counter
        if self.uid == -1:
            self.uid = _hit_object_uid_counter
            _hit_object_uid_counter += 1

    @property
    def interpreted_x(self):
        return interpreted_hitobject_x(self.x)

    @property
    def is_event(self):
        if self.custom_data is not None:
            return False
        return self.interpreted_x == 384

    @property
    def is_flip(self):
        if self.custom_data is not None:
            return False
        return self.interpreted_x == 384 and self.hitSound == 0

    @property
    def is_toggle_center(self):
        if self.custom_data is not None:
            return False
        return self.interpreted_x == 384 and self.hitSound == 2
    
    @property
    def is_instant_flip(self):
        if self.custom_data is not None:
            return False
        return self.interpreted_x == 384 and self.hitSound == 8

    @property
    def is_spike(self):
        if self.custom_data is not None:
            return False
        return self.hitSound == 2 and self.type != 128 and not self.is_event and self.objectParams != "3"

    @property
    def is_hide(self):
        if self.custom_data is not None:
            return False
        return self.hitSound == 8 and not self.is_event and self.objectParams != "3"

    @property
    def is_fly_in(self):
        if self.custom_data is not None:
            return False
        if self.is_event:
            return False
        if self.type == 128 and self.hitSound == 0:
            parts = self.hitSample.split(":")
            return len(parts) > 0 and parts[0] == "1"
        return self.objectParams == "1"

    @property
    def is_hold(self):
        if self.custom_data is not None:
            return False
        return self.type == 128 and self.hitSound == 0 and not self.hitSample.startswith(("3:1", "3:0"))

    @property
    def is_screamer(self):
        if self.custom_data is not None:
            return False
        return self.type == 128 and self.hitSound == 2 and not self.hitSample.startswith(("3:1", "3:0"))
    
    @property
    def is_spam(self):
        if self.custom_data is not None:
            return False
        return self.type == 128 and self.hitSound == 4 and not self.hitSample.startswith(("3:1", "3:0"))
    
    @property
    def is_brawl_hit(self):
        if self.custom_data is not None:
            return False
        return self.type == 1 and self.hitSound in (0, 2, 8, 10) and self.objectParams == "3" and not self.is_event
    
    @property
    def is_brawl_final(self):
        if self.custom_data is not None:
            return False
        return self.type == 1 and self.hitSound in (4, 6, 12, 14) and self.objectParams == "3" and not self.is_event

    @property
    def brawl_cop_number(self):
        if self.hitSound in (0, 4): return 1
        if self.hitSound in (2, 6): return 2
        if self.hitSound in (8, 12): return 3
        if self.hitSound in (10, 14): return 4
        return 1

    @property
    def is_brawl_hold(self):
        if self.custom_data is not None:
            return False
        return self.type == 128 and self.hitSample.startswith("3:1")

    @property
    def is_brawl_spam(self):
        if self.custom_data is not None:
            return False
        return self.type == 128 and self.hitSample.startswith("3:0")

    @property
    def is_brawl_hold_knockout(self):
         return self.is_brawl_hold and self.hitSound in (4, 6, 12, 14)

    @property
    def is_brawl_spam_knockout(self):
         return self.is_brawl_spam and self.hitSound in (4, 6, 12, 14)

    @property
    def is_freestyle(self):
        if self.custom_data is not None:
            return False
        return self.interpreted_x == 427 and self.type == 1 and self.objectParams != "3" and self.objectParams != "Flip"

    @property
    def lane(self):
        if self.custom_data is not None:
            return self.custom_data.lane
        if self.is_event or self.is_freestyle: return -1
        if self.y == 192: return -1
        if self.y == 320: return 2
        if self.interpreted_x == 255: return 0
        return 1
    
    @property
    def end_time(self):
        if self.custom_data is not None:
            return self.custom_data.end_time
        if self.type == 128:
            params = self.objectParams
            if params == self._cached_end_params:
                return self._cached_end_value
            try:
                value = int(params)
            except (TypeError, ValueError):
                return self.time
            self._cached_end_params = params
            self._cached_end_value = value
            return value
        return self.time

    @end_time.setter
    def end_time(self, value):
        if self.custom_data is not None:
            self.custom_data.end_time = int(value)
            return
        if self.type == 128:
            parsed_value = int(value)
            self.objectParams = str(parsed_value)
            self._cached_end_params = self.objectParams
            self._cached_end_value = parsed_value

class BeatmapData:
    def __init__(self, difficulty_key: str):
        self.difficulty_key = difficulty_key
        self.metadata = BeatmapMetadata(Version=difficulty_key)
        self.hit_objects: List[HitObject] = []
        self.timing_points = [{'time': 0, 'bpm': 120.0}]
        self.created = False
        self.unsaved = False
        self._edit_revision = 0
        self.editor_zoom = 1.0
        self.filename: Optional[str] = None
        
    def get_filename(self) -> str:
        if self.filename:
            return self.filename
        return f"{self.difficulty_key}.txt"

    def copy_from(self, other: 'BeatmapData'):
        self.metadata.Title = other.metadata.Title
        self.metadata.TitleUnicode = other.metadata.TitleUnicode
        self.metadata.Artist = other.metadata.Artist
        self.metadata.ArtistUnicode = other.metadata.ArtistUnicode
        self.metadata.Creator = other.metadata.Creator
        self.metadata.AudioFilename = other.metadata.AudioFilename
        self.metadata.BPM = other.metadata.BPM
        self.metadata.Offset = other.metadata.Offset
        self.metadata.Level = other.metadata.Level
        self.metadata.FlavorText = other.metadata.FlavorText
        self.metadata.Attributes = list(other.metadata.Attributes)
        self.metadata.GridSize = other.metadata.GridSize
        
        self.timing_points = [tp.copy() for tp in getattr(other, 'timing_points', [])]
        
        self.hit_objects = [HitObject(ho.x, ho.y, ho.time, ho.type, ho.hitSound, ho.objectParams, ho.hitSample, ho.order_index, custom_data=copy_custom_object_data(ho.custom_data)) 
                           for ho in other.hit_objects]
        self.created = True
        self.unsaved = True
        self.editor_zoom = other.editor_zoom

    def _resolve_event_orders(self):
        toggle_centers = sorted([o for o in self.hit_objects if o.is_toggle_center], key=lambda x: (x.time, x.order_index))
        tc_start_ids = set(o.uid for i, o in enumerate(toggle_centers) if i % 2 == 0)

        current_time = -1
        seen_note = False
        
        for obj in self.hit_objects:
            if obj.time != current_time:
                current_time = obj.time
                seen_note = False
            
            if obj.is_toggle_center:
                if obj.uid in tc_start_ids:
                    obj.order_index = 0
                else:
                    obj.order_index = 1
            elif obj.is_event:
                if seen_note:
                    obj.order_index = 1
                else:
                    obj.order_index = 0
            elif obj.is_spike:
                if seen_note:
                    obj.order_index = 1
                else:
                    obj.order_index = 0
            elif not obj.is_event:
                if obj.custom_data is not None:
                    continue
                seen_note = True

    def _generate_save_objects(self):
        all_objs = sorted(self.hit_objects, key=lambda x: (x.time, 0 if x.is_event and x.order_index == 0 else (2 if x.is_event else 1), 0 if getattr(x, 'is_freestyle', False) else 1, 0.5 if not x.is_event else float(x.order_index)))
        from itertools import groupby
        grouped = groupby(all_objs, key=lambda x: x.time)
        
        final_objects = []
        
        is_centered = False
        is_right = True
        
        for time_ms, group in grouped:
            objs = list(group)
            
            events_pre = [o for o in objs if o.is_event and o.order_index == 0]
            events_post = sorted([o for o in objs if o.is_event and o.order_index > 0], key=lambda x: x.order_index)
            notes = [o for o in objs if not o.is_event]
            
            for e in events_pre:
                final_objects.append(e)
                if e.is_toggle_center:
                    is_centered = not is_centered
                elif e.is_flip or e.is_instant_flip:
                    is_right = not is_right
            
            if not notes:
                pass
            elif not is_centered:
                for n in notes:
                    if n.custom_data is not None:
                        final_objects.append(n)
                        continue
                    n_copy = HitObject(n.x, n.y, n.time, n.type, n.hitSound, n.objectParams, n.hitSample, n.order_index)
                    if n.is_freestyle:
                        final_objects.append(n_copy)
                        continue

                    if n.is_spam:
                        n_copy.x = 427
                        final_objects.append(n_copy)
                        continue

                    if n.lane == -1: n_copy.x = 255
                    elif n.lane == 2: n_copy.x = 256
                    final_objects.append(n_copy)
            else:
                group_right = []
                group_left = []
                
                for n in notes:
                    if n.custom_data is not None:
                        final_objects.append(n)
                        continue
                    if n.is_freestyle:
                        n_copy = HitObject(n.x, n.y, n.time, n.type, n.hitSound, n.objectParams, n.hitSample, n.order_index)
                        final_objects.append(n_copy)
                        continue

                    n_copy = HitObject(n.x, n.y, n.time, n.type, n.hitSound, n.objectParams, n.hitSample, n.order_index)
                    n_copy.y = 0
                    if n.is_spam: n_copy.x = 427
                    
                    l = n.lane 
                    if l == -1: 
                        if not n.is_spam: n_copy.x = 255
                        group_left.append(n_copy)
                    elif l == 2: 
                        if not n.is_spam: n_copy.x = 256
                        group_left.append(n_copy)
                    elif l == 0:
                        if not n.is_spam: n_copy.x = 255
                        group_right.append(n_copy)
                    else:
                        if not n.is_spam: n_copy.x = 256
                        group_right.append(n_copy)
                
                if is_right:
                    final_objects.extend(group_right)
                    
                    if group_left:
                        flip = HitObject(384, 0, time_ms, 1, 8, "Flip", "0:0:0:", 0)
                        final_objects.append(flip)
                        is_right = False
                        
                        final_objects.extend(group_left)
                else:
                    final_objects.extend(group_left)
                    
                    if group_right:
                        flip = HitObject(384, 0, time_ms, 1, 8, "Flip", "0:0:0:", 0)
                        final_objects.append(flip)
                        is_right = True
                        
                        final_objects.extend(group_right)

            for e in events_post:
                if e.is_toggle_center:
                    was_centered = is_centered
                    is_centered = not is_centered
                    if was_centered:
                        target_is_right = getattr(e, 'tc_is_blue', None)
                        if target_is_right is not None and is_right != target_is_right:
                            flip = HitObject(384, 0, time_ms, 1, 8, "Flip", "0:0:0:", 0.8)
                            final_objects.append(flip)
                            is_right = target_is_right
                final_objects.append(e)
                if e.is_flip or e.is_instant_flip:
                    if not e.is_toggle_center:
                        is_right = not is_right
                    
        return final_objects

    def _custom_object_section(self, obj):
        type_data = get_custom_type(obj.custom_data.type_id) if obj.custom_data is not None else None
        if type_data is not None:
            return type_data.get("section", "HitObjects")
        return getattr(obj.custom_data, "section", "HitObjects") if obj.custom_data is not None else "HitObjects"

    def _render_custom_object_line(self, obj):
        type_data = get_custom_type(obj.custom_data.type_id)
        if type_data is None or obj.custom_data.missing:
            return obj.custom_data.raw_line
        values = {
            "time": obj.time,
            "end": obj.end_time,
            "lane": obj.custom_data.lane,
        }
        try:
            rendered = render_custom_template(type_data["syntax"], values, type_data)
            obj.custom_data.raw_line = rendered
            obj.custom_data.section = type_data.get("section", "HitObjects")
            return rendered
        except Exception:
            return obj.custom_data.raw_line

    def save(self, folder: Path, extension: str = None):
        old_filename = self.filename

        artist = self.metadata.Artist or "Unknown Artist"
        title = self.metadata.Title or "Unknown Title"
        creator = self.metadata.Creator or "Unknown Creator"
        diff_map = {
            "Beginner": "Beginner",
            "Normal": "Easy",
            "Hard": "Normal",
            "Expert": "Hard",
            "UNBEATABLE": "UNBEATABLE",
            "Star": "Star"
        }
        internal_diff = diff_map.get(self.difficulty_key, self.difficulty_key)

        base_name = f"{artist} - {title} ({creator}) [{internal_diff}]"
        base_name = re.sub(r'[<>:"/\\|?*]', '_', base_name)

        if extension:
             self.filename = f"{base_name}{extension}"
        else:
             self.filename = f"{base_name}.txt"

        if old_filename and old_filename != self.filename:
            old_path = folder / old_filename
            if old_path.exists():
                try:
                    old_path.unlink()
                except:
                    pass

        path = folder / self.get_filename()
        
        objects_to_save = self._generate_save_objects()

        length = 0.0
        if objects_to_save:
            last_obj = max(objects_to_save, key=lambda o: o.end_time)
            length = last_obj.end_time / 1000.0 + 2.0
            
        tags_data = {
            "Level": self.metadata.Level,
            "FlavorText": self.metadata.FlavorText,
            "SongLength": length,
            "Attributes": self.metadata.Attributes
        }
        
        difficulty_name = self.difficulty_key
        version_name = self.metadata.Version
        if not version_name:
             version_name = difficulty_name

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"-Made With CBM Editor {VERSION_NUMBER} by Splash!-\n")
                f.write("[General]\n")
                f.write(f"AudioFilename: {self.metadata.AudioFilename}\n")
                f.write(f"AudioLeadIn: 0\n")
                f.write(f"PreviewTime: -1\n\n")

                f.write("[Metadata]\n")
                f.write(f"Title:{self.metadata.Title}\n")
                f.write(f"TitleUnicode:{self.metadata.TitleUnicode if self.metadata.TitleUnicode else self.metadata.Title}\n")
                f.write(f"Artist:{self.metadata.Artist}\n")
                f.write(f"ArtistUnicode:{self.metadata.ArtistUnicode if self.metadata.ArtistUnicode else self.metadata.Artist}\n")
                f.write(f"Creator:{self.metadata.Creator}\n")
                f.write(f"Difficulty:{difficulty_name}\n")
                f.write(f"Version:{version_name}\n")
                f.write("Source:\n")
                f.write(f"Tags:{json.dumps(tags_data, separators=(',', ':'))}\n\n")

                f.write("[Editor]\n")
                f.write(f"GridSize:{self.metadata.GridSize}\n")
                f.write(f"Zoom:{self.editor_zoom}\n\n")

                f.write("[Events]\n")
                custom_event_objects = [
                    ho for ho in objects_to_save
                    if ho.custom_data is not None and self._custom_object_section(ho) == "Events"
                ]
                custom_event_objects.sort(key=lambda ho: (ho.time, ho.creation_time, ho.uid))
                for ho in custom_event_objects:
                    f.write(f"{self._render_custom_object_line(ho)}\n")
                f.write("\n")

                f.write("[TimingPoints]\n")
                if self.timing_points:
                    self.timing_points.sort(key=lambda x: x['time'])
                    for tp in self.timing_points:
                         beat_len = 60000.0 / tp['bpm'] if tp['bpm'] > 0 else 500
                         f.write(f"{int(tp['time'])},{beat_len},4,1,0,100,1,0\n")
                    f.write("\n")
                else:
                    beat_len = 60000.0 / self.metadata.BPM if self.metadata.BPM > 0 else 500
                    f.write(f"{int(self.metadata.Offset)},{beat_len},4,1,0,100,1,0\n\n")
                
                f.write("[HitObjects]\n")
                for ho in objects_to_save:
                    if ho.custom_data is not None:
                        if self._custom_object_section(ho) == "Events":
                            continue
                        f.write(f"{self._render_custom_object_line(ho)}\n")
                        continue
                    param_str = ho.objectParams
                    if ho.is_event and param_str == "Flip":
                        param_str = "0"
                        
                    hit_sample = ho.hitSample if ho.hitSample else "0:0:0:0:"
                    if not hit_sample.endswith(":"):
                        hit_sample += ":"
                    
                    if ho.is_hold and ho.is_fly_in:
                        parts = hit_sample.rstrip(":").split(":")
                        while len(parts) < 4:
                            parts.append("0")
                        parts[0] = "1"
                        hit_sample = ":".join(parts) + ":"
                        
                    output_x = interpreted_hitobject_x(ho.x)
                    if output_x is None:
                        output_x = ho.x
                    f.write(f"{output_x},0,{ho.time},{ho.type},{ho.hitSound},{param_str}:{hit_sample}\n")
                
            self.created = True
            self.unsaved = False
            
            if old_filename and old_filename != self.filename:
                 old_path = folder / old_filename
                 if old_path.exists() and str(old_path.absolute()).lower() != str(path.absolute()).lower():
                      try:
                           os.remove(old_path)
                      except:
                           pass

            return True
        except Exception as e:
            print(f"Error saving {path}: {e}")
            return False

    def load(self, folder: Path, filename: str = None):
        if filename:
            self.filename = filename
            path = folder / filename
        else:
            path = folder / self.get_filename()
            if not path.exists() and path.suffix == ".osu":
                 txt_path = folder / f"{self.difficulty_key}.txt"
                 if txt_path.exists():
                     path = txt_path
                     self.filename = path.name

        if not path.exists():
            return False
            
        self.created = True
        self.unsaved = False
        self.hit_objects.clear()
        if not hasattr(self, 'timing_points'):
             self.timing_points = []
        self.timing_points.clear()
        
        current_section = ""
        raw_objects = []
        extracted_version = None
        extracted_difficulty = None
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if not lines:
                return True

            for raw_line in lines:
                original_line = raw_line.rstrip("\r\n")
                line = original_line.strip()
                if not line or line.startswith("//"):
                    if line.startswith("//"):
                        continue
                
                if line.startswith("[") and line.endswith("]"):
                    current_section = line
                    continue

                if current_section in ("[HitObjects]", "[Events]"):
                    section_name = current_section.strip("[]")
                    custom_match = match_custom_hitobject_line(line, section_name)
                    if custom_match is not None:
                        type_data, values, time_value, end_value, lane, missing = custom_match
                        fields = line.split(",")
                        try:
                            parsed_x = int(fields[0])
                        except (IndexError, ValueError):
                            parsed_x = 427 if lane == -2 else (255 if lane <= 0 else 256)
                        try:
                            parsed_y = int(fields[1])
                        except (IndexError, ValueError):
                            parsed_y = 0
                        try:
                            parsed_type = int(fields[3])
                        except (IndexError, ValueError):
                            parsed_type = 1
                        try:
                            parsed_hit_sound = int(fields[4])
                        except (IndexError, ValueError):
                            parsed_hit_sound = 0
                        custom_data = CustomObjectData(
                            str(type_data.get("id") or ""),
                            str(type_data.get("note_id") or ""),
                            lane,
                            end_value,
                            original_line,
                            missing,
                            type_data.get("section", section_name),
                        )
                        raw_objects.append(HitObject(
                            parsed_x,
                            parsed_y,
                            time_value,
                            parsed_type,
                            parsed_hit_sound,
                            "0",
                            "0:0:0:",
                            custom_data=custom_data,
                        ))
                        continue
                    if current_section == "[Events]":
                        continue
                    parts = line.split(",")
                    if len(parts) >= 5:
                        try:
                            x = int(parts[0])
                            y = int(parts[1])
                            time = int(parts[2])
                            type_ = int(parts[3])
                            hitSound = int(parts[4])
                            extras = parts[5] if len(parts) > 5 else ""

                            if str(path).lower().endswith(".osu") or str(path).lower().endswith(".txt"):
                                interpreted_x = interpreted_hitobject_x(x)
                                if interpreted_x is None:
                                    continue
                                # Keep the source X coordinate intact. Only Y is
                                # normalized for the non-event categories, as before.
                                if interpreted_x != 384:
                                    y = 0
                            obj_params = "0"
                            hit_sample = "0:0:0:"
                            if ":" in extras:
                                p_split = extras.split(":", 1)
                                obj_params = p_split[0]
                                hit_sample = p_split[1]
                            else:
                                obj_params = extras
                            
                            if interpreted_hitobject_x(x) == 384 and obj_params == "0" and type_ != 128:
                                obj_params = "Flip"
                                
                            raw_objects.append(HitObject(x, y, time, type_, hitSound, obj_params, hit_sample))
                        except ValueError:
                            pass
                    continue
                if current_section == "[TimingPoints]":
                     parts = line.split(",")
                     if len(parts) >= 2:
                         try:
                             t_time = float(parts[0])
                             beat_len = float(parts[1])
                             if beat_len > 0:
                                 bpm_val = round(60000.0 / beat_len, 3)
                                 self.timing_points.append({'time': int(t_time), 'bpm': bpm_val})
                         except:
                             pass

                if ":" in line and (current_section == "[General]" or current_section == "[Metadata]" or current_section == ""):
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == "Title": self.metadata.Title = value
                    elif key == "TitleUnicode": self.metadata.TitleUnicode = value
                    elif key == "Artist": self.metadata.Artist = value
                    elif key == "ArtistUnicode": self.metadata.ArtistUnicode = value
                    elif key == "AudioFilename": self.metadata.AudioFilename = value
                    elif key == "Creator": self.metadata.Creator = value
                    elif key == "BPM": 
                        try: self.metadata.BPM = float(value)
                        except: pass
                    elif key == "Version": extracted_version = value
                    elif key == "Difficulty": extracted_difficulty = value
                    elif key == "Tags":
                        try:
                            tag_data = json.loads(value)
                            self.metadata.Level = tag_data.get("Level", 1)
                            self.metadata.FlavorText = tag_data.get("FlavorText", "")
                            self.metadata.Attributes = tag_data.get("Attributes", [])
                        except:
                            pass
                    elif key == "AudioLeadIn":
                         try: self.metadata.Offset = int(value)
                         except: pass
                
                if current_section == "[Editor]":
                     if ":" in line:
                         key, value = line.split(":", 1)
                         key = key.strip()
                         value = value.strip()
                         if key == "GridSize":
                             try: self.metadata.GridSize = int(value)
                             except: pass
                         elif key == "Zoom":
                             try: self.editor_zoom = float(value)
                             except: pass
            
            if extracted_difficulty:
                self.metadata.Version = extracted_version if extracted_version else extracted_difficulty
            else:
                if extracted_version and extracted_version in DIFFICULTIES:
                    self.metadata.Version = ""
                else:
                    self.metadata.Version = extracted_version if extracted_version else "Star"
            
            current_time = -1
            seen_note = False
            
            is_centered = False
            is_right = True
            
            current_time = -1
            
            for obj in raw_objects:
                if obj.custom_data is not None:
                    self.hit_objects.append(obj)
                    continue
                if obj.is_toggle_center:
                    if is_centered:
                        obj.tc_is_blue = is_right
                    is_centered = not is_centered
                elif obj.is_flip or obj.is_instant_flip:
                    if is_centered and obj.is_instant_flip:
                        is_right = not is_right
                        continue
                    else:
                        is_right = not is_right
                    
                else:
                    if is_centered:
                        if not is_right:
                            if obj.interpreted_x == 255:
                                obj.y = 192 
                            elif obj.interpreted_x == 256:
                                obj.y = 320
                            elif obj.is_spam:
                                obj.y = 192
                        else:
                             if obj.interpreted_x == 255: obj.y = 0
                             pass
                             
                self.hit_objects.append(obj)

            if self.timing_points:
                 self.timing_points.sort(key=lambda x: x['time'])
                 if self.timing_points[0]['bpm'] > 0:
                      self.metadata.BPM = self.timing_points[0]['bpm']
                      self.metadata.Offset = self.timing_points[0]['time']
            elif self.metadata.BPM > 0:
                 self.timing_points.append({'time': int(self.metadata.Offset), 'bpm': self.metadata.BPM})

            self._resolve_event_orders()
            self.hit_objects.sort(key=lambda x: (x.time, (0.5 if not x.is_event else float(x.order_index))))
            
            return True
        except Exception as e:
            print(f"Error loading {path}: {e}")
            return True

