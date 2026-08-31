from .dialogs import *

register_shared_globals(globals())

class TimelineWidget(QOpenGLWidget):
    def __init__(self, editor):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.editor = editor
        self.beatmap: Optional[BeatmapData] = None
        self._tps_cache_audio_times = []
        self._tps_cache_visual_times = []
        self._tps_cache_data = []
        self.pressed_keys = set()

        self.current_time = 0.0
        self.target_time = 0.0
        self.vis_bar_heights = np.zeros(32, dtype=np.float64)
        self.vis_bar_phase_1 = np.arange(32, dtype=np.float64) * 0.5
        self.vis_bar_phase_2 = np.arange(32, dtype=np.float64) * 1.1
        self.vis_bar_factors = 1.0 - (np.arange(32, dtype=np.float64) / 32.0) * 0.4
        self.last_vis_update_time = time.perf_counter()
        self.zoom = 1.0
        self.target_zoom = 1.0
        self.pixels_per_beat = 200
        self.grid_snap_div = 4
        self.saved_grid_div = 4
        self.is_triplet_mode = False
        
        self.current_tool_type = "note"
        self.current_note_type = "normal"
        self.current_custom_type_id = None
        self.current_brawl_type = "hit"
        
        self.beat_flash_intensity = 0.0
        self.current_event_type = "flip"
        
        self.bpm_drag_start_times = {}
        self.bpm_drag_release_times = {}
        self.dying_bpm_tags = []
        self.bpm_interpolating = []
        self.bpm_follow_drag_state = None
        
        self.selected_objects: Set[HitObject] = set()
        self.clipboard: List[Dict] = []
        
        self.dragging_objects = False
        self.drag_mode = "move" 
        self.drag_start_time_map = {}
        self.drag_start_lane_map = {}
        self.drag_original_end_time_map = {}
        self.drag_last_snapped_time = None
        self.drag_last_lane = None
        self._live_event_cache_active = False
        self._live_event_cache_dirty = False
        self._live_event_cache_generation = 0
        self._last_live_event_cache_time = 0.0
        self._live_note_phase_states = {}
        
        self.visual_interpolating_objects = set()
        
        self.last_click_pos = None
        self.click_cycle_index = 0
        
        self.last_mouse_pos = None
        self.selection_start = None
        self.selection_start_y = None
        self.selection_rect = None
        self.selection_last_mouse_y = None
        self.timeline_click_pos = None
        
        self.selection_anim_time = 0
        self.selection_active_visible = False
        self.selection_was_active = False 
        self.selection_anim_state = "none"
        
        self.selection_target_bounds = None
        self.selection_current_bounds = None
        self.selection_last_drawn_rect = None
        
        self.dying_objects = []
        self.gp_visual_times = {}
        self.gp_visual_last_frame = time.perf_counter()
        
        self.last_drag_sound_time = 0
        self.drag_release_times = {}
        self.drag_start_times = {}
        self.drag_release_mode = {}
        
        self.waveform_data = None
        self.waveform_ratio = 1.0
        self.waveform_loaded_points = 0
        self.temp_waveform_offset = 0
        self._waveform_tile_cache = {}
        self._waveform_tile_signature = None
        self._waveform_cache_generation = 0
        self.timeline_scrollbar: Optional[QScrollBar] = None
        
        self.undo_stack = []
        self.redo_stack = []
        
        self.elapsed_timer = QElapsedTimer()
        self.elapsed_timer.start()
        self.last_frame_time = self.elapsed_timer.elapsed()
        self._display_refresh_rate = max(1.0, float(TARGET_FPS))
        self._frame_interval_seconds = 1.0 / self._display_refresh_rate
        self._next_frame_deadline = time.perf_counter() + self._frame_interval_seconds
        self._last_status_ui_update = 0.0
        self._vsync_frame_clock = False
        self._last_frame_swap = 0.0
        self._fast_frame_swaps = 0
        self._vsync_disabled_until = 0.0
        
        self.smooth_timer = QTimer(self)
        self.smooth_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.smooth_timer.setSingleShot(True)
        self.smooth_timer.timeout.connect(self.run_frame_cycle)
        self.schedule_next_frame()

        self.vsync_watchdog = QTimer(self)
        self.vsync_watchdog.setInterval(100)
        self.vsync_watchdog.timeout.connect(self.check_vsync_frame_clock)
        self.vsync_watchdog.start()
        self.frameSwapped.connect(self.on_frame_swapped)
        
        self.edge_scroll_timer = QTimer()
        self.edge_scroll_timer.setInterval(max(1, int(1000 / TARGET_FPS)))
        self.edge_scroll_timer.timeout.connect(self.on_edge_scroll)
        self.edge_scroll_speed = 0
        self._last_edge_scroll_tick = time.perf_counter()

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(400)

        self.col_bg = QColor(30, 30, 35)
        self.col_lane = QColor(45, 45, 50)
        self.col_beat = QColor(100, 100, 100)
        self.col_subbeat = QColor(60, 60, 60)
        self.col_cursor = QColor(255, 255, 255)
        
        accent_col = QColor(UI_THEME["accent"])
        self.col_selection = QColor(accent_col)
        self.col_selection.setAlpha(100)
        self.col_selection_border = QColor(accent_col)
        self.col_selection_border.setAlpha(200)
        
        self.color_config = DEFAULT_COLORS.copy()
        self.object_colors = {}
        self.update_color_objects()
        
        self.bg_image_path = None
        self.bg_pixmap_scaled = None
        self.bg_pixmap_scaled_size = None
        self.load_background_image()
        
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, 'gp_visual_times'):
            self.gp_visual_times.clear()
            self.gp_visual_last_frame = time.perf_counter()
        self.update()

    def update_color_objects(self):
        accent_col = QColor(UI_THEME["accent"])
        self.col_selection = QColor(accent_col)
        self.col_selection.setAlpha(100)
        self.col_selection_border = QColor(accent_col)
        self.col_selection_border.setAlpha(200)

        if not hasattr(self, 'original_object_colors'):
            self.original_object_colors = {}
        for key, name in self.color_config.items():
            if name in COLOR_PALETTE:
                hex_col = COLOR_PALETTE[name]
            else:
                hex_col = name if (isinstance(name, str) and name.startswith("#")) else "#FFFFFF"
            base_c = QColor(hex_col)
            if not base_c.isValid():
                base_c = QColor("#FFFFFF")
            self.original_object_colors[key] = QColor(base_c)
            self.object_colors[key] = QColor(base_c)
        self.update()
    
    def load_background_image(self):
        try:
            self.bg_image_path = None
            self.bg_pixmap_scaled = None
            self.bg_pixmap_scaled_size = None
            if getattr(self.editor, 'background_opacity', 100) <= 0:
                return
            if self.editor.game_root_path:
                resources_dir = self.editor.game_root_path / "ChartEditorResources"
                bg_path = resources_dir / "bg.png"
                if bg_path.exists():
                    self.bg_image_path = str(bg_path)
        except Exception as e:
            print(f"Error loading background image: {e}")
            self.bg_image_path = None

    def release_background_image(self):
        self.bg_image_path = None
        self.bg_pixmap_scaled = None
        self.bg_pixmap_scaled_size = None
        self.update()

    def update_caches_if_needed(self):
        beatmap_id = id(self.beatmap) if self.beatmap else None
        ho_len = len(self.beatmap.hit_objects) if self.beatmap else 0
        tps_state = tuple((tp.get('time', 0), tp.get('bpm', 120)) for tp in getattr(self.beatmap, 'timing_points', [])) if self.beatmap else ()
        timing_dirty = False
        object_dirty = False
        if getattr(self, '_last_beatmap_id', None) != beatmap_id:
            timing_dirty = True
            object_dirty = True
            self._last_beatmap_id = beatmap_id
        if not hasattr(self, '_last_ho_len') or self._last_ho_len != ho_len:
            object_dirty = True
            self._last_ho_len = ho_len
        if not hasattr(self, '_last_tps_state') or self._last_tps_state != tps_state:
            timing_dirty = True
            self._last_tps_state = tps_state
        if getattr(self, '_force_cache_update', False):
            timing_dirty = True
            object_dirty = True
            self._force_cache_update = False

        if timing_dirty and self.beatmap:
            tps = self.get_sorted_timing_points()
            self._update_tps_cache(tps)
            self._cached_seg_boundaries = [self.audio_to_visual_ms(tp['time'], tps_cache=tps) for tp in tps]
            self._waveform_cache_generation += 1

        if object_dirty and self.beatmap:
            self._object_cache_generation = getattr(self, '_object_cache_generation', 0) + 1
            t_centers = sorted([o for o in self.beatmap.hit_objects if o.is_toggle_center], key=lambda x: x.time)
            for i, c in enumerate(t_centers):
                expected = i % 2
                if getattr(c, 'order_index', 0) != expected:
                    c.order_index = expected
            self._cached_centers = t_centers
            self._cached_all_objs = sorted(self.beatmap.hit_objects, key=lambda x: (x.time, 0 if x.is_event and x.order_index == 0 else (2 if x.is_event else 1), 0 if getattr(x, 'is_freestyle', False) else 1, 0.5 if not x.is_event else float(x.order_index)))
            self._cached_events = [o for o in self._cached_all_objs if o.is_event]
            self._cached_event_indices = {o: index for index, o in enumerate(self._cached_events)}
            self._cached_event_times_np = np.fromiter((o.time for o in self._cached_events), dtype=np.int64, count=len(self._cached_events))
            self._cached_event_orders_np = np.fromiter((float(o.order_index) for o in self._cached_events), dtype=np.float64, count=len(self._cached_events))
            self._cached_event_ranks_np = np.arange(len(self._cached_events), dtype=np.int64)
            self._cached_event_types_np = np.fromiter((o.hitSound for o in self._cached_events), dtype=np.int16, count=len(self._cached_events))
            self._cached_event_tc_values_np = np.fromiter(
                (-1 if o.tc_is_blue is None else (1 if o.tc_is_blue else 0) for o in self._cached_events),
                dtype=np.int8,
                count=len(self._cached_events)
            )
            self._cached_direction_note_times = []
            self._cached_direction_note_values = []
            for obj in self._cached_all_objs:
                if obj.is_event or obj.is_freestyle or obj.custom_data is not None:
                    continue
                value = obj.lane in [0, 1]
                if self._cached_direction_note_times and self._cached_direction_note_times[-1] == obj.time:
                    self._cached_direction_note_values[-1] = value
                else:
                    self._cached_direction_note_times.append(obj.time)
                    self._cached_direction_note_values.append(value)
            self._cached_direction_change_times = []
            self._cached_direction_change_values = []
            for note_time, value in zip(self._cached_direction_note_times, self._cached_direction_note_values):
                if not self._cached_direction_change_values or self._cached_direction_change_values[-1] != value:
                    self._cached_direction_change_times.append(note_time)
                    self._cached_direction_change_values.append(value)
            self._cached_direction_note_times_np = np.asarray(self._cached_direction_note_times, dtype=np.int64)
            self._cached_direction_note_values_np = np.asarray(self._cached_direction_note_values, dtype=np.bool_)
            self._cached_direction_change_times_np = np.asarray(self._cached_direction_change_times, dtype=np.int64)
            self._cached_hit_object_times = [o.time for o in self.beatmap.hit_objects]
            self._cached_obj_times = [o.time for o in self._cached_all_objs]
            self._cached_tail_objs = sorted(
                (
                    o for o in self._cached_all_objs
                    if o.is_hold or o.is_screamer or o.is_spam or o.is_brawl_hold or o.is_brawl_spam or self.is_custom_length(o)
                ),
                key=lambda o: o.end_time
            )
            self._cached_tail_times = [o.end_time for o in self._cached_tail_objs]
            self._cached_tail_start_objs = [
                o for o in self._cached_all_objs
                if o.is_hold or o.is_screamer or o.is_spam or o.is_brawl_hold or o.is_brawl_spam or self.is_custom_length(o)
            ]
            self._cached_tail_start_times = [o.time for o in self._cached_tail_start_objs]
            self._cached_tail_prefix_max = []
            max_end = -1
            for obj in self._cached_tail_start_objs:
                max_end = max(max_end, obj.end_time)
                self._cached_tail_prefix_max.append(max_end)
            
            c_right = True
            c_centered = False
            last_t = 0
            self._cached_obj_flip_color = {}
            self._cached_obj_dir = {}
            self._cached_segments = []
            self._cached_segment_ends = []

            for obj in self._cached_all_objs:
                if obj.is_toggle_center:
                    if last_t < obj.time:
                        self._cached_segments.append((last_t, obj.time, c_right, c_centered, False))
                        self._cached_segment_ends.append(obj.time)
                        last_t = obj.time
                    was_centered = c_centered
                    c_centered = not c_centered
                    if was_centered:
                        if getattr(obj, 'tc_is_blue', None) is None:
                            obj.tc_is_blue = c_right
                        else:
                            c_right = obj.tc_is_blue
                    is_blue = c_right
                    self._cached_obj_flip_color[obj.uid] = self.object_colors.get("direction_right_event", self.object_colors.get("direction_right", QColor("blue"))) if is_blue else self.object_colors.get("direction_left_event", self.object_colors.get("direction_left", QColor("yellow")))

                elif obj.is_flip or obj.is_instant_flip:
                    if not obj.is_toggle_center:
                        if last_t < obj.time:
                            self._cached_segments.append((last_t, obj.time, c_right, c_centered, getattr(obj, 'is_instant_flip', False)))
                            self._cached_segment_ends.append(obj.time)
                            last_t = obj.time
                        c_right = not c_right
                    is_blue = c_right
                    self._cached_obj_flip_color[obj.uid] = self.object_colors.get("direction_right_event", self.object_colors.get("direction_right", QColor("blue"))) if is_blue else self.object_colors.get("direction_left_event", self.object_colors.get("direction_left", QColor("yellow")))

                elif not obj.is_event:
                    new_c_right = c_right
                    if obj.custom_data is None and c_centered and not getattr(obj, 'is_freestyle', False):
                        if obj.lane in [0, 1]: new_c_right = True
                        elif obj.lane in [-1, 2]: new_c_right = False
                    
                    if new_c_right != c_right:
                        if last_t < obj.time:
                            self._cached_segments.append((last_t, obj.time, c_right, c_centered, False))
                            self._cached_segment_ends.append(obj.time)
                            last_t = obj.time
                        c_right = new_c_right
                        
                    obj_dir = c_right
                    if c_centered and not getattr(obj, 'is_freestyle', False):
                        if obj.lane in [0, 1]: obj_dir = True
                        elif obj.lane in [-1, 2]: obj_dir = False
                    self._cached_obj_dir[obj.uid] = obj_dir

            audio_song_len = self.beatmap.metadata.ActualAudioLength * 1000 if hasattr(self.beatmap.metadata, 'ActualAudioLength') and self.beatmap.metadata.ActualAudioLength > 0 else 0
                
            end_t = audio_song_len
            if self.beatmap.hit_objects:
                last_obj = self.beatmap.hit_objects[-1]
                obj_end = last_obj.end_time if hasattr(last_obj, 'end_time') else last_obj.time
                if obj_end > end_t:
                    end_t = obj_end
                    
            if end_t < last_t:
                end_t = last_t + 1000
                
            self._cached_segments.append((last_t, end_t, c_right, c_centered, False))
            self._cached_segment_ends.append(end_t)
            
            self._cached_center_times = [c.time for c in self._cached_centers]
            self._cached_map_end_time = self._cached_all_objs[-1].end_time if self._cached_all_objs else 0
            
            self._fast_note_times = {
                o.time
                for o in self._cached_all_objs
                if not o.is_event and not o.is_spike and o.custom_data is None
            }
            self._cached_event_tc_values_np = np.fromiter(
                (-1 if o.tc_is_blue is None else (1 if o.tc_is_blue else 0) for o in self._cached_events),
                dtype=np.int8,
                count=len(self._cached_events)
            )
            self._live_event_orders_np = self._cached_event_orders_np.copy()
            self._live_event_tc_values_np = self._cached_event_tc_values_np.copy()
            self._live_event_cache_active = False
            self._live_event_cache_dirty = False
                

    def ensure_object_cache(self):
        if not self.beatmap:
            return
        if (
            getattr(self, '_force_cache_update', False)
            or getattr(self, '_last_beatmap_id', None) != id(self.beatmap)
            or getattr(self, '_last_ho_len', -1) != len(self.beatmap.hit_objects)
        ):
            self.update_caches_if_needed()

    def insert_hit_object_sorted(self, obj):
        objects = self.beatmap.hit_objects
        sort_key = lambda item: (item.time, 0 if item.is_event and item.order_index == 0 else (2 if item.is_event else 1), 0 if getattr(item, 'is_freestyle', False) else 1, 0.5 if not item.is_event else float(item.order_index))
        insert_index = bisect.bisect_right(objects, sort_key(obj), key=sort_key)
        objects.insert(insert_index, obj)

    def queue_delete_animations(self, objects):
        queued = {obj for obj, _ in self.dying_objects}
        for obj in objects:
            if obj not in queued:
                self.dying_objects.append((obj, None))
                queued.add(obj)

    def sync_structural_object_caches(self, changed_objects):
        if not self.beatmap:
            return
        if not hasattr(self, '_cached_all_objs'):
            self._force_cache_update = True
            self.update_caches_if_needed()
            return

        changed_objects = tuple(changed_objects)
        objects = self.beatmap.hit_objects
        self._last_beatmap_id = id(self.beatmap)
        self._last_ho_len = len(objects)
        self._force_cache_update = False
        self._object_cache_generation = getattr(self, '_object_cache_generation', 0) + 1
        self._cached_all_objs = list(objects)
        object_times = [obj.time for obj in objects]
        self._cached_hit_object_times = object_times
        self._cached_obj_times = object_times

        tail_changed = any(
            obj.is_hold or obj.is_screamer or obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam or self.is_custom_length(obj)
            for obj in changed_objects
        )
        if tail_changed:
            self._cached_tail_objs = sorted(
                (
                    obj for obj in objects
                    if obj.is_hold or obj.is_screamer or obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam or self.is_custom_length(obj)
                ),
                key=lambda obj: obj.end_time
            )
            self._cached_tail_times = [obj.end_time for obj in self._cached_tail_objs]
            self._cached_tail_start_objs = [
                obj for obj in objects
                if obj.is_hold or obj.is_screamer or obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam or self.is_custom_length(obj)
            ]
            self._cached_tail_start_times = [obj.time for obj in self._cached_tail_start_objs]
            self._cached_tail_prefix_max = []
            max_end = -1
            for obj in self._cached_tail_start_objs:
                max_end = max(max_end, obj.end_time)
                self._cached_tail_prefix_max.append(max_end)

        event_changed = any(obj.is_event for obj in changed_objects)
        toggle_changed = any(obj.is_toggle_center for obj in changed_objects)
        if event_changed:
            self._cached_events = [obj for obj in objects if obj.is_event]
            self._cached_event_indices = {obj: index for index, obj in enumerate(self._cached_events)}
            event_count = len(self._cached_events)
            self._cached_event_times_np = np.fromiter(
                (obj.time for obj in self._cached_events),
                dtype=np.int64,
                count=event_count
            )
            self._cached_event_orders_np = np.fromiter(
                (float(obj.order_index) for obj in self._cached_events),
                dtype=np.float64,
                count=event_count
            )
            self._cached_event_ranks_np = np.arange(event_count, dtype=np.int64)
            self._cached_event_types_np = np.fromiter(
                (obj.hitSound for obj in self._cached_events),
                dtype=np.int16,
                count=event_count
            )
            self._cached_event_tc_values_np = np.fromiter(
                (-1 if obj.tc_is_blue is None else (1 if obj.tc_is_blue else 0) for obj in self._cached_events),
                dtype=np.int8,
                count=event_count
            )
            self._live_event_orders_np = self._cached_event_orders_np.copy()
            self._live_event_tc_values_np = self._cached_event_tc_values_np.copy()

        direction_times = {
            obj.time
            for obj in changed_objects
            if not obj.is_event and not obj.is_freestyle and obj.custom_data is None
        }
        direction_changed = bool(direction_times)
        if direction_changed:
            note_times = self._cached_direction_note_times
            note_values = self._cached_direction_note_values
            for note_time in sorted(direction_times):
                cache_index = bisect.bisect_left(note_times, note_time)
                start_index = bisect.bisect_left(object_times, note_time)
                end_index = bisect.bisect_right(object_times, note_time, start_index)
                value = None
                for obj in objects[start_index:end_index]:
                    if not obj.is_event and not obj.is_freestyle and obj.custom_data is None:
                        value = obj.lane in [0, 1]
                if value is None:
                    if cache_index < len(note_times) and note_times[cache_index] == note_time:
                        note_times.pop(cache_index)
                        note_values.pop(cache_index)
                elif cache_index < len(note_times) and note_times[cache_index] == note_time:
                    note_values[cache_index] = value
                else:
                    note_times.insert(cache_index, note_time)
                    note_values.insert(cache_index, value)

            self._cached_direction_note_times_np = np.asarray(note_times, dtype=np.int64)
            self._cached_direction_note_values_np = np.asarray(note_values, dtype=np.bool_)
            if self._cached_direction_note_times_np.size:
                change_mask = np.empty(self._cached_direction_note_values_np.size, dtype=np.bool_)
                change_mask[0] = True
                change_mask[1:] = (
                    self._cached_direction_note_values_np[1:]
                    != self._cached_direction_note_values_np[:-1]
                )
                change_times_np = self._cached_direction_note_times_np[change_mask]
                change_values_np = self._cached_direction_note_values_np[change_mask]
            else:
                change_times_np = np.empty(0, dtype=np.int64)
                change_values_np = np.empty(0, dtype=np.bool_)
            self._cached_direction_change_times_np = change_times_np
            self._cached_direction_change_times = change_times_np.tolist()
            self._cached_direction_change_values = change_values_np.tolist()

        changed_times = {obj.time for obj in changed_objects}
        for changed_time in changed_times:
            start_index = bisect.bisect_left(object_times, changed_time)
            end_index = bisect.bisect_right(object_times, changed_time, start_index)
            if any(not obj.is_event and not obj.is_spike and obj.custom_data is None for obj in objects[start_index:end_index]):
                self._fast_note_times.add(changed_time)
            else:
                self._fast_note_times.discard(changed_time)

        last_object_end = 0
        if objects:
            last_object = objects[-1]
            last_object_end = getattr(last_object, 'end_time', last_object.time)
        if getattr(self, '_cached_tail_times', None):
            last_object_end = max(last_object_end, self._cached_tail_times[-1])
        self._cached_map_end_time = last_object_end
        self._pending_toggle_cache_source = None

        if event_changed or direction_changed:
            if self._cached_events:
                self.rebuild_live_event_cache()
            else:
                audio_song_len = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap.metadata.ActualAudioLength > 0 else 0
                end_time = max(audio_song_len, self._cached_map_end_time)
                self._live_centers = []
                self._live_center_times = []
                self._live_segments = [(0, end_time, True, False, False)]
                self._live_segment_ends = [end_time]
                self._live_obj_flip_color = {}
                self._live_note_pre_states = {}
                self._live_note_phase_states = {}
                self._live_event_cache_active = True
                self._live_event_cache_dirty = False
                self._live_event_cache_generation += 1
                self._last_live_event_cache_time = time.perf_counter()

        if toggle_changed:
            objects.sort(key=lambda obj: (obj.time, 0 if obj.is_event and obj.order_index == 0 else (2 if obj.is_event else 1), 0 if getattr(obj, 'is_freestyle', False) else 1, 0.5 if not obj.is_event else float(obj.order_index)))
            self._cached_all_objs = list(objects)
            object_times = [obj.time for obj in objects]
            self._cached_hit_object_times = object_times
            self._cached_obj_times = object_times

    def rebuild_live_event_cache(self):
        if not self.beatmap:
            return
        rebuild_started = time.perf_counter()
        self.ensure_object_cache()
        event_refs = getattr(self, '_cached_events', ())
        event_count = len(event_refs)
        event_times = self._cached_event_times_np.copy()
        event_orders = getattr(self, '_live_event_orders_np', self._cached_event_orders_np).copy()
        event_ranks = self._cached_event_ranks_np
        event_types = self._cached_event_types_np
        event_tc_values = getattr(self, '_live_event_tc_values_np', self._cached_event_tc_values_np).copy()
        event_indices = self._cached_event_indices
        for obj in self.selected_objects:
            if obj.is_event:
                event_index = event_indices.get(obj)
                if event_index is not None:
                    event_times[event_index] = obj.time

        toggle_indices = np.flatnonzero(event_types == 2)
        toggle_sort = np.lexsort((event_ranks[toggle_indices], event_orders[toggle_indices], event_times[toggle_indices]))
        center_event_indices = toggle_indices[toggle_sort]
        event_orders[center_event_indices] = np.arange(center_event_indices.size, dtype=np.float64) % 2
        center_times_np = event_times[center_event_indices]
        centers = [event_refs[index] for index in center_event_indices.tolist()]
        event_phases = np.where(event_orders == 0, 0, 2).astype(np.int8)
        event_sort = np.lexsort((event_ranks, event_orders, event_phases, event_times))
        flip_mask = (event_types == 0) | (event_types == 8)
        flip_indices = event_sort[flip_mask[event_sort]]

        note_times = getattr(self, '_cached_direction_note_times_np', np.empty(0, dtype=np.int64))
        note_values = getattr(self, '_cached_direction_note_values_np', np.empty(0, dtype=np.bool_))
        change_times = getattr(self, '_cached_direction_change_times_np', np.empty(0, dtype=np.int64))
        candidate_times = []
        if center_times_np.size and change_times.size:
            center_indices = np.searchsorted(center_times_np, change_times, side="right")
            exact_closes = np.zeros(change_times.size, dtype=np.bool_)
            valid_indices = center_indices > 0
            exact_closes[valid_indices] = (
                (center_indices[valid_indices] % 2 == 0)
                & (center_times_np[center_indices[valid_indices] - 1] == change_times[valid_indices])
            )
            inside_changes = (center_indices % 2 == 1) | exact_closes
            candidate_times.append(change_times[inside_changes])
        if center_times_np.size and note_times.size:
            opening_indices = np.searchsorted(note_times, center_times_np[::2], side="left")
            opening_indices = opening_indices[opening_indices < note_times.size]
            if opening_indices.size:
                candidate_times.append(note_times[opening_indices])
        if flip_indices.size and note_times.size:
            pre_flip_times = event_times[flip_indices[event_orders[flip_indices] == 0]]
            post_flip_times = event_times[flip_indices[event_orders[flip_indices] != 0]]
            next_note_indices = []
            if pre_flip_times.size:
                next_note_indices.append(np.searchsorted(note_times, pre_flip_times, side="left"))
            if post_flip_times.size:
                next_note_indices.append(np.searchsorted(note_times, post_flip_times, side="right"))
            if next_note_indices:
                next_note_indices = np.concatenate(next_note_indices)
                next_note_indices = next_note_indices[next_note_indices < note_times.size]
                if next_note_indices.size:
                    candidate_times.append(note_times[next_note_indices])
        if candidate_times:
            relevant_times = np.unique(np.concatenate(candidate_times))
            if center_times_np.size:
                center_indices = np.searchsorted(center_times_np, relevant_times, side="right")
                exact_closes = np.zeros(relevant_times.size, dtype=np.bool_)
                valid_indices = center_indices > 0
                exact_closes[valid_indices] = (
                    (center_indices[valid_indices] % 2 == 0)
                    & (center_times_np[center_indices[valid_indices] - 1] == relevant_times[valid_indices])
                )
                relevant_times = relevant_times[(center_indices % 2 == 1) | exact_closes]
            else:
                relevant_times = np.empty(0, dtype=np.int64)
            note_indices = np.searchsorted(note_times, relevant_times, side="left")
            relevant_values = note_values[note_indices]
        else:
            relevant_times = np.empty(0, dtype=np.int64)
            relevant_values = np.empty(0, dtype=np.bool_)

        event_stable = event_ranks
        event_toggles = event_types == 2
        event_instants = event_types == 8
        event_kinds = np.zeros(event_count, dtype=np.int8)
        event_kinds[flip_mask] = 1
        closing_assignments = event_toggles & (event_orders != 0) & (event_tc_values >= 0)
        event_kinds[closing_assignments] = np.where(event_tc_values[closing_assignments] > 0, 3, 2)

        note_count = relevant_times.size
        action_times = np.concatenate((event_times, relevant_times))
        action_phases = np.concatenate((event_phases, np.ones(note_count, dtype=np.int8)))
        action_orders = np.concatenate((event_orders, np.full(note_count, 0.5, dtype=np.float64)))
        action_stable = np.concatenate((event_stable, np.zeros(note_count, dtype=np.int64)))
        action_kinds = np.concatenate((event_kinds, np.where(relevant_values, 3, 2).astype(np.int8)))
        action_toggles = np.concatenate((event_toggles, np.zeros(note_count, dtype=np.bool_)))
        action_instants = np.concatenate((event_instants, np.zeros(note_count, dtype=np.bool_)))
        action_events = np.concatenate((np.ones(event_count, dtype=np.bool_), np.zeros(note_count, dtype=np.bool_)))
        action_sources = np.concatenate((np.arange(event_count, dtype=np.int64), np.full(note_count, -1, dtype=np.int64)))
        action_order = np.lexsort((action_stable, action_orders, action_phases, action_times))
        sorted_times = action_times[action_order]
        sorted_kinds = action_kinds[action_order]
        sorted_toggles = action_toggles[action_order]
        sorted_instants = action_instants[action_order]
        sorted_events = action_events[action_order]
        sorted_sources = action_sources[action_order]
        sorted_phases = action_phases[action_order]

        action_indices = np.arange(sorted_times.size, dtype=np.int64)
        flips = sorted_kinds == 1
        assignments = sorted_kinds >= 2
        assignment_values = sorted_kinds == 3
        flip_prefix = np.cumsum(flips, dtype=np.int64)
        last_assignments = np.maximum.accumulate(np.where(assignments, action_indices, -1))
        right_states = np.ones(sorted_times.size, dtype=np.bool_)
        has_assignment = last_assignments >= 0
        right_states[has_assignment] = assignment_values[last_assignments[has_assignment]]
        flips_at_assignment = np.zeros(sorted_times.size, dtype=np.int64)
        flips_at_assignment[has_assignment] = flip_prefix[last_assignments[has_assignment]]
        right_states ^= ((flip_prefix - flips_at_assignment) & 1).astype(np.bool_)
        right_before = np.empty(sorted_times.size, dtype=np.bool_)
        right_before[0] = True
        right_before[1:] = right_states[:-1]

        centered_states = (np.cumsum(sorted_toggles, dtype=np.int64) & 1).astype(np.bool_)
        centered_before = np.empty(sorted_times.size, dtype=np.bool_)
        centered_before[0] = False
        centered_before[1:] = centered_states[:-1]

        unique_times, first_indices, counts = np.unique(sorted_times, return_index=True, return_counts=True)
        last_indices = first_indices + counts - 1
        note_phase_candidates = np.where(
            sorted_phases >= 1,
            action_indices,
            sorted_times.size,
        )
        first_note_phase_indices = np.minimum.reduceat(note_phase_candidates, first_indices)
        event_note_times = np.intersect1d(note_times, event_times)
        note_phase_states = {}
        if event_note_times.size:
            group_indices = np.searchsorted(unique_times, event_note_times)
            phase_indices = first_note_phase_indices[group_indices]
            group_last_indices = last_indices[group_indices]
            phase_right = right_states[group_last_indices].copy()
            phase_centered = centered_states[group_last_indices].copy()
            has_phase_boundary = phase_indices < sorted_times.size
            if np.any(has_phase_boundary):
                valid_phase_indices = phase_indices[has_phase_boundary]
                phase_right[has_phase_boundary] = right_before[valid_phase_indices]
                phase_centered[has_phase_boundary] = centered_before[valid_phase_indices]
            note_phase_states = {
                int(note_time): (bool(is_right), bool(is_centered))
                for note_time, is_right, is_centered in zip(
                    event_note_times,
                    phase_right,
                    phase_centered,
                )
            }
        boundary_candidates = sorted_events | (right_states != right_before)
        candidate_indices = np.where(boundary_candidates, action_indices, sorted_times.size)
        first_candidates = np.minimum.reduceat(candidate_indices, first_indices)
        boundary_groups = first_candidates < sorted_times.size
        boundary_times = unique_times[boundary_groups]
        boundary_first_indices = first_indices[boundary_groups]
        boundary_candidate_indices = first_candidates[boundary_groups]
        positive_boundaries = boundary_times > 0
        boundary_times = boundary_times[positive_boundaries]
        boundary_first_indices = boundary_first_indices[positive_boundaries]
        boundary_candidate_indices = boundary_candidate_indices[positive_boundaries]

        segments = []
        segment_ends = boundary_times.tolist()
        last_t = 0
        for boundary_time, first_index, candidate_index in zip(boundary_times.tolist(), boundary_first_indices.tolist(), boundary_candidate_indices.tolist()):
            segments.append((
                last_t,
                boundary_time,
                bool(right_before[first_index]),
                bool(centered_before[first_index]),
                bool(sorted_instants[candidate_index])
            ))
            last_t = boundary_time

        event_positions = np.flatnonzero(sorted_events)
        state_by_event = np.empty(event_count, dtype=np.bool_)
        state_by_event[sorted_sources[event_positions]] = right_states[event_positions]
        right_color = self.object_colors.get("direction_right_event", self.object_colors.get("direction_right", QColor("blue")))
        left_color = self.object_colors.get("direction_left_event", self.object_colors.get("direction_left", QColor("yellow")))
        flip_colors = {
            obj.uid: right_color if state_by_event[index] else left_color
            for index, obj in enumerate(event_refs)
        }
        missing_tc_values = event_toggles & (event_orders != 0) & (event_tc_values < 0)
        event_tc_values[missing_tc_values] = state_by_event[missing_tc_values].astype(np.int8)
        for index in center_event_indices.tolist():
            obj = event_refs[index]
            obj.order_index = int(event_orders[index])
            if event_tc_values[index] >= 0:
                obj.tc_is_blue = bool(event_tc_values[index])

        note_positions = np.flatnonzero(~sorted_events)
        centered_note_positions = note_positions[centered_before[note_positions]]
        note_pre_states = {
            int(sorted_times[position]): bool(right_before[position])
            for position in centered_note_positions
        }

        audio_song_len = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap.metadata.ActualAudioLength > 0 else 0
        end_t = max(audio_song_len, getattr(self, '_cached_map_end_time', 0), last_t)
        if end_t < last_t:
            end_t = last_t + 1000
        segments.append((last_t, end_t, bool(right_states[-1]), bool(centered_states[-1]), False))
        segment_ends.append(end_t)

        self._live_centers = centers
        self._live_center_times = center_times_np.tolist()
        self._live_segments = segments
        self._live_segment_ends = segment_ends
        self._live_obj_flip_color = flip_colors
        self._live_note_pre_states = note_pre_states
        self._live_note_phase_states = note_phase_states
        self._live_event_orders_np = event_orders
        self._live_event_tc_values_np = event_tc_values
        self._live_event_cache_active = True
        self._live_event_cache_dirty = False
        self._live_event_cache_generation += 1
        self._last_live_event_cache_time = rebuild_started

    def get_live_event_cache_interval(self):
        return 1.0 / min(60.0, self._display_refresh_rate)

    def get_center_times(self):
        if self._live_event_cache_active:
            return self._live_center_times
        return getattr(self, '_cached_center_times', [])

    def get_direction_segments(self):
        if self._live_event_cache_active:
            return self._live_segments, self._live_segment_ends
        return getattr(self, '_cached_segments', []), getattr(self, '_cached_segment_ends', [])

    def get_event_flip_colors(self):
        if self._live_event_cache_active:
            return self._live_obj_flip_color
        return getattr(self, '_cached_obj_flip_color', {})

    def get_toggle_centers(self):
        if not self.beatmap: return []
        self.ensure_object_cache()
        if self._live_event_cache_active:
            return self._live_centers
        return getattr(self, '_cached_centers', [])

    def get_objects_in_range(self, start_ms, end_ms):
        if not self.beatmap or not self.beatmap.hit_objects: return []
        objs = self.beatmap.hit_objects
        self.ensure_object_cache()
        times = getattr(self, '_cached_hit_object_times', [])
        start_idx = bisect.bisect_left(times, start_ms)
        end_idx = bisect.bisect_right(times, end_ms, start_idx)
        active_tails = self.get_active_tail_objects(start_ms)
        return active_tails + list(objs[start_idx:end_idx])

    def get_active_tail_objects(self, ms, include_starts=False):
        self.ensure_object_cache()
        tail_objs = getattr(self, '_cached_tail_start_objs', [])
        tail_times = getattr(self, '_cached_tail_start_times', [])
        prefix_max = getattr(self, '_cached_tail_prefix_max', [])
        if include_starts:
            idx = bisect.bisect_right(tail_times, ms) - 1
        else:
            idx = bisect.bisect_left(tail_times, ms) - 1
        active = []
        while idx >= 0:
            if prefix_max[idx] < ms:
                break
            obj = tail_objs[idx]
            if obj.end_time >= ms:
                active.append(obj)
            idx -= 1
        active.reverse()
        return active

    def get_selection_candidates(self, x1, x2):
        if not self.beatmap:
            return ()
        self.ensure_object_cache()
        audio_1 = self.x_to_audio_ms(x1)
        audio_2 = self.x_to_audio_ms(x2)
        start_ms = min(audio_1, audio_2)
        end_ms = max(audio_1, audio_2)
        obj_times = getattr(self, '_cached_obj_times', [])
        objs = getattr(self, '_cached_all_objs', [])
        start_idx = bisect.bisect_left(obj_times, start_ms)
        end_idx = bisect.bisect_right(obj_times, end_ms)
        candidates = set(objs[start_idx:end_idx])
        tail_times = getattr(self, '_cached_tail_times', [])
        tail_objs = getattr(self, '_cached_tail_objs', [])
        tail_start_idx = bisect.bisect_left(tail_times, start_ms)
        tail_end_idx = bisect.bisect_right(tail_times, end_ms)
        candidates.update(tail_objs[tail_start_idx:tail_end_idx])
        return candidates

    def get_custom_type_data(self, obj):
        data = getattr(obj, 'custom_data', None)
        if data is None:
            return None
        return get_custom_type(data.type_id)

    def is_custom_missing(self, obj):
        data = getattr(obj, 'custom_data', None)
        return data is not None and (data.missing or self.get_custom_type_data(obj) is None)

    def is_custom_length(self, obj):
        type_data = self.get_custom_type_data(obj)
        return bool(type_data and type_data.get('kind') == 'Note' and type_data.get('length'))

    def get_custom_object_y(self, obj):
        if self.is_custom_missing(obj):
            return 174.0
        visual_lane = getattr(obj, '_current_visual_lane', self.get_visual_lane_value(obj))
        return self.get_lane_y_from_float(visual_lane)

    def get_custom_lane_for_y(self, type_data, y):
        mode = type_data.get('lane_mode', 'Top & Bottom')
        if mode == 'Middle':
            return -2
        if mode == 'Top Only':
            return 0
        if mode == 'Bottom Only':
            return 1
        sf = getattr(self.editor, 'global_scale', 1.0)
        return 0 if y < (self.height() / sf) / 2 else 1

    def is_custom_space_free(self, start_t, end_t, lane, type_data, ignore_obj=None):
        if not type_data.get('collision', True):
            return True
        return self.is_space_free(
            start_t,
            end_t,
            lane,
            ignore_obj=ignore_obj,
            is_freestyle=lane == -2,
        )

    def is_time_in_toggle_center(self, ms, pending_events=None):
        if not self.beatmap: return False
        if not pending_events:
            self.ensure_object_cache()
            center_times = self.get_center_times()
            idx = bisect.bisect_right(center_times, ms)
            if idx > 0 and idx % 2 == 0 and center_times[idx - 1] == ms:
                idx -= 1
            return (idx % 2) == 1
        centers = self.get_toggle_centers()
        generation = (
            getattr(self, '_object_cache_generation', 0),
            self._live_event_cache_generation if self._live_event_cache_active else -1
        )
        if (
            getattr(self, '_pending_toggle_cache_source', None) is not pending_events
            or getattr(self, '_pending_toggle_cache_generation', -1) != generation
            or getattr(self, '_pending_toggle_cache_length', -1) != len(pending_events)
        ):
            combined = centers + pending_events
            combined.sort(key=lambda x: (x.time, float(x.order_index)))
            keys = []
            states = []
            active_opens = 0
            for center in combined:
                is_open = getattr(center, 'order_index', 0) == 0
                keys.append((center.time, 0 if is_open else 1))
                if is_open:
                    active_opens += 1
                else:
                    active_opens = max(0, active_opens - 1)
                states.append(active_opens > 0)
            self._pending_toggle_cache_source = pending_events
            self._pending_toggle_cache_generation = generation
            self._pending_toggle_cache_length = len(pending_events)
            self._pending_toggle_cache_keys = keys
            self._pending_toggle_cache_states = states
        idx = bisect.bisect_right(self._pending_toggle_cache_keys, (ms, 0)) - 1
        return self._pending_toggle_cache_states[idx] if idx >= 0 else False

    def auto_set_tc_order_for_note(self, note_time=None):
        if not self.beatmap: return
        centers = self.get_toggle_centers()
        for i, c in enumerate(centers):
            expected = i % 2
            if getattr(c, 'order_index', 0) != expected:
                c.order_index = expected
                c.last_update_time = time.time()

    def set_colors(self, new_colors):
        self.color_config = new_colors
        self.update_color_objects()
        self._force_cache_update = True
        self.update_caches_if_needed()
        self.update()

    def toggle_triplet(self):
        if not getattr(self, 'is_triplet_mode', False):
            if self.grid_snap_div % 2 == 0:
                self.saved_grid_div = self.grid_snap_div
                self.grid_snap_div = int(self.grid_snap_div * 1.5)
                self.is_triplet_mode = True
        else:
            if hasattr(self, 'saved_grid_div') and self.saved_grid_div is not None:
                self.grid_snap_div = self.saved_grid_div
            self.is_triplet_mode = False
        
        if self.editor:
            self.editor.spin_grid.blockSignals(True)
            self.editor.spin_grid.setValue(self.grid_snap_div)
            self.editor.spin_grid.blockSignals(False)
            if self.editor.current_chart:
                self.editor.current_chart.metadata.GridSize = self.grid_snap_div
                self.editor.mark_unsaved()
        self.update()

    def set_scrollbar(self, scrollbar):
        self.timeline_scrollbar = scrollbar
    
    def update_scrollbar(self):
        if not self.timeline_scrollbar or not self.beatmap:
            return
        
        song_length_ms = self.get_visual_song_length()
        if song_length_ms > 0:
            self.timeline_scrollbar.setEnabled(True)
            self.timeline_scrollbar.blockSignals(True)
            
            overshoot = 0
            if self.current_time < 0:
                overshoot = -self.current_time
            elif self.current_time > song_length_ms:
                overshoot = self.current_time - song_length_ms
            
            effective_max = int(song_length_ms + overshoot)
            
            self.timeline_scrollbar.setMinimum(0)
            self.timeline_scrollbar.setMaximum(effective_max)
            
            visible_ms_range = self.x_to_ms(self.width()) - self.x_to_ms(0)
            self.timeline_scrollbar.setPageStep(max(1000, int(visible_ms_range)))
            self.timeline_scrollbar.setSingleStep(500) 
            
            if self.current_time > song_length_ms:
                self.timeline_scrollbar.setValue(effective_max)
            else:
                self.timeline_scrollbar.setValue(int(self.current_time))
            
            self.timeline_scrollbar.blockSignals(False)
        else:
            self.timeline_scrollbar.setEnabled(False)

    def set_beatmap(self, beatmap: BeatmapData):
        self.beatmap = beatmap
        self.selected_objects.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.gp_visual_times.clear()
        self.gp_visual_last_frame = time.perf_counter()
        self.drag_release_times.clear()
        self.drag_start_times.clear()
        self.drag_release_mode.clear()
        self.bpm_drag_start_times.clear()
        self.bpm_drag_release_times.clear()
        self.bpm_follow_drag_state = None
        self.dying_objects.clear()
        self.dying_bpm_tags.clear()
        self._pending_toggle_cache_source = None
        self._pending_toggle_cache_keys = []
        self._pending_toggle_cache_states = []
        self._live_event_cache_active = False
        self._live_event_cache_dirty = False
        self._live_note_phase_states = {}
        self.current_time = 0
        self.target_time = 0
        self.grid_snap_div = beatmap.metadata.GridSize
        if self.grid_snap_div < 1:
            self.grid_snap_div = 4
        self.target_zoom = beatmap.editor_zoom
        self.zoom = beatmap.editor_zoom
        if self.editor:
            self.editor.spin_grid.blockSignals(True)
            self.editor.spin_grid.setValue(self.grid_snap_div)
            self.editor.spin_grid.blockSignals(False)
            self.editor.sync_audio_to_time()
        self.update_scrollbar()
        self.update()
    
    def save_undo_state(self):
        if not self.beatmap:
            return

        reference_state = self.undo_stack[-1] if self.undo_stack else None
        self.undo_stack.append(self._get_current_state(reference_state))
        
        self.redo_stack.clear()
    
    def undo(self):
        if not self.undo_stack or not self.beatmap:
            return
        
        reference_state = self.undo_stack[-1]
        current_state = self._get_current_state(reference_state)
        self.redo_stack.append(current_state)
        
        prev_state = self.undo_stack.pop()
        self._restore_state(prev_state)
        self.editor.mark_unsaved()
        self.update()
    
    def redo(self):
        if not self.redo_stack or not self.beatmap:
            return
        
        reference_state = self.undo_stack[-1] if self.undo_stack else None
        current_state = self._get_current_state(reference_state)
        self.undo_stack.append(current_state)
        
        next_state = self.redo_stack.pop()
        self._restore_state(next_state)
        self.editor.mark_unsaved()
        self.update()

    def _restore_state(self, state):
        self.beatmap.hit_objects = [
            HitObject(
                obj_data[0],
                obj_data[1],
                obj_data[2],
                obj_data[3],
                obj_data[4],
                obj_data[5],
                obj_data[6],
                obj_data[7],
                obj_data[8],
                obj_data[9],
                obj_data[10],
                uid=obj_data[11],
                custom_data=custom_object_data_from_tuple(obj_data[12] if len(obj_data) > 12 else None)
            )
            for obj_data in state['hit_objects']
        ]
        self.selected_objects.clear()
        if hasattr(self.beatmap, 'timing_points'):
            self.beatmap.timing_points = [
                {'time': tp_data[0], 'bpm': tp_data[1], 'creation_time': tp_data[2]}
                for tp_data in state.get('timing_points', ())
            ]
            self.beatmap.timing_points.sort(key=lambda x: x['time'])
            if hasattr(self.editor, 'update_bpm_list'):
                self.editor.update_bpm_list()
        self._force_cache_update = True

    def frame_update(self):
        self.perform_frame_update()

    def perform_frame_update(self):
        if ACTIVE_UI_ANIMATIONS:
            update_ui_animations()
        if getattr(self.editor, 'is_loading_project', False):
            return
        start_screen = getattr(self.editor, 'start_screen', None)
        if start_screen and start_screen.isVisible():
            start_screen.update_cover_animations()
            return
        self.update_caches_if_needed()
        if (
            self._live_event_cache_dirty
            and self.dragging_objects
            and time.perf_counter() - self._last_live_event_cache_time >= self.get_live_event_cache_interval()
        ):
            self.rebuild_live_event_cache()
        if self.editor and self.editor.is_playing:
            self.editor.tick()
        sidebar_vis = getattr(self.editor, 'sidebar_vis', None)
        if sidebar_vis and sidebar_vis.needs_animation():
            sidebar_vis.animate()
        self.smooth_update()

    def schedule_next_frame(self):
        now = time.perf_counter()
        if self._next_frame_deadline <= now:
            missed_frames = int((now - self._next_frame_deadline) / self._frame_interval_seconds) + 1
            self._next_frame_deadline += missed_frames * self._frame_interval_seconds
        delay_ms = max(1, int(round((self._next_frame_deadline - now) * 1000.0)))
        self.smooth_timer.start(delay_ms)

    def run_frame_cycle(self):
        self._next_frame_deadline += self._frame_interval_seconds
        try:
            self.frame_update()
        finally:
            if not self._vsync_frame_clock:
                self.schedule_next_frame()

    def can_use_vsync_frame_clock(self):
        if not self.editor or not self.editor.is_playing or not self.isVisible():
            return False
        if time.perf_counter() < self._vsync_disabled_until:
            return False
        screen = self.screen()
        if not screen:
            return False
        refresh_rate = float(screen.refreshRate())
        if refresh_rate <= 0:
            return False
        if abs(refresh_rate - self._display_refresh_rate) > 0.01:
            self._display_refresh_rate = refresh_rate
            self._frame_interval_seconds = 1.0 / refresh_rate
            self._next_frame_deadline = time.perf_counter() + self._frame_interval_seconds
        return self.format().swapInterval() > 0

    def on_frame_swapped(self):
        now = time.perf_counter()
        if not self.can_use_vsync_frame_clock():
            if self._vsync_frame_clock:
                self.stop_vsync_frame_clock(now)
            return
        previous_swap = self._last_frame_swap
        self._last_frame_swap = now
        if not self._vsync_frame_clock:
            self._vsync_frame_clock = True
            self._fast_frame_swaps = 0
            self.smooth_timer.stop()
        elif previous_swap > 0 and now - previous_swap < self._frame_interval_seconds * 0.25:
            self._fast_frame_swaps += 1
            if self._fast_frame_swaps >= 5:
                self._vsync_disabled_until = now + 5.0
                self.stop_vsync_frame_clock(now)
                return
        else:
            self._fast_frame_swaps = 0
        self.frame_update()

    def stop_vsync_frame_clock(self, now=None):
        self._vsync_frame_clock = False
        self._fast_frame_swaps = 0
        current = time.perf_counter() if now is None else now
        self._next_frame_deadline = current + self._frame_interval_seconds
        if not self.smooth_timer.isActive():
            self.schedule_next_frame()

    def check_vsync_frame_clock(self):
        if not self._vsync_frame_clock:
            return
        now = time.perf_counter()
        if (
            not self.can_use_vsync_frame_clock()
            or now - self._last_frame_swap > max(0.1, self._frame_interval_seconds * 3.0)
        ):
            self.stop_vsync_frame_clock(now)

    def smooth_update(self):
        current_time = self.elapsed_timer.elapsed()
        dt_ms = current_time - self.last_frame_time
        self.last_frame_time = current_time
        
        if dt_ms <= 0 or dt_ms > 100:
            return
        
        dt_seconds = dt_ms / 1000.0
        smoothness_per_second = 15.0
        
        needs_repaint = False
        if getattr(self, '_anim_running', False):
            needs_repaint = True
            self._anim_running = False
        
        if self.beatmap and not self.editor.is_playing:
            song_length_ms = self.get_visual_song_length()
            spring_speed = 6.0
            if self.target_time < 0:
                diff = 0 - self.target_time
                if abs(diff) < 1.0: 
                    if self.target_time != 0:
                        self.target_time = 0
                        needs_repaint = True
                else: 
                    self.target_time += diff * min(1.0, dt_seconds * spring_speed)
                    needs_repaint = True
            elif song_length_ms > 0 and self.target_time > song_length_ms:
                diff = song_length_ms - self.target_time
                if abs(diff) < 1.0: 
                    if self.target_time != song_length_ms:
                        self.target_time = song_length_ms
                        needs_repaint = True
                else: 
                    self.target_time += diff * min(1.0, dt_seconds * spring_speed)
                    needs_repaint = True

        time_changed = False
        time_settled = False
        zoom_changed = False
        
        time_diff = self.target_time - self.current_time
        if abs(time_diff) > 0.1:
            lerp_factor = min(1.0, smoothness_per_second * dt_seconds)
            self.current_time += time_diff * lerp_factor
            self.current_time = float(self.current_time) 
            time_changed = True
            needs_repaint = True
        else:
            if self.current_time != self.target_time:
                self.current_time = self.target_time
                time_settled = True
                needs_repaint = True
        
        zoom_diff = self.target_zoom - self.zoom
        if abs(zoom_diff) > self.zoom * 0.00001:
            lerp_factor = min(1.0, smoothness_per_second * dt_seconds)
            self.zoom += zoom_diff * lerp_factor
            zoom_changed = True
            needs_repaint = True
        else:
            if self.zoom != self.target_zoom:
                self.zoom = self.target_zoom
                needs_repaint = True
        
        if time_changed or zoom_changed:
            if time_changed and not self.editor.is_playing:
                if abs(time_diff) > 10:
                    self.editor.sync_audio_to_time(video_exact=False)
            
            if self.dragging_objects:
                self.update_dragged_objects()
            
            if self.selection_start is not None:
                self.update_selection_rect()

            self.update_scrollbar()

        if time_settled and not self.editor.is_playing:
            self.editor.sync_audio_to_time(video_exact=True)
            
        
        has_multi_select = len(self.selected_objects) >= 2
        
        if has_multi_select:
            if not self.selection_was_active:
                self.selection_anim_state = "in"
                self.selection_anim_time = time.time()
                
                self.selection_current_bounds = None
                self.selection_target_bounds = None
                needs_repaint = True
            self.selection_was_active = True
            self.selection_active_visible = True
            if self.selection_anim_state == "in" and (time.time() - self.selection_anim_time) < 0.2:
                needs_repaint = True
        else:
            if self.selection_was_active:
                self.selection_anim_state = "out"
                self.selection_anim_time = time.time()
                self.selection_was_active = False
                needs_repaint = True
            
            if self.selection_anim_state == "out":
                 if time.time() - self.selection_anim_time < 0.2:
                     needs_repaint = True
                 else:
                     if self.selection_active_visible:
                         self.selection_active_visible = False
                         self.selection_anim_state = "none"
                         needs_repaint = True
            
        if self.selection_target_bounds is not None:
             if self.selection_current_bounds is None:
                 self.selection_current_bounds = list(self.selection_target_bounds)
                 needs_repaint = True
             else:
                 speed = 15.0 * dt_seconds
                 factor = min(1.0, speed)
                 for i in range(4):
                     diff = self.selection_target_bounds[i] - self.selection_current_bounds[i]
                     if abs(diff) > 0.1:
                         self.selection_current_bounds[i] += diff * factor
                         needs_repaint = True

        status_now = time.perf_counter()
        update_status_ui = (
            not self.editor.is_playing
            or status_now - self._last_status_ui_update >= 1.0 / 30.0
        )
        if update_status_ui:
            self._last_status_ui_update = status_now
            audio_ms = self.visual_to_audio_ms(self.current_time)
            if self.editor and hasattr(self.editor, 'gb_timing') and self.editor.gb_timing.isVisible():
                new_text = format_editor_timestamp(audio_ms, include_milliseconds=True)
                if self.editor.lbl_current_time.text() != new_text:
                    self.editor.lbl_current_time.setText(new_text)

                if hasattr(self.editor, 'lbl_current_ms'):
                    ms_text = f"{int(audio_ms)} ms"
                    if self.editor.lbl_current_ms.text() != ms_text:
                        self.editor.lbl_current_ms.setText(ms_text)
                        
            if self.editor and hasattr(self.editor, 'meta_widgets') and "BPM" in self.editor.meta_widgets:
                if not (getattr(self.editor, 'start_screen', None) and self.editor.start_screen.isVisible()):
                    new_bpm = self.get_bpm_at_ms(audio_ms)
                    if self.editor.meta_widgets["BPM"].value() != new_bpm:
                        self.editor.meta_widgets["BPM"].setValue(new_bpm)

        self.process_visual_interpolation(dt_seconds)
        self.process_bpm_interpolation(dt_seconds)
        if (
            getattr(self.editor, 'enable_visualizer', False)
            and np.any(self.vis_bar_heights > 0.001)
        ):
            needs_repaint = True
        if (self.visual_interpolating_objects or self.bpm_interpolating or
            getattr(self, 'bpm_drag_start_times', {}) or
            getattr(self, 'bpm_drag_release_times', {}) or
            getattr(self, 'dying_bpm_tags', []) or
            (hasattr(self, 'dragging_bpm_tag') and self.dragging_bpm_tag)):
             needs_repaint = True
        
        if needs_repaint:
            self.update()

    def process_visual_interpolation(self, dt):
        to_remove = []
        speed = 25.0
        
        for obj in self.visual_interpolating_objects:
            if hasattr(obj, '_target_visual_time'):
                if not hasattr(obj, '_current_visual_time'):
                    obj._current_visual_time = obj.time
                
                diff = obj._target_visual_time - obj._current_visual_time
                if abs(diff) < 0.1 and not self.dragging_objects:
                    obj._current_visual_time = obj._target_visual_time
                else:
                    obj._current_visual_time += diff * min(1.0, dt * speed)
            
            if hasattr(obj, '_target_visual_end_time'):
                 current_end = obj._current_visual_end_time if hasattr(obj, '_current_visual_end_time') else obj.end_time
                 if not hasattr(obj, '_current_visual_end_time'):
                     obj._current_visual_end_time = current_end

                 diff = obj._target_visual_end_time - obj._current_visual_end_time
                 if abs(diff) < 0.1 and not self.dragging_objects:
                     obj._current_visual_end_time = obj._target_visual_end_time
                 else:
                     obj._current_visual_end_time += diff * min(1.0, dt * speed)

            settled = True
            if hasattr(obj, '_target_visual_time'):
                if abs(obj._current_visual_time - obj._target_visual_time) > 0.1: settled = False
            
            if hasattr(obj, '_target_visual_end_time'):
                if abs(obj._current_visual_end_time - obj._target_visual_end_time) > 0.1: settled = False

            if hasattr(obj, '_target_visual_lane'):
                if not hasattr(obj, '_current_visual_lane'):
                     obj._current_visual_lane = self.get_visual_lane_value(obj)
                
                diff = obj._target_visual_lane - obj._current_visual_lane
                if abs(diff) < 0.01 and not self.dragging_objects:
                     obj._current_visual_lane = obj._target_visual_lane
                else:
                     obj._current_visual_lane += diff * min(1.0, dt * speed)
                
                if abs(obj._current_visual_lane - obj._target_visual_lane) > 0.01: settled = False

            if hasattr(obj, '_target_visual_pair_lane'):
                pair_lane = self.get_pair_lane(obj.lane)
                if pair_lane is not None:
                    if not hasattr(obj, '_current_visual_pair_lane'):
                        obj._current_visual_pair_lane = float(pair_lane)
                    
                    diff = obj._target_visual_pair_lane - obj._current_visual_pair_lane
                    if abs(diff) < 0.01 and not self.dragging_objects:
                        obj._current_visual_pair_lane = obj._target_visual_pair_lane
                    else:
                        obj._current_visual_pair_lane += diff * min(1.0, dt * speed)
                    
                    if abs(obj._current_visual_pair_lane - obj._target_visual_pair_lane) > 0.01: settled = False

            
            if settled and not self.dragging_objects:
                to_remove.append(obj)
        
        for obj in to_remove:
            self.visual_interpolating_objects.discard(obj)
            if hasattr(obj, '_target_visual_pair_lane'): del obj._target_visual_pair_lane
            if hasattr(obj, '_current_visual_pair_lane'): del obj._current_visual_pair_lane

    def process_bpm_interpolation(self, dt):
        to_remove = []
        speed = 25.0
        
        for tp in self.bpm_interpolating:
             if '_target_visual_time' in tp:
                 if '_current_visual_time' not in tp:
                     tp['_current_visual_time'] = tp['time']
                 
                 diff = tp['_target_visual_time'] - tp['_current_visual_time']
                 dragging_this = getattr(self, 'dragging_bpm_tag', None) is tp
                 
                 if abs(diff) < 0.1 and not dragging_this:
                      tp['_current_visual_time'] = tp['_target_visual_time']
                      to_remove.append(tp)
                 else:
                      tp['_current_visual_time'] += diff * min(1.0, dt * speed)
                      
        for tp in to_remove:
             if tp in self.bpm_interpolating:
                 self.bpm_interpolating.remove(tp)
             if '_target_visual_time' in tp: del tp['_target_visual_time']
             if '_current_visual_time' in tp: del tp['_current_visual_time']

    def get_pair_lane(self, l):
        if l == -1: return 2
        if l == 2: return -1
        if l == 0: return 1
        if l == 1: return 0
        return None

    def get_visual_lane_value(self, obj, lane=None):
        lane = obj.lane if lane is None else lane
        if obj.custom_data is not None and lane == -2:
            return 0.5
        return float(lane)

    def get_lane_y_from_float(self, l_float):
        sf = getattr(self.editor, 'global_scale', 1.0)
        center_y = (self.height() / sf) / 2
        return center_y + (l_float - 0.5) * LANE_HEIGHT

    def get_effective_lane(self, obj):
        lane = obj.lane
        if (
            self._live_event_cache_active
            and not obj.is_event
            and not obj.is_freestyle
            and obj.custom_data is None
            and lane in [-1, 2]
            and not self.is_time_in_toggle_center(obj.time)
        ):
            return 0 if lane == -1 else 1
        return lane

    def get_draw_y(self, obj):
        effective_lane = self.get_effective_lane(obj)
        if effective_lane != obj.lane:
            return self.get_lane_y_from_float(float(effective_lane))
        return self.get_lane_y_from_float(getattr(obj, '_current_visual_lane', float(obj.lane)))

    def get_draw_pair_y(self, obj):
        effective_lane = self.get_effective_lane(obj)
        if effective_lane != obj.lane:
            pair = self.get_pair_lane(effective_lane)
            return self.get_lane_y_from_float(float(pair if pair is not None else effective_lane))
        current_pair_lane = getattr(obj, '_current_visual_pair_lane', None)
        if current_pair_lane is not None:
            return self.get_lane_y_from_float(current_pair_lane)
        pair = self.get_pair_lane(obj.lane)
        if pair is not None:
             return self.get_lane_y_from_float(float(pair))
        return self.get_draw_y(obj)

    def get_draw_time(self, obj):
        state = getattr(self, 'bpm_follow_drag_state', None)
        if state and 'preview_times' in state:
            index = state['object_indices'].get(obj)
            if index is not None:
                return int(state['preview_times'][index])
        return getattr(obj, '_current_visual_time', obj.time)

    def get_draw_end_time(self, obj):
        state = getattr(self, 'bpm_follow_drag_state', None)
        if state and 'preview_end_times' in state:
            index = state['hold_indices'].get(obj)
            if index is not None:
                return max(self.get_draw_time(obj), int(state['preview_end_times'][index]))
        return getattr(obj, '_current_visual_end_time', obj.end_time)

    def on_edge_scroll(self):
        now = time.perf_counter()
        dt = min(0.05, max(0.0, now - self._last_edge_scroll_tick))
        self._last_edge_scroll_tick = now
        self.target_time += self.edge_scroll_speed * dt * 60.0
        self.target_time = max(0, self.target_time)
        song_length_ms = self.get_visual_song_length()
        if song_length_ms > 0:
            self.target_time = min(self.target_time, song_length_ms)
            
        self.update_scrollbar()
        self.update_dragged_objects()
        self.update_selection_rect()
        self.update()

    def update_selection_rect(self):
        if self.selection_start is None or self.selection_last_mouse_y is None:
            return
        
        start_x = self.ms_to_x(self.selection_start)
        current_x = self.last_mouse_pos.x() if self.last_mouse_pos else start_x
        x1 = min(start_x, current_x)
        y1 = min(self.selection_start_y, self.selection_last_mouse_y)
        x2 = max(start_x, current_x)
        y2 = max(self.selection_start_y, self.selection_last_mouse_y)
        
        self.selection_rect = QRectF(x1, y1, x2-x1, y2-y1)
        
        center_y = self.height() / 2
        lane_0_y = center_y - LANE_HEIGHT / 2
        lane_1_y = center_y + LANE_HEIGHT / 2
        
        if self.beatmap:
            self.selected_objects = set(getattr(self, '_drag_base_selection', set()))
            for obj in self.get_selection_candidates(x1, x2):
                if self.is_custom_missing(obj):
                    continue
                obj_x = self.audio_ms_to_x(obj.time)
                
                if obj.custom_data is not None:
                    obj_y = self.get_custom_object_y(obj)
                elif obj.is_event:
                    obj_y = center_y
                else:
                    obj_y = lane_0_y if obj.lane == 0 else lane_1_y
                
                if x1 <= obj_x <= x2 and y1 <= obj_y <= y2:
                    self.selected_objects.add(obj)
                elif obj.is_hold or obj.is_screamer or obj.is_spam or self.is_custom_length(obj):
                    end_x = self.audio_ms_to_x(obj.end_time)
                    if x1 <= end_x <= x2 and y1 <= obj_y <= y2:
                        self.selected_objects.add(obj)

    def get_sorted_timing_points(self):
        if self.beatmap and self.beatmap.timing_points:
            return self.beatmap.timing_points
        bpm = self.beatmap.metadata.BPM if self.beatmap else 120
        offset = self.beatmap.metadata.Offset if self.beatmap else 0
        return [{'time': int(offset), 'bpm': bpm}]

    def get_effective_timing_bpm(self, timing_point):
        base_bpm = self.beatmap.metadata.BPM if self.beatmap else 120
        if base_bpm <= 0:
            base_bpm = 120
        bpm = float(timing_point.get('bpm', base_bpm))
        return bpm if bpm > 0 else base_bpm

    def capture_bpm_follow_state(self, timing_point):
        if not self.beatmap or not getattr(self.editor, 'objects_follow_bpm_grid', True):
            return None
        timing_points = list(self.get_sorted_timing_points())
        tag_index = next((i for i, tp in enumerate(timing_points) if tp is timing_point), -1)
        if tag_index < 0:
            return None
        tag_time = float(timing_point['time'])
        next_time = float(timing_points[tag_index + 1]['time']) if tag_index + 1 < len(timing_points) else float('inf')
        bpm = self.get_effective_timing_bpm(timing_point)
        beat_factor = bpm / 60000.0
        objects = []
        start_beats = []
        hold_objects = []
        hold_start_indices = []
        end_beats = []
        max_beat = 0.0
        for obj in self.beatmap.hit_objects:
            if self.is_custom_missing(obj):
                continue
            if obj.time < tag_time:
                continue
            if obj.time >= next_time:
                break
            start_beat = (float(obj.time) - tag_time) * beat_factor
            end_beat = (float(obj.end_time) - tag_time) * beat_factor if obj.type == 128 or self.is_custom_length(obj) else None
            objects.append(obj)
            start_beats.append(start_beat)
            max_beat = max(max_beat, start_beat)
            if end_beat is not None:
                hold_objects.append(obj)
                hold_start_indices.append(len(objects) - 1)
                end_beats.append(end_beat)
                max_beat = max(max_beat, end_beat)
        return {
            'timing_point': timing_point,
            'objects': objects,
            'start_beats': np.asarray(start_beats, dtype=np.float64),
            'object_indices': {obj: index for index, obj in enumerate(objects)},
            'hold_objects': hold_objects,
            'hold_start_indices': np.asarray(hold_start_indices, dtype=np.int64),
            'hold_indices': {obj: index for index, obj in enumerate(hold_objects)},
            'end_beats': np.asarray(end_beats, dtype=np.float64),
            'max_beat': max_beat
        }

    def get_bpm_follow_max_offset(self, state):
        if not state:
            return 0.0
        timing_point = state['timing_point']
        beat_length = 60000.0 / self.get_effective_timing_bpm(timing_point)
        return state.get('max_beat', 0.0) * beat_length

    def update_bpm_follow_preview(self, state):
        if not state:
            return
        timing_point = state['timing_point']
        tag_time = float(timing_point['time'])
        beat_length = 60000.0 / self.get_effective_timing_bpm(timing_point)
        state['preview_times'] = np.rint(tag_time + state['start_beats'] * beat_length).astype(np.int64)
        state['preview_end_times'] = np.rint(tag_time + state['end_beats'] * beat_length).astype(np.int64)

    def apply_bpm_follow_state(self, state, finalize=True):
        if not state or not self.beatmap:
            return
        timing_point = state['timing_point']
        if timing_point not in self.beatmap.timing_points:
            return
        tag_time = float(timing_point['time'])
        beat_length = 60000.0 / self.get_effective_timing_bpm(timing_point)
        changed = False
        new_times = np.rint(tag_time + state['start_beats'] * beat_length).astype(np.int64)
        for obj, new_time_value in zip(state['objects'], new_times):
            new_time = int(new_time_value)
            if obj.time != new_time:
                obj.time = new_time
                changed = True
            if hasattr(obj, '_current_visual_time'):
                obj._current_visual_time = float(new_time)
            if hasattr(obj, '_target_visual_time'):
                obj._target_visual_time = float(new_time)
        new_end_times = np.rint(tag_time + state['end_beats'] * beat_length).astype(np.int64)
        for obj, new_end_time_value in zip(state['hold_objects'], new_end_times):
            new_end_time = max(obj.time, int(new_end_time_value))
            if obj.end_time != new_end_time:
                obj.end_time = new_end_time
                changed = True
            if hasattr(obj, '_current_visual_end_time'):
                obj._current_visual_end_time = float(new_end_time)
            if hasattr(obj, '_target_visual_end_time'):
                obj._target_visual_end_time = float(new_end_time)
        if changed:
            state['dirty'] = True
        if finalize and state.get('dirty', False):
            self.beatmap.hit_objects.sort(key=lambda obj: (obj.time, 0 if obj.is_event and obj.order_index == 0 else (2 if obj.is_event else 1), 0 if getattr(obj, 'is_freestyle', False) else 1, 0.5 if not obj.is_event else float(obj.order_index)))
            self._force_cache_update = True
            state['dirty'] = False

    def ms_to_visual_beats(self, ms):
        tps = self.get_sorted_timing_points()
        total_beats = 0.0
        prev_time = tps[0]['time']
        prev_bpm = tps[0]['bpm']
        for i in range(1, len(tps)):
            tp_time = tps[i]['time']
            if ms <= prev_time:
                break
            seg_end = min(ms, tp_time)
            if seg_end > prev_time:
                if prev_bpm > 0:
                    total_beats += (seg_end - prev_time) * (prev_bpm / 60000.0)
            prev_time = tp_time
            prev_bpm = tps[i]['bpm']
        if ms > prev_time:
            if prev_bpm > 0:
                total_beats += (ms - prev_time) * (prev_bpm / 60000.0)
        elif ms < tps[0]['time']:
            bpm0 = tps[0]['bpm'] if tps[0]['bpm'] > 0 else 120
            total_beats = (ms - tps[0]['time']) * (bpm0 / 60000.0)
        return total_beats

    def ms_to_x(self, ms):
        bpm = self.beatmap.metadata.BPM if self.beatmap else 120
        px_per_ms = (self.pixels_per_beat * (bpm / 60000)) * self.zoom
        val_start = getattr(self.editor, 'timeline_visual_start', TIMELINE_START_X)
        return (ms - self.current_time) * px_per_ms + val_start

    def x_to_ms(self, x):
        bpm = self.beatmap.metadata.BPM if self.beatmap else 120
        px_per_ms = (self.pixels_per_beat * (bpm / 60000)) * self.zoom
        val_start = getattr(self.editor, 'timeline_visual_start', TIMELINE_START_X)
        return (x - val_start) / px_per_ms + self.current_time

    def audio_ms_to_x(self, audio_ms):
        return self.ms_to_x(self.audio_to_visual_ms(audio_ms))

    def x_to_audio_ms(self, x):
        return self.visual_to_audio_ms(self.x_to_ms(x))

    def get_bpm_at_ms(self, ms):
        tps = self.get_sorted_timing_points()
        if not self._tps_cache_audio_times or len(self._tps_cache_audio_times) != len(tps):
            self._update_tps_cache(tps)
        idx = bisect.bisect_right(self._tps_cache_audio_times, ms) - 1
        if idx < 0:
            idx = 0
        bpm = tps[idx]['bpm']
        return bpm if bpm > 0 else 120

    def get_segment_offset(self, ms):
        tps = self.get_sorted_timing_points()
        if not self._tps_cache_audio_times or len(self._tps_cache_audio_times) != len(tps):
            self._update_tps_cache(tps)
        idx = bisect.bisect_right(self._tps_cache_audio_times, ms) - 1
        if idx < 0:
            idx = 0
        return self._tps_cache_audio_times[idx]

    def get_segment_offset_visual(self, visual_ms):
        audio_ms = self.visual_to_audio_ms(visual_ms)
        audio_seg_off = self.get_segment_offset(audio_ms)
        return self.audio_to_visual_ms(audio_seg_off)

    def _update_tps_cache(self, tps):
        base_bpm = self.beatmap.metadata.BPM if self.beatmap else 120
        if base_bpm <= 0: base_bpm = 120
        self._tps_cache_audio_times = []
        self._tps_cache_visual_times = []
        self._tps_cache_data = []
        if not tps: return
        vis = float(tps[0]['time'])
        for i in range(len(tps)):
            t = tps[i]['time']
            bpm = tps[i]['bpm'] if tps[i]['bpm'] > 0 else base_bpm
            ratio = bpm / base_bpm
            self._tps_cache_audio_times.append(t)
            self._tps_cache_visual_times.append(vis)
            self._tps_cache_data.append(ratio)
            if i + 1 < len(tps):
                vis += (tps[i+1]['time'] - t) * ratio

    def audio_to_visual_ms(self, audio_ms, tps_cache=None):
        if not self._tps_cache_audio_times:
            tps = tps_cache if tps_cache is not None else self.get_sorted_timing_points()
            self._update_tps_cache(tps)
            if not self._tps_cache_audio_times:
                return audio_ms
        idx = bisect.bisect_right(self._tps_cache_audio_times, audio_ms) - 1
        if idx < 0: return audio_ms
        t = self._tps_cache_audio_times[idx]
        vis = self._tps_cache_visual_times[idx]
        ratio = self._tps_cache_data[idx]
        return vis + (audio_ms - t) * ratio

    def visual_to_audio_ms(self, visual_ms, ignore_bpm_tag=None, tps_cache=None):
        if ignore_bpm_tag:
            tps = tps_cache if tps_cache is not None else self.get_sorted_timing_points()
            tps = [tp for tp in tps if tp is not ignore_bpm_tag]
            base_bpm = self.beatmap.metadata.BPM if self.beatmap else 120
            if base_bpm <= 0: base_bpm = 120
            if not tps:
                offset = self.beatmap.metadata.Offset if self.beatmap else 0
                tps = [{'time': int(offset), 'bpm': base_bpm}]
            remaining = visual_ms - float(tps[0]['time'])
            if remaining <= 0: return visual_ms
            audio_pos = float(tps[0]['time'])
            for i in range(len(tps)):
                seg_bpm = tps[i]['bpm'] if tps[i]['bpm'] > 0 else base_bpm
                ratio = seg_bpm / base_bpm
                seg_start = tps[i]['time']
                seg_end = tps[i + 1]['time'] if i + 1 < len(tps) else float('inf')
                seg_audio_dur = seg_end - seg_start
                seg_visual_dur = seg_audio_dur * ratio
                if remaining <= seg_visual_dur:
                    if ratio > 0: audio_pos = seg_start + remaining / ratio
                    return audio_pos
                remaining -= seg_visual_dur
                audio_pos = seg_end
            return audio_pos
            
        if not self._tps_cache_visual_times:
            tps = tps_cache if tps_cache is not None else self.get_sorted_timing_points()
            self._update_tps_cache(tps)
            if not self._tps_cache_visual_times: return visual_ms
        idx = bisect.bisect_right(self._tps_cache_visual_times, visual_ms) - 1
        if idx < 0: return visual_ms
        t = self._tps_cache_audio_times[idx]
        vis = self._tps_cache_visual_times[idx]
        ratio = self._tps_cache_data[idx]
        if ratio > 0: return t + (visual_ms - vis) / ratio
        return t

    def get_visual_song_length(self):
        if not self.beatmap:
            return 0
        audio_len = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap.metadata.ActualAudioLength > 0 else 0
        if audio_len <= 0:
            return 0
        return self.audio_to_visual_ms(audio_len)

    def get_snap_time(self, ms):
        if not self.beatmap: return ms
        bpm = self.beatmap.metadata.BPM
        if bpm <= 0: return ms
        beat_len = 60000 / bpm
        snap_len = beat_len / self.grid_snap_div
        offset = self.get_segment_offset_visual(ms)
        return round((ms - offset) / snap_len) * snap_len + offset

    def get_waveform_tile(self, tile_index, tile_width, strip_h, px_per_ms, offset_ms, wf_len):
        device_pixel_ratio = self.devicePixelRatio()
        raster_scale = device_pixel_ratio * max(0.1, float(getattr(self.editor, 'global_scale', 1.0)))
        signature = (
            id(self.waveform_data),
            self.waveform_ratio,
            round(px_per_ms, 9),
            round(float(offset_ms), 6),
            self._waveform_cache_generation,
            round(device_pixel_ratio, 4),
            round(raster_scale, 4),
            tile_width,
            strip_h,
            UI_THEME["accent"],
        )
        if signature != self._waveform_tile_signature:
            self._waveform_tile_cache.clear()
            self._waveform_tile_signature = signature

        cached = self._waveform_tile_cache.get(tile_index)
        if cached is not None:
            cached_pixmap, cached_loaded_points, required_start, required_end = cached
            if (
                cached_loaded_points >= required_end
                or wf_len <= cached_loaded_points
                or wf_len <= required_start
            ):
                self._waveform_tile_cache.pop(tile_index)
                self._waveform_tile_cache[tile_index] = cached
                return cached_pixmap

        pixel_width = max(1, int(math.ceil(tile_width * raster_scale)))
        pixel_height = max(1, int(math.ceil(strip_h * raster_scale)))
        pixmap = QPixmap(pixel_width, pixel_height)
        pixmap.setDevicePixelRatio(raster_scale)
        pixmap.fill(Qt.GlobalColor.transparent)

        tile_world_x = tile_index * tile_width
        chunk_ms = 2.0 / px_per_ms
        tile_visual_start = tile_world_x / px_per_ms - offset_ms
        aligned_start = math.floor(tile_visual_start / chunk_ms) * chunk_ms
        point_count = int(math.ceil(tile_width / 2.0)) + 3
        visual_points = aligned_start + np.arange(point_count, dtype=np.float64) * chunk_ms
        world_points = (visual_points + offset_ms) * px_per_ms
        local_points = world_points[:-1] - tile_world_x

        audio_points = visual_points.copy()
        visual_times = self._tps_cache_visual_times
        if visual_times:
            visual_times_np = np.asarray(visual_times, dtype=np.float64)
            audio_times_np = np.asarray(self._tps_cache_audio_times, dtype=np.float64)
            ratios_np = np.asarray(self._tps_cache_data, dtype=np.float64)
            segment_indices = np.searchsorted(visual_times_np, visual_points, side='right') - 1
            mapped = segment_indices >= 0
            mapped_indices = segment_indices[mapped]
            mapped_ratios = ratios_np[mapped_indices]
            mapped_audio = audio_times_np[mapped_indices]
            positive_ratios = mapped_ratios > 0
            mapped_audio[positive_ratios] += (
                visual_points[mapped][positive_ratios]
                - visual_times_np[mapped_indices[positive_ratios]]
            ) / mapped_ratios[positive_ratios]
            audio_points[mapped] = mapped_audio

        start_indices = np.trunc(audio_points[:-1] / self.waveform_ratio).astype(np.int64)
        end_indices = np.trunc(audio_points[1:] / self.waveform_ratio).astype(np.int64)
        end_indices = np.maximum(end_indices, start_indices + 1)
        nonnegative_starts = start_indices[start_indices >= 0]
        required_start = min(
            len(self.waveform_data),
            int(np.min(nonnegative_starts)) if nonnegative_starts.size else 0,
        )
        required_end = min(
            len(self.waveform_data),
            max(0, int(np.max(end_indices))) if end_indices.size else 0,
        )
        clipped_ends = np.minimum(end_indices, wf_len)
        values = np.zeros(start_indices.size, dtype=np.float32)
        valid = (
            (start_indices >= 0)
            & (start_indices < wf_len)
            & (clipped_ends > start_indices)
        )
        single = valid & (clipped_ends == start_indices + 1)
        if np.any(single):
            values[single] = self.waveform_data[start_indices[single]]
        wide_positions = np.flatnonzero(valid & ~single)
        if wide_positions.size:
            wide_starts = start_indices[wide_positions]
            wide_ends = clipped_ends[wide_positions]
            if (
                wide_positions.size > 1
                and np.all(wide_ends[:-1] == wide_starts[1:])
            ):
                waveform_slice = self.waveform_data[wide_starts[0]:wide_ends[-1]]
                boundaries = wide_starts - wide_starts[0]
                values[wide_positions] = np.maximum.reduceat(waveform_slice, boundaries)
            else:
                values[wide_positions] = [
                    np.max(self.waveform_data[start_idx:end_idx])
                    for start_idx, end_idx in zip(wide_starts, wide_ends)
                ]

        center_y = strip_h / 2.0
        heights = values * center_y * 0.95
        points_top = [
            QPointF(float(x), float(center_y - height))
            for x, height in zip(local_points, heights)
        ]
        points_bottom = [
            QPointF(float(x), float(center_y + height))
            for x, height in zip(local_points, heights)
        ]
        if points_top:
            tile_painter = QPainter(pixmap)
            tile_painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            tile_painter.setPen(Qt.PenStyle.NoPen)
            tile_painter.setBrush(QColor(UI_THEME["accent"]))
            tile_painter.drawPolygon(QPolygonF(points_top + list(reversed(points_bottom))))
            tile_painter.end()

        self._waveform_tile_cache[tile_index] = (pixmap, wf_len, required_start, required_end)
        while len(self._waveform_tile_cache) > 8:
            oldest = next(iter(self._waveform_tile_cache))
            self._waveform_tile_cache.pop(oldest)
        return pixmap

    def paintEvent(self, e):
        if hasattr(self, "sc_timer") and self.sc_timer.isActive():
            self.sc_update_scroll()
            
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        sf = getattr(self.editor, 'global_scale', 1.0)
        p.scale(sf, sf)
        w, h = self.width() / sf, self.height() / sf

        start_screen_visible = (
            hasattr(self.editor, "start_screen")
            and self.editor.start_screen.isVisible()
        )

        background_drawn = False
        if self.bg_image_path:
            bg_opacity = getattr(self.editor, 'background_opacity', 100) / 100.0
            preview_vis = 100 if start_screen_visible else getattr(self.editor, 'preview_bg_opacity', 30)
            target_w = int(w)
            target_h = int(h)
            device_pixel_ratio = self.devicePixelRatio()
            scaled_w = int(target_w * device_pixel_ratio)
            scaled_h = int(target_h * device_pixel_ratio)
            background_signature = (
                scaled_w,
                scaled_h,
                round(bg_opacity, 4),
                int(preview_vis),
                self.col_bg.rgba(),
            )

            if self.bg_pixmap_scaled is None or self.bg_pixmap_scaled_size != background_signature:
                source_pixmap = load_scaled_display_pixmap(
                    self.bg_image_path,
                    self,
                    target_w,
                    target_h,
                )
                if source_pixmap:
                    composite = QPixmap(max(1, scaled_w), max(1, scaled_h))
                    composite.setDevicePixelRatio(device_pixel_ratio)
                    composite.fill(self.col_bg)
                    composite_painter = QPainter(composite)
                    composite_painter.setOpacity(bg_opacity)
                    source_dpr = source_pixmap.devicePixelRatio()
                    x_offset = (w - source_pixmap.width() / source_dpr) / 2
                    y_offset = (h - source_pixmap.height() / source_dpr) / 2
                    composite_painter.drawPixmap(QPointF(x_offset, y_offset), source_pixmap)
                    composite_painter.setOpacity(1.0)
                    preview_top = h / 2 + LANE_HEIGHT / 2 + LANE_HEIGHT + 70
                    preview_alpha = int(255 * (1.0 - preview_vis / 100.0))
                    if preview_alpha > 0:
                        composite_painter.fillRect(
                            QRectF(0, preview_top, w, max(0.0, h - preview_top)),
                            QColor(30, 30, 35, preview_alpha),
                        )
                    composite_painter.end()
                    self.bg_pixmap_scaled = composite
                else:
                    self.bg_pixmap_scaled = None
                self.bg_pixmap_scaled_size = background_signature

            if self.bg_pixmap_scaled:
                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
                p.drawPixmap(QPointF(0, 0), self.bg_pixmap_scaled)
                background_drawn = True

        if not background_drawn:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.fillRect(QRectF(0, 0, w, h), self.col_bg)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        if getattr(self.editor, 'is_loading_project', False) or start_screen_visible:
            p.end()
            return

        video_controller = getattr(self.editor, "video_controller", None)
        if video_controller and video_controller.enabled:
            video_controller.paint(p, QRectF(0, 0, w, h))

        self.update_caches_if_needed()
        
        if self.beat_flash_intensity > 0.01:
            self.beat_flash_intensity *= 0.92
        else:
            self.beat_flash_intensity = 0.0
        
        if getattr(self.editor, "enable_visualizer", True):
            vis_opacity = getattr(self.editor, 'visualizer_opacity', 100) / 100.0
            if vis_opacity > 0.01:
                base_val = getattr(self.editor, 'visualizer_level', 0.0) if self.editor.is_playing else 0.0
                
                num_bars = 32
                bar_width = w / num_bars
                p.setPen(Qt.PenStyle.NoPen)
                
                vis_now = time.perf_counter()
                vis_dt = min(0.05, max(0.0, vis_now - self.last_vis_update_time))
                self.last_vis_update_time = vis_now

                audio_time = self.visual_to_audio_ms(self.current_time)
                current_bpm = self.get_bpm_at_ms(audio_time)
                beat_interval = 60000.0 / current_bpm
                segment_offset = self.get_segment_offset(audio_time)
                beat_phase = (
                    ((audio_time - segment_offset) % beat_interval)
                    / beat_interval
                    * 2.0
                    * math.pi
                )
                noise = (
                    np.sin(beat_phase + self.vis_bar_phase_1)
                    + np.cos(beat_phase * 2.0 + self.vis_bar_phase_2)
                    + 2.0
                ) * 0.25
                target_vals = base_val * noise * self.vis_bar_factors
                smooth_rates = np.where(target_vals > self.vis_bar_heights, 52.0, 19.0)
                smooth_f = 1.0 - np.exp(-smooth_rates * vis_dt)
                self.vis_bar_heights += (target_vals - self.vis_bar_heights) * smooth_f
                direction_line_y = min(h, h / 2 + LANE_HEIGHT / 2 + LANE_HEIGHT + 50)
                bar_hs = direction_line_y * np.clip(self.vis_bar_heights, 0.0, 1.0)
                bar_alpha = int(255 * vis_opacity)
                p.setBrush(QColor(255, 255, 255, bar_alpha))
                bar_rects = [
                    QRectF(i * bar_width, 0, bar_width - 2, float(bar_hs[i]))
                    for i in range(num_bars)
                    if bar_hs[i] > 0.01
                ]
                if bar_rects:
                    p.drawRects(bar_rects)
            
        if self.waveform_data is not None and len(self.waveform_data):
            strip_h = 85
            strip_y = 0
            
            song_len_ms = self.get_visual_song_length()
            if song_len_ms <= 0:
                song_len_ms = self.beatmap.metadata.SongLength * 1000 if self.beatmap else 0
            
            offset_ms = self.temp_waveform_offset
            
            bg_start_x = self.ms_to_x(0 + offset_ms)
            bg_end_x = self.ms_to_x(song_len_ms + offset_ms)
            
            draw_bg_x = max(0, bg_start_x)
            draw_bg_w = min(w, bg_end_x) - draw_bg_x
            
            if draw_bg_w > 0:
                p.setBrush(QColor(20, 20, 20, 80))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(QRectF(draw_bg_x, strip_y, draw_bg_w, strip_h))
            
            start_ms = self.x_to_ms(0) - offset_ms
            end_ms = self.x_to_ms(w) - offset_ms

            if end_ms > start_ms:
                wf_len = min(len(self.waveform_data), self.waveform_loaded_points)
                view_bpm = self.beatmap.metadata.BPM if self.beatmap else 120.0
                if view_bpm <= 0:
                    view_bpm = 120.0
                view_px_per_ms = self.pixels_per_beat * (view_bpm / 60000.0) * self.zoom
                view_start = getattr(self.editor, 'timeline_visual_start', TIMELINE_START_X)
                if view_px_per_ms > 0 and wf_len > 0:
                    tile_width = 1024
                    world_view_left = self.current_time * view_px_per_ms - view_start
                    world_view_right = world_view_left + w
                    first_tile = math.floor(world_view_left / tile_width)
                    last_tile = math.floor(world_view_right / tile_width)
                    for tile_index in range(first_tile, last_tile + 1):
                        tile = self.get_waveform_tile(
                            tile_index,
                            tile_width,
                            strip_h,
                            view_px_per_ms,
                            offset_ms,
                            wf_len,
                        )
                        tile_x = tile_index * tile_width - world_view_left
                        p.drawPixmap(QPointF(tile_x, strip_y), tile)

        if not self.beatmap:
            return

        opacity_val = getattr(self.editor, 'lane_opacity', 100)
        a_base = min(255, max(0, int(255 * (opacity_val / 100.0))))

        base_lane_col = getattr(self, 'original_object_colors', getattr(self, 'object_colors', {})).get("normal_lane", QColor(45, 45, 50))
        self.col_lane = QColor(base_lane_col)
        self.col_lane.setAlpha(a_base)
        
        orig_colors = getattr(self, 'original_object_colors', getattr(self, 'object_colors', {}))
        user_blue = orig_colors.get("direction_right", QColor("blue"))
        user_yellow = orig_colors.get("direction_left", QColor("yellow"))
        
        col_blue_cache = QColor(user_blue)
        col_blue_cache.setAlpha(a_base)
        col_yellow_cache = QColor(user_yellow)
        col_yellow_cache.setAlpha(a_base)
        
        col_blue_shadow_cache = col_blue_cache.darker(200)
        col_yellow_shadow_cache = col_yellow_cache.darker(200)
        
        col_freestyle_right = QColor(user_blue).lighter(150)
        col_freestyle_right.setAlpha(a_base)
        col_freestyle_left = QColor(user_yellow).lighter(150)
        col_freestyle_left.setAlpha(a_base)
        
        col_shadow_cache = self.col_lane.darker(300)

        center_y = h / 2
        lane_0_y = center_y - LANE_HEIGHT / 2
        lane_1_y = center_y + LANE_HEIGHT / 2
        lane_upper_y = lane_0_y - LANE_HEIGHT
        lane_lower_y = lane_1_y + LANE_HEIGHT

        centers = self.get_toggle_centers()
        _center_times = self.get_center_times()
        
        def is_in_toggle_center(ms):
            idx = bisect.bisect_right(_center_times, ms)
            if idx > 0 and idx % 2 == 0 and _center_times[idx - 1] == ms:
                idx -= 1
            return (idx % 2) == 1

        song_length_ms_pre = self.get_visual_song_length()
        if song_length_ms_pre <= 0:
            song_length_ms_pre = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap.metadata.ActualAudioLength > 0 else 0
        vis_min_ms_pre = self.x_to_ms(0)
        vis_max_ms_pre = self.x_to_ms(w)

        audio_min_ms_pre = self.visual_to_audio_ms(vis_min_ms_pre)
        audio_max_ms_pre = self.visual_to_audio_ms(vis_max_ms_pre)
        
        idx = bisect.bisect_right(_center_times, audio_min_ms_pre)
        cur_centered_pre = is_in_toggle_center(audio_min_ms_pre)
        
        st_audio = _center_times[idx - 1] if idx > 0 else 0
        st = self.audio_to_visual_ms(st_audio) if st_audio > 0 else 0
        
        for k in range(idx, len(centers) + 1):
            if k < len(centers):
                c = centers[k]
                et_audio = c.time
            else:
                et_audio = self.visual_to_audio_ms(song_length_ms_pre) if song_length_ms_pre > 0 else 9999999
                
            et = self.audio_to_visual_ms(et_audio)
            
            sx = int(self.ms_to_x(max(st, vis_min_ms_pre)))
            ex = int(self.ms_to_x(min(et, vis_max_ms_pre)))
            w_rect = ex - sx
            
            if w_rect > 0:
                shadow_h = 10
                if cur_centered_pre:
                    p.fillRect(sx, int(lane_0_y + 30), w_rect, shadow_h, col_blue_shadow_cache)
                    p.fillRect(sx, int(lane_1_y + 30), w_rect, shadow_h, col_blue_shadow_cache)
                    p.fillRect(sx, int(lane_upper_y + 30), w_rect, shadow_h, col_yellow_shadow_cache)
                    p.fillRect(sx, int(lane_lower_y + 30), w_rect, shadow_h, col_yellow_shadow_cache)

                    p.fillRect(sx, int(lane_0_y - 30), w_rect, 60, col_blue_cache)
                    p.fillRect(sx, int(lane_1_y - 30), w_rect, 60, col_blue_cache)
                    p.fillRect(sx, int(lane_upper_y - 30), w_rect, 60, col_yellow_cache)
                    p.fillRect(sx, int(lane_lower_y - 30), w_rect, 60, col_yellow_cache)
                else:
                    p.fillRect(sx, int(lane_0_y + 30), w_rect, shadow_h, col_shadow_cache)
                    p.fillRect(sx, int(lane_1_y + 30), w_rect, shadow_h, col_shadow_cache)

                    p.fillRect(sx, int(lane_0_y - 30), w_rect, 60, self.col_lane)
                    p.fillRect(sx, int(lane_1_y - 30), w_rect, 60, self.col_lane)
            
            if et_audio > audio_max_ms_pre:
                break
                
            if k < len(centers):
                cur_centered_pre = is_in_toggle_center(et_audio + 1)
            st = et
            
        segments, seg_ends = self.get_direction_segments()
        idx = bisect.bisect_right(seg_ends, audio_min_ms_pre) if seg_ends else 0

        for k in range(idx, len(segments)):
            seg = segments[k]
            st_audio = seg[0]
            et_audio = seg[1]
            
            if st_audio > audio_max_ms_pre: break
            
            st = self.audio_to_visual_ms(st_audio)
            et = self.audio_to_visual_ms(et_audio)
            
            if et < vis_min_ms_pre: continue
            if st > vis_max_ms_pre: break
            
            sx = int(self.ms_to_x(st))
            ex = int(self.ms_to_x(et))
            w_rect = ex - sx
            if w_rect > 0:
                is_centered = seg[3]
                if is_centered:
                    is_right = seg[2]
                    col_freestyle = col_freestyle_right if is_right else col_freestyle_left
                    start_y = int(lane_0_y + 40)
                    height = int(lane_1_y - 30 - start_y)
                    p.fillRect(sx, start_y, w_rect, height, col_freestyle)
        
        song_length_ms = self.get_visual_song_length()

        bpm = self.beatmap.metadata.BPM
        if bpm > 0:
            beat_ms = 60000 / bpm
            vis_start_ms = max(0, self.x_to_ms(0))
            vis_end_ms = min(self.x_to_ms(w), song_length_ms) if song_length_ms > 0 else self.x_to_ms(w)

            last_x = -1000
            min_line_spacing = 8

            visual_grid_div = self.grid_snap_div
            test_div = self.grid_snap_div
            test_t = vis_start_ms
            while test_div > 1:
                test_snap_len = beat_ms / test_div
                test_x1 = self.ms_to_x(test_t)
                test_x2 = self.ms_to_x(test_t + test_snap_len)
                if abs(test_x2 - test_x1) >= min_line_spacing:
                    visual_grid_div = test_div
                    break
                if test_div % 2 == 0:
                    test_div = test_div // 2
                else:
                    test_div = (test_div // 2) + 1 if test_div > 1 else 1
            else:
                visual_grid_div = max(1, test_div)

            tps = self.get_sorted_timing_points()
            seg_boundaries = getattr(self, '_cached_seg_boundaries', [])
            if not seg_boundaries:
                seg_boundaries = [self.beatmap.metadata.Offset]

            for seg_idx in range(len(seg_boundaries)):
                seg_offset = seg_boundaries[seg_idx]
                seg_end = seg_boundaries[seg_idx + 1] if seg_idx + 1 < len(seg_boundaries) else vis_end_ms + 60000

                if seg_end < vis_start_ms:
                    continue
                if seg_offset > vis_end_ms:
                    break

                draw_start = max(vis_start_ms, seg_offset)
                draw_end = min(seg_end, vis_end_ms)

                current_beat = max(0, int((draw_start - seg_offset) / beat_ms))
                t = current_beat * beat_ms + seg_offset

                grid_opacity = getattr(self.editor, 'grid_opacity', 100) / 100.0
                grid_thickness = getattr(self.editor, 'grid_thickness', 1)
                
                sub_col = QColor(self.col_subbeat)
                sub_col.setAlphaF(grid_opacity)
                sub_pen = QPen(sub_col, grid_thickness, Qt.PenStyle.SolidLine)
                
                enable_beatflash = getattr(self.editor, "enable_beatflash", True)
                beat_flash = self.beat_flash_intensity
                
                base_r, base_g, base_b = self.col_beat.red(), self.col_beat.green(), self.col_beat.blue()
                reg_col = QColor(base_r, base_g, base_b)
                reg_col.setAlphaF(grid_opacity)
                reg_pen = QPen(reg_col, grid_thickness)
                
                boost = int(155 * beat_flash)
                flash_col = QColor(min(255, base_r + boost), min(255, base_g + boost), min(255, base_b + boost))
                flash_col.setAlphaF(grid_opacity)
                flash_pen = QPen(flash_col, grid_thickness)
                
                lines_beat = []
                lines_flash = []
                lines_subbeat = []
                
                grid_y_bottom = int(h / 2 + LANE_HEIGHT / 2 + LANE_HEIGHT + 50)

                while t < draw_end:
                    if t >= 0:
                        x = self.ms_to_x(t)
                        is_segment_start = abs(t - seg_offset) < 0.001
                        if 0 <= x <= w and (is_segment_start or abs(x - last_x) >= min_line_spacing):
                            if beat_flash > 0 and enable_beatflash:
                                lines_flash.append(QLineF(int(x), 0, int(x), grid_y_bottom))
                            else:
                                lines_beat.append(QLineF(int(x), 0, int(x), grid_y_bottom))
                                
                            last_x = x

                        for i in range(1, visual_grid_div):
                            sub_t = t + (beat_ms * i / visual_grid_div)
                            if sub_t > draw_end: break
                            if sub_t >= 0:
                                sub_x = self.ms_to_x(sub_t)
                                if 0 <= sub_x <= w and abs(sub_x - last_x) >= min_line_spacing:
                                    lines_subbeat.append(QLineF(int(sub_x), 0, int(sub_x), grid_y_bottom))
                                    last_x = sub_x
                    t += beat_ms

                p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                if lines_subbeat:
                    p.setPen(sub_pen)
                    p.drawLines(lines_subbeat)
                if lines_beat:
                    p.setPen(reg_pen)
                    p.drawLines(lines_beat)
                if lines_flash:
                    p.setPen(flash_pen)
                    p.drawLines(lines_flash)
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)



        if hasattr(self.beatmap, 'timing_points'):
             accent_col = QColor(UI_THEME["accent"])
             p.setBrush(QBrush(accent_col))
             p.setPen(QPen(Qt.GlobalColor.white))
             
             tag_y = 90
             tag_w = 40
             tag_h = 50
             
             font = p.font()
             font.setBold(True)
             font.setPixelSize(12)
             p.setFont(font)
             
             current_time = time.time()
             self.bpm_drag_release_times = {
                 key: release_time
                 for key, release_time in self.bpm_drag_release_times.items()
                 if current_time - release_time < 0.25
             }
             tags_to_render = []
             for tp in self.beatmap.timing_points:
                  tags_to_render.append((tp, "normal"))
             
             self.dying_bpm_tags = [(tp, t) for tp, t in self.dying_bpm_tags if current_time - t < 0.2]
             for tp, t in self.dying_bpm_tags:
                  tags_to_render.append((tp, "dying"))

             for tp, status in tags_to_render:
                 t_val = tp.get('_current_visual_time', tp['time'])
                 t_val = self.audio_to_visual_ms(t_val)
                 tx = self.ms_to_x(t_val)
                 if status == "normal":
                      if tx < -50 or tx > w + 50: continue

                 scale = 1.0
                 alpha = 1.0
                 
                 if status == "dying":
                     original_death_time = next((t for obj, t in self.dying_bpm_tags if obj == tp), current_time)
                     pass_time = current_time - original_death_time
                     t_val = pass_time / 0.2
                     scale = 1.0 + t_val * 2.0 - t_val * t_val * 3.0
                     alpha = 1.0 - t_val
                 else:
                     if 'creation_time' in tp:
                         dt = current_time - tp['creation_time']
                         if dt < 0.3:
                             self._anim_running = True
                             t = dt / 0.3
                             s = 2.5
                             t = t - 1.0
                             val = t * t * ((s + 1.0) * t + s) + 1.0
                             
                             t_raw = dt / 0.3
                             t_val = t_raw - 1
                             val = t_val * t_val * ((s + 1) * t_val + s) + 1
                             scale = 1.4 - 0.4 * val
                     
                     if id(tp) in self.bpm_drag_start_times:
                          drag_start_time = self.bpm_drag_start_times[id(tp)]
                          pass_time = current_time - drag_start_time
                          if pass_time < 0.08:
                              t = min(1.0, pass_time / 0.08)
                              target_scale = 1.3
                              scale *= (1.0 + (target_scale - 1.0) * t)
                          else:
                              scale *= 1.3

                     if id(tp) in self.bpm_drag_release_times:
                          release_time = self.bpm_drag_release_times[id(tp)]
                          pass_time = current_time - release_time
                          if pass_time < 0.25:
                              t = pass_time / 0.25
                              s = 3.5
                              t_shifted = t - 1.0
                              ease_val = t_shifted * t_shifted * ((s + 1.0) * t_shifted + s) + 1.0
                              overshoot = -0.2 * math.sin(t * math.pi) * (1.0 - t)
                              bounce_scale = 1.3 - 0.3 * ease_val + overshoot
                              scale *= bounce_scale
                          else:
                              del self.bpm_drag_release_times[id(tp)]

                 if scale <= 0: continue
                 
                 rect_w = tag_w * scale
                 rect_h = tag_h * scale
                 rect = QRectF(tx - rect_w/2, tag_y, rect_w, rect_h)
                 
                 p.setOpacity(alpha)
                 p.setBrush(QBrush(accent_col))
                 p.setPen(Qt.PenStyle.NoPen)
                 p.drawRoundedRect(rect, 8 * scale, 8 * scale)
                 
                 p.setPen(QColor("white"))
                 bpm_val = tp['bpm']
                 if bpm_val.is_integer():
                     text_bpm = str(int(bpm_val))
                 else:
                     text_bpm = f"{bpm_val:.1f}"
                 
                 font.setPixelSize(int(12 * scale))
                 p.setFont(font)
                 
                 p.drawText(QRectF(rect.x(), rect.y() + 5 * scale, rect.width(), 20 * scale), Qt.AlignmentFlag.AlignCenter, text_bpm)
                 p.drawText(QRectF(rect.x(), rect.y() + 25 * scale, rect.width(), 20 * scale), Qt.AlignmentFlag.AlignCenter, "BPM")
                 p.setOpacity(1.0)
             
             p.setFont(font)
             font.setPixelSize(12)
             p.setFont(font)

        p.setPen(QPen(self.col_cursor, 2))
        if hasattr(self.editor, 'timeline_visual_start'):
            tx = self.editor.timeline_visual_start
        else:
            tx = TIMELINE_START_X
        p.drawLine(int(tx), 0, int(tx), int(h / 2 + LANE_HEIGHT / 2 + LANE_HEIGHT + 50))

        strip_h = 20
        strip_y = h / 2 + LANE_HEIGHT / 2 + LANE_HEIGHT + 50
        vis_min_ms = self.x_to_ms(0)
        vis_max_ms = self.x_to_ms(w)
        
        if hasattr(self, 'timeline_scrollbar') and self.timeline_scrollbar:
            cur_ms = self.visual_to_audio_ms(max(0, self.current_time))
            tot_ms = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap and self.beatmap.metadata.ActualAudioLength > 0 else self.visual_to_audio_ms(song_length_ms)
            show_hours = max(abs(cur_ms), abs(tot_ms)) >= 3600000
            current_text = format_editor_timestamp(cur_ms, force_hours=show_hours, pad_minutes=False)
            total_text = format_editor_timestamp(tot_ms, force_hours=show_hours, pad_minutes=False)
            scrollbar_text = f"{current_text} / {total_text}"
            if self.timeline_scrollbar.text != scrollbar_text:
                self.timeline_scrollbar.text = scrollbar_text
                self.timeline_scrollbar.update()
        
        obj_flip_color = self.get_event_flip_colors()
        audio_min_ms = self.visual_to_audio_ms(vis_min_ms)
        audio_max_ms = self.visual_to_audio_ms(vis_max_ms)
        
        segments, seg_ends = self.get_direction_segments()
        idx = bisect.bisect_right(seg_ends, audio_min_ms) if seg_ends else 0
        
        for k in range(idx, len(segments)):
            t1, t2, is_r, is_c, _is_inst = segments[k]
            if t1 > audio_max_ms: break
            
            vt1 = self.audio_to_visual_ms(t1) if t1 > 0 else t1
            vt2 = self.audio_to_visual_ms(t2) if t2 > 0 else t2
            if vt2 <= vt1: continue
            
            sx = int(self.ms_to_x(vt1))
            ex = int(self.ms_to_x(vt2))
            w_rect = ex - sx
            if w_rect <= 0: continue
            
            if is_c:
                col = QColor(getattr(self, 'original_object_colors', self.object_colors).get("toggle_center", QColor("purple")))
                arrow_txt = ""
            else:
                orig_colors = getattr(self, 'original_object_colors', self.object_colors)
                right_col = orig_colors.get("direction_right_event", orig_colors.get("direction_right", QColor("blue")))
                left_col = orig_colors.get("direction_left_event", orig_colors.get("direction_left", QColor("yellow")))
                col = QColor(right_col) if is_r else QColor(left_col)
                arrow_txt = ">>>" if is_r else "<<<"
                
            col.setAlpha(150)
            p.setBrush(col)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(sx, int(strip_y), w_rect, int(strip_h))
            
            if arrow_txt:
                p.setPen(QColor("white"))
                spacing = 300
                start_marker = (sx // spacing) * spacing
                if start_marker < sx: start_marker += spacing
                curr_x = start_marker
                while curr_x < ex:
                    if curr_x > 0 and curr_x < w:
                        p.drawText(curr_x, int(strip_y), 50, 20, Qt.AlignmentFlag.AlignCenter, arrow_txt)
                    curr_x += spacing

        note_radius = 20
        hold_end_radius = 12
        screamer_end_radius = 15
        brawl_size = 30

        margin_ms = 2000
        visible_min = self.visual_to_audio_ms(vis_min_ms - margin_ms)
        visible_max = self.visual_to_audio_ms(vis_max_ms + margin_ms)
        
        visible_objects = self.get_objects_in_range(visible_min, visible_max)
        bpm_follow_state = getattr(self, 'bpm_follow_drag_state', None)
        if bpm_follow_state and 'preview_times' in bpm_follow_state:
            visible_set = set(visible_objects)
            preview_times = bpm_follow_state['preview_times']
            start_index = int(np.searchsorted(preview_times, visible_min, side='left'))
            end_index = int(np.searchsorted(preview_times, visible_max, side='right'))
            for obj in bpm_follow_state['objects'][start_index:end_index]:
                if obj not in visible_set:
                    visible_objects.append(obj)
                    visible_set.add(obj)
            if bpm_follow_state['hold_objects']:
                hold_start_times = preview_times[bpm_follow_state['hold_start_indices']]
                hold_mask = (
                    (bpm_follow_state['preview_end_times'] >= visible_min)
                    & (hold_start_times <= visible_max)
                )
                for hold_index in np.flatnonzero(hold_mask):
                    obj = bpm_follow_state['hold_objects'][int(hold_index)]
                    if obj not in visible_set:
                        visible_objects.append(obj)
                        visible_set.add(obj)
        if self.dragging_objects and self.selected_objects:
            visible_set = set(visible_objects)
            sf = getattr(self.editor, 'global_scale', 1.0)
            viewport_width = self.width() / sf
            for obj in self.selected_objects:
                draw_time = self.get_draw_time(obj)
                draw_end_time = self.get_draw_end_time(obj)
                target_time = getattr(obj, '_target_visual_time', draw_time)
                target_end_time = getattr(obj, '_target_visual_end_time', draw_end_time)
                draw_x = self.audio_ms_to_x(draw_time)
                draw_end_x = self.audio_ms_to_x(draw_end_time)
                target_x = self.audio_ms_to_x(target_time)
                target_end_x = self.audio_ms_to_x(target_end_time)
                is_visible = (
                    max(draw_x, draw_end_x) >= -50 and min(draw_x, draw_end_x) <= viewport_width + 50
                    or max(target_x, target_end_x) >= -50 and min(target_x, target_end_x) <= viewport_width + 50
                )
                if is_visible and obj not in visible_set:
                    visible_objects.append(obj)
                    visible_set.add(obj)

        non_events = [o for o in visible_objects if not o.is_event]
        events = [o for o in visible_objects if o.is_event]

        current_time = time.time()
        expired_drag_objects = [
            obj
            for obj, release_time in self.drag_release_times.items()
            if current_time - release_time >= 0.25
        ]
        for obj in expired_drag_objects:
            self.drag_release_times.pop(obj, None)
            self.drag_release_mode.pop(obj, None)
        
        active_dying_objects = []
        for obj, started_at in self.dying_objects:
            if started_at is None:
                started_at = current_time
            if current_time - started_at < 0.2:
                active_dying_objects.append((obj, started_at))
        self.dying_objects = active_dying_objects
        
        visual_list = []
        for o in non_events: visual_list.append((o, "normal"))
        for o in events: visual_list.append((o, "normal"))
        for o, t in self.dying_objects: visual_list.append((o, "dying"))
        
        def sort_key(item):
            obj = item[0]
            if item[1] == "dying": return (False, obj.time)
            return (obj in self.selected_objects, obj.time)

        visual_list.sort(key=sort_key)
        
        lane_upper_y = lane_0_y - LANE_HEIGHT
        lane_lower_y = lane_1_y + LANE_HEIGHT
        
        def get_lane_y(l):
            if l == -1: return lane_upper_y
            if l == 2: return lane_lower_y
            if l == 0: return lane_0_y
            return lane_1_y

        def get_pair_y(l):
            if l == -1: return lane_lower_y
            if l == 2: return lane_upper_y
            if l == 0: return lane_1_y
            return lane_0_y

        current_audio_time = self.visual_to_audio_ms(self.current_time) if self.editor.is_playing else self.current_time
        dying_dict = {o: t for o, t in self.dying_objects}
        batched_shape_path = QPainterPath()
        batched_shape_path.setFillRule(Qt.FillRule.WindingFill)
        batched_shape_count = 0
        batched_shape_key = None
        batched_shape_color = None
        batched_shape_last_x = {}

        def flush_batched_shapes():
            nonlocal batched_shape_path, batched_shape_count, batched_shape_key, batched_shape_color, batched_shape_last_x
            if batched_shape_count:
                previous_opacity = p.opacity()
                p.setOpacity(1.0)
                p.setBrush(QBrush(batched_shape_color))
                p.setPen(QPen(Qt.GlobalColor.white, 2))
                p.drawPath(batched_shape_path)
                p.setOpacity(previous_opacity)
                batched_shape_path = QPainterPath()
                batched_shape_path.setFillRule(Qt.FillRule.WindingFill)
                batched_shape_count = 0
                batched_shape_key = None
                batched_shape_color = None
                batched_shape_last_x = {}

        def begin_batched_shape(key, color, x, y, width):
            nonlocal batched_shape_key, batched_shape_color
            y_key = round(y, 3)
            previous_x = batched_shape_last_x.get(y_key)
            if batched_shape_count and (
                batched_shape_key != key
                or previous_x is not None and abs(x - previous_x) < width
            ):
                flush_batched_shapes()
            batched_shape_key = key
            batched_shape_color = color
            batched_shape_last_x[y_key] = x

        for obj_data in visual_list:
            obj = obj_data[0]
            status = obj_data[1]
            
            anim_scale = 1.0
            anim_alpha = 1.0
            
            if status == "dying":
                pass_time = current_time - dying_dict.get(obj, current_time)
                if pass_time < 0.2: self._anim_running = True
                t_val = pass_time / 0.2
                anim_scale = 1.0 + t_val * 2.0 - t_val * t_val * 3.0
                anim_alpha = 1.0 - t_val
            elif obj.creation_time:
                pass_time = current_time - obj.creation_time
                if pass_time < 0.3:
                     self._anim_running = True
                     t = pass_time / 0.3
                     s = 2.5
                     t = t - 1.0
                     val = t * t * ((s + 1.0) * t + s) + 1.0
                     t_raw = pass_time / 0.3
                     t_val = t_raw - 1
                     val = t_val * t_val * ((s + 1) * t_val + s) + 1
                     anim_scale = 1.4 - 0.4 * val
            
            if obj.last_update_time and current_time - obj.last_update_time < 0.2:
                self._anim_running = True
                pass_time = current_time - obj.last_update_time
                t_val = pass_time / 0.2
                bounce = 0.3 * math.sin(t_val * math.pi)
                anim_scale *= (1.0 + bounce)
            
            drag_head_scale = 1.0
            drag_tail_scale = 1.0
            
            if self.dragging_objects and obj in self.selected_objects:
                if obj in self.drag_start_times:
                    drag_start_time = self.drag_start_times[obj]
                    pass_time = current_time - drag_start_time
                    if pass_time < 0.08:
                        self._anim_running = True
                        t = min(1.0, pass_time / 0.08)
                        target_scale = 1.3
                        drag_scale = 1.0 + (target_scale - 1.0) * t
                    else:
                        drag_scale = 1.3
                    
                    if self.drag_mode == 'resize':
                        drag_tail_scale = drag_scale
                    else:
                        drag_head_scale = drag_scale
                        drag_tail_scale = drag_scale
                else:
                    if self.drag_mode == 'resize':
                        drag_tail_scale = 1.3
                    else:
                        drag_head_scale = 1.3
                        drag_tail_scale = 1.3
            elif obj in self.drag_release_times:
                release_time = self.drag_release_times[obj]
                release_mode = self.drag_release_mode.get(obj, 'move')
                pass_time = current_time - release_time
                if pass_time < 0.25:
                    self._anim_running = True
                    t = pass_time / 0.25
                    s = 3.5
                    t_shifted = t - 1.0
                    ease_val = t_shifted * t_shifted * ((s + 1.0) * t_shifted + s) + 1.0
                    overshoot = -0.2 * math.sin(t * math.pi) * (1.0 - t)
                    drag_scale = 1.3 - 0.3 * ease_val + overshoot
                    
                    if release_mode == 'resize':
                        drag_tail_scale = drag_scale
                    else:
                        drag_head_scale = drag_scale
                        drag_tail_scale = drag_scale
                else:
                    del self.drag_release_times[obj]
                    if obj in self.drag_release_mode:
                        del self.drag_release_mode[obj]
            
            if anim_scale <= 0: continue

            head_scale = anim_scale * drag_head_scale
            tail_scale = anim_scale * drag_tail_scale

            if self.editor.is_playing:
                diff_play = current_audio_time - obj.time
                if 0 <= diff_play <= 250:
                     prog = diff_play / 250.0
                     head_scale *= (1.0 + 0.25 * math.sin(prog * math.pi))
                
                if obj.type == 128 or self.is_custom_length(obj):
                    diff_end = current_audio_time - obj.end_time
                    if 0 <= diff_end <= 250:
                        prog = diff_end / 250.0
                        tail_scale *= (1.0 + 0.25 * math.sin(prog * math.pi))
            
            painter_opacity = p.opacity()
            p.setOpacity(anim_alpha)
            
            x = self.audio_ms_to_x(self.get_draw_time(obj))

            if obj.custom_data is not None:
                flush_batched_shapes()
                is_selected = obj in self.selected_objects
                if self.is_custom_missing(obj):
                    if -70 < x < w + 70:
                        size = 66.0 * head_scale
                        y = self.get_custom_object_y(obj)
                        color = QColor('#FF2D9A')
                        if is_selected:
                            color = color.lighter(135)
                        p.setBrush(color)
                        p.setPen(QPen(QColor('white'), max(2.0, 3.0 * head_scale)))
                        rect = QRectF(x - size / 2, y - size / 2, size, size)
                        p.drawRoundedRect(rect, 7, 7)
                        font = p.font()
                        font.setBold(True)
                        font.setPointSizeF(max(7.0, 9.0 * head_scale))
                        p.setFont(font)
                        p.setPen(QColor('white'))
                        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, 'Missing')
                    p.setOpacity(painter_opacity)
                    continue

                type_data = self.get_custom_type_data(obj)
                y = self.get_custom_object_y(obj)
                color = QColor(type_data.get('color', '#FF4FA3'))
                connection_color = QColor(type_data.get('connection_color', '#B52D73'))
                if is_selected:
                    color = color.lighter(140)
                    connection_color = connection_color.lighter(130)

                head_flash = 0.0
                tail_flash = 0.0
                if self.editor.is_playing:
                    head_diff = current_audio_time - obj.time
                    if 0 <= head_diff <= 300:
                        head_flash = 1.0 - head_diff / 300.0
                    if self.is_custom_length(obj):
                        tail_diff = current_audio_time - obj.end_time
                        if 0 <= tail_diff <= 300:
                            tail_flash = 1.0 - tail_diff / 300.0

                def custom_flash_color(base_color, amount):
                    if amount <= 0:
                        return base_color
                    return QColor(
                        round(base_color.red() + (255 - base_color.red()) * amount),
                        round(base_color.green() + (255 - base_color.green()) * amount),
                        round(base_color.blue() + (255 - base_color.blue()) * amount),
                        base_color.alpha(),
                    )

                head_color = custom_flash_color(color, head_flash)
                tail_color = custom_flash_color(color, tail_flash)

                def draw_custom_shape(cx, cy, scale_value, shape_color):
                    radius = note_radius * scale_value
                    p.setBrush(shape_color)
                    p.setPen(QPen(QColor('white'), max(1.0, 2.0 * scale_value)))
                    shape = type_data.get('shape', 'Circle')
                    if shape == 'Square':
                        half_size = radius * 0.75
                        p.drawRect(QRectF(cx - half_size, cy - half_size, half_size * 2, half_size * 2))
                    elif shape == 'Triangle':
                        half_size = radius * 0.91
                        p.drawPolygon(QPolygonF([
                            QPointF(cx, cy - half_size),
                            QPointF(cx + half_size, cy + half_size),
                            QPointF(cx - half_size, cy + half_size),
                        ]))
                    else:
                        p.drawEllipse(QPointF(cx, cy), radius, radius)

                if type_data.get('kind') == 'Event':
                    if -50 < x < w + 50:
                        event_half = 30.0 * head_scale
                        p.setPen(QPen(head_color, max(2.0, 3.0 * head_scale)))
                        p.drawLine(QPointF(x, y - event_half), QPointF(x, y + event_half))
                        p.setBrush(head_color)
                        p.setPen(Qt.PenStyle.NoPen)
                        p.drawEllipse(QPointF(x, y), 8 * head_scale, 8 * head_scale)
                elif type_data.get('length'):
                    end_x = self.audio_ms_to_x(self.get_draw_end_time(obj))
                    if end_x > -50 and x < w + 50:
                        p.setPen(QPen(connection_color, max(3.0, 6.0 * anim_scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                        p.drawLine(QPointF(x, y), QPointF(end_x, y))
                        draw_custom_shape(x, y, head_scale, head_color)
                        draw_custom_shape(end_x, y, tail_scale, tail_color)
                elif -50 < x < w + 50:
                    draw_custom_shape(x, y, head_scale, head_color)
                p.setOpacity(painter_opacity)
                continue

            can_batch_static_shape = (
                status == "normal"
                and not obj.is_event
                and not obj.is_hold
                and not obj.is_screamer
                and not obj.is_spam
                and not obj.is_brawl_hit
                and not obj.is_brawl_final
                and not obj.is_brawl_hold
                and not obj.is_brawl_spam
                and not obj.is_hide
                and not obj.is_fly_in
                and obj not in self.selected_objects
                and abs(head_scale - 1.0) < 1e-9
                and abs(anim_alpha - 1.0) < 1e-9
                and not (
                    self.editor.is_playing
                    and 0 <= current_audio_time - obj.time <= 500
                )
            )

            if can_batch_static_shape:
                if -50 < x < w + 50:
                    y = self.get_draw_y(obj)
                    if obj.is_spike:
                        color = self.object_colors["spike"]
                        spike_size = note_radius * 1.3
                        begin_batched_shape(("spike", color.rgba()), color, x, y, spike_size * 1.4)
                        if obj.lane <= 0:
                            points = [
                                QPointF(x, y + spike_size),
                                QPointF(x + spike_size * 0.7, y - spike_size * 0.4),
                                QPointF(x - spike_size * 0.7, y - spike_size * 0.4),
                            ]
                        else:
                            points = [
                                QPointF(x, y - spike_size),
                                QPointF(x + spike_size * 0.7, y + spike_size * 0.4),
                                QPointF(x - spike_size * 0.7, y + spike_size * 0.4),
                            ]
                        batched_shape_path.addPolygon(QPolygonF(points))
                        batched_shape_path.closeSubpath()
                    elif obj.is_freestyle:
                        color = self.object_colors["freestyle"]
                        begin_batched_shape(("freestyle", color.rgba()), color, x, center_y, note_radius * 2)
                        batched_shape_path.addEllipse(QPointF(x, center_y), note_radius, note_radius)
                    else:
                        color = self.object_colors["note"]
                        begin_batched_shape(("note", color.rgba()), color, x, y, note_radius * 2)
                        batched_shape_path.addEllipse(QPointF(x, y), note_radius, note_radius)
                    batched_shape_count += 1
                p.setOpacity(painter_opacity)
                continue

            flush_batched_shapes()
            
            if obj.is_event:
                if -50 < x < w + 50:
                    is_selected = obj in self.selected_objects
                    color = self.object_colors.get("direction_right_event", self.object_colors.get("direction_right", QColor("blue")))
                    circle_color = color

                    if obj.is_toggle_center:
                        color = QColor(self.object_colors.get("toggle_center", QColor("purple")))
                        circle_color = obj_flip_color.get(obj.uid, color)
                    elif obj.is_flip or obj.is_instant_flip:
                        color = obj_flip_color.get(obj.uid, color)
                        circle_color = color
                        
                    if is_selected:
                        color = color.lighter(150)
                        circle_color = circle_color.lighter(150)
                    p.setPen(QPen(color, 3 * head_scale))
                    p.drawLine(int(x), int(lane_0_y + (lane_1_y - lane_0_y) * (1 - anim_scale) * 0.5), 
                               int(x), int(lane_1_y - (lane_1_y - lane_0_y) * (1 - anim_scale) * 0.5))
                    
                    if obj.is_instant_flip:
                         p.setBrush(QColor("white"))
                    elif obj.is_toggle_center:
                         if obj.order_index != 0:
                             p.setBrush(circle_color)
                         else:
                             p.setBrush(color)
                    else:
                         p.setBrush(circle_color)

                    p.drawEllipse(QPointF(x, center_y), 8 * head_scale, 8 * head_scale)
                    
                    if self.editor.is_playing:
                         diff = current_audio_time - obj.time
                         if 0 <= diff <= 300:
                             alpha = int(255 * (1.0 - (diff / 300.0)))
                             
                             p.setPen(QPen(QColor(255, 255, 255, alpha), 3))
                             p.drawLine(int(x), int(lane_0_y), int(x), int(lane_1_y))
                             
                             p.setBrush(QColor(255, 255, 255, alpha))
                             p.setPen(Qt.PenStyle.NoPen)
                             p.drawEllipse(QPointF(x, center_y), 8, 8)
                    
                    has_notes_at_time = obj.time in self._fast_note_times
                    if has_notes_at_time:
                        p.setBrush(QColor("white"))
                        p.setPen(Qt.PenStyle.NoPen)
                        if obj.order_index == 0:
                            p.drawEllipse(QPointF(x - 10 * head_scale, center_y), 4 * head_scale, 4 * head_scale)
                        elif obj.order_index == 1:
                            p.drawEllipse(QPointF(x + 10 * head_scale, center_y), 4 * head_scale, 4 * head_scale)
            else:
                y = self.get_draw_y(obj)
                
                splits = []
                if (obj.is_hold or obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam or obj.is_screamer) and obj.lane in [-1, 2]:
                    split_start = bisect.bisect_left(_center_times, obj.time)
                    split_end = bisect.bisect_right(_center_times, obj.end_time)
                    for c in centers[split_start:split_end]:
                        sx = self.audio_ms_to_x(c.time)
                        is_cen = is_in_toggle_center(c.time + 1) if c.time < obj.end_time else is_in_toggle_center(c.time)
                        if obj.lane == -1:
                            sy = (lane_0_y - LANE_HEIGHT) if is_cen else lane_0_y
                            spy = lane_lower_y if is_cen else lane_1_y
                        else:
                            sy = lane_lower_y if is_cen else lane_1_y
                            spy = (lane_0_y - LANE_HEIGHT) if is_cen else lane_0_y
                        splits.append((sx, sy, spy))
                
                is_selected = obj in self.selected_objects
                
                if obj.is_spam:
                    end_x = self.audio_ms_to_x(self.get_draw_end_time(obj))
                    if end_x > x or -50 < x < w + 50:
                        pair_y = self.get_draw_pair_y(obj)
                        p.setPen(QPen(self.object_colors["spam_line"], 4 * head_scale))
                        
                        if splits:
                             curr_x = x
                             curr_y = y
                             curr_py = pair_y
                             for sx, sy, spy in splits:
                                 p.drawLine(int(curr_x), int(curr_y), int(sx), int(curr_y))
                                 p.drawLine(int(curr_x), int(curr_py), int(sx), int(curr_py))
                                 p.drawLine(int(sx), int(curr_y), int(sx), int(sy))
                                 p.drawLine(int(sx), int(curr_py), int(sx), int(spy))
                                 curr_x = sx
                                 curr_y = sy
                                 curr_py = spy
                             p.drawLine(int(curr_x), int(curr_y), int(end_x), int(curr_y))
                             p.drawLine(int(curr_x), int(curr_py), int(end_x), int(curr_py))
                             final_y = curr_y
                             final_pair_y = curr_py
                        else:
                             p.drawLine(int(x), int(y), int(end_x), int(y))
                             p.drawLine(int(x), int(pair_y), int(end_x), int(pair_y))
                             final_y = y
                             final_pair_y = pair_y
                        
                        col_spam_head = self.object_colors["spam"]
                        col_spam_tail = self.object_colors["spam"]
                        
                        is_head_sel = is_selected and not (self.dragging_objects and self.drag_mode == 'resize')
                        is_tail_sel = is_selected

                        if is_head_sel: col_spam_head = col_spam_head.lighter(150)
                        if is_tail_sel: col_spam_tail = col_spam_tail.lighter(150)

                        p.setBrush(QBrush(col_spam_head))
                        pen_col = Qt.GlobalColor.white if not is_head_sel else col_spam_head.lighter(180)
                        p.setPen(QPen(pen_col, 2))
                        
                        p.drawEllipse(QPointF(x, y), note_radius * head_scale, note_radius * head_scale)
                        p.drawEllipse(QPointF(x, pair_y), note_radius * head_scale, note_radius * head_scale)
                        
                        p.setBrush(QBrush(col_spam_tail))
                        pen_col_tail = Qt.GlobalColor.white if not is_tail_sel else col_spam_tail.lighter(180)
                        p.setPen(QPen(pen_col_tail, 2))
                        
                        p.drawEllipse(QPointF(end_x, final_y), hold_end_radius * tail_scale, hold_end_radius * tail_scale)
                        p.drawEllipse(QPointF(end_x, final_pair_y), hold_end_radius * tail_scale, hold_end_radius * tail_scale)

                elif obj.is_screamer:
                    end_x = self.audio_ms_to_x(self.get_draw_end_time(obj))
                    other_y = self.get_draw_pair_y(obj)
                    
                    if -50 < x < w + 50 or end_x > -50:
                         
                         final_tail_y = other_y
                         if splits:
                             final_tail_y = splits[-1][2]
                         
                         p.setPen(QPen(self.object_colors["double_line"], 4 * head_scale))
                         p.drawLine(int(x), int(y), int(end_x), int(final_tail_y))
                         
                         col_screamer_head = self.object_colors["double"]
                         col_screamer_tail = self.object_colors["double"]
                         
                         is_head_sel = is_selected and not (self.dragging_objects and self.drag_mode == 'resize')
                         is_tail_sel = is_selected
                         
                         if is_head_sel: col_screamer_head = col_screamer_head.lighter(150)
                         if is_tail_sel: col_screamer_tail = col_screamer_tail.lighter(150)

                         p.setBrush(QBrush(col_screamer_head))
                         p.setPen(QPen(Qt.GlobalColor.white if not is_head_sel else col_screamer_head.lighter(180), 2))
                         p.drawEllipse(QPointF(x, y), note_radius * head_scale, note_radius * head_scale)
                         
                         p.setBrush(QBrush(col_screamer_tail))
                         p.setPen(QPen(Qt.GlobalColor.white if not is_tail_sel else col_screamer_tail.lighter(180), 2))
                         p.drawEllipse(QPointF(end_x, final_tail_y), screamer_end_radius * tail_scale, screamer_end_radius * tail_scale)

                elif obj.is_hold:
                    end_x = self.audio_ms_to_x(self.get_draw_end_time(obj))
                    if end_x > x:
                        p.setPen(QPen(self.object_colors["hold_line"], 4 * head_scale))
                        
                        if splits:
                            curr_x = x
                            curr_y = y
                            for sx, sy, spy in splits:
                                p.drawLine(int(curr_x), int(curr_y), int(sx), int(curr_y))
                                p.drawLine(int(sx), int(curr_y), int(sx), int(sy))
                                curr_x = sx
                                curr_y = sy
                            p.drawLine(int(curr_x), int(curr_y), int(end_x), int(curr_y))
                            final_y = curr_y
                        else:
                            p.drawLine(int(x), int(y), int(end_x), int(y))
                            final_y = y
                        
                        col_hold = self.object_colors["hold"]
                        is_tail_sel = is_selected
                        if is_tail_sel: col_hold = col_hold.lighter(150)

                        p.setBrush(QBrush(col_hold))
                        p.setPen(QPen(Qt.GlobalColor.white if not is_tail_sel else col_hold.lighter(180), 2))
                        p.drawEllipse(QPointF(end_x, final_y), hold_end_radius * tail_scale, hold_end_radius * tail_scale)

                elif obj.is_brawl_hold or obj.is_brawl_spam:
                    end_x = self.audio_ms_to_x(self.get_draw_end_time(obj))
                    if end_x > x:
                        col_key = "brawl_hold" if obj.is_brawl_hold else "brawl_spam"
                        line_col_key = "brawl_hold_line" if obj.is_brawl_hold else "brawl_spam_line"
                        line_col = self.object_colors.get(line_col_key, self.object_colors[col_key])
                        
                        draw_lanes_start = [y]
                        
                        p.setPen(QPen(line_col, 4 * head_scale))
                        
                        if splits:
                            curr_x = x
                            curr_y = y
                            for sx, sy, spy in splits:
                                p.drawLine(int(curr_x), int(curr_y), int(sx), int(curr_y))
                                p.drawLine(int(sx), int(curr_y), int(sx), int(sy))
                                curr_x = sx
                                curr_y = sy
                            p.drawLine(int(curr_x), int(curr_y), int(end_x), int(curr_y))
                            final_draw_lanes_end = [curr_y]
                        else:
                            p.drawLine(int(x), int(y), int(end_x), int(y))
                            final_draw_lanes_end = [y]
                        
                        col_base_head = self.object_colors[col_key]
                        col = col_base_head
                        col_tail = col_base_head
                        
                        is_head_sel = is_selected and not (self.dragging_objects and self.drag_mode == 'resize')
                        is_tail_sel = is_selected
                        if is_head_sel: col = col.lighter(150)
                        if is_tail_sel: col_tail = col_tail.lighter(150)
                                
                        p.setBrush(QBrush(col))
                        p.setPen(QPen(Qt.GlobalColor.white, 2))
                        
                        head_size = brawl_size
                        tail_size = brawl_size * 0.7
                        s = head_size * head_scale
                        rect = QRectF(x - s/2, y - s/2, s, s)
                        p.drawRect(rect)
                        
                        tail_col = col_tail
                        if obj.is_brawl_hold_knockout or obj.is_brawl_spam_knockout:
                             base_tail = self.object_colors.get("brawl_knockout", Qt.GlobalColor.black)
                             tail_col = QColor(base_tail)
                             if is_selected: tail_col = QColor(60, 60, 60)
                        
                        p.setBrush(QBrush(tail_col))
                        
                        for ly in final_draw_lanes_end:
                            s = tail_size * tail_scale
                            rect_end = QRectF(end_x - s/2, ly - s/2, s, s)
                            p.drawRect(rect_end)
                        
                        p.setPen(QPen(Qt.GlobalColor.white))
                        font = p.font()
                        font.setBold(True)
                        font.setPixelSize(max(1, int(16 * head_scale)))
                        p.setFont(font)
                        cop_num = obj.brawl_cop_number
                        for ly in draw_lanes_start:
                            s = head_size * head_scale
                            rect = QRectF(x - s/2, ly - s/2, s, s)
                            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(cop_num))
                
                if not obj.is_screamer and not obj.is_spam and not obj.is_brawl_hold and not obj.is_brawl_spam:
                    if -50 < x < w + 50 or (obj.is_hold and self.audio_ms_to_x(obj.end_time) > -50):
                        if obj.is_freestyle:
                            color = QColor(self.object_colors["freestyle"])
                            if is_selected: 
                                color = color.lighter(150)
                                h_c, s_c, v_c, a_c = color.getHsv()
                                color.setHsv(h_c, max(0, int(s_c * 0.5)), v_c, a_c)
                            p.setBrush(QBrush(color))
                            p.setPen(QPen(Qt.GlobalColor.white, 2))
                            p.drawEllipse(QPointF(x, center_y), note_radius * head_scale, note_radius * head_scale)
                            if obj.is_hide:
                                p.setBrush(QBrush(QColor("black") if not is_selected else QColor(80, 80, 80)))
                                p.setPen(Qt.PenStyle.NoPen)
                                p.drawEllipse(QPointF(x, center_y), 6 * head_scale, 6 * head_scale)
                        elif obj.is_brawl_hit:
                            color = self.object_colors["brawl_hit"]
                            if is_selected: color = color.lighter(150)
                            p.setBrush(QBrush(color))
                            p.setPen(QPen(Qt.GlobalColor.white, 2))
                            s = brawl_size * head_scale
                            rect = QRectF(x - s/2, y - s/2, s, s)
                            p.drawRect(rect)
                            p.setPen(QPen(Qt.GlobalColor.white))
                            font = p.font()
                            font.setBold(True)
                            font.setPixelSize(max(1, int(16 * head_scale)))
                            p.setFont(font)
                            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(obj.brawl_cop_number))
                        
                        elif obj.is_brawl_final:
                            color = self.object_colors["brawl_knockout"]
                            if is_selected: color = QColor(60, 60, 60)
                            p.setBrush(QBrush(color))
                            p.setPen(QPen(Qt.GlobalColor.white, 2))
                            s = brawl_size * head_scale
                            rect = QRectF(x - s/2, y - s/2, s, s)
                            p.drawRect(rect)
                            p.setPen(QPen(Qt.GlobalColor.white))
                            font = p.font()
                            font.setBold(True)
                            font.setPixelSize(max(1, int(16 * anim_scale)))
                            p.setFont(font)
                            
                            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(obj.brawl_cop_number))
                        
                        elif obj.is_spike:
                            color = self.object_colors["spike"]
                            if is_selected: color = color.lighter(150)
                            p.setBrush(QBrush(color))
                            p.setPen(QPen(Qt.GlobalColor.white, 2))
                            
                            spike_size = note_radius * head_scale * 1.3
                            if obj.lane <= 0: 
                                points = [
                                    QPointF(x, y + spike_size),
                                    QPointF(x + spike_size * 0.7, y - spike_size * 0.4),
                                    QPointF(x - spike_size * 0.7, y - spike_size * 0.4)
                                ]
                            else: 
                                points = [
                                    QPointF(x, y - spike_size),
                                    QPointF(x + spike_size * 0.7, y + spike_size * 0.4),
                                    QPointF(x - spike_size * 0.7, y + spike_size * 0.4)
                                ]
                            p.drawPolygon(points)
                            
                        elif not obj.is_freestyle:
                            color = self.object_colors["note"]
                            if obj.is_hold:
                                color = self.object_colors["hold"]
                            
                            if is_selected and not (self.dragging_objects and self.drag_mode == 'resize'):
                                color = color.lighter(150)
                                
                            p.setBrush(QBrush(color))
                            p.setPen(QPen(Qt.GlobalColor.white, 2))
                            p.drawEllipse(QPointF(x, y), note_radius * head_scale, note_radius * head_scale)
                        
                        if obj.is_hide and not obj.is_freestyle and not obj.is_brawl_hit and not obj.is_brawl_final:
                            p.setBrush(QBrush(QColor("black") if not is_selected else QColor(80, 80, 80)))
                            p.setPen(Qt.PenStyle.NoPen)
                            p.drawEllipse(QPointF(x, y), 6 * head_scale, 6 * head_scale)
                        
                        if obj.is_fly_in:
                            p.setBrush(QBrush(self.object_colors["fly_in_marker"]))
                            p.setPen(Qt.PenStyle.NoPen)
                            p.drawEllipse(QPointF(x, y), 6 * head_scale, 6 * head_scale)
                        
                if self.editor.is_playing:
                     diff = self.visual_to_audio_ms(self.current_time) - obj.time
                     if 0 <= diff <= 500: 
                        alpha = int(255 * (1.0 - (diff / 500.0)))
                        p.setBrush(QColor(255, 255, 255, alpha))
                        p.setPen(Qt.PenStyle.NoPen)
                        
                        if obj.is_brawl_hit or obj.is_brawl_final:
                            s = brawl_size * head_scale
                            rect = QRectF(x - s/2, y - s/2, s, s)
                            p.drawRect(rect)
                        elif obj.is_brawl_hold or obj.is_brawl_spam:
                            draw_lanes = [get_lane_y(obj.lane)]
                            if obj.is_brawl_spam:
                                if obj.lane == 2: draw_lanes = [lane_lower_y]
                                elif obj.lane == 1: draw_lanes = [lane_1_y]
                                else: draw_lanes = [get_lane_y(obj.lane)]
                            
                            for ly in draw_lanes:
                                s = brawl_size * head_scale
                                rect = QRectF(x - s/2, ly - s/2, s, s)
                                p.drawRect(rect)
                        elif obj.is_spike:
                            spike_size = note_radius * 1.3 * head_scale
                            if obj.lane <= 0: 
                                points = [QPointF(x, y + spike_size), QPointF(x + spike_size * 0.7, y - spike_size * 0.4), QPointF(x - spike_size * 0.7, y - spike_size * 0.4)]
                            else: 
                                points = [QPointF(x, y - spike_size), QPointF(x + spike_size * 0.7, y + spike_size * 0.4), QPointF(x - spike_size * 0.7, y + spike_size * 0.4)]
                            p.drawPolygon(points)
                        elif obj.is_screamer:
                            p.drawEllipse(QPointF(x, y), note_radius * head_scale, note_radius * head_scale)
                        elif obj.is_spam:
                            p.drawEllipse(QPointF(x, y), note_radius * head_scale, note_radius * head_scale)
                            pair_y = self.get_draw_pair_y(obj)
                            p.drawEllipse(QPointF(x, pair_y), note_radius * head_scale, note_radius * head_scale)
                        elif obj.is_freestyle:
                            p.drawEllipse(QPointF(x, center_y), note_radius * head_scale, note_radius * head_scale)
                        else:
                            p.drawEllipse(QPointF(x, y), note_radius * head_scale, note_radius * head_scale)
                     
                     if obj.type == 128:
                        diff_end = self.visual_to_audio_ms(self.current_time) - obj.end_time
                        if 0 <= diff_end <= 500:
                             alpha_end = int(255 * (1.0 - (diff_end / 500.0)))
                             end_x = int(self.audio_ms_to_x(self.get_draw_end_time(obj)))
                             
                             p.setBrush(QColor(255, 255, 255, alpha_end))
                             p.setPen(Qt.PenStyle.NoPen)
                             
                             if obj.is_brawl_hold or obj.is_brawl_spam:
                                  draw_lanes = [get_lane_y(obj.lane)]
                                  if obj.is_brawl_spam:
                                        if obj.lane == 2: draw_lanes = [lane_lower_y]
                                        elif obj.lane == 1: draw_lanes = [lane_1_y]
                                        else: draw_lanes = [get_lane_y(obj.lane)]
                                  
                                  draw_lanes_end = draw_lanes
                                  if splits:
                                      draw_lanes_end = [splits[-1][1]]
                                  
                                  tail_size = brawl_size * 0.7 * tail_scale
                                  for ly in draw_lanes_end:
                                      rect = QRectF(end_x - tail_size/2, ly - tail_size/2, tail_size, tail_size)
                                      p.drawRect(rect)
                             elif obj.is_spam:
                                 target_y = splits[-1][1] if splits else y
                                 target_pair_y = splits[-1][2] if splits else self.get_draw_pair_y(obj)
                                 
                                 p.drawEllipse(QPointF(end_x, target_y), hold_end_radius * tail_scale, hold_end_radius * tail_scale)
                                 p.drawEllipse(QPointF(end_x, target_pair_y), hold_end_radius * tail_scale, hold_end_radius * tail_scale)
                             elif obj.is_screamer:
                                 other_y = self.get_draw_pair_y(obj)
                                 target_y = splits[-1][2] if splits else other_y
                                 p.drawEllipse(QPointF(end_x, target_y), screamer_end_radius * tail_scale, screamer_end_radius * tail_scale)
                             else:
                                 target_y = splits[-1][1] if splits else y
                                 p.drawEllipse(QPointF(end_x, target_y), hold_end_radius * tail_scale, hold_end_radius * tail_scale)

            p.setOpacity(painter_opacity)

        flush_batched_shapes()
        
        if self.selection_active_visible:
            min_x, max_x = float('inf'), float('-inf')
            min_y, max_y = float('inf'), float('-inf')
            found = False
            
            if self.selected_objects:
                for obj in self.selected_objects:
                    ms_start = self.get_draw_time(obj)
                    x_start = self.audio_ms_to_x(ms_start)
                    
                    found = True
                    min_x = min(min_x, x_start - 30)
                    max_x = max(max_x, x_start + 30)
                    
                    if obj.custom_data is not None:
                         y = self.get_custom_object_y(obj)
                         min_y = min(min_y, y - 30)
                         max_y = max(max_y, y + 30)
                    elif obj.is_event or obj.is_freestyle:
                         if obj.is_event:
                             min_y = min(min_y, lane_0_y - 20)
                             max_y = max(max_y, lane_1_y + 20)
                         else:
                             center_y = (lane_0_y + lane_1_y) / 2
                             min_y = min(min_y, center_y - 30)
                             max_y = max(max_y, center_y + 30)
                    else:
                         y = self.get_draw_y(obj)
                         min_y = min(min_y, y - 30)
                         max_y = max(max_y, y + 30)
                         
                         if obj.is_spam or obj.is_screamer:
                              pair_y = self.get_draw_pair_y(obj)
                              min_y = min(min_y, pair_y - 30)
                              max_y = max(max_y, pair_y + 30)
                         
                         if obj.is_brawl_hold or obj.is_brawl_spam:
                              if obj.is_brawl_spam:
                                   if obj.lane == 2: draw_lanes = [lane_lower_y]
                                   elif obj.lane == 1: draw_lanes = [lane_1_y]
                                   else: draw_lanes = [get_lane_y(obj.lane)]
                              else:
                                   draw_lanes = [get_lane_y(obj.lane)]
                              for ly in draw_lanes:
                                   min_y = min(min_y, ly - 35)
                                   max_y = max(max_y, ly + 35)

                    if obj.type == 128 or self.is_custom_length(obj):
                         x_end = self.audio_ms_to_x(self.get_draw_end_time(obj))
                         max_x = max(max_x, x_end + 30)
                         if obj.custom_data is None and obj.lane in [-1, 2]:
                             if any(obj.time <= c.time <= obj.end_time for c in centers):
                                 if obj.lane == -1:
                                     min_y = min(min_y, lane_upper_y - 30)
                                     max_y = max(max_y, lane_0_y + 30)
                                 elif obj.lane == 2:
                                     min_y = min(min_y, lane_1_y - 30)
                                     max_y = max(max_y, lane_lower_y + 30)

            if found and len(self.selected_objects) >= 2:
                 t_start_ms = self.x_to_ms(min_x)
                 t_end_ms = self.x_to_ms(max_x)
                 
                 self.selection_target_bounds = [t_start_ms, t_end_ms, min_y, max_y]

            final_rect = None
            
            if self.selection_active_visible:
                 if self.selection_current_bounds:
                      c_start = self.selection_current_bounds[0]
                      c_end = self.selection_current_bounds[1]
                      c_min_y = self.selection_current_bounds[2]
                      c_max_y = self.selection_current_bounds[3]
                      
                      c_min_x = self.ms_to_x(c_start)
                      c_max_x = self.ms_to_x(c_end)
                      
                      final_rect = QRectF(c_min_x, c_min_y, c_max_x - c_min_x, c_max_y - c_min_y)
                      self.selection_last_drawn_rect = final_rect
                 elif self.selection_last_drawn_rect:
                      final_rect = self.selection_last_drawn_rect
            
            if final_rect and self.selection_active_visible:
                t_val = 0.0
                state = self.selection_anim_state
                elapsed = time.time() - self.selection_anim_time
                
                scale = 1.0
                alpha = 1.0
                
                if state == "in":
                    if elapsed < 0.2:
                        t = elapsed / 0.2
                        s = 1.70158
                        t = t - 1
                        val = t*t*((s+1)*t + s) + 1
                        scale = 0.7 + 0.3 * val
                        alpha = elapsed / 0.2
                    else:
                        scale = 1.0
                        alpha = 1.0
                elif state == "out":
                    if elapsed < 0.15:
                        t_out = elapsed / 0.15
                        scale = 1.0 - 0.05 * t_out
                        alpha = 1.0 - t_out
                    else:
                        scale = 0.95
                        alpha = 0.0

                center = final_rect.center()
                curr_w = final_rect.width() * scale
                curr_h = final_rect.height() * scale
                
                rect = QRectF(center.x() - curr_w/2, center.y() - curr_h/2, curr_w, curr_h)
                
                col = QColor(UI_THEME["accent"])
                if alpha > 1: alpha = 1
                if alpha < 0: alpha = 0
                col.setAlphaF(alpha)
                
                if alpha > 0:
                    p.setPen(QPen(col, 2, Qt.PenStyle.SolidLine))
                    p.setBrush(Qt.GlobalColor.transparent)
                    p.drawRoundedRect(rect, 15, 15)

        if self.selection_rect:
            p.setBrush(QBrush(self.col_selection))
            p.setPen(QPen(self.col_selection_border, 2))
            p.drawRoundedRect(self.selection_rect, 5.0, 5.0)

        if hasattr(self, 'flashing_blocked_objects'):
            current_time = time.time()
            self.flashing_blocked_objects = [(o, t) for o, t in self.flashing_blocked_objects if current_time - t < 0.5]
            
            if self.flashing_blocked_objects:
                for obj, t in self.flashing_blocked_objects:
                    pass_time = current_time - t
                    alpha = max(0, 1.0 - (pass_time / 0.5))
                    p.setOpacity(alpha)
                    
                    x = self.audio_ms_to_x(obj.time)
                    if obj.is_freestyle or obj.is_event:
                        sf = getattr(self.editor, 'global_scale', 1.0)
                        y1 = (self.height() / sf) / 2
                    else:
                        y1 = self.get_draw_y(obj)
                    
                    if obj.is_hold or obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam or obj.is_screamer:
                        end_x = self.audio_ms_to_x(self.get_draw_end_time(obj))
                    else:
                        end_x = x
                    
                    if obj.is_screamer or obj.is_spam:
                        y2 = self.get_draw_pair_y(obj)
                    else:
                        y2 = y1
                        
                    min_y = min(y1, y2) - 35
                    max_y = max(y1, y2) + 35
                    min_x = x - 35
                    max_x = end_x + 35
                    
                    rect = QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
                    p.setBrush(QColor(255, 50, 50, 100))
                    p.setPen(QPen(QColor(255, 0, 0, 200), 3))
                    p.drawRoundedRect(rect, 35, 35)
                
                p.setOpacity(1.0)
                self.update()

        p.setOpacity(1.0)
        gp_lane_lower = h / 2 + LANE_HEIGHT / 2 + LANE_HEIGHT
        gp_top = gp_lane_lower + 50 + 20
        gp_bottom = h
        gp_height = gp_bottom - gp_top
        gp_width = w
        gp_x = 0

        self.game_preview_rect = QRectF(gp_x, gp_top, gp_width, gp_height)

        preview_font = p.font()
        preview_font.setPixelSize(22)
        preview_font.setBold(True)
        p.setFont(preview_font)
        preview_text_col = QColor(UI_THEME["accent"])
        preview_text_col.setAlpha(120)
        p.setPen(preview_text_col)
        gp_pad = 10
        p.drawText(QRectF(gp_x + gp_pad, gp_top + gp_pad-5, 200, 30), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, "PREVIEW")

        gp_center_x = gp_x + gp_width / 2
        gp_line_offset = 80

        gp_left_line_x = gp_center_x - gp_line_offset
        gp_right_line_x = gp_center_x + gp_line_offset
        gp_left_zone = gp_left_line_x - gp_x
        gp_right_zone = (gp_x + gp_width) - gp_right_line_x

        gp_center_y = gp_top + gp_height / 2
        gp_lane_spacing = gp_height * 0.25
        gp_lane_top_y = gp_center_y - gp_lane_spacing
        gp_lane_bot_y = gp_center_y + gp_lane_spacing

        if self.beatmap and self.beatmap.metadata.BPM > 0:
            p.save()
            p.setClipRect(self.game_preview_rect)

            current_visual_ms = self.current_time
            current_audio_ms = self.visual_to_audio_ms(current_visual_ms)
            tps = self.get_sorted_timing_points()

            base_bpm = self.beatmap.metadata.BPM if self.beatmap else 120
            if base_bpm <= 0: base_bpm = 120

            beat_ms = 60000.0 / base_bpm
            lookahead_beats = 4.0
            lookahead_visual_ms = beat_ms * lookahead_beats
            vis_end_ms = current_visual_ms + lookahead_visual_ms

            seg_boundaries = getattr(self, '_cached_seg_boundaries', [])
            if not seg_boundaries:
                seg_boundaries = [self.beatmap.metadata.Offset]

            for seg_idx in range(len(seg_boundaries)):
                seg_offset = seg_boundaries[seg_idx]
                seg_end = seg_boundaries[seg_idx + 1] if seg_idx + 1 < len(seg_boundaries) else vis_end_ms + 60000

                if seg_end < current_visual_ms:
                    continue
                if seg_offset > vis_end_ms:
                    break

                draw_start = max(current_visual_ms, seg_offset)
                draw_end = min(seg_end, vis_end_ms)

                current_beat = max(0, int((draw_start - seg_offset) / beat_ms))
                t = current_beat * beat_ms + seg_offset

                preview_grid_lines = []
                while t <= draw_end:
                    vt_until = t - current_visual_ms
                    if 0 <= vt_until <= lookahead_visual_ms:
                        progress = vt_until / lookahead_visual_ms

                        left_x = gp_left_line_x - progress * gp_left_zone
                        right_x = gp_right_line_x + progress * gp_right_zone
                        preview_grid_lines.append(QLineF(left_x, gp_top, left_x, gp_bottom))
                        preview_grid_lines.append(QLineF(right_x, gp_top, right_x, gp_bottom))

                    t += beat_ms

                if preview_grid_lines:
                    preview_grid_gradient = QLinearGradient(gp_x, 0, gp_x + gp_width, 0)
                    preview_grid_gradient.setColorAt(0.0, QColor(255, 255, 255, 32))
                    preview_grid_gradient.setColorAt((gp_left_line_x - gp_x) / gp_width, QColor(255, 255, 255, 80))
                    preview_grid_gradient.setColorAt((gp_right_line_x - gp_x) / gp_width, QColor(255, 255, 255, 80))
                    preview_grid_gradient.setColorAt(1.0, QColor(255, 255, 255, 32))
                    p.setPen(QPen(QBrush(preview_grid_gradient), 1))
                    p.drawLines(preview_grid_lines)

                def gp_get_direction_at(ms, lane=0, is_freestyle=False, obj=None):
                    if not self._live_event_cache_active and obj is not None and hasattr(self, '_cached_obj_dir') and obj.uid in self._cached_obj_dir:
                        return self._cached_obj_dir[obj.uid]
                    if self._live_event_cache_active and obj is not None:
                        phase_state = self._live_note_phase_states.get(obj.time)
                        if phase_state is not None:
                            phase_right, phase_centered = phase_state
                            if phase_centered and not is_freestyle:
                                if lane in [0, 1]:
                                    return True
                                if lane in [-1, 2]:
                                    return False
                            return phase_right
                        if is_freestyle:
                            pre_state = self._live_note_pre_states.get(obj.time)
                            if pre_state is not None:
                                return pre_state
                    index = bisect.bisect_right(seg_ends, ms)
                    if index >= len(segments):
                        return True
                    t1, _t2, is_r, is_c, _is_inst = segments[index]
                    if ms == t1 and not is_c and index > 0 and segments[index - 1][3]:
                        is_c = True
                        is_r = segments[index - 1][2]
                    if is_c and not is_freestyle:
                        if lane in [0, 1]:
                            return True
                        if lane in [-1, 2]:
                            return False
                    return is_r

                def get_flash_alpha(time_until):
                    if time_until < 0 and getattr(self.editor, 'is_playing', False):
                        hit_diff = -time_until
                        if 0 <= hit_diff <= 300:
                            return int(255 * (1.0 - (hit_diff / 300.0)))
                    return 0

                def gp_note_x(note_visual, is_right):
                    time_until = note_visual - current_visual_ms
                    if time_until < 0:
                        time_until = 0
                    progress = time_until / lookahead_visual_ms
                    if is_right:
                        return gp_right_line_x + progress * gp_right_zone
                    else:
                        return gp_left_line_x - progress * gp_left_zone

                def gp_lane_y(lane, is_freestyle=False):
                    if is_freestyle:
                        return gp_center_y
                    if lane in [0, -1]:
                        return gp_lane_top_y
                    return gp_lane_bot_y

                def gp_dynamic_y(lane, is_freestyle, time_until, is_fly_in):
                    base_y = gp_lane_y(lane, is_freestyle)
                    if not is_fly_in or is_freestyle or time_until <= 0:
                        return base_y
                    progress = min(1.0, time_until / lookahead_visual_ms)
                    if lane in [0, -1]:
                        start_y = gp_center_y - 10
                        return base_y + (start_y - base_y) * progress
                    else:
                        start_y = gp_center_y + 10
                        return base_y + (start_y - base_y) * progress

                note_radius = 20
                gp_min = current_audio_ms - 500
                gp_visible_audio_max = self.visual_to_audio_ms(current_visual_ms + lookahead_visual_ms)
                gp_max = self.visual_to_audio_ms(current_visual_ms + lookahead_visual_ms + 500)
                gp_subset = self.get_objects_in_range(gp_min, gp_max)
                visible_notes = [o for o in gp_subset if not o.is_event and not self.is_custom_missing(o)]

                gp_current_time = time.time()
                gp_frame_time = time.perf_counter()
                gp_frame_dt = min(0.05, max(0.0, gp_frame_time - self.gp_visual_last_frame))
                self.gp_visual_last_frame = gp_frame_time
                gp_lerp_alpha = 1.0 - math.pow(0.75, gp_frame_dt * 60.0)
                gp_dying = [(o, t) for o, t in self.dying_objects if not o.is_event]
                gp_dying_times = {o: t for o, t in gp_dying}

                gp_visual_list = []
                for o in visible_notes:
                    gp_visual_list.append((o, "normal"))
                for o, t in gp_dying:
                    gp_visual_list.append((o, "dying"))

                gp_active_keys = set()
                for obj, gp_status in gp_visual_list:
                    obj_end = obj.end_time if obj.type == 128 or self.is_custom_length(obj) else obj.time
                    if gp_status != "dying":
                        if obj_end < current_audio_ms - 200:
                            continue
                        if obj.time > gp_visible_audio_max:
                            continue

                    gp_anim_scale = 1.0
                    gp_anim_alpha = 1.0

                    if gp_status == "dying":
                        die_time = gp_dying_times.get(obj)
                        if die_time is None:
                            continue
                        pass_t = gp_current_time - die_time
                        t_val = min(1.0, pass_t / 0.2)
                        gp_anim_scale = 1.0 + t_val * 0.5
                        gp_anim_alpha = 1.0 - t_val
                    else:
                        if obj.creation_time:
                            pass_t = gp_current_time - obj.creation_time
                            if pass_t < 0.3:
                                self._anim_running = True
                                s = 2.5
                                t_raw = pass_t / 0.3
                                t_val = t_raw - 1
                                val = t_val * t_val * ((s + 1) * t_val + s) + 1
                                gp_anim_scale = 1.4 - 0.4 * val

                        if obj.last_update_time and gp_current_time - obj.last_update_time < 0.2:
                            pass_t = gp_current_time - obj.last_update_time
                            t_val = pass_t / 0.2
                            bounce = 0.3 * math.sin(t_val * math.pi)
                            gp_anim_scale *= (1.0 + bounce)

                    scale = gp_anim_scale
                    alpha_factor = gp_anim_alpha
                    elapsed_since_end = current_audio_ms - obj_end
                    if gp_status != "dying" and elapsed_since_end > 0:
                        progress_out = min(1.0, elapsed_since_end / 100.0)
                        scale *= 1.0 + progress_out * 0.5
                        alpha_factor *= 1.0 - progress_out

                    time_until_start = obj.time - current_audio_ms
                    if obj.is_hide and gp_status != "dying":
                        if 0 <= time_until_start < 250:
                            hide_alpha = max(0.0, (time_until_start - 50) / 200.0)
                            alpha_factor *= hide_alpha
                    
                    if alpha_factor <= 0:
                        continue
                        
                    rad = note_radius * scale
                    p.setOpacity(alpha_factor)

                    obj_id = obj.uid
                    gp_active_keys.add(obj_id)
                    if obj_id in self.gp_visual_times:
                        prev_vt = self.gp_visual_times[obj_id]
                        self.gp_visual_times[obj_id] = prev_vt + (obj.time - prev_vt) * gp_lerp_alpha
                    else:
                        self.gp_visual_times[obj_id] = float(obj.time)
                    visual_time = self.gp_visual_times[obj_id]
                    vt_visual = self.audio_to_visual_ms(visual_time)
                    vt_until_start = vt_visual - current_visual_ms

                    visual_end = obj.end_time
                    ve_visual = vt_visual
                    if obj.type == 128 or self.is_custom_length(obj):
                        vt_end_key = str(obj_id) + "_e"
                        gp_active_keys.add(vt_end_key)
                        if vt_end_key in self.gp_visual_times:
                            prev_ve = self.gp_visual_times[vt_end_key]
                            self.gp_visual_times[vt_end_key] = prev_ve + (obj.end_time - prev_ve) * gp_lerp_alpha
                        else:
                            self.gp_visual_times[vt_end_key] = float(obj.end_time)
                        visual_end = self.gp_visual_times[vt_end_key]
                        ve_visual = self.audio_to_visual_ms(visual_end)

                    lane = self.get_effective_lane(obj)
                    is_right = gp_get_direction_at(visual_time, lane, obj.is_freestyle, obj=obj)
                    target_ny = gp_center_y if obj.custom_data is not None and lane == -2 else gp_dynamic_y(lane, obj.is_freestyle, vt_until_start, obj.is_fly_in)

                    vy_key = str(obj_id) + "_y"
                    gp_active_keys.add(vy_key)
                    if vy_key in self.gp_visual_times:
                        prev_ny = self.gp_visual_times[vy_key]
                        if obj.is_fly_in and self.editor.is_playing:
                            self.gp_visual_times[vy_key] = target_ny
                        else:
                            self.gp_visual_times[vy_key] = prev_ny + (target_ny - prev_ny) * gp_lerp_alpha
                    else:
                        self.gp_visual_times[vy_key] = target_ny
                    ny = self.gp_visual_times[vy_key]

                    custom_type = self.get_custom_type_data(obj)
                    if custom_type is not None:
                        time_until_start = visual_time - current_audio_ms
                        time_until_end = visual_end - current_audio_ms
                        start_x = gp_note_x(vt_visual, is_right) if time_until_start > 0 else (gp_right_line_x if is_right else gp_left_line_x)
                        end_x = gp_note_x(ve_visual, is_right)
                        custom_color = QColor(custom_type.get('color', '#FF4FA3'))
                        connection_color = QColor(custom_type.get('connection_color', '#B52D73'))
                        head_flash = get_flash_alpha(time_until_start) / 255.0
                        tail_flash = get_flash_alpha(time_until_end) / 255.0

                        def gp_custom_flash_color(base_color, amount):
                            if amount <= 0:
                                return base_color
                            return QColor(
                                round(base_color.red() + (255 - base_color.red()) * amount),
                                round(base_color.green() + (255 - base_color.green()) * amount),
                                round(base_color.blue() + (255 - base_color.blue()) * amount),
                                base_color.alpha(),
                            )

                        head_color = gp_custom_flash_color(custom_color, head_flash)
                        tail_color = gp_custom_flash_color(custom_color, tail_flash)

                        def draw_gp_custom_shape(cx, cy, radius, shape_color):
                            p.setPen(QPen(QColor(255, 255, 255, 200), 2))
                            p.setBrush(shape_color)
                            shape = custom_type.get('shape', 'Circle')
                            if shape == 'Square':
                                half_size = radius * 0.75
                                p.drawRect(QRectF(cx - half_size, cy - half_size, half_size * 2, half_size * 2))
                            elif shape == 'Triangle':
                                half_size = radius * 0.91
                                p.drawPolygon(QPolygonF([
                                    QPointF(cx, cy - half_size),
                                    QPointF(cx + half_size, cy + half_size),
                                    QPointF(cx - half_size, cy + half_size),
                                ]))
                            else:
                                p.drawEllipse(QPointF(cx, cy), radius, radius)

                        if custom_type.get('length'):
                            if time_until_end > 0:
                                p.setPen(QPen(connection_color, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                                p.drawLine(QPointF(start_x, ny), QPointF(end_x, ny))
                                draw_gp_custom_shape(start_x, ny, rad, head_color)
                                draw_gp_custom_shape(end_x, ny, rad * 0.8, tail_color)
                            else:
                                draw_gp_custom_shape(end_x, ny, rad * 0.8, tail_color)
                        elif custom_type.get('kind') == 'Event':
                            p.setPen(QPen(head_color, 3))
                            p.drawLine(QPointF(start_x, ny - rad), QPointF(start_x, ny + rad))
                            p.setBrush(head_color)
                            p.setPen(Qt.PenStyle.NoPen)
                            p.drawEllipse(QPointF(start_x, ny), max(4.0, rad * 0.4), max(4.0, rad * 0.4))
                        else:
                            draw_gp_custom_shape(start_x, ny, rad, head_color)

                    elif obj.is_screamer:
                        time_until_start = visual_time - current_audio_ms
                        duration = visual_end - visual_time
                        if duration <= 0:
                            duration = 1
                            
                        time_until_end = visual_end - current_audio_ms
                        flash_alpha_start = get_flash_alpha(time_until_start)
                        flash_alpha_end = get_flash_alpha(time_until_end)

                        if time_until_end < -0.5 and flash_alpha_end == 0:
                            continue

                        gp_note_pen = QPen(QColor(255, 255, 255, 200), 2)
                        col = QColor(self.object_colors.get("double", QColor("#00FF00")))

                        if time_until_start > 0:
                            nx = gp_note_x(vt_visual, is_right)
                            p.setPen(gp_note_pen)
                            p.setBrush(col)
                            p.drawEllipse(QPointF(nx, ny), rad, rad)
                        else:
                            elapsed = current_audio_ms - visual_time
                            linear_progress = min(1.0, elapsed / duration)
                            
                            t_ease = linear_progress - 1.0
                            s_ease = 1.5
                            fly_progress = t_ease * t_ease * ((s_ease + 1) * t_ease + s_ease) + 1.0

                            pair_lane = 1 if lane in [0, -1] else 0
                            start_y = gp_lane_y(lane)
                            end_y = gp_lane_y(pair_lane)
                            fly_y = start_y + (end_y - start_y) * fly_progress

                            if is_right:
                                fly_x = gp_right_line_x
                            else:
                                fly_x = gp_left_line_x

                            if flash_alpha_start > 0:
                                f = flash_alpha_start / 255.0
                                r = int(255 * f + col.red() * (1 - f))
                                g = int(255 * f + col.green() * (1 - f))
                                b = int(255 * f + col.blue() * (1 - f))
                                col = QColor(r, g, b, col.alpha())

                            if time_until_end <= 0 and flash_alpha_end > 0:
                                col = QColor(255, 255, 255, flash_alpha_end)
                                gp_note_pen = QPen(QColor(255, 255, 255, int(200 * (flash_alpha_end / 255.0))), 2)

                            p.setPen(gp_note_pen)
                            p.setBrush(col)
                            p.drawEllipse(QPointF(fly_x, fly_y), rad, rad)

                    elif obj.is_hold or obj.is_brawl_hold:
                        time_until_start = visual_time - current_audio_ms
                        time_until_end = visual_end - current_audio_ms

                        flash_alpha_start = get_flash_alpha(time_until_start)
                        flash_alpha_end = get_flash_alpha(time_until_end)

                        if time_until_end < -0.5 and flash_alpha_end == 0:
                            continue

                        if obj.is_brawl_hold:
                            start_col = QColor(self.object_colors.get("brawl_hold", QColor("#4169E1")))
                            line_col = QColor(self.object_colors.get("brawl_hold_line", QColor("#2E4A9E")))
                            if obj.is_brawl_hold_knockout:
                                end_col = QColor(self.object_colors.get("brawl_knockout", QColor("#000000")))
                            else:
                                end_col = start_col
                        else:
                            start_col = QColor(self.object_colors.get("hold", QColor("#FF3232")))
                            end_col = start_col
                            line_col = QColor(self.object_colors.get("hold_line", QColor("#FF5050")))

                        start_pen = QPen(QColor(255, 255, 255, 200), 2)
                        if flash_alpha_start > 0:
                            f = flash_alpha_start / 255.0
                            r = int(255 * f + start_col.red() * (1 - f))
                            g = int(255 * f + start_col.green() * (1 - f))
                            b = int(255 * f + start_col.blue() * (1 - f))
                            start_col = QColor(r, g, b, start_col.alpha())
                        
                        end_pen = QPen(QColor(255, 255, 255, 200), 2)
                        if flash_alpha_end > 0:
                            end_col = QColor(255, 255, 255, flash_alpha_end)
                            end_pen = QPen(QColor(255, 255, 255, int(200 * (flash_alpha_end / 255.0))), 2)

                        if time_until_start > 0:
                            start_x = gp_note_x(vt_visual, is_right)
                        else:
                            if is_right:
                                start_x = gp_right_line_x
                            else:
                                start_x = gp_left_line_x

                        end_x = gp_note_x(ve_visual, is_right)

                        if time_until_end > 0:
                            p.setPen(QPen(line_col, 4))
                            p.drawLine(QPointF(start_x, ny), QPointF(end_x, ny))

                        p.setPen(start_pen)
                        p.setBrush(start_col)
                        p.drawEllipse(QPointF(start_x, ny), rad, rad)
                        p.setPen(end_pen)
                        p.setBrush(end_col)
                        p.drawEllipse(QPointF(end_x, ny), rad * 0.8, rad * 0.8)

                    elif obj.is_spam or obj.is_brawl_spam:
                        time_until_start = visual_time - current_audio_ms
                        time_until_end = visual_end - current_audio_ms

                        flash_alpha_start = get_flash_alpha(time_until_start)
                        flash_alpha_end = get_flash_alpha(time_until_end)

                        if time_until_end < -0.5 and flash_alpha_end == 0:
                            continue

                        if obj.is_brawl_spam:
                            start_col = QColor(self.object_colors.get("brawl_spam", QColor("#FF4500")))
                            line_col = QColor(self.object_colors.get("brawl_spam_line", QColor("#CC3700")))
                            if obj.is_brawl_spam_knockout:
                                end_col = QColor(self.object_colors.get("brawl_knockout", QColor("#000000")))
                            else:
                                end_col = start_col
                        else:
                            start_col = QColor(self.object_colors.get("spam", QColor("#FFA500")))
                            end_col = start_col
                            line_col = QColor(self.object_colors.get("spam_line", QColor("#FF8C00")))

                        start_pen = QPen(QColor(255, 255, 255, 200), 2)
                        if flash_alpha_start > 0:
                            f = flash_alpha_start / 255.0
                            r = int(255 * f + start_col.red() * (1 - f))
                            g = int(255 * f + start_col.green() * (1 - f))
                            b = int(255 * f + start_col.blue() * (1 - f))
                            start_col = QColor(r, g, b, start_col.alpha())
                            
                        end_pen = QPen(QColor(255, 255, 255, 200), 2)
                        if flash_alpha_end > 0:
                            end_col = QColor(255, 255, 255, flash_alpha_end)
                            end_pen = QPen(QColor(255, 255, 255, int(200 * (flash_alpha_end / 255.0))), 2)

                        if time_until_start > 0:
                            start_x = gp_note_x(vt_visual, is_right)
                        else:
                            if is_right:
                                start_x = gp_right_line_x
                            else:
                                start_x = gp_left_line_x

                        end_x = gp_note_x(ve_visual, is_right)

                        pair_lane = 1 if lane in [0, -1] else 0
                        pair_y = gp_dynamic_y(pair_lane, obj.is_freestyle, time_until_start, obj.is_fly_in)

                        if time_until_end > 0:
                            p.setPen(QPen(line_col, 4))
                            p.drawLine(QPointF(start_x, ny), QPointF(end_x, ny))
                            p.drawLine(QPointF(start_x, pair_y), QPointF(end_x, pair_y))

                        p.setPen(start_pen)
                        p.setBrush(start_col)
                        p.drawEllipse(QPointF(start_x, ny), rad, rad)
                        p.drawEllipse(QPointF(start_x, pair_y), rad, rad)
                        p.setPen(end_pen)
                        p.setBrush(end_col)
                        p.drawEllipse(QPointF(end_x, ny), rad * 0.8, rad * 0.8)
                        p.drawEllipse(QPointF(end_x, pair_y), rad * 0.8, rad * 0.8)

                    else:
                        time_until = visual_time - current_audio_ms
                        flash_alpha = get_flash_alpha(time_until)
                        
                        if time_until < -0.5 and flash_alpha == 0:
                            continue

                        nx = gp_note_x(vt_visual, is_right)
                        gp_note_pen = QPen(QColor(255, 255, 255, 200), 2)
                        if flash_alpha > 0:
                            gp_note_pen = QPen(QColor(255, 255, 255, int(200 * (flash_alpha / 255.0))), 2)

                        if obj.is_spike:
                            col = QColor(self.object_colors.get("spike", QColor("#e0c61d")))
                            if flash_alpha > 0: col = QColor(255, 255, 255, flash_alpha)
                            p.setPen(gp_note_pen)
                            p.setBrush(col)
                            tri_size = rad
                            tri_path = QPainterPath()
                            if lane in [1, 2]:
                                tri_path.moveTo(nx, ny - tri_size)
                                tri_path.lineTo(nx - tri_size, ny + tri_size * 0.7)
                                tri_path.lineTo(nx + tri_size, ny + tri_size * 0.7)
                            else:
                                tri_path.moveTo(nx, ny + tri_size)
                                tri_path.lineTo(nx - tri_size, ny - tri_size * 0.7)
                                tri_path.lineTo(nx + tri_size, ny - tri_size * 0.7)
                            tri_path.closeSubpath()
                            p.drawPath(tri_path)
                        elif obj.is_brawl_hit:
                            col = QColor(self.object_colors.get("brawl_hit", QColor("#0064FF")))
                            if flash_alpha > 0: col = QColor(255, 255, 255, flash_alpha)
                            p.setPen(gp_note_pen)
                            p.setBrush(col)
                            p.drawEllipse(QPointF(nx, ny), rad, rad)
                        elif obj.is_brawl_final:
                            col = QColor(self.object_colors.get("brawl_knockout", QColor("#000000")))
                            if flash_alpha > 0: col = QColor(255, 255, 255, flash_alpha)
                            p.setPen(gp_note_pen)
                            p.setBrush(col)
                            p.drawEllipse(QPointF(nx, ny), rad, rad)
                        elif obj.is_hide:
                            col = QColor(self.object_colors.get("note", QColor("#64C8FF")))
                            if flash_alpha > 0: col = QColor(255, 255, 255, flash_alpha)
                            p.setPen(gp_note_pen)
                            p.setBrush(col)
                            p.drawEllipse(QPointF(nx, ny), rad, rad)
                        elif obj.is_freestyle:
                            col = QColor(self.object_colors.get("freestyle", QColor("#800080")))
                            if flash_alpha > 0: col = QColor(255, 255, 255, flash_alpha)
                            p.setPen(gp_note_pen)
                            p.setBrush(col)
                            p.drawEllipse(QPointF(nx, ny), rad, rad)
                        else:
                            col = QColor(self.object_colors.get("note", QColor("#64C8FF")))
                            if flash_alpha > 0: col = QColor(255, 255, 255, flash_alpha)
                            p.setPen(gp_note_pen)
                            p.setBrush(col)
                            p.drawEllipse(QPointF(nx, ny), rad, rad)

                if len(self.gp_visual_times) > max(128, len(gp_active_keys) * 4):
                    self.gp_visual_times = {
                        key: value
                        for key, value in self.gp_visual_times.items()
                        if key in gp_active_keys
                    }

            p.restore()

        p.setPen(QPen(QColor(255, 255, 255, 200), 2))
        p.drawLine(QPointF(gp_center_x - gp_line_offset, gp_top), QPointF(gp_center_x - gp_line_offset, gp_bottom))
        p.drawLine(QPointF(gp_center_x + gp_line_offset, gp_top), QPointF(gp_center_x + gp_line_offset, gp_bottom))

        if self.beatmap and self.beatmap.metadata.BPM > 0:
            cam_x, cam_w, cam_h = self.evaluate_camera_preview(current_audio_ms, segments)
            cam_cx = gp_center_x + gp_width * cam_x
            cam_cw = gp_width * cam_w
            cam_ch = gp_height * cam_h
            
            cam_rect = QRectF(cam_cx - cam_cw / 2, gp_center_y - cam_ch / 2, cam_cw, cam_ch)
            
            cam_accent = QColor(UI_THEME["accent"])
            cam_accent.setAlpha(100)
            p.setPen(QPen(cam_accent, 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(cam_rect)

        p.end()

    def camera_preview_state_value(self, state):
        if state == "WIDE":
            return (0.0, 0.4, 0.9)
        if state == "ANTICIPATE_L":
            return (0.05, 0.3, 0.9)
        if state == "ANTICIPATE_R":
            return (-0.05, 0.3, 0.9)
        if state == "RIGHT":
            return (0.125, 0.25, 0.75)
        return (-0.125, 0.25, 0.75)

    def camera_preview_segment_state(self, segment):
        if segment[3]:
            return "WIDE"
        return "RIGHT" if segment[2] else "LEFT"

    def camera_preview_lerp(self, start, target, elapsed_ms):
        progress = min(1.0, max(0.0, float(elapsed_ms) / 700.0))
        progress = 1.0 - (1.0 - progress)**5
        return (
            start[0] + (target[0] - start[0]) * progress,
            start[1] + (target[1] - start[1]) * progress,
            start[2] + (target[2] - start[2]) * progress
        )

    def rebuild_camera_preview_cache(self, segments):
        initial_state = self.camera_preview_segment_state(segments[0]) if segments else "RIGHT"
        initial_value = self.camera_preview_state_value(initial_state)
        target_changes = []

        for index in range(len(segments) - 1):
            segment = segments[index]
            next_segment = segments[index + 1]
            current_state = self.camera_preview_segment_state(segment)
            next_state = self.camera_preview_segment_state(next_segment)
            if current_state == next_state:
                continue

            boundary = float(segment[1])
            is_side_flip = (
                (current_state == "RIGHT" and next_state == "LEFT")
                or (current_state == "LEFT" and next_state == "RIGHT")
            )
            is_instant = bool(segment[4]) if len(segment) > 4 else False

            if is_side_flip and not is_instant:
                bpm = self.get_bpm_at_ms(boundary)
                beat_ms = 60000.0 / bpm if bpm > 0 else 500.0
                anticipation_time = max(boundary - beat_ms * 2.0, float(segment[0]))
                anticipation_state = "ANTICIPATE_L" if current_state == "RIGHT" else "ANTICIPATE_R"
                target_changes.append((anticipation_time, self.camera_preview_state_value(anticipation_state)))

            target_changes.append((boundary, self.camera_preview_state_value(next_state)))

        target_changes.sort(key=lambda change: change[0])
        tween_times = []
        tween_starts = []
        tween_targets = []
        active_start = initial_value
        active_target = initial_value
        active_time = 0.0

        for change_time, target in target_changes:
            if target == active_target:
                continue
            current_value = self.camera_preview_lerp(active_start, active_target, change_time - active_time)
            if tween_times and change_time == tween_times[-1]:
                tween_starts[-1] = current_value
                tween_targets[-1] = target
            else:
                tween_times.append(change_time)
                tween_starts.append(current_value)
                tween_targets.append(target)
            active_start = current_value
            active_target = target
            active_time = change_time

        self._camera_preview_initial = initial_value
        self._camera_preview_tween_times = tween_times
        self._camera_preview_tween_starts = tween_starts
        self._camera_preview_tween_targets = tween_targets
        self._camera_preview_cache_key = (
            getattr(self, '_object_cache_generation', 0),
            getattr(self, '_last_tps_state', None),
            self._live_event_cache_generation if self._live_event_cache_active else -1
        )

    def evaluate_live_camera_preview(self, time_ms, segments):
        if not segments:
            return self.camera_preview_state_value("RIGHT")
        segment_ends = self._live_segment_ends
        segment_index = min(len(segments) - 1, bisect.bisect_right(segment_ends, time_ms))
        changes_desc = []
        anchor_target = None

        for index in range(min(segment_index, len(segments) - 2), -1, -1):
            segment = segments[index]
            next_segment = segments[index + 1]
            current_state = self.camera_preview_segment_state(segment)
            next_state = self.camera_preview_segment_state(next_segment)
            if current_state == next_state:
                continue

            boundary = float(segment[1])
            local_changes = []
            is_side_flip = (
                (current_state == "RIGHT" and next_state == "LEFT")
                or (current_state == "LEFT" and next_state == "RIGHT")
            )
            is_instant = bool(segment[4]) if len(segment) > 4 else False
            if is_side_flip and not is_instant:
                bpm = self.get_bpm_at_ms(boundary)
                beat_ms = 60000.0 / bpm if bpm > 0 else 500.0
                anticipation_time = max(boundary - beat_ms * 2.0, float(segment[0]))
                anticipation_state = "ANTICIPATE_L" if current_state == "RIGHT" else "ANTICIPATE_R"
                local_changes.append((anticipation_time, self.camera_preview_state_value(anticipation_state)))
            local_changes.append((boundary, self.camera_preview_state_value(next_state)))

            for change_time, target in reversed(local_changes):
                if change_time > time_ms:
                    continue
                if changes_desc and changes_desc[-1][0] - change_time >= 700.0:
                    anchor_target = target
                    break
                changes_desc.append((change_time, target))
            if anchor_target is not None:
                break

        if anchor_target is None:
            anchor_target = self.camera_preview_state_value(self.camera_preview_segment_state(segments[0]))
        if not changes_desc:
            return anchor_target

        changes = list(reversed(changes_desc))
        active_start = anchor_target
        active_target = anchor_target
        active_time = changes[0][0]
        for change_time, target in changes:
            if target == active_target:
                continue
            current_value = self.camera_preview_lerp(active_start, active_target, change_time - active_time)
            active_start = current_value
            active_target = target
            active_time = change_time
        return self.camera_preview_lerp(active_start, active_target, time_ms - active_time)

    def evaluate_camera_preview(self, time_ms, segments):
        if self._live_event_cache_active:
            return self.evaluate_live_camera_preview(time_ms, segments)
        cache_key = (
            getattr(self, '_object_cache_generation', 0),
            getattr(self, '_last_tps_state', None),
            self._live_event_cache_generation if self._live_event_cache_active else -1
        )
        if getattr(self, '_camera_preview_cache_key', None) != cache_key:
            self.rebuild_camera_preview_cache(segments)

        tween_times = getattr(self, '_camera_preview_tween_times', [])
        index = bisect.bisect_right(tween_times, time_ms) - 1
        if index < 0:
            return getattr(self, '_camera_preview_initial', self.camera_preview_state_value("RIGHT"))
        return self.camera_preview_lerp(
            self._camera_preview_tween_starts[index],
            self._camera_preview_tween_targets[index],
            time_ms - tween_times[index]
        )

    def generate_waveform(self, segment):
        self.waveform_data = None
        self.waveform_loaded_points = 0
        self.waveform_ratio = 1.0
        self._waveform_tile_cache.clear()
        self._waveform_tile_signature = None
        self.update()

    def get_object_at_pos(self, pos, tolerance=30):
        if not self.beatmap:
            return None, None
        
        sf = getattr(self.editor, 'global_scale', 1.0)
        center_y = (self.height() / sf) / 2
        lane_0_y = center_y - LANE_HEIGHT / 2
        lane_1_y = center_y + LANE_HEIGHT / 2
        
        closest_obj = None
        min_dist = float('inf')
        click_type = None 
        
        centers = self.get_toggle_centers()
        
        for obj in self.get_objects_in_range(self.x_to_audio_ms(pos.x() - 100), self.x_to_audio_ms(pos.x() + 100)):
            x = self.audio_ms_to_x(obj.time)

            if obj.custom_data is not None:
                obj_y = self.get_custom_object_y(obj)
                dx = x - pos.x()
                dy = obj_y - pos.y()
                dist = (dx * dx + dy * dy) ** 0.5
                custom_tolerance = max(tolerance, 38) if self.is_custom_missing(obj) else tolerance
                if dist < custom_tolerance and dist < min_dist:
                    min_dist = dist
                    closest_obj = obj
                    click_type = 'head'
                if self.is_custom_length(obj):
                    end_x = self.audio_ms_to_x(obj.end_time)
                    dx_end = end_x - pos.x()
                    dist_end = (dx_end * dx_end + dy * dy) ** 0.5
                    if dist_end < tolerance and dist_end < min_dist:
                        min_dist = dist_end
                        closest_obj = obj
                        click_type = 'tail'
                continue
            
            if obj.is_event or obj.is_freestyle:
                dy = center_y - pos.y()
                dx = x - pos.x()
                dist = (dx*dx + dy*dy) ** 0.5
                if dist < tolerance and dist < min_dist:
                    min_dist = dist
                    closest_obj = obj
                    click_type = 'head'
            else:
                lane_upper_y = lane_0_y - LANE_HEIGHT
                lane_lower_y = lane_1_y + LANE_HEIGHT
                obj_y = self.get_draw_y(obj)
                
                is_split_tail = False
                split_tail_primary_y = obj_y
                split_tail_pair_y = self.get_draw_pair_y(obj)
                
                if (obj.is_hold or obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam or obj.is_screamer) and obj.lane in [-1, 2]:
                    is_cen_end = self.is_time_in_toggle_center(obj.end_time)
                    is_split_tail = True
                    if obj.lane == -1:
                        split_tail_primary_y = (lane_0_y - LANE_HEIGHT) if is_cen_end else lane_0_y
                        split_tail_pair_y = lane_lower_y if is_cen_end else lane_1_y
                    else: 
                        split_tail_primary_y = lane_lower_y if is_cen_end else lane_1_y
                        split_tail_pair_y = (lane_0_y - LANE_HEIGHT) if is_cen_end else lane_0_y
                
                if obj.is_spam:
                    pair_y = self.get_draw_pair_y(obj)
                    for ly in [obj_y, pair_y]:
                        dx = x - pos.x()
                        dy = ly - pos.y()
                        dist = (dx*dx + dy*dy) ** 0.5
                        if dist < tolerance and dist < min_dist:
                            min_dist = dist
                            closest_obj = obj
                            click_type = 'head'
                    
                    end_x = self.audio_ms_to_x(obj.end_time)
                    
                    tail_ys = [obj_y, pair_y]
                    if is_split_tail:
                        tail_ys = [split_tail_primary_y, split_tail_pair_y]

                    for ly in tail_ys:
                        dx_end = end_x - pos.x()
                        dy_end = ly - pos.y()
                        dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                        if dist_end < tolerance and dist_end < min_dist:
                            min_dist = dist_end
                            closest_obj = obj
                            click_type = 'tail'

                elif obj.is_brawl_spam:
                    ly = lane_1_y if obj.lane == 1 else (lane_lower_y if obj.lane == 2 else obj_y)
                    
                    dx = x - pos.x()
                    dy = ly - pos.y()
                    dist = (dx*dx + dy*dy) ** 0.5
                    if dist < tolerance:
                        min_dist = dist
                        closest_obj = obj
                        click_type = 'head'
                    
                    if obj.lane == 2 and ly != lane_lower_y:
                        dy_alt = lane_lower_y - pos.y()
                        dist_alt = (dx*dx + dy_alt*dy_alt) ** 0.5
                        if dist_alt < tolerance and dist_alt < min_dist:
                            min_dist = dist_alt
                            closest_obj = obj
                            click_type = 'head'

                    end_x = self.audio_ms_to_x(obj.end_time)
                    dx_end = end_x - pos.x()
                    
                    tail_y = ly
                    if is_split_tail:
                        tail_y = split_tail_primary_y 
                    
                    dy_end = tail_y - pos.y()
                    
                    dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                    if dist_end < tolerance and dist_end < min_dist:
                        min_dist = dist_end
                        closest_obj = obj
                        click_type = 'tail'

                elif obj.is_brawl_hold:
                    dx = x - pos.x()
                    dy = obj_y - pos.y()
                    dist = (dx*dx + dy*dy) ** 0.5
                    if dist < tolerance and dist < min_dist:
                        min_dist = dist
                        closest_obj = obj
                        click_type = 'head'

                    end_x = self.audio_ms_to_x(obj.end_time)
                    dx_end = end_x - pos.x()
                    
                    tail_y = obj_y
                    if is_split_tail:
                        tail_y = split_tail_primary_y

                    dy_end = tail_y - pos.y()
                    dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                    if dist_end < tolerance and dist_end < min_dist:
                        min_dist = dist_end
                        closest_obj = obj
                        click_type = 'tail'

                else:
                    dx = x - pos.x()
                    dy = obj_y - pos.y()
                    dist = (dx*dx + dy*dy) ** 0.5
                    
                    if dist < tolerance and dist < min_dist:
                        min_dist = dist
                        closest_obj = obj
                        click_type = 'head'
                    
                    if obj.is_hold:
                        end_x = self.audio_ms_to_x(obj.end_time)
                        dx_end = end_x - pos.x()
                        
                        tail_y = obj_y
                        if is_split_tail:
                            tail_y = split_tail_primary_y
                            
                        dist_end = (dx_end*dx_end + (tail_y - pos.y())**2) ** 0.5
                        if dist_end < tolerance and dist_end < min_dist:
                            min_dist = dist_end
                            closest_obj = obj
                            click_type = 'tail'
                    
                    if obj.is_screamer:
                        end_x = self.audio_ms_to_x(obj.end_time)
                        other_y = lane_lower_y if obj.lane == -1 else (lane_upper_y if obj.lane == 2 else (lane_1_y if obj.lane == 0 else lane_0_y))
                        
                        tail_y = other_y
                        if is_split_tail:
                            tail_y = split_tail_pair_y
                        
                        dx_end = end_x - pos.x()
                        dy_end = tail_y - pos.y()
                        dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                        
                        if dist_end < tolerance + 5 and dist_end < min_dist:
                             min_dist = dist_end
                             closest_obj = obj
                             click_type = 'tail'
        
        return closest_obj, click_type

    def get_all_objects_at_pos(self, pos, tolerance=30):
        if not self.beatmap:
            return []
        
        sf = getattr(self.editor, 'global_scale', 1.0)
        center_y = (self.height() / sf) / 2
        lane_0_y = center_y - LANE_HEIGHT / 2
        lane_1_y = center_y + LANE_HEIGHT / 2
        
        matching_objects = []
        
        centers = self.get_toggle_centers()

        for obj in self.get_objects_in_range(self.x_to_audio_ms(pos.x() - 100), self.x_to_audio_ms(pos.x() + 100)):
            x = self.audio_ms_to_x(obj.time)

            if obj.custom_data is not None:
                obj_y = self.get_custom_object_y(obj)
                dx = x - pos.x()
                dy = obj_y - pos.y()
                dist = (dx * dx + dy * dy) ** 0.5
                custom_tolerance = max(tolerance, 38) if self.is_custom_missing(obj) else tolerance
                if dist < custom_tolerance:
                    matching_objects.append((obj, 'head', dist))
                if self.is_custom_length(obj):
                    end_x = self.audio_ms_to_x(obj.end_time)
                    dx_end = end_x - pos.x()
                    dist_end = (dx_end * dx_end + dy * dy) ** 0.5
                    if dist_end < tolerance and not any(o is obj for o, _, _ in matching_objects):
                        matching_objects.append((obj, 'tail', dist_end))
                continue
            
            if obj.is_event or obj.is_freestyle:
                dy = center_y - pos.y()
                dx = x - pos.x()
                dist = (dx*dx + dy*dy) ** 0.5
                if dist < tolerance:
                    matching_objects.append((obj, 'head', dist))
            else:
                lane_upper_y = lane_0_y - LANE_HEIGHT
                lane_lower_y = lane_1_y + LANE_HEIGHT
                if obj.lane == -1: obj_y = lane_upper_y
                elif obj.lane == 2: obj_y = lane_lower_y
                obj_y = self.get_draw_y(obj)
                
                is_split_tail = False
                split_tail_primary_y = obj_y
                split_tail_pair_y = self.get_draw_pair_y(obj)
                
                if (obj.is_hold or obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam or obj.is_screamer) and obj.lane in [-1, 2]:
                    is_cen_end = self.is_time_in_toggle_center(obj.end_time)
                    is_split_tail = True
                    if obj.lane == -1:
                        split_tail_primary_y = (lane_0_y - LANE_HEIGHT) if is_cen_end else lane_0_y
                        split_tail_pair_y = lane_lower_y if is_cen_end else lane_1_y
                    else: 
                        split_tail_primary_y = lane_lower_y if is_cen_end else lane_1_y
                        split_tail_pair_y = (lane_0_y - LANE_HEIGHT) if is_cen_end else lane_0_y
                
                if obj.is_spam:
                    pair_y = self.get_draw_pair_y(obj)
                    for ly in [obj_y, pair_y]:
                        dx = x - pos.x()
                        dy = ly - pos.y()
                        dist = (dx*dx + dy*dy) ** 0.5
                        if dist < tolerance:
                            matching_objects.append((obj, 'head', dist))
                            break
                    
                    end_x = self.audio_ms_to_x(obj.end_time)
                    
                    tail_ys = [obj_y, pair_y]
                    if is_split_tail:
                        tail_ys = [split_tail_primary_y, split_tail_pair_y]

                    for ly in tail_ys:
                        dx_end = end_x - pos.x()
                        dy_end = ly - pos.y()
                        dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                        if dist_end < tolerance:
                            if not any(o is obj for o, _, _ in matching_objects):
                                matching_objects.append((obj, 'tail', dist_end))
                            break

                elif obj.is_brawl_spam:
                    ly = lane_1_y if obj.lane == 1 else (lane_lower_y if obj.lane == 2 else obj_y)
                    
                    dx = x - pos.x()
                    dy = ly - pos.y()
                    dist = (dx*dx + dy*dy) ** 0.5
                    if dist < tolerance:
                        matching_objects.append((obj, 'head', dist))
                    
                    if obj.lane == 2 and ly != lane_lower_y: 
                        dy_alt = lane_lower_y - pos.y()
                        dist_alt = (dx*dx + dy_alt*dy_alt) ** 0.5
                        if dist_alt < tolerance:
                            matching_objects.append((obj, 'head', dist_alt))
                            
                    end_x = self.audio_ms_to_x(obj.end_time)
                    dx_end = end_x - pos.x()
                    
                    tail_y = ly
                    if is_split_tail:
                        tail_y = split_tail_primary_y

                    dy_end = tail_y - pos.y()
                    dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                    if dist_end < tolerance:
                        if not any(o is obj for o, _, _ in matching_objects):
                            matching_objects.append((obj, 'tail', dist_end))

                elif obj.is_brawl_hold:
                    dx = x - pos.x()
                    dy = obj_y - pos.y()
                    dist = (dx*dx + dy*dy) ** 0.5
                    if dist < tolerance:
                        matching_objects.append((obj, 'head', dist))
                    
                    end_x = self.audio_ms_to_x(obj.end_time)
                    dx_end = end_x - pos.x()
                    
                    tail_y = obj_y
                    if is_split_tail:
                        tail_y = split_tail_primary_y

                    dy_end = tail_y - pos.y()
                    dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                    if dist_end < tolerance:
                         if not any(o is obj for o, _, _ in matching_objects):
                             matching_objects.append((obj, 'tail', dist_end))

                else:
                    dx = x - pos.x()
                    dy = obj_y - pos.y()
                    dist = (dx*dx + dy*dy) ** 0.5
                    
                    if dist < tolerance:
                        matching_objects.append((obj, 'head', dist))
                    
                    if obj.is_hold:
                        end_x = self.audio_ms_to_x(obj.end_time)
                        dx_end = end_x - pos.x()
                        
                        tail_y = obj_y
                        if is_split_tail:
                            tail_y = split_tail_primary_y

                        dist_end = (dx_end*dx_end + (tail_y - pos.y())**2) ** 0.5
                        if dist_end < tolerance:
                            if not any(o is obj for o, _, _ in matching_objects):
                                matching_objects.append((obj, 'tail', dist_end))
                    
                    if obj.is_screamer:
                        end_x = self.audio_ms_to_x(obj.end_time)
                        other_y = lane_lower_y if obj.lane == -1 else (lane_upper_y if obj.lane == 2 else (lane_1_y if obj.lane == 0 else lane_0_y))
                        
                        tail_y = other_y
                        if is_split_tail:
                            tail_y = split_tail_pair_y

                        dx_end = end_x - pos.x()
                        dy_end = tail_y - pos.y()
                        dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                        
                        if dist_end < tolerance + 5:
                            if not any(o is obj for o, _, _ in matching_objects):
                                matching_objects.append((obj, 'tail', dist_end))
        
        matching_objects.sort(key=lambda x: x[2])
        return matching_objects

    def mousePressEvent(self, e: QMouseEvent):
        if getattr(self.editor, 'start_screen', None) and self.editor.start_screen.isVisible():
            return
        sf = getattr(self.editor, 'global_scale', 1.0)
        if sf != 1.0:
            p = e.position()
            e = QMouseEvent(e.type(), QPointF(p.x() / sf, p.y() / sf), e.globalPosition(), e.button(), e.buttons(), e.modifiers())
        if not self.beatmap or self.beatmap.metadata.ActualAudioLength <= 0: return

        if hasattr(self.beatmap, 'timing_points'):
             tag_y = 90
             tag_w = 40
             tag_h = 50
             click_x = e.pos().x()
             click_y = e.pos().y()
             
             if tag_y <= click_y <= tag_y + tag_h:
                  for tp in self.beatmap.timing_points:
                       tx = self.audio_ms_to_x(tp['time'])
                       if abs(tx - click_x) <= tag_w / 2:
                            if e.button() == Qt.MouseButton.RightButton:
                                 if len(self.beatmap.timing_points) <= 1:
                                      return

                                 new_tps = [x for x in self.beatmap.timing_points if x != tp]
                                 if new_tps and self.beatmap.hit_objects:
                                      first_tp_time = new_tps[0]['time']
                                      first_note_time = min(o.time for o in self.beatmap.hit_objects)
                                      if first_note_time < first_tp_time:
                                           QMessageBox.warning(self.editor if self.editor else None, "Action Prevented", "Cannot delete this BPM tag because a note would be left without a preceding BPM tag.")
                                           return

                                 self.save_undo_state()
                                 self.dying_bpm_tags.append((tp.copy(), time.time()))
                                 current_audio = self.visual_to_audio_ms(self.current_time)
                                 self.beatmap.timing_points.remove(tp)
                                 self.current_time = self.audio_to_visual_ms(current_audio)
                                 self.target_time = self.current_time
                                 if hasattr(self.editor, 'sync_audio_to_time'): self.editor.sync_audio_to_time()
                                 if hasattr(self.editor, 'update_bpm_list'):
                                      self.editor.update_bpm_list()
                                 self.editor.mark_unsaved()
                                 self.update_scrollbar()
                                 self.update()
                                 return
                            elif e.button() == Qt.MouseButton.LeftButton:
                                 if hasattr(self, 'editor') and self.editor and self.editor.is_playing:
                                      return
                                 self.save_undo_state()
                                 self.dragging_bpm_tag = tp
                                 self.bpm_follow_drag_state = self.capture_bpm_follow_state(tp)
                                 if self.beatmap.timing_points:
                                      self.drag_bpm_was_first = (tp == self.beatmap.timing_points[0])
                                 visual_tp_time = self.audio_to_visual_ms(tp['time'])
                                 self.bpm_drag_offset = visual_tp_time - self.x_to_ms(click_x)
                                 self.bpm_drag_start_times[id(tp)] = time.time()
                                 if id(tp) in self.bpm_drag_release_times:
                                      del self.bpm_drag_release_times[id(tp)]
                                 return
        
        center_y = (self.height() / sf) / 2
        lane_0_y = center_y - LANE_HEIGHT / 2
        lane_1_y = center_y + LANE_HEIGHT / 2
        lane_upper_y = lane_0_y - LANE_HEIGHT
        lane_lower_y = lane_1_y + LANE_HEIGHT
        
        ms = self.x_to_ms(e.pos().x())
        is_toggle = self.is_time_in_toggle_center(self.visual_to_audio_ms(ms))
        
        top_limit = lane_upper_y - 50 if is_toggle else lane_0_y - 40
        bottom_limit = lane_lower_y + 50 if is_toggle else lane_1_y + 40
        
        in_lane_area = (top_limit < e.pos().y() < bottom_limit)
        
        if is_toggle and in_lane_area:
            gap_upper = (lane_upper_y + lane_0_y) / 2
            gap_lower = (lane_1_y + lane_lower_y) / 2
            gap_margin = 10
            
            if abs(e.pos().y() - gap_upper) < gap_margin or abs(e.pos().y() - gap_lower) < gap_margin:
                in_lane_area = False
        
        if e.button() == Qt.MouseButton.LeftButton:
            all_objects = self.get_all_objects_at_pos(e.pos())
            
            clicked_obj = None
            click_type = None
            
            if all_objects:
                is_same_position = (self.last_click_pos is not None and 
                                   abs(self.last_click_pos.x() - e.pos().x()) < 5 and 
                                   abs(self.last_click_pos.y() - e.pos().y()) < 5)
                
                if is_same_position and len(all_objects) > 1:
                    self.click_cycle_index = (self.click_cycle_index + 1) % len(all_objects)
                else:
                    self.click_cycle_index = 0
                
                clicked_obj, click_type, _ = all_objects[self.click_cycle_index]
                
                self.last_click_pos = e.pos()
            else:
                self.last_click_pos = None
                self.click_cycle_index = 0
            
            if clicked_obj:
                pk = self.pressed_keys | getattr(self.editor, 'pressed_keys', set())
                is_ctrl = check_modifier(e.modifiers(), getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("modify_note_modifier", "Ctrl"), pk)
                is_shift = check_modifier(e.modifiers(), getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("multiselect_modifier", "Shift"), pk)
                is_alt = check_modifier(e.modifiers(), getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("range_select_modifier", "Alt"), pk)
                is_alt_ctrl = check_modifier(e.modifiers(), getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("range_select_type_modifier", "Ctrl+Alt"), pk)

                if self.is_custom_missing(clicked_obj):
                    self.selected_objects.clear()
                    self.selected_objects.add(clicked_obj)
                    self.dragging_objects = False
                    self.update()
                    return
                
                if is_alt_ctrl or is_alt:
                    filter_same_type = is_alt_ctrl
                    anchor = getattr(self, 'range_select_anchor', None)
                    
                    can_range_select = False
                    if anchor and self.beatmap and hasattr(self.beatmap, 'hit_objects') and anchor in self.beatmap.hit_objects and is_same_lane(anchor, clicked_obj):
                        anchor_cat = get_note_type_category(anchor)
                        clicked_cat = get_note_type_category(clicked_obj)
                        if not filter_same_type or (anchor_cat == clicked_cat):
                            can_range_select = True

                    if can_range_select:
                        anchor_cat = get_note_type_category(anchor)
                        t_start = min(anchor.time, clicked_obj.time)
                        t_end = max(anchor.time, clicked_obj.time)
                        
                        for obj in self.beatmap.hit_objects:
                            if self.is_custom_missing(obj):
                                continue
                            if is_same_lane(anchor, obj) and t_start <= obj.time <= t_end:
                                if not filter_same_type or (get_note_type_category(obj) == anchor_cat):
                                    self.selected_objects.add(obj)
                        
                        self.range_select_anchor = None
                    else:
                        self.selected_objects.clear()
                        self.selected_objects.add(clicked_obj)
                        self.range_select_anchor = clicked_obj
                    
                    self.drag_mode = 'move'
                elif is_ctrl and clicked_obj.custom_data is None:
                    targets = [clicked_obj]
                    if clicked_obj in self.selected_objects:
                        targets = [o for o in self.selected_objects]

                    if clicked_obj.is_toggle_center:
                        toggle_centers = self.get_toggle_centers()
                        tc_start_ids = set(o.uid for i, o in enumerate(toggle_centers) if i % 2 == 0)
                        
                        if clicked_obj.uid not in tc_start_ids:
                            self.save_undo_state()
                            for t in targets:
                                if t.is_toggle_center and t.uid not in tc_start_ids:
                                    current_val = getattr(t, 'tc_is_blue', None)
                                    if current_val is None:
                                        t.tc_is_blue = False
                                    else:
                                        t.tc_is_blue = not current_val
                                    t.last_update_time = time.time()
                                    
                            self.editor.play_ui_sound_suppressed('UI Change', self.editor.get_pan_for_widget(self))
                            self.editor.mark_unsaved()
                            self.update()
                            return
                        
                    if clicked_obj.is_brawl_hit or clicked_obj.is_brawl_final or clicked_obj.is_brawl_hold or clicked_obj.is_brawl_spam:
                        self.save_undo_state()
                        
                        current_cop = clicked_obj.brawl_cop_number
                        new_cop = (current_cop % 4) + 1
                        
                        for t in targets:
                            if t.is_brawl_hit or t.is_brawl_final or t.is_brawl_hold or t.is_brawl_spam:
                                tc = t.brawl_cop_number
                                base = t.hitSound
                                if tc == 2: base -= 2
                                elif tc == 3: base -= 8
                                elif tc == 4: base -= 10
                                
                                if new_cop == 1: t.hitSound = base
                                elif new_cop == 2: t.hitSound = base + 2
                                elif new_cop == 3: t.hitSound = base + 8
                                elif new_cop == 4: t.hitSound = base + 10
                                t.last_update_time = time.time()
                                
                        self.editor.play_ui_sound_suppressed('UI Change', self.editor.get_pan_for_widget(self))
                        self.editor.mark_unsaved()
                        self.update()
                        return
                    
                    if clicked_obj.is_spike:
                        self.save_undo_state()
                        new_params = "0" if clicked_obj.is_fly_in else "1"
                        
                        for t in targets:
                            if t.is_spike:
                                t.objectParams = new_params
                                t.last_update_time = time.time()
                                
                        self.editor.play_ui_sound_suppressed('UI Change', self.editor.get_pan_for_widget(self))
                        self.editor.mark_unsaved()
                        self.update()
                        return
                    
                    if clicked_obj.is_hold:
                        self.save_undo_state()
                        
                        for t in targets:
                            if t.is_hold:
                                parts = t.hitSample.rstrip(":").split(":")
                                while len(parts) < 4:
                                    parts.append("0")
                                
                                if parts[0] == "1":
                                    parts[0] = "0"
                                else:
                                    parts[0] = "1"
                                
                                t.hitSample = ":".join(parts) + ":"
                                t.last_update_time = time.time()
                        
                        self.editor.play_ui_sound_suppressed('UI Change', self.editor.get_pan_for_widget(self))
                        self.editor.mark_unsaved()
                        self.update()
                        return
                    
                    if not clicked_obj.is_event and not clicked_obj.is_spike and not clicked_obj.is_hold and not clicked_obj.is_screamer and not clicked_obj.is_spam and not clicked_obj.is_brawl_hit and not clicked_obj.is_brawl_final and not clicked_obj.is_brawl_hold and not clicked_obj.is_brawl_spam and not clicked_obj.is_freestyle:
                        self.save_undo_state()
                        
                        next_state = "normal"
                        if clicked_obj.is_hide:
                            next_state = "normal"
                        elif clicked_obj.is_fly_in:
                            next_state = "hide"
                        else:
                            next_state = "fly_in"
                            
                        for t in targets:
                            if not t.is_event and not t.is_spike and not t.is_hold and not t.is_screamer and not t.is_spam and not t.is_brawl_hit and not t.is_brawl_final and not t.is_brawl_hold and not t.is_brawl_spam and not t.is_freestyle:
                                if next_state == "normal":
                                    t.hitSound = 0
                                    t.objectParams = "0"
                                elif next_state == "fly_in":
                                    t.objectParams = "1"
                                    t.hitSound = 0
                                elif next_state == "hide":
                                    t.hitSound = 8
                                    t.objectParams = "0"
                                t.last_update_time = time.time()
                                    
                        self.editor.play_ui_sound_suppressed('UI Change', self.editor.get_pan_for_widget(self))
                        self.editor.mark_unsaved()
                        self.update()
                        return

                if not (is_alt or is_alt_ctrl):
                    if is_ctrl or is_shift:
                        if clicked_obj in self.selected_objects:
                            self.selected_objects.remove(clicked_obj)
                        else:
                            self.selected_objects.add(clicked_obj)
                        self.drag_mode = 'move'
                    else:
                        if click_type == 'tail':
                            self.drag_mode = 'resize'
                            if clicked_obj not in self.selected_objects:
                                self._temp_resize_obj = clicked_obj
                                self.selected_objects.add(clicked_obj)
                        else:
                            if clicked_obj not in self.selected_objects:
                                self.selected_objects.clear()
                                self.selected_objects.add(clicked_obj)
                            self.drag_mode = 'move'

                self.selected_objects = {obj for obj in self.selected_objects if not self.is_custom_missing(obj)}
                if not self.selected_objects:
                    self.update()
                    return
                self.save_undo_state()
                self.dragging_objects = True
                self.last_mouse_pos = e.pos()
                self.drag_start_time_map.clear()
                self.drag_start_lane_map.clear()
                self.drag_original_end_time_map.clear()
                self.drag_last_snapped_time = None
                self.drag_last_lane = None
                self.drag_reference_obj = clicked_obj
                self.timeline_click_pos = e.pos()
                
                current_time = time.time()
                for obj in self.selected_objects:
                    if self.is_custom_missing(obj):
                        continue
                    if not hasattr(obj, '_current_visual_time'):
                        obj._current_visual_time = float(obj.time)
                    if not hasattr(obj, '_current_visual_lane'):
                        obj._current_visual_lane = self.get_visual_lane_value(obj)
                    self.drag_start_time_map[obj] = obj.time
                    self.drag_start_lane_map[obj] = obj.lane if not obj.is_event else -1
                    if obj.type == 128 or self.is_custom_length(obj):
                        if not hasattr(obj, '_current_visual_end_time'):
                            obj._current_visual_end_time = float(obj.end_time)
                        self.drag_original_end_time_map[obj] = obj.end_time
                    self.drag_start_times[obj] = current_time
                
                self.update()
                return
            
            pk = self.pressed_keys | getattr(self.editor, 'pressed_keys', set())
            is_shift = check_modifier(e.modifiers(), getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("multiselect_modifier", "Shift"), pk)
            if is_shift:
                self._drag_base_selection = set(self.selected_objects)
            else:
                self.selected_objects.clear()
                self._drag_base_selection = set()
            
            if is_shift or not in_lane_area:
                self.timeline_click_pos = e.pos()
                self.selection_start = self.x_to_ms(e.pos().x())
                self.selection_start_y = e.pos().y()
                self.selection_rect = None
                return
            
            if in_lane_area:
                ms = self.x_to_ms(e.pos().x())
                snapped_visual = round(self.get_snap_time(ms))
                
                song_length_ms = self.get_visual_song_length()
                if snapped_visual < 0 or (song_length_ms > 0 and snapped_visual > song_length_ms):
                    return
                
                snapped_ms = round(self.visual_to_audio_ms(snapped_visual))
                if self.beatmap.timing_points and snapped_ms < round(self.beatmap.timing_points[0]['time']) - 1:
                    return
                
                if self.current_tool_type == "note" or self.current_tool_type == "brawl":
                    lane_upper_y = lane_0_y - LANE_HEIGHT
                    lane_lower_y = lane_1_y + LANE_HEIGHT
                    
                    clicked_lane = 0
                    
                    center_y_pos = (self.height() / sf) / 2
                    click_y = e.pos().y()
                    
                    split_upper_mid = (lane_upper_y + lane_0_y) / 2
                    split_mid = center_y_pos
                    split_lower_mid = (lane_1_y + lane_lower_y) / 2
                    
                    if click_y < split_upper_mid:
                        clicked_lane = -1
                    elif click_y < split_mid:
                        clicked_lane = 0
                    elif click_y < split_lower_mid:
                        clicked_lane = 1
                    else:
                        clicked_lane = 2
                    
                    if not self.is_time_in_toggle_center(snapped_ms):
                        if clicked_lane == -1: clicked_lane = 0
                        if clicked_lane == 2: clicked_lane = 1
                    
                    if clicked_lane == -1:
                        x_pos = 255
                        y_pos = 192
                    elif clicked_lane == 2:
                        x_pos = 256
                        y_pos = 320
                    elif clicked_lane == 0:
                        x_pos = 255
                        y_pos = 0
                    else:
                        x_pos = 256
                        y_pos = 0
                    
                    hit_sound = 0
                    note_type = 1
                    params = "0"
                    sample = "0:0:0:"
                    
                    if self.current_tool_type == "brawl":
                        params = "3"
                        cop_offset = 0
                        if hasattr(self.editor, 'brawl_cop_index'):
                            if self.editor.brawl_cop_index == 2: cop_offset = 2
                            elif self.editor.brawl_cop_index == 3: cop_offset = 8
                            elif self.editor.brawl_cop_index == 4: cop_offset = 10
                        
                        if self.current_brawl_type == "hit":
                            hit_sound = 0 + cop_offset
                        elif self.current_brawl_type == "final":
                            hit_sound = 4 + cop_offset
                        elif self.current_brawl_type in ["hold", "hold_knockout", "spam", "spam_knockout"]:
                            note_type = 128
                            if self.current_brawl_type in ["hold", "spam"]:
                                hit_sound = 0 + cop_offset
                            else:
                                hit_sound = 4 + cop_offset
                                
                            if self.current_brawl_type in ["hold", "hold_knockout"]:
                                sample = "3:1:0:0:"
                            else:
                                sample = "3:0:0:0:"
                                if clicked_lane not in [1, 2]:
                                    return
                                    
                            end_ms = self.visual_to_audio_ms(self.audio_to_visual_ms(snapped_ms) + 100)
                            params = str(int(end_ms))
                    else:
                        style = self.editor.combo_note_style.currentText()
                        
                        if self.current_note_type == "freestyle":
                            x_pos = 427
                            if style == "Hide":
                                hit_sound = 8
                        elif self.current_note_type == "spike":
                            hit_sound = 2
                            if style == "Fly In":
                                params = "1"
                        elif self.current_note_type == "hold":
                            note_type = 128
                            hit_sound = 0
                            if style == "Fly In":
                                sample = "1:0:0:0:"
                        elif self.current_note_type == "normal":
                             if style == "Hide":
                                 hit_sound = 8
                             elif style == "Fly In":
                                 params = "1"
                        elif self.current_note_type == "screamer":
                             note_type = 128
                             hit_sound = 2 
                        elif self.current_note_type == "spam":
                             note_type = 128
                             hit_sound = 4
                    
                    if note_type == 128:
                        bpm = self.beatmap.metadata.BPM if self.beatmap.metadata.BPM > 0 else 120
                        beat_ms = 60000 / bpm
                        snap_len = beat_ms / self.editor.timeline.grid_snap_div if hasattr(self.editor, 'timeline') else beat_ms / 4
                        end_ms = snapped_ms + max(10, snap_len)
                        params = str(int(end_ms))

                    is_brawl_hold_spam = sample.startswith("3:")
                    is_screamer = (note_type == 128 and hit_sound == 2 and not is_brawl_hold_spam)
                    is_spam = (note_type == 128 and hit_sound == 4 and not is_brawl_hold_spam)
                    is_freestyle = (x_pos == 427 and note_type == 1)
                    is_spike_note = (hit_sound == 2 and note_type != 128)
                    is_brawl_note_new = (self.current_tool_type == "brawl")

                    if self.is_space_free(snapped_ms, int(params) if note_type == 128 else snapped_ms, clicked_lane, is_screamer=is_screamer, is_spam=is_spam, is_brawl_hold_spam=is_brawl_hold_spam, is_freestyle=is_freestyle, is_spike=is_spike_note, is_brawl=is_brawl_note_new):
                        self.save_undo_state()
                        new_obj = HitObject(x_pos, y_pos, snapped_ms, note_type, hit_sound, params, sample)
                        if is_spike_note:
                            new_obj.order_index = 1
                        new_obj.creation_time = time.time()
                        self.insert_hit_object_sorted(new_obj)
                        self.editor.mark_unsaved()
                        self.sync_structural_object_caches((new_obj,))
                        global_x = self.mapToGlobal(e.pos()).x()
                        pan = self.editor.calculate_pan(global_x)
                        self.editor.play_ui_sound_suppressed('UI Place', pan)
                
                elif self.current_tool_type == "custom":
                    type_data = get_custom_type(self.current_custom_type_id)
                    if type_data is None:
                        return
                    clicked_lane = self.get_custom_lane_for_y(type_data, e.pos().y())
                    end_ms = snapped_ms
                    if type_data.get('kind') == 'Note' and type_data.get('length'):
                        bpm = self.beatmap.metadata.BPM if self.beatmap.metadata.BPM > 0 else 120
                        beat_ms = 60000 / bpm
                        snap_len = beat_ms / self.grid_snap_div
                        end_ms = int(round(snapped_ms + max(10, snap_len)))
                    lane_x, lane_y = custom_lane_values(clicked_lane)
                    values = {
                        'time': snapped_ms,
                        'end': end_ms,
                        'lane': clicked_lane,
                    }
                    raw_line = render_custom_template(type_data['syntax'], values, type_data)
                    fields = raw_line.split(',')
                    try:
                        x_pos = int(fields[0])
                        y_pos = int(fields[1])
                        object_type = int(fields[3])
                        hit_sound = int(fields[4])
                    except (IndexError, ValueError):
                        return
                    object_params = fields[5] if len(fields) > 5 else '0'
                    hit_sample = ','.join(fields[6:]) if len(fields) > 6 else '0:0:0:'
                    if self.is_custom_space_free(snapped_ms, end_ms, clicked_lane, type_data):
                        self.save_undo_state()
                        custom_data = CustomObjectData(
                            type_data['id'],
                            type_data.get('note_id', ''),
                            clicked_lane,
                            end_ms,
                            raw_line,
                            False,
                        )
                        new_obj = HitObject(x_pos, y_pos, snapped_ms, object_type, hit_sound, object_params, hit_sample, custom_data=custom_data)
                        new_obj.creation_time = time.time()
                        self.insert_hit_object_sorted(new_obj)
                        self.editor.mark_unsaved()
                        self.sync_structural_object_caches((new_obj,))
                        global_x = self.mapToGlobal(e.pos()).x()
                        self.editor.play_ui_sound_suppressed('UI Place', self.editor.calculate_pan(global_x))

                elif self.current_tool_type == "event":
                    hit_sound = 0
                    if self.current_event_type == "toggle_center":
                        hit_sound = 2
                    elif self.current_event_type == "instant_flip":
                        if self.is_time_in_toggle_center(snapped_ms):
                            print("Cannot place Instant Flip inside a Toggle Center")
                            return
                        hit_sound = 8
                    
                    if self.is_space_free(snapped_ms, snapped_ms, -1, ignore_notes=True):
                        self.save_undo_state()
                        new_event = HitObject(384, 0, snapped_ms, 1, hit_sound, "Flip", "0:0:0:")
                        if new_event.is_toggle_center:
                            new_event.tc_is_blue = True
                        new_event.creation_time = time.time()
                        new_event.order_index = 1 if self.editor.event_default_order == "After" else 0
                        self.insert_hit_object_sorted(new_event)
                        self.editor.mark_unsaved()
                        self.sync_structural_object_caches((new_event,))
                        global_x = self.mapToGlobal(e.pos()).x()
                        pan = self.editor.calculate_pan(global_x)
                        self.editor.play_ui_sound_suppressed('UI Place', pan)
                
                self.update()

        elif e.button() == Qt.MouseButton.RightButton:
            if self.dragging_objects and self.selected_objects:
                stranded = self.validate_deletion(list(self.selected_objects))
                if stranded:
                    if not hasattr(self, 'flashing_blocked_objects'):
                        self.flashing_blocked_objects = []
                    curr_t = time.time()
                    for o in stranded:
                        self.flashing_blocked_objects.append((o, curr_t))
                    self.editor.play_ui_sound_suppressed('UI Error', 0.5)
                    self.update()
                    return

                self.save_undo_state()
                to_remove_list = list(self.selected_objects)
                for o in to_remove_list:
                    if o in self.beatmap.hit_objects:
                        self.queue_delete_animations((o,))
                        self.beatmap.hit_objects.remove(o)
                    if o in self.drag_start_time_map: del self.drag_start_time_map[o]
                    if o in self.drag_start_lane_map: del self.drag_start_lane_map[o]
                    if o in self.drag_original_end_time_map: del self.drag_original_end_time_map[o]
                self.selected_objects.clear()
                self.dragging_objects = False
                
                global_x = self.mapToGlobal(e.pos()).x()
                pan = self.editor.calculate_pan(global_x)
                self.editor.play_ui_sound_suppressed('UI Delete', pan)
                self.editor.mark_unsaved()
                self.sync_structural_object_caches(to_remove_list)
                self.update()
                return

            to_remove, _ = self.get_object_at_pos(e.pos(), tolerance=40)
            
            if to_remove:
                pk = self.pressed_keys | getattr(self.editor, 'pressed_keys', set())
                if check_modifier(e.modifiers(), getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("modify_note_modifier", "Ctrl"), pk):
                    if to_remove.is_event and not to_remove.is_toggle_center:
                        self.save_undo_state()
                        
                        targets = [to_remove]
                        if to_remove in self.selected_objects:
                            targets = [o for o in self.selected_objects if (o.is_event and not o.is_toggle_center)]
                        
                        has_changes = False
                        for t in targets:
                            has_notes = any(o is not t and o.time == t.time and not o.is_event for o in self.beatmap.hit_objects)
                            if has_notes:
                                t.order_index = 1 if t.order_index == 0 else 0
                                t.last_update_time = time.time()
                                has_changes = True
                        
                        if has_changes:
                            self.beatmap.hit_objects.sort(key=lambda x: (x.time, 0 if x.is_event and x.order_index == 0 else (2 if x.is_event else 1), 0 if getattr(x, 'is_freestyle', False) else 1, 0.5 if not x.is_event else float(x.order_index)))
                            self.editor.play_ui_sound_suppressed('UI Change', self.editor.get_pan_for_widget(self))
                            self.editor.mark_unsaved()
                            self.sync_structural_object_caches(targets)
                            self.update()
                    return

                stranded = self.validate_deletion([to_remove])
                if stranded:
                    if not hasattr(self, 'flashing_blocked_objects'):
                        self.flashing_blocked_objects = []
                    curr_t = time.time()
                    for o in stranded:
                        self.flashing_blocked_objects.append((o, curr_t))
                    self.editor.play_ui_sound_suppressed('UI Error', 0.5)
                    self.update()
                    return

                self.save_undo_state()

                obj_x = self.audio_ms_to_x(to_remove.time)
                global_x = self.mapToGlobal(QPoint(int(obj_x), 0)).x()
                pan = self.editor.calculate_pan(global_x)
                self.editor.play_ui_sound_suppressed('UI Delete', pan)

                self.queue_delete_animations((to_remove,))
                self.beatmap.hit_objects.remove(to_remove)
                if to_remove in self.selected_objects:
                    self.selected_objects.remove(to_remove)
                if to_remove in self.drag_start_time_map:
                    del self.drag_start_time_map[to_remove]
                if to_remove in self.drag_start_lane_map:
                    del self.drag_start_lane_map[to_remove]
                if to_remove in self.drag_original_end_time_map:
                    del self.drag_original_end_time_map[to_remove]
                if not self.selected_objects:
                    self.dragging_objects = False
                self.editor.mark_unsaved()
                self.sync_structural_object_caches((to_remove,))
                self.update()

    def is_space_free(self, start_t, end_t, lane, ignore_obj=None, is_screamer=False, is_spam=False, is_brawl_hold_spam=False, is_freestyle=False, tail_lane=None, is_spike=False, ignore_notes=False, is_brawl=False, pending_events=None):
        if is_spam:
            return True

        start_t = int(start_t)
        end_t = int(end_t)
        new_footprints = []
        
        def get_pair_lane(l):
            if l == -1: return 2
            if l == 2: return -1
            if l == 0: return 1
            if l == 1: return 0
            return None
            
        pair_lane = get_pair_lane(lane)
        
        if is_spam or is_brawl_hold_spam:
            h_lane = tail_lane if tail_lane is not None else lane
            new_footprints.append((start_t, start_t, h_lane))
            if is_spam and pair_lane is not None:
                new_footprints.append((start_t, start_t, pair_lane))

            body_start = start_t + 1
            body_end = max(start_t, end_t - 1)
            if body_end >= body_start:
                new_footprints.append((body_start, body_end, lane))
                if pair_lane is not None:
                    new_footprints.append((body_start, body_end, pair_lane))
            
            t_lane = tail_lane if tail_lane is not None else lane
            new_footprints.append((end_t, end_t, t_lane))
            if is_spam and pair_lane is not None:
                new_footprints.append((end_t, end_t, pair_lane))
        elif is_screamer:
            new_footprints.append((start_t, start_t, lane))
            if pair_lane is not None:
                new_footprints.append((end_t, end_t, pair_lane))
        elif is_freestyle:
            new_footprints.append((start_t, end_t, 2))
        else:
            if not (getattr(self.editor, 'disable_hold_collisions', False) and end_t > start_t):
                new_footprints.append((start_t, end_t, lane))

        centers = self.get_toggle_centers()
        if pending_events:
            centers = centers + pending_events
            centers.sort(key=lambda x: (x.time, float(x.order_index)))
        
        def apply_split_to_footprints(footprints, chk_start, chk_end, chk_lane):
            if chk_lane not in [-1, 2]: return footprints
            
            splits = [chk_start]
            for c in centers:
                if chk_start <= c.time <= chk_end:
                    splits.append(c.time)
            splits.append(chk_end)
            
            mapped_lane = 0 if chk_lane == -1 else 1
            mapped_pair = 1 if mapped_lane == 0 else 0
            
            final_fps = []
            for (fs, fe, fl) in footprints:
                for i in range(len(splits) - 1):
                    seg_s = max(fs, splits[i])
                    seg_e = min(fe, splits[i+1])
                    if seg_s <= seg_e:
                        eval_t = seg_s + 1 if seg_s < seg_e else seg_s
                        is_cen = self.is_time_in_toggle_center(eval_t, pending_events)
                        
                        target = fl
                        if not is_cen:
                            if fl == chk_lane: target = mapped_lane
                            elif get_pair_lane(chk_lane) is not None and fl == get_pair_lane(chk_lane): target = mapped_pair
                            
                        final_fps.append((seg_s, seg_e, target))
            return final_fps

        if lane in [-1, 2] and not is_freestyle and not is_spike:
             is_relevant = False
             if (end_t - start_t) > 0: is_relevant = True
             if is_screamer: is_relevant = True
             
             if is_relevant:
                 new_footprints = apply_split_to_footprints(new_footprints, start_t, end_t, lane)

        ignore_set = set()
        if ignore_obj:
            if isinstance(ignore_obj, (list, set, tuple)):
                ignore_set.update(ignore_obj)
            else:
                ignore_set.add(ignore_obj)

        margin = 1
        
        candidates = self.get_objects_in_range(start_t - 5000, end_t + 5000) if hasattr(self, 'get_objects_in_range') else self.beatmap.hit_objects
        for obj in candidates:
            if obj in ignore_set: continue
            if self.is_custom_missing(obj): continue
            other_custom_type = self.get_custom_type_data(obj)
            if other_custom_type is not None and not other_custom_type.get('collision', True): continue
            if other_custom_type is not None:
                if ignore_notes:
                    continue
                obj_start = int(obj.time)
                obj_end = int(obj.end_time) if self.is_custom_length(obj) else obj_start
                custom_lane = int(obj.custom_data.lane)
                for footprint_start, footprint_end, footprint_lane in new_footprints:
                    effective_lane = -2 if is_freestyle else footprint_lane
                    if effective_lane != custom_lane:
                        continue
                    if max(footprint_start - margin, obj_start - margin) <= min(footprint_end + margin, obj_end + margin):
                        return False
                continue
            if getattr(obj, 'is_spam', False): continue
            
            obj_is_brawl = getattr(obj, 'is_brawl_hit', False) or getattr(obj, 'is_brawl_final', False) or getattr(obj, 'is_brawl_hold', False) or getattr(obj, 'is_brawl_spam', False)
            obj_is_brawl_all_lane = getattr(obj, 'is_brawl_hold', False) or getattr(obj, 'is_brawl_spam', False)
            
            is_obj_cop_hit = getattr(obj, 'is_brawl_hit', False) or getattr(obj, 'is_brawl_final', False)
            is_new_cop_hit = is_brawl and not is_brawl_hold_spam
            is_obj_normal_hold = obj.is_hold
            is_new_normal_hold = (end_t > start_t and not is_brawl and not is_spam and not is_screamer and not is_freestyle)
            
            allow_inside_overlap = False
            if is_new_cop_hit and is_obj_normal_hold:
                allow_inside_overlap = True
            elif is_new_normal_hold and is_obj_cop_hit:
                allow_inside_overlap = True

            cop_time = start_t if is_new_cop_hit else obj.time
            hold_start = obj.time if is_new_cop_hit else start_t
            hold_end = getattr(obj, 'end_time', obj.time) if is_new_cop_hit else end_t
            
            if not obj.is_event and not ignore_notes:
                obj_start = obj.time
                obj_end = obj.end_time
                time_overlap = max(start_t - margin, obj_start - margin) <= min(end_t + margin, obj_end + margin)
                
                if time_overlap:
                    if is_brawl and obj_is_brawl:
                        return False
                        
                    if is_brawl_hold_spam or obj_is_brawl_all_lane:
                        obj_is_spk = getattr(obj, 'is_spike', False)
                        if not is_spike and not obj_is_spk:
                            return False
                            
                    elif is_brawl or obj_is_brawl:
                        if not is_freestyle and not getattr(obj, 'is_freestyle', False):
                            if lane in [-1, 2] and obj.lane in [-1, 2]:
                                if allow_inside_overlap:
                                    if not getattr(self.editor, 'disable_hold_collisions', False):
                                        if abs(cop_time - hold_start) <= margin * 2: return False
                                        if abs(cop_time - hold_end) <= margin * 2: return False
                                else:
                                    return False
                
                if is_brawl_hold_spam or obj_is_brawl_all_lane:
                    continue
                if is_brawl and obj_is_brawl:
                    continue     
            
            if obj.is_event:
                 if not ignore_notes: continue 
            else:
                 if ignore_notes: continue

            if is_freestyle:
                if obj.is_freestyle:
                     if max(start_t, obj.time) <= min(end_t, obj.end_time):
                         return False
                elif obj.is_brawl_hold:
                     if max(start_t, obj.time) <= min(end_t, obj.end_time):
                         return False
                continue

            if obj.is_freestyle:
                if is_spam or is_brawl_hold_spam:
                     if max(start_t, obj.time) <= min(end_t, obj.end_time):
                         return False
                continue
            
            obj_start = obj.time
            obj_end = obj.end_time if obj.type == 128 or self.is_custom_length(obj) else obj.time
            
            if max(start_t - margin, obj_start - margin) > min(end_t + margin, obj_end + margin):
                continue
            
            obj_footprints = []
            obj_pair = get_pair_lane(obj.lane)
            
            if obj.is_spike:
                if is_spam or is_brawl_hold_spam: continue
            
            if obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam:
                if is_spike: continue
                
                h_lane = obj.lane
                obj_footprints.append((obj.time - margin, obj.time + margin, obj.lane))
                if obj.is_spam and obj_pair is not None:
                    obj_footprints.append((obj.time - margin, obj.time + margin, obj_pair))
                
                body_start = obj.time + 1
                body_end = max(obj.time, obj.end_time - 1)
                if body_end >= body_start:
                    if not getattr(self.editor, 'disable_hold_collisions', False):
                        obj_footprints.append((body_start, body_end, obj.lane))
                        if obj.is_spam and obj_pair is not None:
                            obj_footprints.append((body_start, body_end, obj_pair))
                
                t_lane = obj.lane
                obj_footprints.append((obj.end_time - margin, obj.end_time + margin, t_lane))
                if obj.is_spam and obj_pair is not None:
                    obj_footprints.append((obj.end_time - margin, obj.end_time + margin, obj_pair))

            elif obj.is_screamer:
                s_lane = obj.lane
                e_lane = obj_pair if obj_pair is not None else (1 if s_lane == 0 else 0)
                obj_footprints.append((obj.time - margin, obj.time + margin, s_lane))
                obj_footprints.append((obj.end_time - margin, obj.end_time + margin, e_lane))
            else:
                if not (getattr(self.editor, 'disable_hold_collisions', False) and obj_end > obj_start):
                    obj_footprints.append((obj_start - margin, obj_end + margin, obj.lane))
            
            if (obj.is_hold or obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam or obj.is_screamer) and obj.lane in [-1, 2]:
                 obj_footprints = apply_split_to_footprints(obj_footprints, obj.time, obj.end_time, obj.lane)
                
            for nf in new_footprints:
                 for of in obj_footprints:
                     if nf[2] == of[2]:
                         if max(nf[0], of[0]) <= min(nf[1], of[1]):
                             if allow_inside_overlap:
                                 if abs(cop_time - hold_start) <= margin * 2: return False
                                 if abs(cop_time - hold_end) <= margin * 2: return False
                                 continue
                             return False
        return True

    def update_dragged_objects(self):
        if not self.dragging_objects or not self.last_mouse_pos or not self.beatmap:
            return

        current_mouse_time = self.x_to_ms(self.last_mouse_pos.x())
        start_mouse_time = self.x_to_ms(self.timeline_click_pos.x()) if self.timeline_click_pos else current_mouse_time
        
        if not hasattr(self, 'drag_start_mouse_time'):
            self.drag_start_mouse_time = start_mouse_time

        sf = getattr(self.editor, 'global_scale', 1.0)
        center_y = (self.height() / sf) / 2
        lane_0_y = center_y - LANE_HEIGHT / 2
        lane_1_y = center_y + LANE_HEIGHT / 2
        lane_upper_y = lane_0_y - LANE_HEIGHT
        lane_lower_y = lane_1_y + LANE_HEIGHT
        
        target_lane = 0
        center_y_pos = (self.height() / sf) / 2
        mouse_y = self.last_mouse_pos.y()
        
        split_upper_mid = (lane_upper_y + lane_0_y) / 2
        split_mid = center_y_pos
        split_lower_mid = (lane_1_y + lane_lower_y) / 2
        
        if mouse_y < split_upper_mid:
            target_lane = -1
        elif mouse_y < split_mid:
            target_lane = 0
        elif mouse_y < split_lower_mid:
            target_lane = 1
        else:
            target_lane = 2
            
        start_mouse_y = self.timeline_click_pos.y() if self.timeline_click_pos else mouse_y
        if start_mouse_y < split_upper_mid: start_mouse_lane = -1
        elif start_mouse_y < split_mid: start_mouse_lane = 0
        elif start_mouse_y < split_lower_mid: start_mouse_lane = 1
        else: start_mouse_lane = 2
            
        if not self.is_time_in_toggle_center(self.visual_to_audio_ms(current_mouse_time)):
            if target_lane == -1: target_lane = 0
            if target_lane == 2: target_lane = 1
            
        if not self.is_time_in_toggle_center(self.visual_to_audio_ms(start_mouse_time)):
            if start_mouse_lane == -1: start_mouse_lane = 0
            if start_mouse_lane == 2: start_mouse_lane = 1
        
        valid_selected = [o for o in self.selected_objects if o in self.drag_start_time_map and not self.is_custom_missing(o)]
        if not valid_selected:
            return
        
        reference_obj = getattr(self, 'drag_reference_obj', None)
        if reference_obj not in valid_selected:
            reference_obj = valid_selected[0]
            
        reference_start_lane = self.drag_start_lane_map.get(reference_obj, 0)

        unique_lanes = set()
        for obj in valid_selected:
            l = self.drag_start_lane_map.get(obj)
            if l != -1:
                unique_lanes.add(l)
        
        time_delta = current_mouse_time - self.drag_start_mouse_time
        
        collision_detected = False
        potential_moves = []

        if self.drag_mode == 'move':
            ms_diff = self.x_to_ms(self.last_mouse_pos.x()) - self.drag_start_mouse_time
            
            max_duration = float('inf')
            vsl = self.get_visual_song_length()
            if vsl > 0:
                max_duration = vsl
            elif self.beatmap.metadata.ActualAudioLength > 0:
                max_duration = self.beatmap.metadata.ActualAudioLength * 1000

            sel_min_time_audio = min(self.drag_start_time_map[o] for o in self.selected_objects) if self.selected_objects else 0
            sel_min_time_visual = self.audio_to_visual_ms(sel_min_time_audio)
            
            sel_max_end_audio = 0
            for o in self.selected_objects:
                st = self.drag_start_time_map[o]
                et = self.drag_original_end_time_map[o] if o in self.drag_original_end_time_map else st
                if et > sel_max_end_audio: sel_max_end_audio = et
            sel_max_end_visual = self.audio_to_visual_ms(sel_max_end_audio)
            
            min_allowed_audio = 0
            if self.beatmap.timing_points:
                min_allowed_audio = self.beatmap.timing_points[0]['time']
            min_allowed_visual = self.audio_to_visual_ms(min_allowed_audio)
            
            if ms_diff < min_allowed_visual - sel_min_time_visual: ms_diff = min_allowed_visual - sel_min_time_visual
            if max_duration != float('inf') and ms_diff > max_duration - sel_max_end_visual: ms_diff = max_duration - sel_max_end_visual

            selection_lanes = set()
            for o in self.selected_objects:
                if not getattr(o, 'is_event', False) and not getattr(o, 'is_freestyle', False):
                    selection_lanes.add(o.lane)

            is_vertical_allowed = True
            is_swap_mode = False
            
            if reference_obj and (getattr(reference_obj, 'is_freestyle', False) or getattr(reference_obj, 'is_event', False)):
                is_vertical_allowed = False
                is_swap_mode = False
            elif len(self.selected_objects) > 1:
                if len(selection_lanes) > 1:
                    is_vertical_allowed = False
                    is_swap_mode = True

            for obj in self.selected_objects:
                original_time = self.drag_start_time_map[obj]
                original_visual = self.audio_to_visual_ms(original_time)
                new_visual_raw = original_visual + ms_diff
                new_visual_snapped = round(self.get_snap_time(new_visual_raw))
                new_time_snapped = round(self.visual_to_audio_ms(new_visual_snapped))
                new_time = new_time_snapped
                new_time_raw = self.visual_to_audio_ms(new_visual_raw)
                
                if getattr(self, 'is_g_pressed', False):
                    new_time = round(new_time_raw)
                    
                if new_time < 0: new_time = 0

                original_lane = self.drag_start_lane_map[obj]
                new_lane = original_lane
                
                custom_type = self.get_custom_type_data(obj)
                if custom_type is not None:
                    new_lane = self.get_custom_lane_for_y(custom_type, self.last_mouse_pos.y())
                elif obj.is_event or obj.is_freestyle:
                     new_lane = original_lane
                else:
                    if is_vertical_allowed:
                        center_y_pos = (self.height() / sf) / 2
                        mouse_y = self.last_mouse_pos.y()
                        
                        split_upper_mid = (lane_upper_y + lane_0_y) / 2
                        split_mid = center_y_pos
                        split_lower_mid = (lane_1_y + lane_lower_y) / 2
                        
                        new_lane = original_lane + (target_lane - start_mouse_lane)
                        if new_lane < -1: new_lane = -1
                        elif new_lane > 2: new_lane = 2
                        
                        if not self.is_time_in_toggle_center(new_time):
                            if new_lane == -1: new_lane = 0
                            elif new_lane == 2: new_lane = 1
                        
                        if getattr(obj, 'is_brawl_spam', False) or getattr(obj, 'is_brawl_spam_knockout', False):
                             if new_lane == 0: new_lane = 1
                             elif new_lane == -1: new_lane = 2
                             elif new_lane not in [1, 2]: new_lane = 1
                    elif is_swap_mode and target_lane != reference_start_lane:
                        if original_lane == 0: new_lane = 1
                        elif original_lane == 1: new_lane = 0
                        elif original_lane == -1: new_lane = 2
                        elif original_lane == 2: new_lane = -1
                        
                duration = 0
                new_end_time = new_time
                new_end_time_raw = new_time_raw
                new_end_time_snapped = new_time_snapped
                if obj.type == 128 or self.is_custom_length(obj):
                    duration = self.drag_original_end_time_map[obj] - original_time
                    new_end_time = int(new_time + duration)
                    new_end_time_raw = new_time_raw + duration
                    new_end_time_snapped = int(new_time_snapped + duration)
                
                is_sc = obj.is_screamer
                is_sp = obj.is_spam
                is_bhs = obj.is_brawl_hold or obj.is_brawl_spam
                is_fs = obj.is_freestyle
                is_spk = obj.is_spike
                t_lane = getattr(obj, 'tail_lane', None)
                if t_lane is not None:
                    t_lane = t_lane

                is_b_note = getattr(obj, 'is_brawl_hit', False) or getattr(obj, 'is_brawl_final', False) or getattr(obj, 'is_brawl_hold', False) or getattr(obj, 'is_brawl_spam', False)
                if custom_type is not None:
                    space_free = self.is_custom_space_free(new_time, new_end_time, new_lane, custom_type, self.selected_objects)
                else:
                    space_free = self.is_space_free(new_time, new_end_time, new_lane, ignore_obj=self.selected_objects, is_screamer=is_sc, is_spam=is_sp, is_brawl_hold_spam=is_bhs, is_freestyle=is_fs, tail_lane=t_lane, is_spike=is_spk, ignore_notes=obj.is_event, is_brawl=is_b_note)
                if not space_free:
                    collision_detected = True
                    break
                potential_moves.append((obj, new_time, new_end_time, new_lane, new_time_raw, new_end_time_raw, new_time_snapped, new_end_time_snapped))

        elif self.drag_mode == 'resize':
            max_duration = float('inf')
            vsl = self.get_visual_song_length()
            if vsl > 0:
                max_duration = vsl
            elif self.beatmap.metadata.ActualAudioLength > 0:
                max_duration = self.beatmap.metadata.ActualAudioLength * 1000

            for obj in self.selected_objects:
                if obj.type == 128 or self.is_custom_length(obj):
                    orig_end_visual = self.audio_to_visual_ms(self.drag_original_end_time_map[obj])
                    new_end_visual_raw = orig_end_visual + time_delta
                    new_end_visual = round(self.get_snap_time(new_end_visual_raw))
                    new_end_time_raw = self.visual_to_audio_ms(new_end_visual_raw)
                    new_end_time_snapped = round(self.visual_to_audio_ms(new_end_visual))
                    new_end_time = new_end_time_snapped
                    
                    if getattr(self, 'is_g_pressed', False):
                        new_end_time = round(new_end_time_raw)
                    
                    if new_end_time > max_duration: new_end_time = int(max_duration)
                    
                    new_lane = self.drag_start_lane_map[obj]
                    
                    if new_end_time <= obj.time:
                         new_end_time = int(obj.time + (self.drag_original_end_time_map[obj] - self.drag_start_time_map[obj]))
                         if new_end_time <= obj.time: new_end_time = obj.time + 100 
                         new_end_time_raw = obj.time + 100 

                    is_sc = obj.is_screamer
                    is_sp = obj.is_spam
                    is_bhs = obj.is_brawl_hold or obj.is_brawl_spam
                    is_fs = obj.is_freestyle
                    
                    t_lane = None
                    if obj.is_brawl_spam: t_lane = 1
                    elif obj.is_brawl_hold: t_lane = 0 if new_lane == 0 else 1
                    elif is_sp: t_lane = new_lane

                    if new_end_time > obj.time:
                         is_sp = getattr(obj, 'is_spam', False)
                         is_bhs = getattr(obj, 'is_brawl_hold', False) or getattr(obj, 'is_brawl_spam', False)
                         is_fs = getattr(obj, 'is_freestyle', False)
                         is_b_note = getattr(obj, 'is_brawl_hit', False) or getattr(obj, 'is_brawl_final', False) or getattr(obj, 'is_brawl_hold', False) or getattr(obj, 'is_brawl_spam', False)
                         
                         t_lane = getattr(obj, 'tail_lane', None)
                         if t_lane is not None:
                             t_lane = t_lane
                         custom_type = self.get_custom_type_data(obj)
                         if custom_type is not None:
                             space_free = self.is_custom_space_free(obj.time, new_end_time, new_lane, custom_type, obj)
                         else:
                             space_free = self.is_space_free(obj.time, new_end_time, new_lane, ignore_obj=obj, is_screamer=is_sc, is_spam=is_sp, is_brawl_hold_spam=is_bhs, is_freestyle=is_fs, tail_lane=t_lane, ignore_notes=obj.is_event, is_brawl=is_b_note)
                         if not space_free:
                            collision_detected = True
                            break
                         else:
                            potential_moves.append((obj, obj.time, new_end_time, new_lane, obj.time, new_end_time_raw, obj.time, new_end_time_snapped))
        
        if not collision_detected and potential_moves:
            if self.drag_mode == 'resize':
                new_snapped_value = potential_moves[0][7] if potential_moves else None
            else:
                new_snapped_value = potential_moves[0][6] if potential_moves else None
            
            should_play_drag = False
            drag_sound_name = 'UI Drag'
            
            if new_snapped_value is not None:
                if self.drag_last_snapped_time is None:
                    self.drag_last_snapped_time = new_snapped_value
                elif new_snapped_value != self.drag_last_snapped_time:
                    should_play_drag = True
                    
                    if self.drag_mode == 'resize' and potential_moves:
                         obj = potential_moves[0][0]
                         if obj in self.drag_original_end_time_map and obj in self.drag_start_time_map:
                             orig_len = self.drag_original_end_time_map[obj] - self.drag_start_time_map[obj]
                             curr_len = potential_moves[0][2] - potential_moves[0][1]
                             
                             diff = curr_len - orig_len
                             
                             bpm = self.beatmap.metadata.BPM if self.beatmap.metadata.BPM > 0 else 120
                             beat_ms = 60000.0 / bpm
                             
                             div = 4
                             if hasattr(self.editor, 'spin_grid'):
                                 div = self.editor.spin_grid.value()
                                 
                             snap_len = beat_ms / div
                             if snap_len < 1: snap_len = 1
                             
                             steps = int(round(diff / snap_len))
                             
                             steps = max(-24, min(24, steps))
                             
                             if steps != 0:
                                 potential_name = f"UI Drag P{steps}"
                                 if potential_name in self.editor.sounds:
                                     drag_sound_name = potential_name

                    self.drag_last_snapped_time = new_snapped_value
            
            new_lane_value = potential_moves[0][3] if potential_moves else None
            if new_lane_value is not None:
                if self.drag_last_lane is None:
                    self.drag_last_lane = new_lane_value
                elif new_lane_value != self.drag_last_lane:
                    should_play_drag = True
                    self.drag_last_lane = new_lane_value
            
            live_event_state_changed = False
            for obj, t, et, l, tr, etr, *args in potential_moves:
                new_object_time = int(t)
                if obj.is_event and obj.time != new_object_time:
                    live_event_state_changed = True
                obj.time = new_object_time
                obj._target_visual_time = tr
                if obj.type == 128 or self.is_custom_length(obj):
                    obj.end_time = int(et)
                    obj._target_visual_end_time = etr
                self.visual_interpolating_objects.add(obj)
                
                if obj.custom_data is not None:
                    obj.custom_data.lane = int(l)
                    lane_x, lane_y = custom_lane_values(int(l))
                    obj.x = lane_x
                    obj.y = lane_y
                    obj._target_visual_lane = self.get_visual_lane_value(obj, l)
                elif l is not None and not obj.is_freestyle and not obj.is_event:
                    if not self.is_time_in_toggle_center(obj.time) and l in [-1, 2]:
                         if l == -1: l = 0
                         if l == 2: l = 1
                    
                    obj._target_visual_lane = float(l)
                    
                    pair_lane = self.get_pair_lane(l)
                    if pair_lane is not None:
                        obj._target_visual_pair_lane = float(pair_lane)

                    obj.x = 255 if l == 0 else 256
                    if l == -1: 
                        obj.x = 255
                        obj.y = 192
                    elif l == 2:
                        obj.x = 256
                        obj.y = 320
                    else:
                        obj.y = 0

            if live_event_state_changed:
                self._live_event_cache_dirty = True
                now = time.perf_counter()
                refresh_interval = self.get_live_event_cache_interval()
                if now - self._last_live_event_cache_time >= refresh_interval:
                    self.rebuild_live_event_cache()

            self.editor.mark_unsaved()
            
            current_time = time.time()
            if should_play_drag and (current_time - self.last_drag_sound_time > 0.038):

                try:
                    sf = getattr(self.editor, 'global_scale', 1.0)
                    local_x = self.last_mouse_pos.x() * sf
                    pan = self.editor.calculate_pan_relative(local_x)
                except:
                    pan = 0.0
                
                self.editor.play_ui_sound_suppressed(drag_sound_name, pan=pan)
                self.last_drag_sound_time = current_time
            
            self.update()

    def mouseMoveEvent(self, e: QMouseEvent):
        if getattr(self.editor, 'start_screen', None) and self.editor.start_screen.isVisible():
            return
        sf = getattr(self.editor, 'global_scale', 1.0)
        if sf != 1.0:
            p = e.position()
            e = QMouseEvent(e.type(), QPointF(p.x() / sf, p.y() / sf), e.globalPosition(), e.button(), e.buttons(), e.modifiers())
        
        if hasattr(self, 'dragging_bpm_tag') and self.dragging_bpm_tag:
             current_audio = self.visual_to_audio_ms(self.current_time)
             self.last_mouse_pos = e.pos()
             new_x = e.pos().x()
             offset = getattr(self, 'bpm_drag_offset', 0)
             new_visual_raw = self.x_to_ms(new_x) + offset
             new_time = float(self.visual_to_audio_ms(new_visual_raw, ignore_bpm_tag=self.dragging_bpm_tag))
             if new_time < 0: new_time = 0
             audio_len = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap.metadata.ActualAudioLength > 0 else 0
             if audio_len > 0 and new_time > audio_len:
                  new_time = audio_len
             follow_state = getattr(self, 'bpm_follow_drag_state', None)
             if follow_state and audio_len > 0:
                  new_time = min(new_time, max(0.0, audio_len - self.get_bpm_follow_max_offset(follow_state)))
             if not follow_state and getattr(self, 'drag_bpm_was_first', False) and self.beatmap.hit_objects:
                  first_note = min([o.time for o in self.beatmap.hit_objects])
                  if new_time > first_note:
                      new_time = first_note

             for tp in self.beatmap.timing_points:
                  if tp is not self.dragging_bpm_tag:
                       if abs(tp['time'] - new_time) < 0.001:
                            if new_time > tp['time']: new_time = tp['time'] + 0.01
                            else: new_time = tp['time'] - 0.01

             self.dragging_bpm_tag['time'] = new_time
             self.dragging_bpm_tag['_target_visual_time'] = float(new_time)
             self.update_bpm_follow_preview(follow_state)
             if self.dragging_bpm_tag not in self.bpm_interpolating:
                  self.bpm_interpolating.append(self.dragging_bpm_tag)
                 
             self.beatmap.timing_points.sort(key=lambda x: x['time'])
             
             if self.editor.is_playing:
                  self.current_time = self.audio_to_visual_ms(current_audio)
                  self.target_time = self.current_time

             if hasattr(self.editor, 'update_bpm_list'):
                  self.editor.update_bpm_list()
             self.editor.mark_unsaved()
             self.update_scrollbar()
             self.update()
             return

        if self.dragging_objects:
            self.last_mouse_pos = e.pos()
            if not hasattr(self, 'drag_start_mouse_time'):
                self.drag_start_mouse_time = self.x_to_ms(e.pos().x())

            margin = 50
            w = self.width() / sf
            scroll = 0
            if e.pos().x() < margin: scroll = -1
            elif e.pos().x() > w - margin: scroll = 1
            
            if scroll != 0:
                self.edge_scroll_speed = scroll * 50
                if not self.edge_scroll_timer.isActive():
                    self._last_edge_scroll_tick = time.perf_counter()
                    self.edge_scroll_timer.start()
            else:
                self.edge_scroll_timer.stop()
            
            self.update_dragged_objects()
            self.update()
        
        elif self.selection_start is not None:
            self.last_mouse_pos = e.pos()
            self.selection_last_mouse_y = e.pos().y()
            start_x = self.ms_to_x(self.selection_start)
            current_x = e.pos().x()
            x1 = min(start_x, current_x)
            y1 = min(self.selection_start_y, e.pos().y())
            x2 = max(start_x, current_x)
            y2 = max(self.selection_start_y, e.pos().y())
            
            self.selection_rect = QRectF(x1, y1, x2-x1, y2-y1)
            
            margin = 50
            w = self.width() / sf
            scroll = 0
            if e.pos().x() < margin: scroll = -1
            elif e.pos().x() > w - margin: scroll = 1
            
            if scroll != 0:
                self.edge_scroll_speed = scroll * 50
                if not self.edge_scroll_timer.isActive():
                    self._last_edge_scroll_tick = time.perf_counter()
                    self.edge_scroll_timer.start()
            else:
                self.edge_scroll_timer.stop()
            
            pk = self.pressed_keys | getattr(self.editor, 'pressed_keys', set())
            if check_modifier(e.modifiers(), getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("multiselect_modifier", "Shift"), pk):
                self.selected_objects = set(getattr(self, '_drag_base_selection', set()))
            else:
                self.selected_objects.clear()
            
            center_y = (self.height() / sf) / 2
            lane_0_y = center_y - LANE_HEIGHT / 2
            lane_1_y = center_y + LANE_HEIGHT / 2
            lane_upper_y = lane_0_y - LANE_HEIGHT
            lane_lower_y = lane_1_y + LANE_HEIGHT
            
            for obj in self.get_selection_candidates(x1, x2):
                if self.is_custom_missing(obj):
                    continue
                obj_x = self.audio_ms_to_x(obj.time)
                
                ys_to_check = []
                if obj.custom_data is not None:
                    ys_to_check.append(self.get_custom_object_y(obj))
                elif obj.is_event:
                    ys_to_check.append(center_y)
                elif obj.is_freestyle:
                    ys_to_check.append(center_y)
                else:
                    if obj.lane == -1: obj_y = lane_upper_y
                    elif obj.lane == 2: obj_y = lane_lower_y
                    elif obj.lane == 0: obj_y = lane_0_y
                    else: obj_y = lane_1_y
                    ys_to_check.append(obj_y)
                    
                    if obj.is_spam:
                        pair_y = lane_lower_y if obj.lane == -1 else (lane_upper_y if obj.lane == 2 else (lane_1_y if obj.lane == 0 else lane_0_y))
                        ys_to_check.append(pair_y)
                
                selected = False
                for y in ys_to_check:
                    if x1 <= obj_x <= x2 and y1 <= y <= y2:
                        self.selected_objects.add(obj)
                        selected = True
                        break
                
                if not selected and (obj.is_hold or obj.is_screamer or obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam or self.is_custom_length(obj)):
                    end_x = self.audio_ms_to_x(obj.end_time)
                    if x1 <= end_x <= x2:
                        tail_ys = ys_to_check
                        
                        check_tail_ys = []
                        if obj.is_screamer:
                             pair_y = lane_lower_y if obj.lane == -1 else (lane_upper_y if obj.lane == 2 else (lane_1_y if obj.lane == 0 else lane_0_y))
                             check_tail_ys.append(pair_y)
                        else:
                             check_tail_ys = ys_to_check
                        
                        for y in check_tail_ys:
                            if y1 <= y <= y2:
                                self.selected_objects.add(obj)
                                break
            self.update()
    
    def finalize_toggle_center_drag(self):
        centers = sorted(
            (obj for obj in self.beatmap.hit_objects if obj.is_toggle_center),
            key=lambda obj: (obj.time, float(obj.order_index))
        )
        for index, obj in enumerate(centers):
            obj.order_index = index % 2
        center_times = [obj.time for obj in centers]
        for obj in self.beatmap.hit_objects:
            if obj.is_event or obj.is_freestyle or obj.lane not in [-1, 2]:
                continue
            idx = bisect.bisect_right(center_times, obj.time)
            if idx > 0 and idx % 2 == 0 and center_times[idx - 1] == obj.time:
                idx -= 1
            if idx % 2 == 0:
                if obj.lane == -1:
                    obj.x = 255
                else:
                    obj.x = 256
                obj.y = 0

    def _get_current_state(self, reference_state=None):
        if not self.beatmap:
            return None
        reference_objects = reference_state.get('hit_objects', ()) if reference_state else ()
        reference_by_uid = None
        hit_objects = []
        for index, obj in enumerate(self.beatmap.hit_objects):
            obj_data = (
                obj.x,
                obj.y,
                obj.time,
                obj.type,
                obj.hitSound,
                obj.objectParams,
                obj.hitSample,
                obj.order_index,
                obj.creation_time,
                obj.last_update_time,
                obj.tc_is_blue,
                obj.uid,
                custom_object_data_to_tuple(obj.custom_data)
            )
            shared_data = None
            matched_position = False
            if index < len(reference_objects):
                candidate = reference_objects[index]
                if candidate[11] == obj.uid:
                    matched_position = True
                    if candidate == obj_data:
                        shared_data = candidate
            if shared_data is None and reference_objects and not matched_position:
                if reference_by_uid is None:
                    reference_by_uid = {item[11]: item for item in reference_objects}
                candidate = reference_by_uid.get(obj.uid)
                if candidate == obj_data:
                    shared_data = candidate
            hit_objects.append(shared_data if shared_data is not None else obj_data)

        reference_timing = reference_state.get('timing_points', ()) if reference_state else ()
        timing_points = []
        for index, tp in enumerate(self.beatmap.timing_points):
            tp_data = (tp['time'], tp['bpm'], tp.get('creation_time', 0.0))
            if index < len(reference_timing) and reference_timing[index] == tp_data:
                tp_data = reference_timing[index]
            timing_points.append(tp_data)

        return {
            'hit_objects': hit_objects,
            'timing_points': timing_points
        }

    def release_bpm_tag(self):
        if hasattr(self, 'dragging_bpm_tag') and self.dragging_bpm_tag:
             self.apply_bpm_follow_state(getattr(self, 'bpm_follow_drag_state', None))
             self.bpm_drag_release_times[id(self.dragging_bpm_tag)] = time.time()
             if id(self.dragging_bpm_tag) in self.bpm_drag_start_times:
                  del self.bpm_drag_start_times[id(self.dragging_bpm_tag)]
             
             tp = self.dragging_bpm_tag
             tp['_target_visual_time'] = tp['time']
             if tp not in self.bpm_interpolating:
                 self.bpm_interpolating.append(tp)
              
             self.dragging_bpm_tag = None
             self.bpm_follow_drag_state = None

    def mouseReleaseEvent(self, e: QMouseEvent):
        if getattr(self.editor, 'start_screen', None) and self.editor.start_screen.isVisible():
            return
        sf = getattr(self.editor, 'global_scale', 1.0)
        if sf != 1.0:
            p = e.position()
            e = QMouseEvent(e.type(), QPointF(p.x() / sf, p.y() / sf), e.globalPosition(), e.button(), e.buttons(), e.modifiers())
        
        if hasattr(self, 'dragging_bpm_tag') and self.dragging_bpm_tag:
             self.release_bpm_tag()

        self.edge_scroll_timer.stop()
        if hasattr(self, 'drag_start_mouse_time'):
            del self.drag_start_mouse_time
        
        if e.button() == Qt.MouseButton.LeftButton:
            if self.timeline_click_pos and not self.selection_rect and not self.dragging_objects:
                center_y = self.height() / 2
                lane_0_y = center_y - LANE_HEIGHT / 2
                lane_1_y = center_y + LANE_HEIGHT / 2
                in_lane_area = (lane_0_y - 40 < self.timeline_click_pos.y() < lane_1_y + 40)
                
                if not in_lane_area and not self.selected_objects and not self.editor.is_playing:
                    ms = self.x_to_ms(self.timeline_click_pos.x())
                    snapped_ms = int(self.get_snap_time(ms))
                    
                    song_length_ms = self.get_visual_song_length()
                    if snapped_ms >= 0 and (song_length_ms == 0 or snapped_ms <= song_length_ms):
                        self.target_time = snapped_ms
                        self.editor.sync_audio_to_time()
                        self.update_scrollbar()
            
            if self.dragging_objects:
                event_changed = any(
                    obj.is_event
                    and obj.time != self.drag_start_time_map.get(obj, obj.time)
                    for obj in self.selected_objects
                )
                toggle_center_changed = any(
                    obj.is_toggle_center
                    and obj.time != self.drag_start_time_map.get(obj, obj.time)
                    for obj in self.selected_objects
                )
                if event_changed and self._live_event_cache_dirty:
                    self.rebuild_live_event_cache()
                if toggle_center_changed:
                    self.finalize_toggle_center_drag()
                if self.undo_stack and self.undo_stack[-1] == self._get_current_state(self.undo_stack[-1]):
                    self.undo_stack.pop()
                
                current_time = time.time()
                current_drag_mode = self.drag_mode
                for obj in self.selected_objects:
                    self.drag_release_times[obj] = current_time
                    self.drag_release_mode[obj] = current_drag_mode
                    
                    if hasattr(obj, 'time'):
                        obj._target_visual_time = obj.time
                    if hasattr(obj, 'end_time') and (obj.type == 128 or self.is_custom_length(obj)):
                        obj._target_visual_end_time = obj.end_time
                    
                    if hasattr(obj, 'lane'):
                         obj._target_visual_lane = self.get_visual_lane_value(obj)
                         pair = self.get_pair_lane(obj.lane)
                         if pair is not None:
                             obj._target_visual_pair_lane = float(pair)

                    if obj in self.drag_start_times:
                        del self.drag_start_times[obj]
                
                for obj in list(self.selected_objects):
                    if hasattr(obj, 'lane') and not obj.is_event and obj.custom_data is None:
                        self.auto_set_tc_order_for_note(obj.time)
                
                pk = self.pressed_keys | getattr(self.editor, 'pressed_keys', set())
                is_shift = check_modifier(e.modifiers(), getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("multiselect_modifier", "Shift"), pk)
                is_alt = check_modifier(e.modifiers(), getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("range_select_modifier", "Alt"), pk)
                is_alt_ctrl = check_modifier(e.modifiers(), getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("range_select_type_modifier", "Ctrl+Alt"), pk)
                
                if not is_shift and not is_alt and not is_alt_ctrl:
                    self.selected_objects.clear()
                
                if hasattr(self, '_temp_resize_obj') and self._temp_resize_obj:
                    self.selected_objects.discard(self._temp_resize_obj)
                    self._temp_resize_obj = None
            
            if self.beatmap and hasattr(self.beatmap, "hit_objects"):
                self.beatmap.hit_objects.sort(key=lambda x: (x.time, 0 if x.is_event and x.order_index == 0 else (2 if x.is_event else 1), 0 if getattr(x, 'is_freestyle', False) else 1, 0.5 if not x.is_event else float(x.order_index)))
                self._force_cache_update = True
            
            self.dragging_objects = False
            self.last_mouse_pos = None
            self.selection_start = None
            self.selection_start_y = None
            self.selection_rect = None
            self.selection_last_mouse_y = None
            self.timeline_click_pos = None
            
            if hasattr(self.editor, 'update_add_bpm_button_text'):
                self.editor.update_add_bpm_button_text()
            self.update()

    def copy_selected(self):
        if not self.selected_objects:
            return
        
        self.clipboard = []
        copyable = [obj for obj in self.selected_objects if not self.is_custom_missing(obj)]
        if not copyable:
            return
        min_time = min(obj.time for obj in copyable)
        
        for obj in sorted(copyable, key=lambda o: o.time):
            relative_time = obj.time - min_time
            duration = 0
            if obj.type == 128 or self.is_custom_length(obj):
                duration = obj.end_time - obj.time
                
            self.clipboard.append({
                'relative_time': relative_time,
                'duration': duration,
                'x': obj.x,
                'y': obj.y,
                'type': obj.type,
                'hitSound': obj.hitSound,
                'objectParams': obj.objectParams,
                'hitSample': obj.hitSample,
                'order_index': obj.order_index,
                'custom_data': custom_object_data_to_tuple(obj.custom_data)
            })
            
        self.selected_objects.clear()
        self.update()

    def paste_clipboard(self):
                
        if not self.clipboard or not self.beatmap:
            return
        
        paste_visual = self.get_snap_time(self.current_time)
        paste_time = int(round(self.visual_to_audio_ms(paste_visual)))
        
        possible_objects = []
        blocked_objects = []
        pending_tc_events = []
        
        for item in self.clipboard:
            new_time = paste_time + item['relative_time']
            if new_time >= 0 and not item.get('custom_data'):
                dummy = HitObject(
                    item['x'], item['y'], new_time, item['type'], 
                    item['hitSound'], item['objectParams'], item['hitSample'], 
                    item.get('order_index', 0)
                )
                if dummy.is_toggle_center:
                    pending_tc_events.append(dummy)
                    
        for item in self.clipboard:
            new_time = paste_time + item['relative_time']
            if new_time >= 0:
                if item.get('custom_data'):
                    custom_data = custom_object_data_from_tuple(item['custom_data'])
                    type_data = get_custom_type(custom_data.type_id)
                    if type_data is None:
                        continue
                    new_end = new_time + item['duration'] if type_data.get('length') else new_time
                    custom_data.end_time = int(new_end)
                    custom_data.missing = False
                    lane_x, lane_y = custom_lane_values(custom_data.lane)
                    custom_data.raw_line = render_custom_template(type_data['syntax'], {
                        'time': new_time,
                        'end': new_end,
                        'lane': custom_data.lane,
                    }, type_data)
                    custom_obj = HitObject(
                        lane_x,
                        lane_y,
                        new_time,
                        item['type'],
                        item['hitSound'],
                        item['objectParams'],
                        item['hitSample'],
                        item.get('order_index', 0),
                        custom_data=custom_data,
                    )
                    if self.is_custom_space_free(new_time, new_end, custom_data.lane, type_data):
                        possible_objects.append(custom_obj)
                    else:
                        blocked_objects.append(custom_obj)
                    continue
                params = item['objectParams']
                if item['type'] == 128:
                    new_end = new_time + item['duration']
                    params = str(int(new_end))

                new_obj_dummy = HitObject(
                    item['x'],
                    item['y'],
                    new_time,
                    item['type'],
                    item['hitSound'],
                    params, 
                    item['hitSample'],
                    item.get('order_index', 0)
                )
                
                check_lane = new_obj_dummy.lane
                end_t = new_obj_dummy.end_time
                is_sc = new_obj_dummy.is_screamer
                is_sp = new_obj_dummy.is_spam
                is_bhs = new_obj_dummy.is_brawl_hold or new_obj_dummy.is_brawl_spam
                is_fs = new_obj_dummy.is_freestyle
                is_spk = new_obj_dummy.is_spike

                is_b_note = new_obj_dummy.is_brawl_hit or new_obj_dummy.is_brawl_final or new_obj_dummy.is_brawl_hold

                if not new_obj_dummy.is_event and not new_obj_dummy.is_freestyle and check_lane in [-1, 2] and not self.is_time_in_toggle_center(new_time, pending_events=pending_tc_events):
                    new_obj_dummy.y = 256
                    new_obj_dummy.x = 255 if check_lane == -1 else 256
                    check_lane = new_obj_dummy.lane

                if not self.is_space_free(new_time, end_t, check_lane, ignore_obj=None, is_screamer=is_sc, is_spam=is_sp, is_brawl_hold_spam=is_bhs, is_freestyle=is_fs, is_spike=is_spk, ignore_notes=new_obj_dummy.is_event, is_brawl=is_b_note, pending_events=pending_tc_events):
                    blocked_objects.append(new_obj_dummy)
                else:
                    possible_objects.append(new_obj_dummy)
        
        if blocked_objects:
            if not hasattr(self, 'flashing_blocked_objects'):
                self.flashing_blocked_objects = []
            curr_t = time.time()
            for obj in blocked_objects:
                self.flashing_blocked_objects.append((obj, curr_t))
            self.editor.play_ui_sound_suppressed('UI Error', 0.5)
            self.update()
            return
        
        self.save_undo_state()
        self.selected_objects.clear()
        
        for obj in possible_objects:
            self.beatmap.hit_objects.append(obj)
            self.selected_objects.add(obj)
        
        self.editor.mark_unsaved()
        if self.beatmap and self.beatmap.hit_objects:
             self.beatmap.hit_objects.sort(key=lambda x: (x.time, 0 if x.is_event and x.order_index == 0 else (2 if x.is_event else 1), 0 if getattr(x, 'is_freestyle', False) else 1, 0.5 if not x.is_event else float(x.order_index)))
        self.sync_structural_object_caches(possible_objects)
        self.update()

    def wheelEvent(self, event: QWheelEvent):
        if getattr(self.editor, 'start_screen', None) and self.editor.start_screen.isVisible():
            event.ignore()
            return
        if not self.beatmap or self.beatmap.metadata.ActualAudioLength <= 0: return

        modifiers = QApplication.keyboardModifiers()
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.angleDelta().x()
        if delta == 0:
            return

        if bool(modifiers & Qt.KeyboardModifier.ControlModifier) and not bool(modifiers & Qt.KeyboardModifier.AltModifier):
            if delta < 0: self.target_zoom /= 1.1
            else: self.target_zoom *= 1.1
            self.target_zoom = max(0.1, min(10.0, self.target_zoom))
        else:
            if getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("invert_scroll", False):
                delta = -delta

            song_length_ms = self.get_visual_song_length()
            if self.beatmap and self.beatmap.metadata.BPM > 0 and not self.editor.is_playing:
                bpm = self.beatmap.metadata.BPM
                beat_len = 60000 / bpm
                snap_len = beat_len / self.grid_snap_div
                offset = self.get_segment_offset_visual(self.target_time)
                
                default_boxes = self.grid_snap_div // 2
                if default_boxes < 1:
                    default_boxes = 1
                
                zoom_factor = max(0.1, min(10.0, self.zoom))
                boxes_to_scroll = float(default_boxes)
                
                if zoom_factor > 1.0:
                    zoom_steps = 0
                    temp_zoom = zoom_factor
                    while temp_zoom > 1.5:
                        zoom_steps += 1
                        temp_zoom /= 1.5
                    
                    for _ in range(zoom_steps):
                        if boxes_to_scroll > 1:
                            boxes_to_scroll = boxes_to_scroll / 2
                            if boxes_to_scroll != int(boxes_to_scroll):
                                boxes_to_scroll = int(boxes_to_scroll) + 1
                        else:
                            boxes_to_scroll = boxes_to_scroll / 2
                elif zoom_factor < 1.0:
                    zoom_steps = 0
                    temp_zoom = zoom_factor
                    while temp_zoom < 0.5:
                        zoom_steps += 1
                        temp_zoom *= 2
                    
                    for _ in range(zoom_steps):
                        boxes_to_scroll = boxes_to_scroll * 2
                
                pk = self.pressed_keys | getattr(self.editor, 'pressed_keys', set())
                if check_modifier(modifiers, getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("faster_modifier", "Shift"), pk):
                    boxes_to_scroll *= 2
                
                if boxes_to_scroll >= 1:
                    scroll_time = boxes_to_scroll * snap_len
                    sub_snap_len = snap_len
                else:
                    sub_divisions = 1
                    temp_boxes = boxes_to_scroll
                    while temp_boxes < 1:
                        sub_divisions *= 2
                        temp_boxes *= 2
                    sub_snap_len = snap_len / sub_divisions
                    scroll_time = sub_snap_len
                
                scroll_aligned_pos = (self.target_time - offset) / scroll_time
                scroll_aligned_snapped = round(scroll_aligned_pos) * scroll_time + offset
                off_grid_distance = abs(self.target_time - scroll_aligned_snapped)
                
                if off_grid_distance > 0.5:
                    if delta > 0:
                        target_snapped = int(scroll_aligned_pos + 1) * scroll_time + offset
                    else:
                        target_snapped = int(scroll_aligned_pos) * scroll_time + offset
                        if target_snapped >= self.target_time:
                            target_snapped = (int(scroll_aligned_pos) - 1) * scroll_time + offset
                else:
                    if delta > 0:
                        target_snapped = scroll_aligned_snapped + scroll_time
                    else:
                        target_snapped = scroll_aligned_snapped - scroll_time
                
                if target_snapped < 0:
                    overshoot = -target_snapped
                    target_snapped = - (overshoot ** 0.98)
                elif song_length_ms > 0:
                    max_grid_time = int((song_length_ms - offset) / scroll_time) * scroll_time + offset
                    if target_snapped > max_grid_time:
                        overshoot = target_snapped - max_grid_time
                        target_snapped = max_grid_time + (overshoot ** 0.98)

                self.target_time = target_snapped
            else:
                base_scroll = 200
                scroll_amount = base_scroll * (1.0 / max(0.1, self.zoom))

                pk = self.pressed_keys | getattr(self.editor, 'pressed_keys', set())
                if check_modifier(modifiers, getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("faster_modifier", "Shift"), pk):
                    scroll_amount *= 4.0

                if self.target_time < 0 or (song_length_ms > 0 and self.target_time > song_length_ms):
                    scroll_amount *= 0.95

                if delta > 0:
                    self.target_time += scroll_amount
                else:
                    self.target_time -= scroll_amount
            
            if self.editor.is_playing:
                if self.target_time < 0: self.target_time = 0
                if song_length_ms > 0 and self.target_time > song_length_ms:
                    self.target_time = song_length_ms

                self.current_time = self.target_time
                self.editor.sync_audio_to_time(force_play=True)
            
            if self.dragging_objects:
                self.update_dragged_objects()
            
            if hasattr(self, 'dragging_bpm_tag') and self.dragging_bpm_tag and hasattr(self, 'last_mouse_pos'):
                new_x = self.last_mouse_pos.x()
                offset = getattr(self, 'bpm_drag_offset', 0)
                new_visual_raw = self.x_to_ms(new_x) + offset
                new_time = float(self.visual_to_audio_ms(new_visual_raw, ignore_bpm_tag=self.dragging_bpm_tag))
                if new_time < 0: new_time = 0
                audio_len = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap.metadata.ActualAudioLength > 0 else 0
                if audio_len > 0 and new_time > audio_len:
                    new_time = audio_len
                follow_state = getattr(self, 'bpm_follow_drag_state', None)
                if follow_state and audio_len > 0:
                    new_time = min(new_time, max(0.0, audio_len - self.get_bpm_follow_max_offset(follow_state)))
                for tp in self.beatmap.timing_points:
                    if tp is not self.dragging_bpm_tag:
                        if abs(tp['time'] - new_time) < 0.001:
                            if new_time > tp['time']: new_time = tp['time'] + 0.01
                            else: new_time = tp['time'] - 0.01
                self.dragging_bpm_tag['time'] = new_time
                self.dragging_bpm_tag['_target_visual_time'] = float(new_time)
                self.update_bpm_follow_preview(follow_state)
                self.beatmap.timing_points.sort(key=lambda x: x['time'])
                if hasattr(self.editor, 'update_bpm_list'):
                    self.editor.update_bpm_list()

            self.update_selection_rect()

    def validate_deletion(self, to_remove_list):
        has_tc_event = any(getattr(o, 'is_event', False) and getattr(o, 'is_toggle_center', False) for o in to_remove_list)
        if not has_tc_event:
            return []
            
        stranded_notes = []
        to_remove = set(to_remove_list)
        simulated_objects = [o for o in self.beatmap.hit_objects if o not in to_remove]
        
        centers = []
        for obj in simulated_objects:
            if getattr(obj, 'is_event', False) and getattr(obj, 'is_toggle_center', False):
                centers.append(obj)
        centers.sort(key=lambda x: (x.time, 0 if x.is_event and x.order_index == 0 else (2 if x.is_event else 1), 0 if getattr(x, 'is_freestyle', False) else 1, 0.5 if not x.is_event else float(x.order_index)))
        center_times = [c.time for c in centers]
        
        for obj in simulated_objects:
            if getattr(obj, 'is_event', False) or getattr(obj, 'is_freestyle', False) or getattr(obj, 'is_spike', False):
                continue
            if obj.lane in [-1, 2]:
                ms = obj.time
                idx = bisect.bisect_right(center_times, ms)
                if idx > 0 and idx % 2 == 0 and center_times[idx - 1] == ms:
                    idx -= 1
                if idx % 2 == 0:
                    stranded_notes.append(obj)
        return stranded_notes

    def keyPressEvent(self, e: QKeyEvent):
        if getattr(self.editor, 'start_screen', None) and self.editor.start_screen.isVisible():
            e.ignore()
            return
        if not e.isAutoRepeat():
            self.pressed_keys.add(e.key())
        if not self.beatmap or self.beatmap.metadata.ActualAudioLength <= 0: return
        
        kb = getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS)
        pk = self.pressed_keys | getattr(self.editor, 'pressed_keys', set())

        is_left = check_keybind_match(kb.get("timeline_left", "Left"), e.key(), e.modifiers(), pk)
        is_right = check_keybind_match(kb.get("timeline_right", "Right"), e.key(), e.modifiers(), pk)
        is_jump_start = check_keybind_match(kb.get("jump_start", "Shift+Space"), e.key(), e.modifiers(), pk)
        is_jump_end = check_keybind_match(kb.get("jump_end", "Ctrl+Space"), e.key(), e.modifiers(), pk)
        is_space = check_keybind_match(kb.get("play_pause", "Space"), e.key(), e.modifiers(), pk)
        is_g = check_keybind_match(kb.get("smooth_placement", "G"), e.key(), e.modifiers(), pk)
        is_video_preview = check_keybind_match_exact(kb.get("toggle_video_preview", "V"), e.key(), e.modifiers(), pk)

        if e.isAutoRepeat():
            if not (is_left or is_right):
                e.ignore()
                return

        if is_left or is_right:
            if getattr(self.editor, 'is_playing', False): return

            bpm = self.beatmap.metadata.BPM if self.beatmap and self.beatmap.metadata.BPM > 0 else 120
            if check_modifier(e.modifiers(), kb.get("faster_modifier", "Shift"), pk):
                snap_len = 60000 / bpm
            else:
                snap_len = (60000 / bpm) / getattr(self, 'grid_snap_div', 4)

            offset = self.get_segment_offset_visual(self.target_time)

            import math
            eps = 0.5
            if is_left:
                new_t = math.floor((self.target_time - offset - eps) / snap_len) * snap_len + offset
            else:
                new_t = math.ceil((self.target_time - offset + eps) / snap_len) * snap_len + offset

            self.target_time = max(0.0, float(new_t))
            song_len = self.get_visual_song_length()
            if song_len > 0:
                self.target_time = min(self.target_time, float(song_len))

            if hasattr(self.editor, 'sync_audio_to_time'):
                self.editor.sync_audio_to_time()
            self.update_scrollbar()
            self.update()
            return

        if is_video_preview:
            self.editor.toggle_video_preview()
            e.accept()
            return

        if is_g:
            self.is_g_pressed = True
            self.update_dragged_objects()
            self.update()

        if is_jump_start:
            self.current_time = 0
            self.target_time = 0
            if hasattr(self.editor, 'sync_audio_to_time'):
                self.editor.sync_audio_to_time()
            self.update_scrollbar()
            self.update()
            e.accept()
            return

        if is_jump_end:
            song_len = self.get_visual_song_length()
            if song_len > 0:
                if getattr(self.editor, 'is_playing', False):
                    self.editor.is_playing = False
                    self.editor.stop_music_playback()
                    self.editor.stop_all_hold_sounds()
                    if getattr(self.editor, 'sidebar_vis', None):
                        self.editor.sidebar_vis.set_active(False)
                self.current_time = float(song_len)
                self.target_time = float(song_len)
                if hasattr(self.editor, 'sync_audio_to_time'):
                    self.editor.sync_audio_to_time()
                self.update_scrollbar()
                self.update()
            e.accept()
            return

        if is_space:
            self.editor.toggle_play()
            e.accept()
            return

        if e.key() == Qt.Key.Key_A and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.beatmap:
                self.selected_objects = set(self.beatmap.hit_objects)
                self.update()
            e.accept()
        elif e.key() == Qt.Key.Key_C and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.copy_selected()
            e.accept()
        elif e.key() == Qt.Key.Key_V and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.paste_clipboard()
            e.accept()
        elif e.key() == Qt.Key.Key_Z and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
             if hasattr(self, 'undo_redo_timer') and self.undo_redo_timer.isActive():
                 e.accept()
                 return
             
             if not hasattr(self, 'undo_redo_timer'):
                 self.undo_redo_timer = QTimer(self)
                 self.undo_redo_timer.timeout.connect(self.perform_undo_redo_action)
             
             self.current_undo_key = (e.key(), e.modifiers())
             self.perform_undo_redo_action()
             
             try: self.undo_redo_timer.timeout.disconnect()
             except: pass
             
             def fast_repeat():
                self.perform_undo_redo_action()
                self.undo_redo_timer.setInterval(50)

             self.undo_redo_timer.timeout.connect(fast_repeat)
             self.undo_redo_timer.start(500)
             e.accept()

        elif e.key() == Qt.Key.Key_Y and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
             if hasattr(self, 'undo_redo_timer') and self.undo_redo_timer.isActive():
                 e.accept()
                 return
             
             if not hasattr(self, 'undo_redo_timer'):
                 self.undo_redo_timer = QTimer(self)
                 self.undo_redo_timer.timeout.connect(self.perform_undo_redo_action)
             
             self.current_undo_key = (e.key(), e.modifiers())
             self.perform_undo_redo_action()
             
             try: self.undo_redo_timer.timeout.disconnect()
             except: pass
             
             def fast_repeat():
                self.perform_undo_redo_action()
                self.undo_redo_timer.setInterval(50)

             self.undo_redo_timer.timeout.connect(fast_repeat)
             self.undo_redo_timer.start(500)
             e.accept()
        elif e.key() == Qt.Key.Key_Delete or e.key() == Qt.Key.Key_Backspace:
            if self.selected_objects and self.beatmap:
                to_remove_list = list(self.selected_objects)
                stranded = self.validate_deletion(to_remove_list)
                if stranded:
                    if not hasattr(self, 'flashing_blocked_objects'):
                        self.flashing_blocked_objects = []
                    curr_t = time.time()
                    for o in stranded:
                        self.flashing_blocked_objects.append((o, curr_t))
                    self.editor.play_ui_sound_suppressed('UI Error', 0.5)
                    self.update()
                    e.accept()
                    return

                self.save_undo_state()

                avg_time = sum(o.time for o in self.selected_objects) / len(self.selected_objects)
                obj_x = self.audio_ms_to_x(avg_time)
                global_x = self.mapToGlobal(QPoint(int(obj_x), 0)).x()
                pan = self.editor.calculate_pan(global_x)
                self.editor.play_ui_sound_suppressed('UI Delete', pan)

                selected = set(self.selected_objects)
                self.queue_delete_animations(selected)
                self.beatmap.hit_objects = [
                    obj for obj in self.beatmap.hit_objects
                    if obj not in selected
                ]
                self.selected_objects.clear()
                self.editor.mark_unsaved()
                self.sync_structural_object_caches(selected)
                self.update()
            e.accept()
        elif e.key() == Qt.Key.Key_Shift:
            e.accept()
        else:
            super().keyPressEvent(e)

    def keyReleaseEvent(self, e: QKeyEvent):
        if not e.isAutoRepeat():
            self.pressed_keys.discard(e.key())
        if e.isAutoRepeat():
            e.ignore()
            return

        if e.key() in (Qt.Key.Key_Alt, Qt.Key.Key_Control, Qt.Key.Key_Meta) or not check_modifier(QApplication.keyboardModifiers(), getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("range_select_modifier", "Alt"), self.pressed_keys):
            self.range_select_anchor = None


            
        if e.key() == get_key(getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("smooth_placement", "G")):
            self.is_g_pressed = False
            self.update_dragged_objects()
            self.update()

        if e.key() == Qt.Key.Key_Z or e.key() == Qt.Key.Key_Y:
            if hasattr(self, 'undo_redo_timer') and self.undo_redo_timer.isActive():
                self.undo_redo_timer.stop()
        
        super().keyReleaseEvent(e)


        
    def perform_undo_redo_action(self):
        if not hasattr(self, 'current_undo_key'): return
        
        key, modifiers = self.current_undo_key
        
        if key == Qt.Key.Key_Z:
             if modifiers & Qt.KeyboardModifier.ShiftModifier:
                 self.redo()
             else:
                 self.undo()
        elif key == Qt.Key.Key_Y:
             self.redo()

