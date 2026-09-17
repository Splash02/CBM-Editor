from .dialogs import *
from PyQt6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, pyqtProperty
from PyQt6.QtGui import QCursor, QPainterPath, QPicture, QRegion
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QStyle, QStyleOptionTab, QStyleOptionViewItem, QStyledItemDelegate, QTabBar, QTabWidget
from .timeline_side_panel import *
from .timeline_rendering import TimelineRenderingMixin
from .timeline_interaction import TimelineInteractionMixin

register_shared_globals(globals())

class TimelineWidget(TimelineRenderingMixin, TimelineInteractionMixin, QOpenGLWidget):
    def __init__(self, editor):
        super().__init__()
        surface_format = self.format()
        surface_format.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
        surface_format.setSamples(4)
        self.setFormat(surface_format)
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
        self.bpm_follow_drag_states = []
        self.bpm_drag_initial_times = {}
        self.selected_timing_points = []
        
        self.selected_objects: Set[HitObject] = set()
        self.clipboard: List[Dict] = []
        self.clipboard_history = []
        self._clipboard_history_generation = 0
        self.active_clipboard_entry = None
        
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
        self.selection_kind = None
        self._drag_base_timing_selection = []
        
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
        self.gp_drag_preview_visual_time = None
        self._timeline_text_path_cache = {}
        self._timeline_text_image_cache = {}
        self._lane_background_cache_key = None
        self._lane_background_cache_paths = None
        self._direction_strip_cache_key = None
        self._direction_strip_cache_data = None
        self._static_event_picture_cache = {}
        
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
        self._undo_chunk_size = 256
        self._undo_object_chunks = []
        self._undo_uid_locations = {}
        self._undo_chunks_beatmap_id = None
        self._undo_chunks_dirty = True
        
        self.elapsed_timer = QElapsedTimer()
        self.elapsed_timer.start()
        self.last_frame_time = self.elapsed_timer.elapsed()
        self.frameSwapped.connect(self.frame_update)

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
        self.side_panel = TimelineSidePanel(self)
        
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, 'gp_visual_times'):
            self.gp_visual_times.clear()
            self.gp_visual_last_frame = time.perf_counter()
            self.gp_drag_preview_visual_time = None
        if hasattr(self, 'side_panel'):
            self.side_panel.reposition()
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        self.last_frame_time = self.elapsed_timer.elapsed()
        self._last_edge_scroll_tick = time.perf_counter()
        self.update()

    def draw_timeline_text(self, painter, rect, alignment, text):
        text = str(text)
        if not text:
            return
        font = QFont(painter.font())
        key = (font.toString(), text)
        path = self._timeline_text_path_cache.get(key)
        if path is None:
            path = QPainterPath()
            path.addText(0.0, 0.0, font, text)
            if len(self._timeline_text_path_cache) >= 512:
                self._timeline_text_path_cache.pop(next(iter(self._timeline_text_path_cache)))
            self._timeline_text_path_cache[key] = path
        bounds = path.boundingRect()
        if alignment & Qt.AlignmentFlag.AlignHCenter:
            offset_x = rect.center().x() - bounds.center().x()
        elif alignment & Qt.AlignmentFlag.AlignRight:
            offset_x = rect.right() - bounds.right()
        else:
            offset_x = rect.left() - bounds.left()
        if alignment & Qt.AlignmentFlag.AlignVCenter:
            offset_y = rect.center().y() - bounds.center().y()
        elif alignment & Qt.AlignmentFlag.AlignBottom:
            offset_y = rect.bottom() - bounds.bottom()
        else:
            offset_y = rect.top() - bounds.top()
        painter.save()
        painter.translate(offset_x, offset_y)
        painter.setBrush(painter.pen().brush())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.drawPath(path)
        painter.restore()

    def draw_timeline_raster_text(self, painter, rect, alignment, text):
        text = str(text)
        if not text:
            return
        font = QFont(painter.font())
        color = painter.pen().color()
        dpr = max(1.0, float(self.devicePixelRatioF()))
        ui_scale = max(0.1, float(getattr(self.editor, 'global_scale', 1.0)))
        raster_scale = max(1.0, dpr * ui_scale)
        width = max(1.0, float(rect.width()))
        height = max(1.0, float(rect.height()))
        key = (font.toString(), color.rgba(), round(raster_scale, 3), round(width, 2), round(height, 2), int(alignment), text)
        image = self._timeline_text_image_cache.get(key)
        if image is None:
            image = QImage(max(1, int(math.ceil(width * raster_scale))), max(1, int(math.ceil(height * raster_scale))), QImage.Format.Format_ARGB32_Premultiplied)
            image.setDevicePixelRatio(raster_scale)
            image.fill(Qt.GlobalColor.transparent)
            image_painter = QPainter(image)
            image_painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            image_painter.setFont(font)
            image_painter.setPen(color)
            image_painter.drawText(QRectF(0.0, 0.0, width, height), alignment, text)
            image_painter.end()
            if len(self._timeline_text_image_cache) >= 32:
                self._timeline_text_image_cache.pop(next(iter(self._timeline_text_image_cache)))
            self._timeline_text_image_cache[key] = image
        painter.drawImage(rect.topLeft(), image)

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
            order_ranks = {
                uid: index
                for ordered_uids in self.beatmap.object_order_overrides.values()
                for index, uid in enumerate(ordered_uids)
            }
            self.beatmap.hit_objects.sort(
                key=lambda obj: (
                    obj.time,
                    0 if obj.uid in order_ranks else 1,
                    order_ranks.get(obj.uid, 0),
                    0 if obj.is_event and obj.order_index == 0 else (2 if obj.is_event else 1),
                    0 if getattr(obj, 'is_freestyle', False) else 1,
                    0.5 if not obj.is_event else float(obj.order_index),
                )
            )
            self._cached_all_objs = self.beatmap.hit_objects
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
                if obj.custom_data is None:
                    obj.undo_data()
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
            self._cached_direction_uids = {
                obj.uid
                for obj in self._cached_all_objs
                if not obj.is_event and not obj.is_freestyle and obj.custom_data is None
            }
            self._direction_numpy_cache_dirty = False
            self._cached_hit_object_times = [o.time for o in self._cached_all_objs]
            self._cached_obj_times = self._cached_hit_object_times
            self._cached_object_uids = [o.uid for o in self._cached_all_objs]
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
            self._cached_freestyle_uids = {
                obj.uid for obj in self._cached_all_objs if obj.is_freestyle
            }
            self._has_freestyle_objects = bool(self._cached_freestyle_uids)
            self.rebuild_freestyle_preview_states()

        if (timing_dirty or object_dirty) and self.beatmap:
            all_objects = getattr(self, '_cached_all_objs', self.beatmap.hit_objects)
            self._cached_obj_visual_times = {
                obj.uid: self.audio_to_visual_ms(obj.time)
                for obj in all_objects
            }
            self._cached_obj_visual_end_times = {
                obj.uid: self.audio_to_visual_ms(obj.end_time)
                for obj in all_objects
                if obj.end_time != obj.time
            }
            if self.timeline_scrollbar and hasattr(self.timeline_scrollbar, "invalidate_overview"):
                self.timeline_scrollbar.invalidate_overview()
                

    def ensure_object_cache(self):
        if not self.beatmap:
            return
        if (
            getattr(self, '_force_cache_update', False)
            or getattr(self, '_last_beatmap_id', None) != id(self.beatmap)
            or getattr(self, '_last_ho_len', -1) != len(self.beatmap.hit_objects)
        ):
            self.update_caches_if_needed()

    def rebuild_direction_numpy_cache(self):
        note_times = self._cached_direction_note_times
        note_values = self._cached_direction_note_values
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
        self._direction_numpy_cache_dirty = False

    def rebuild_freestyle_preview_states(self):
        if not self.beatmap:
            return
        if not getattr(self, "_has_freestyle_objects", False):
            self._preview_small_freestyle_uids = set()
            return
        objects = getattr(self, "_cached_all_objs", None)
        if objects is None or len(objects) != len(self.beatmap.hit_objects):
            objects = sorted(
                self.beatmap.hit_objects,
                key=lambda obj: (
                    obj.time,
                    0 if obj.is_event and obj.order_index == 0 else (2 if obj.is_event else 1),
                    0 if obj.is_freestyle else 1,
                    0.5 if not obj.is_event else float(obj.order_index),
                ),
            )
        is_right = True
        is_centered = False
        chain_active = False
        chain_is_right = True
        small_freestyle_uids = set()
        has_freestyle = False

        for obj in objects:
            if obj.is_toggle_center:
                was_centered = is_centered
                is_centered = not is_centered
                if was_centered and obj.tc_is_blue is not None:
                    is_right = bool(obj.tc_is_blue)
                continue

            if obj.is_flip or obj.is_instant_flip:
                is_right = not is_right
                chain_active = False
                continue

            if obj.is_freestyle:
                has_freestyle = True
                is_continuation = chain_active and chain_is_right == is_right
                if is_continuation:
                    small_freestyle_uids.add(obj.uid)
                chain_active = True
                chain_is_right = is_right
                continue

            if obj.is_event:
                continue

            custom_type = self.get_custom_type_data(obj)
            if custom_type is not None and custom_type.get("kind") == "Event":
                continue

            chain_active = False
            if obj.custom_data is None and is_centered:
                if obj.lane in (0, 1):
                    is_right = True
                elif obj.lane in (-1, 2):
                    is_right = False
        self._has_freestyle_objects = has_freestyle
        self._preview_small_freestyle_uids = small_freestyle_uids

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
        previous_data_by_uid = {}
        for obj in changed_objects:
            location = self._undo_uid_locations.get(obj.uid)
            if location is not None:
                previous_data_by_uid[obj.uid] = location[0][location[1]]
        previous_times = getattr(self, '_cached_hit_object_times', ())
        previous_uids = getattr(self, '_cached_object_uids', ())
        can_patch_order = (
            len(previous_times) == len(previous_uids)
            and len(changed_objects) <= 8
        )
        if can_patch_order:
            object_times = list(previous_times)
            object_uids = list(previous_uids)
            for obj in changed_objects:
                try:
                    old_index = object_uids.index(obj.uid)
                except ValueError:
                    continue
                object_uids.pop(old_index)
                object_times.pop(old_index)
            insertions = []
            for obj in changed_objects:
                try:
                    insertions.append((objects.index(obj), obj))
                except ValueError:
                    pass
            for object_index, obj in sorted(insertions, key=lambda item: item[0]):
                object_uids.insert(object_index, obj.uid)
                object_times.insert(object_index, obj.time)
            if len(object_times) != len(objects):
                can_patch_order = False
        if not can_patch_order:
            object_times = [obj.time for obj in objects]
            object_uids = [obj.uid for obj in objects]
        changed_uids = {obj.uid for obj in changed_objects}
        if len(changed_uids) <= 8:
            present_changed_uids = {uid for uid in changed_uids if uid in object_uids}
        else:
            present_changed_uids = changed_uids.intersection(object_uids)
        self._last_beatmap_id = id(self.beatmap)
        self._last_ho_len = len(objects)
        self._force_cache_update = False
        self._object_cache_generation = getattr(self, '_object_cache_generation', 0) + 1
        self._cached_all_objs = objects
        self._cached_hit_object_times = object_times
        self._cached_obj_times = self._cached_hit_object_times
        self._cached_object_uids = object_uids

        cached_tail_objects = getattr(self, "_cached_tail_start_objs", ())
        tail_changed = any(
            obj in cached_tail_objects
            or obj.is_hold
            or obj.is_screamer
            or obj.is_spam
            or obj.is_brawl_hold
            or obj.is_brawl_spam
            or self.is_custom_length(obj)
            for obj in changed_objects
        )
        if tail_changed:
            tail_objects = list(getattr(self, "_cached_tail_start_objs", ()))
            for obj in changed_objects:
                if obj in tail_objects:
                    tail_objects.remove(obj)
                if (
                    obj in objects
                    and (obj.is_hold or obj.is_screamer or obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam or self.is_custom_length(obj))
                ):
                    tail_objects.append(obj)
            tail_objects.sort(key=lambda obj: obj.time)
            self._cached_tail_start_objs = tail_objects
            self._cached_tail_objs = sorted(tail_objects, key=lambda obj: obj.end_time)
            self._cached_tail_times = [obj.end_time for obj in self._cached_tail_objs]
            self._cached_tail_start_times = [obj.time for obj in self._cached_tail_start_objs]
            self._cached_tail_prefix_max = []
            max_end = -1
            for obj in self._cached_tail_start_objs:
                max_end = max(max_end, obj.end_time)
                self._cached_tail_prefix_max.append(max_end)

        cached_events = getattr(self, "_cached_events", ())
        cached_centers = getattr(self, "_cached_centers", ())
        event_changed = any(obj.is_event or obj in cached_events for obj in changed_objects)
        toggle_changed = any(obj.is_toggle_center or obj in cached_centers for obj in changed_objects)
        if event_changed:
            events = list(getattr(self, "_cached_events", ()))
            for obj in changed_objects:
                if obj in events:
                    events.remove(obj)
                if obj.is_event and obj in objects:
                    events.append(obj)
            events.sort(key=lambda obj: (obj.time, float(obj.order_index)))
            self._cached_events = events
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

        direction_uids = getattr(self, '_cached_direction_uids', set())
        direction_times = set()
        for obj in changed_objects:
            previous_data = previous_data_by_uid.get(obj.uid)
            if obj.uid in direction_uids and previous_data is not None:
                direction_times.add(previous_data[2])
            if (
                obj.uid in present_changed_uids
                and not obj.is_event
                and not obj.is_freestyle
                and obj.custom_data is None
            ):
                direction_times.add(obj.time)
        direction_changed = bool(direction_times)
        direction_affects_event_state = direction_changed and bool(self.get_center_times())
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

            if self.get_center_times():
                self.rebuild_direction_numpy_cache()
            else:
                self._direction_numpy_cache_dirty = True
        for obj in changed_objects:
            direction_uids.discard(obj.uid)
            if (
                obj.uid in present_changed_uids
                and not obj.is_event
                and not obj.is_freestyle
                and obj.custom_data is None
            ):
                direction_uids.add(obj.uid)
        self._cached_direction_uids = direction_uids

        if toggle_changed and getattr(self, '_direction_numpy_cache_dirty', False):
            self.rebuild_direction_numpy_cache()

        changed_times = {obj.time for obj in changed_objects}
        changed_times.update(
            previous_data[2]
            for previous_data in previous_data_by_uid.values()
        )
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

        if event_changed or direction_affects_event_state:
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
            self._cached_all_objs = objects
            object_times = [obj.time for obj in objects]
            self._cached_hit_object_times = object_times
            self._cached_obj_times = self._cached_hit_object_times
            self._cached_object_uids = [obj.uid for obj in objects]
        freestyle_uids = getattr(self, '_cached_freestyle_uids', set())
        freestyle_changed = any(
            obj.is_freestyle or obj.uid in freestyle_uids
            for obj in changed_objects
        )
        if freestyle_changed:
            for obj in changed_objects:
                freestyle_uids.discard(obj.uid)
                if obj.uid in present_changed_uids and obj.is_freestyle:
                    freestyle_uids.add(obj.uid)
            self._cached_freestyle_uids = freestyle_uids
            self._has_freestyle_objects = bool(freestyle_uids)
        if self._has_freestyle_objects and (event_changed or direction_affects_event_state or freestyle_changed):
            self.rebuild_freestyle_preview_states()
        visual_times = getattr(self, '_cached_obj_visual_times', {})
        visual_end_times = getattr(self, '_cached_obj_visual_end_times', {})
        for obj in changed_objects:
            if obj.uid in present_changed_uids:
                visual_times[obj.uid] = self.audio_to_visual_ms(obj.time)
                if obj.end_time != obj.time:
                    visual_end_times[obj.uid] = self.audio_to_visual_ms(obj.end_time)
                else:
                    visual_end_times.pop(obj.uid, None)
            else:
                visual_times.pop(obj.uid, None)
                visual_end_times.pop(obj.uid, None)
        self._cached_obj_visual_times = visual_times
        self._cached_obj_visual_end_times = visual_end_times
        if self.timeline_scrollbar and hasattr(self.timeline_scrollbar, "sync_objects"):
            self.timeline_scrollbar.sync_objects(changed_objects, present_changed_uids)
        if not getattr(self, '_restoring_undo_state', False):
            self._sync_undo_chunks(changed_objects)

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
        event_phases = np.where(event_orders == 0, 0, np.where(event_orders == 1, 2, 1)).astype(np.int8)
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
        self.rebuild_freestyle_preview_states()

    def get_live_event_cache_interval(self):
        return 1.0 / max(1.0, float(TARGET_FPS))

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

    def get_custom_lane_for_y(self, type_data, y, time_ms):
        mode = type_data.get('lane_mode', 'Top & Bottom')
        if mode == 'Middle':
            return -2
        if mode == 'Top Only':
            return 0
        if mode == 'Bottom Only':
            return 1
        return self.get_compound_placement_lane(y, time_ms)

    def get_compound_placement_lane(self, y, time_ms):
        sf = getattr(self.editor, 'global_scale', 1.0)
        center_y = (self.height() / sf) / 2
        lane_0_y = center_y - LANE_HEIGHT / 2
        lane_1_y = center_y + LANE_HEIGHT / 2
        lane_upper_y = lane_0_y - LANE_HEIGHT
        lane_lower_y = lane_1_y + LANE_HEIGHT

        split_upper_mid = (lane_upper_y + lane_0_y) / 2
        split_lower_mid = (lane_1_y + lane_lower_y) / 2
        if y < split_upper_mid:
            lane = -1
        elif y < center_y:
            lane = 0
        elif y < split_lower_mid:
            lane = 1
        else:
            lane = 2

        if not self.is_time_in_toggle_center(time_ms):
            if lane == -1:
                return 0
            if lane == 2:
                return 1
        return lane

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

    def add_compound_time(self, start_ms, value, unit):
        value = max(0.0, float(value))
        if unit == "ms":
            return int(round(float(start_ms) + value))
        base_bpm = self.beatmap.metadata.BPM if self.beatmap and self.beatmap.metadata.BPM > 0 else 120.0
        start_visual = self.audio_to_visual_ms(float(start_ms))
        end_visual = start_visual + value * (60000.0 / base_bpm)
        return int(round(self.visual_to_audio_ms(end_visual)))

    def resolve_compound_lane(self, lane_mode, placement_lane, time_ms):
        if lane_mode == "Top":
            lane = 0
        elif lane_mode == "Bottom":
            lane = 1
        elif lane_mode == "Outer Top":
            lane = -1
        elif lane_mode == "Outer Bottom":
            lane = 2
        elif lane_mode == "Middle":
            lane = -2
        else:
            lane = int(placement_lane)
        if not self.is_time_in_toggle_center(time_ms):
            if lane == -1:
                return 0
            if lane == 2:
                return 1
        return lane

    def create_custom_compound_object(self, type_data, start_ms, lane, end_ms):
        values = {"time": start_ms, "end": end_ms, "lane": lane}
        raw_line = render_custom_template(type_data["syntax"], values, type_data)
        fields = raw_line.split(",")
        try:
            x_pos = int(fields[0])
        except (IndexError, ValueError):
            x_pos = 427 if lane == -2 else (255 if lane <= 0 else 256)
        try:
            y_pos = int(fields[1])
        except (IndexError, ValueError):
            y_pos = 0
        try:
            object_type = int(fields[3])
        except (IndexError, ValueError):
            object_type = 1
        try:
            hit_sound = int(fields[4])
        except (IndexError, ValueError):
            hit_sound = 0
        extras = fields[5] if len(fields) > 5 else "0"
        if ":" in extras:
            object_params, hit_sample = extras.split(":", 1)
        else:
            object_params, hit_sample = extras, "0:0:0:"
        custom_data = CustomObjectData(
            type_data["id"],
            type_data.get("note_id", ""),
            int(lane),
            int(end_ms),
            raw_line,
            False,
            type_data.get("section", "HitObjects"),
        )
        return HitObject(
            x_pos,
            y_pos,
            int(start_ms),
            object_type,
            hit_sound,
            object_params,
            hit_sample,
            custom_data=custom_data,
        )

    def create_builtin_compound_object(self, target, start_ms, lane, end_ms):
        target = str(target).removeprefix("builtin:")
        lane = int(lane)
        if lane == -2:
            lane = 0
        if not self.is_time_in_toggle_center(start_ms) and lane in (-1, 2):
            lane = 0 if lane == -1 else 1
        if lane == -1:
            x_pos, y_pos = 255, 192
        elif lane == 2:
            x_pos, y_pos = 256, 320
        elif lane == 0:
            x_pos, y_pos = 255, 0
        else:
            x_pos, y_pos = 256, 0
        note_type = 1
        hit_sound = 0
        object_params = "0"
        hit_sample = "0:0:0:"
        style = self.editor.combo_note_style.currentText() if hasattr(self.editor, "combo_note_style") else "Normal"
        if target == "normal":
            if style == "Hide":
                hit_sound = 8
            elif style == "Fly In":
                object_params = "1"
        elif target == "spike":
            hit_sound = 2
            if style == "Fly In":
                object_params = "1"
        elif target == "hold":
            note_type = 128
            object_params = str(int(end_ms))
            if style == "Fly In":
                hit_sample = "1:0:0:0:"
            elif style == "Hide":
                hit_sound = 8
        elif target == "screamer":
            note_type = 128
            hit_sound = 2
            object_params = str(int(end_ms))
        elif target == "spam":
            note_type = 128
            hit_sound = 4
            object_params = str(int(end_ms))
        elif target == "freestyle":
            x_pos, y_pos = 427, 0
            if style == "Hide":
                hit_sound = 8
        elif target.startswith("brawl_"):
            cop_index = getattr(self.editor, "brawl_cop_index", 1)
            cop_offset = {1: 0, 2: 2, 3: 8, 4: 10}.get(cop_index, 0)
            is_knockout = target in ("brawl_final", "brawl_hold_knockout", "brawl_spam_knockout")
            hit_sound = (4 if is_knockout else 0) + cop_offset
            object_params = "3"
            if target in ("brawl_hold", "brawl_hold_knockout", "brawl_spam", "brawl_spam_knockout"):
                note_type = 128
                object_params = str(int(end_ms))
                if target in ("brawl_hold", "brawl_hold_knockout"):
                    hit_sample = "3:1:0:0:"
                else:
                    if lane not in (1, 2):
                        return None
                    hit_sample = "3:0:0:0:"
        elif target in ("flip", "toggle_center", "instant_flip"):
            x_pos, y_pos = 384, 0
            hit_sound = {"flip": 0, "toggle_center": 2, "instant_flip": 8}[target]
            object_params = "Flip"
        else:
            return None
        obj = HitObject(x_pos, y_pos, int(start_ms), note_type, hit_sound, object_params, hit_sample)
        if obj.is_event:
            obj.order_index = 1 if self.editor.event_default_order == "After" else 0
            if obj.is_toggle_center:
                obj.tc_is_blue = True
        elif obj.is_spike:
            obj.order_index = 1
        return obj

    def expand_compound(self, type_data, start_ms, placement_lane, stack=None):
        stack = set(stack or ())
        type_id = str(type_data.get("id") or "")
        if type_id in stack:
            return None, "A compound contains itself."
        stack.add(type_id)
        cursor_ms = int(start_ms)
        objects = []
        for step in type_data.get("steps", []):
            if step.get("kind") == "delay":
                delay_value = step.get("value", 0)
                delay_unit = step.get("unit", "grid")
                if delay_unit == "grid":
                    delay_value = float(delay_value) / max(1, int(step.get("grid_division", 4)))
                    delay_unit = "beats"
                cursor_ms = self.add_compound_time(cursor_ms, delay_value, delay_unit)
                continue
            target = str(step.get("target") or "")
            valid_lanes = compound_target_lane_modes(target)
            lane_mode = step.get("lane", "Placement")
            if lane_mode not in valid_lanes:
                lane_mode = valid_lanes[0]
            lane = self.resolve_compound_lane(lane_mode, placement_lane, cursor_ms)
            end_ms = cursor_ms
            if compound_target_is_length(target):
                length_value = step.get("length_value", 1.0)
                length_unit = step.get("length_unit", "grid")
                if length_unit == "grid":
                    length_value = float(length_value) / max(1, int(step.get("length_grid_division", 4)))
                    length_unit = "beats"
                end_ms = self.add_compound_time(
                    cursor_ms,
                    length_value,
                    length_unit,
                )
            if target.startswith("custom:"):
                child_type = get_custom_type(target.split(":", 1)[1])
                if child_type is None:
                    return None, "A referenced custom object is missing."
                if child_type.get("kind") == "Compound":
                    child_objects, error = self.expand_compound(child_type, cursor_ms, lane, stack)
                    if error:
                        return None, error
                    objects.extend(child_objects)
                    continue
                child_lane = lane
                mode = child_type.get("lane_mode", "Top & Bottom")
                if mode == "Middle":
                    child_lane = -2
                elif mode == "Top Only":
                    child_lane = 0
                elif mode == "Bottom Only":
                    child_lane = 1
                obj = self.create_custom_compound_object(child_type, cursor_ms, child_lane, end_ms)
            else:
                obj = self.create_builtin_compound_object(target, cursor_ms, lane, end_ms)
            if obj is None:
                return None, "A compound object cannot be placed in the selected lane."
            objects.append(obj)
        return objects, ""

    def compound_object_space_free(self, obj):
        if obj.custom_data is not None:
            type_data = get_custom_type(obj.custom_data.type_id)
            return bool(type_data and self.is_custom_space_free(obj.time, obj.end_time, obj.custom_data.lane, type_data))
        return self.is_space_free(
            obj.time,
            obj.end_time,
            obj.lane,
            is_screamer=obj.is_screamer,
            is_spam=obj.is_spam,
            is_brawl_hold_spam=obj.is_brawl_hold or obj.is_brawl_spam,
            is_freestyle=obj.is_freestyle,
            is_spike=obj.is_spike,
            ignore_notes=obj.is_event,
            is_brawl=obj.is_brawl_hit or obj.is_brawl_final or obj.is_brawl_hold or obj.is_brawl_spam,
        )

    def place_compound(self, type_data, start_ms, placement_lane):
        objects, error = self.expand_compound(type_data, start_ms, placement_lane)
        if error or not objects:
            self.editor.play_ui_sound_suppressed("UI Error", 0.5)
            return False
        first_time = self.beatmap.timing_points[0]["time"] if self.beatmap.timing_points else 0
        audio_length = self.beatmap.metadata.ActualAudioLength * 1000.0 if self.beatmap.metadata.ActualAudioLength > 0 else 0
        if any(obj.time < first_time or obj.end_time < obj.time or (audio_length > 0 and obj.end_time > audio_length) for obj in objects):
            self.editor.play_ui_sound_suppressed("UI Error", 0.5)
            return False

        staged = []
        valid = True
        try:
            for obj in objects:
                if obj.is_instant_flip and self.is_time_in_toggle_center(obj.time):
                    valid = False
                    break
                if not self.compound_object_space_free(obj):
                    valid = False
                    break
                self.insert_hit_object_sorted(obj)
                staged.append(obj)
                self.sync_structural_object_caches((obj,))
        finally:
            for obj in staged:
                if obj in self.beatmap.hit_objects:
                    self.beatmap.hit_objects.remove(obj)
            if staged:
                self.beatmap.hit_objects.sort(key=lambda item: (item.time, 0 if item.is_event and item.order_index == 0 else (2 if item.is_event else 1), 0 if item.is_freestyle else 1, 0.5 if not item.is_event else float(item.order_index)))
                self._force_cache_update = True
                self.update_caches_if_needed()
        if not valid:
            self.editor.play_ui_sound_suppressed("UI Error", 0.5)
            return False

        self.save_undo_state()
        now = time.time()
        for offset, obj in enumerate(objects):
            obj.creation_time = now + offset * 0.000001
            self.insert_hit_object_sorted(obj)
        self.editor.mark_unsaved()
        self.sync_structural_object_caches(objects)
        return True

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

    def scale_grid(self, multiplier):
        current = int(self.grid_snap_div)
        minimum = self.editor.spin_grid.minimum() if self.editor and hasattr(self.editor, 'spin_grid') else 1
        maximum = self.editor.spin_grid.maximum() if self.editor and hasattr(self.editor, 'spin_grid') else 64
        if multiplier < 1:
            if current % 2 != 0:
                return False
            target = current // 2
        else:
            target = current * 2
        if target < minimum or target > maximum:
            return False
        if getattr(self, 'is_triplet_mode', False):
            saved = int(getattr(self, 'saved_grid_div', current))
            if multiplier < 1:
                if saved % 2 != 0:
                    return False
                self.saved_grid_div = saved // 2
            else:
                doubled_saved = saved * 2
                if doubled_saved < minimum or doubled_saved > maximum:
                    return False
                self.saved_grid_div = doubled_saved
        self.grid_snap_div = target
        if self.editor and hasattr(self.editor, 'spin_grid'):
            self.editor.spin_grid.blockSignals(True)
            self.editor.spin_grid.setValue(target)
            self.editor.spin_grid.blockSignals(False)
            if self.editor.current_chart:
                self.editor.current_chart.metadata.GridSize = target
                self.editor.mark_unsaved()
        self.update()
        return True

    def halve_grid(self):
        return self.scale_grid(0.5)

    def double_grid(self):
        return self.scale_grid(2)

    def set_scrollbar(self, scrollbar):
        self.timeline_scrollbar = scrollbar
        if hasattr(scrollbar, "set_timeline"):
            scrollbar.set_timeline(self)
    
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
        self.selected_timing_points.clear()
        if hasattr(self, 'side_panel'):
            self.side_panel._object_signature = None
            self.side_panel.refresh_active_tab(force=True)
        if self.timeline_scrollbar and hasattr(self.timeline_scrollbar, "invalidate_overview"):
            self.timeline_scrollbar.invalidate_overview()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.gp_visual_times.clear()
        self.gp_visual_last_frame = time.perf_counter()
        self.gp_drag_preview_visual_time = None
        self.drag_release_times.clear()
        self.drag_start_times.clear()
        self.drag_release_mode.clear()
        self.bpm_drag_start_times.clear()
        self.bpm_drag_release_times.clear()
        self.bpm_follow_drag_state = None
        self.bpm_follow_drag_states.clear()
        self.bpm_drag_initial_times.clear()
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
        self._rebuild_undo_chunks()
        if self.editor:
            self.editor.spin_grid.blockSignals(True)
            self.editor.spin_grid.setValue(self.grid_snap_div)
            self.editor.spin_grid.blockSignals(False)
            self.editor.sync_audio_to_time()
        self.update_scrollbar()
        self.update()
    
    def _rebuild_undo_locations(self, chunks=None):
        active_chunks = self._undo_object_chunks if chunks is None else chunks
        locations = {}
        for chunk in active_chunks:
            for offset, obj_data in enumerate(chunk):
                locations[obj_data[11]] = (chunk, offset)
        self._undo_uid_locations = locations

    def _rebuild_undo_chunks(self):
        if not self.beatmap:
            self._undo_object_chunks = []
            self._undo_uid_locations = {}
            self._undo_chunks_beatmap_id = None
            self._undo_chunks_dirty = False
            return
        states = [obj.undo_data() for obj in self.beatmap.hit_objects]
        chunk_size = self._undo_chunk_size
        self._undo_object_chunks = [
            tuple(states[index:index + chunk_size])
            for index in range(0, len(states), chunk_size)
        ]
        self._rebuild_undo_locations()
        self._undo_chunks_beatmap_id = id(self.beatmap)
        self._undo_chunks_dirty = False

    def shift_undo_history(self, delta_ms):
        delta_ms = int(delta_ms)
        if not self.beatmap or not delta_ms:
            return
        self._ensure_undo_chunks()
        shifted_chunks = {}

        def shift_object_data(obj_data):
            values = list(obj_data)
            values[2] = int(values[2]) + delta_ms
            custom_data = values[12] if len(values) > 12 else None
            if custom_data:
                custom_values = list(custom_data)
                custom_values[3] = int(custom_values[3]) + delta_ms
                values[12] = tuple(custom_values)
            elif values[3] == 128:
                try:
                    values[5] = str(int(values[5]) + delta_ms)
                except (TypeError, ValueError):
                    pass
            return tuple(values)

        def shift_chunks(chunks):
            result = []
            for chunk in chunks:
                key = id(chunk)
                if key not in shifted_chunks:
                    shifted_chunks[key] = tuple(
                        shift_object_data(obj_data) for obj_data in chunk
                    )
                shifted = shifted_chunks[key]
                result.append(shifted)
            return tuple(result)

        self._undo_object_chunks = list(shift_chunks(tuple(self._undo_object_chunks)))
        for state in self.undo_stack + self.redo_stack:
            if state.get('hit_object_chunks') is not None:
                state['hit_object_chunks'] = shift_chunks(state['hit_object_chunks'])
            elif state.get('hit_objects') is not None:
                state['hit_objects'] = tuple(
                    shift_object_data(obj_data) for obj_data in state['hit_objects']
                )
            state['timing_points'] = tuple(
                (int(point[0]) + delta_ms, *point[1:])
                for point in state.get('timing_points', ())
            )
            state['object_order'] = tuple(
                (int(time_ms) + delta_ms, tuple(uids))
                for time_ms, uids in state.get('object_order', ())
            )
        self._rebuild_undo_locations()

    def _ensure_undo_chunks(self):
        if (
            self._undo_chunks_beatmap_id != id(self.beatmap)
            or self._undo_chunks_dirty
        ):
            self._rebuild_undo_chunks()

    def _replace_undo_chunk(self, old_chunk, replacement_chunks):
        chunk_index = next(
            index
            for index, chunk in enumerate(self._undo_object_chunks)
            if chunk is old_chunk
        )
        for obj_data in old_chunk:
            self._undo_uid_locations.pop(obj_data[11], None)
        self._undo_object_chunks[chunk_index:chunk_index + 1] = replacement_chunks
        for chunk in replacement_chunks:
            for offset, obj_data in enumerate(chunk):
                self._undo_uid_locations[obj_data[11]] = (chunk, offset)

    def _insert_undo_object_state(self, object_index, obj_data):
        if not self._undo_object_chunks:
            chunk = (obj_data,)
            self._undo_object_chunks.append(chunk)
            self._undo_uid_locations[obj_data[11]] = (chunk, 0)
            return
        remaining = object_index
        target_chunk = self._undo_object_chunks[-1]
        target_offset = len(target_chunk)
        for chunk in self._undo_object_chunks:
            if remaining <= len(chunk):
                target_chunk = chunk
                target_offset = remaining
                break
            remaining -= len(chunk)
        updated = target_chunk[:target_offset] + (obj_data,) + target_chunk[target_offset:]
        if len(updated) > self._undo_chunk_size * 2:
            split_at = len(updated) // 2
            replacements = [updated[:split_at], updated[split_at:]]
        else:
            replacements = [updated]
        self._replace_undo_chunk(target_chunk, replacements)

    def _sync_undo_chunks(self, changed_objects):
        if not self.beatmap:
            return
        if self._undo_chunks_beatmap_id != id(self.beatmap) or not self._undo_object_chunks:
            self._rebuild_undo_chunks()
            return
        changed_by_uid = {obj.uid: obj for obj in changed_objects}
        if not changed_by_uid:
            self._undo_chunks_dirty = False
            return
        affected_chunks = {}
        for uid in changed_by_uid:
            location = self._undo_uid_locations.get(uid)
            if location is not None:
                affected_chunks.setdefault(location[0], set()).add(uid)
        for chunk, removed_uids in affected_chunks.items():
            updated = tuple(obj_data for obj_data in chunk if obj_data[11] not in removed_uids)
            self._replace_undo_chunk(chunk, [updated] if updated else [])
        objects = self.beatmap.hit_objects
        if len(changed_by_uid) <= 8:
            insertions = []
            for obj in changed_by_uid.values():
                try:
                    insertions.append((objects.index(obj), obj))
                except ValueError:
                    pass
        else:
            insertions = [
                (index, obj)
                for index, obj in enumerate(objects)
                if obj.uid in changed_by_uid
            ]
        for object_index, obj in sorted(insertions, key=lambda item: item[0]):
            self._insert_undo_object_state(object_index, obj.undo_data())
        self._undo_chunks_beatmap_id = id(self.beatmap)
        self._undo_chunks_dirty = False

    def _snapshot_timing_points(self):
        return tuple(
            (tp['time'], tp['bpm'], tp.get('creation_time', 0.0))
            for tp in self.beatmap.timing_points
        )

    def save_undo_state(self):
        if not self.beatmap:
            return
        self.undo_stack.append(self._get_current_state())
        self.redo_stack.clear()
    
    def undo(self):
        if not self.undo_stack or not self.beatmap:
            return
        
        reference_state = self.undo_stack[-1]
        current_state = self._get_current_state(reference_state)
        self.redo_stack.append(current_state)
        
        prev_state = self.undo_stack.pop()
        self._restore_state(prev_state)
        self.editor.mark_unsaved(invalidate_timeline=False)
        self.update()
    
    def redo(self):
        if not self.redo_stack or not self.beatmap:
            return
        
        reference_state = self.undo_stack[-1] if self.undo_stack else None
        current_state = self._get_current_state(reference_state)
        self.undo_stack.append(current_state)
        
        next_state = self.redo_stack.pop()
        self._restore_state(next_state)
        self.editor.mark_unsaved(invalidate_timeline=False)
        self.update()

    def _restore_state(self, state):
        existing_objects = self.beatmap.hit_objects
        state_chunks = state.get('hit_object_chunks')
        current_chunks = tuple(self._undo_object_chunks)
        prefix_count = 0
        suffix_count = 0
        if state_chunks is not None:
            shared_limit = min(len(current_chunks), len(state_chunks))
            while prefix_count < shared_limit and current_chunks[prefix_count] is state_chunks[prefix_count]:
                prefix_count += 1
            while (
                suffix_count < shared_limit - prefix_count
                and current_chunks[-1 - suffix_count] is state_chunks[-1 - suffix_count]
            ):
                suffix_count += 1
            current_start = sum(len(chunk) for chunk in current_chunks[:prefix_count])
            current_suffix_size = sum(len(chunk) for chunk in current_chunks[len(current_chunks) - suffix_count:]) if suffix_count else 0
            current_end = len(existing_objects) - current_suffix_size
            target_middle_end = len(state_chunks) - suffix_count if suffix_count else len(state_chunks)
            target_middle_chunks = state_chunks[prefix_count:target_middle_end]
            state_objects = [obj_data for chunk in target_middle_chunks for obj_data in chunk]
            existing_scope = existing_objects[current_start:current_end]
        else:
            current_start = 0
            current_end = len(existing_objects)
            target_middle_chunks = ()
            state_objects = list(state.get('hit_objects', ()))
            existing_scope = existing_objects
        existing_by_uid = {obj.uid: obj for obj in existing_scope}
        restored_objects = []
        changed_objects = []
        visual_attributes = (
            "_current_visual_time", "_target_visual_time", "_current_visual_end_time",
            "_target_visual_end_time", "_current_visual_lane", "_target_visual_lane",
            "_current_visual_pair_lane", "_target_visual_pair_lane",
        )
        for index, obj_data in enumerate(state_objects):
            obj = existing_scope[index] if index < len(existing_scope) else None
            if obj is None or obj.uid != obj_data[11]:
                obj = existing_by_uid.get(obj_data[11])
            if obj is None:
                obj = HitObject(
                    obj_data[0], obj_data[1], obj_data[2], obj_data[3], obj_data[4],
                    obj_data[5], obj_data[6], obj_data[7], obj_data[8], obj_data[9],
                    obj_data[10], uid=obj_data[11],
                    custom_data=custom_object_data_from_tuple(obj_data[12] if len(obj_data) > 12 else None),
                )
                changed_objects.append(obj)
            elif obj.undo_data() != obj_data:
                obj.x = obj_data[0]
                obj.y = obj_data[1]
                obj.time = obj_data[2]
                obj.type = obj_data[3]
                obj.hitSound = obj_data[4]
                obj.objectParams = obj_data[5]
                obj.hitSample = obj_data[6]
                obj.order_index = obj_data[7]
                obj.creation_time = obj_data[8]
                obj.last_update_time = obj_data[9]
                obj.tc_is_blue = obj_data[10]
                obj.uid = obj_data[11]
                obj.custom_data = custom_object_data_from_tuple(obj_data[12] if len(obj_data) > 12 else None)
                for attribute in visual_attributes:
                    if hasattr(obj, attribute):
                        delattr(obj, attribute)
                changed_objects.append(obj)
            restored_objects.append(obj)
        retained_objects = set(restored_objects)
        removed_objects = [obj for obj in existing_scope if obj not in retained_objects]
        if state_chunks is not None:
            existing_objects[current_start:current_end] = restored_objects
        else:
            self.beatmap.hit_objects = restored_objects
        self.selected_objects.clear()
        self.selected_timing_points.clear()
        self.bpm_follow_drag_state = None
        self.bpm_follow_drag_states.clear()
        self.bpm_drag_initial_times.clear()
        timing_before = tuple(
            (tp['time'], tp['bpm'], tp.get('creation_time', 0.0))
            for tp in getattr(self.beatmap, 'timing_points', ())
        )
        timing_after = tuple(state.get('timing_points', ()))
        if hasattr(self.beatmap, 'timing_points'):
            self.beatmap.timing_points = [
                {'time': tp_data[0], 'bpm': tp_data[1], 'creation_time': tp_data[2]}
                for tp_data in timing_after
            ]
            self.beatmap.timing_points.sort(key=lambda x: x['time'])
            if hasattr(self.editor, 'update_bpm_list'):
                self.editor.update_bpm_list()
        self.beatmap.object_order_overrides = {
            int(time_ms): list(uids)
            for time_ms, uids in state.get('object_order', ())
        }
        self._restoring_undo_state = True
        try:
            if timing_before != timing_after or not hasattr(self, '_cached_all_objs'):
                self._force_cache_update = True
            elif changed_objects or removed_objects:
                self.sync_structural_object_caches(tuple(changed_objects) + tuple(removed_objects))
        finally:
            self._restoring_undo_state = False
        if state_chunks is not None:
            current_middle_end = len(current_chunks) - suffix_count if suffix_count else len(current_chunks)
            for chunk in current_chunks[prefix_count:current_middle_end]:
                for obj_data in chunk:
                    self._undo_uid_locations.pop(obj_data[11], None)
            self._undo_object_chunks = list(state_chunks)
            for chunk in target_middle_chunks:
                for offset, obj_data in enumerate(chunk):
                    self._undo_uid_locations[obj_data[11]] = (chunk, offset)
            self._undo_chunks_beatmap_id = id(self.beatmap)
            self._undo_chunks_dirty = False
        else:
            self._rebuild_undo_chunks()

    def frame_update(self):
        self.perform_frame_update()
        if self.isVisible():
            self.update()

    def perform_frame_update(self):
        if ACTIVE_UI_ANIMATIONS:
            update_ui_animations()
        if hasattr(self, 'side_panel') and self.side_panel._slide_animation_active:
            self.side_panel.advance_animation(time.perf_counter())
        if hasattr(self, 'side_panel'):
            self.side_panel.object_order_list.advance_animation(time.perf_counter())
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
        if self.edge_scroll_speed:
            self.on_edge_scroll()
        self.smooth_update()

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

        if (time_changed or time_settled) and hasattr(self.editor, 'update_add_bpm_button_text'):
            self.editor.update_add_bpm_button_text()
        
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
                 dragging_this = self.is_dragging_timing_point(tp)
                 
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
        for state in self.get_bpm_follow_drag_states():
            if 'preview_times' not in state:
                continue
            index = state['object_indices'].get(obj)
            if index is not None:
                return int(state['preview_times'][index])
        return getattr(obj, '_current_visual_time', obj.time)

    def get_draw_end_time(self, obj):
        for state in self.get_bpm_follow_drag_states():
            if 'preview_end_times' not in state:
                continue
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

        base_timing_ids = {id(tp) for tp in self._drag_base_timing_selection}
        timing_ids = set(base_timing_ids)
        for tp in self.beatmap.timing_points:
            tag_x = self.audio_ms_to_x(tp['time'])
            if self.selection_rect.intersects(QRectF(tag_x - 20, 90, 40, 50)):
                timing_ids.add(id(tp))
        has_timing_match = timing_ids != base_timing_ids
        if self.selection_kind == "timing" or self.selection_kind == "auto" and has_timing_match and not getattr(self, '_drag_base_selection', set()):
            self.selected_objects.clear()
            self.selected_timing_points = [tp for tp in self.beatmap.timing_points if id(tp) in timing_ids]
            if has_timing_match:
                self.selection_kind = "timing"
            return
        
        sf = getattr(self.editor, 'global_scale', 1.0)
        center_y = (self.height() / sf) / 2
        lane_0_y = center_y - LANE_HEIGHT / 2
        lane_1_y = center_y + LANE_HEIGHT / 2
        lane_upper_y = lane_0_y - LANE_HEIGHT
        lane_lower_y = lane_1_y + LANE_HEIGHT
        
        if self.beatmap:
            self.selected_objects = set(getattr(self, '_drag_base_selection', set()))
            for obj in self.get_selection_candidates(x1, x2):
                if self.is_custom_missing(obj):
                    continue
                obj_x = self.audio_ms_to_x(obj.time)
                
                ys_to_check = []
                if obj.custom_data is not None:
                    ys_to_check.append(self.get_custom_object_y(obj))
                elif obj.is_event or obj.is_freestyle:
                    ys_to_check.append(center_y)
                else:
                    if obj.lane == -1:
                        obj_y = lane_upper_y
                    elif obj.lane == 2:
                        obj_y = lane_lower_y
                    elif obj.lane == 0:
                        obj_y = lane_0_y
                    else:
                        obj_y = lane_1_y
                    ys_to_check.append(obj_y)
                    if obj.is_spam:
                        pair_y = lane_lower_y if obj.lane == -1 else (lane_upper_y if obj.lane == 2 else (lane_1_y if obj.lane == 0 else lane_0_y))
                        ys_to_check.append(pair_y)

                selected = False
                for obj_y in ys_to_check:
                    if x1 <= obj_x <= x2 and y1 <= obj_y <= y2:
                        self.selected_objects.add(obj)
                        selected = True
                        break

                if not selected and (obj.is_hold or obj.is_screamer or obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam or self.is_custom_length(obj)):
                    end_x = self.audio_ms_to_x(obj.end_time)
                    if x1 <= end_x <= x2:
                        if obj.is_screamer:
                            tail_ys = [lane_lower_y if obj.lane == -1 else (lane_upper_y if obj.lane == 2 else (lane_1_y if obj.lane == 0 else lane_0_y))]
                        else:
                            tail_ys = ys_to_check
                        if any(y1 <= obj_y <= y2 for obj_y in tail_ys):
                            self.selected_objects.add(obj)
            if self.selection_kind == "auto" and self.selected_objects:
                self.selection_kind = "objects"

    def get_sorted_timing_points(self):
        if self.beatmap and self.beatmap.timing_points:
            return self.beatmap.timing_points
        bpm = self.beatmap.metadata.BPM if self.beatmap else 120
        offset = self.beatmap.metadata.Offset if self.beatmap else 0
        return [{'time': int(offset), 'bpm': bpm}]

    def timing_point_is_selected(self, timing_point):
        return any(selected is timing_point for selected in self.selected_timing_points)

    def is_dragging_timing_point(self, timing_point):
        return getattr(self, 'dragging_bpm_tag', None) is not None and id(timing_point) in self.bpm_drag_initial_times

    def get_bpm_follow_drag_states(self):
        states = getattr(self, 'bpm_follow_drag_states', None)
        if states:
            return states
        state = getattr(self, 'bpm_follow_drag_state', None)
        return [state] if state else []

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
            ignored = ignore_bpm_tag if isinstance(ignore_bpm_tag, (list, tuple, set)) else (ignore_bpm_tag,)
            ignored_ids = {id(tp) for tp in ignored}
            tps = [tp for tp in tps if id(tp) not in ignored_ids]
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

    def get_waveform_values(self, visual_points, wf_len):
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
        return values, required_start, required_end

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

        values, required_start, required_end = self.get_waveform_values(visual_points, wf_len)

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

    def draw_live_waveform(self, painter, strip_y, strip_h, width, px_per_ms, offset_ms, wf_len, view_start):
        world_view_left = self.current_time * px_per_ms - view_start
        chunk_ms = 2.0 / px_per_ms
        visual_start = world_view_left / px_per_ms - offset_ms
        aligned_start = math.floor(visual_start / chunk_ms) * chunk_ms
        point_count = int(math.ceil(width / 2.0)) + 3
        visual_points = aligned_start + np.arange(point_count, dtype=np.float64) * chunk_ms
        world_points = (visual_points + offset_ms) * px_per_ms
        local_points = world_points[:-1] - world_view_left
        values, _, _ = self.get_waveform_values(visual_points, wf_len)
        center_y = strip_y + strip_h / 2.0
        heights = values * strip_h / 2.0 * 0.95
        points_top = [
            QPointF(float(x), float(center_y - height))
            for x, height in zip(local_points, heights)
        ]
        points_bottom = [
            QPointF(float(x), float(center_y + height))
            for x, height in zip(local_points, heights)
        ]
        if points_top:
            painter.save()
            painter.setClipRect(QRectF(0, strip_y, width, strip_h))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(UI_THEME["accent"]))
            painter.drawPolygon(QPolygonF(points_top + list(reversed(points_bottom))))
            painter.restore()
