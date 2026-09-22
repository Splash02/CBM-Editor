from .dialogs import *
from PyQt6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, pyqtProperty
from PyQt6.QtGui import QCursor, QPainterPath, QPicture, QRegion
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QStyle, QStyleOptionTab, QStyleOptionViewItem, QStyledItemDelegate, QTabBar, QTabWidget

register_shared_globals(globals())

def game_preview_visible_visual_max(current_visual_ms, lookahead_visual_ms, radius, edge_zone_width):
    return current_visual_ms + lookahead_visual_ms * (1.0 + max(0.0, radius) / max(1.0, edge_zone_width))

class TimelineRenderingMixin:
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
            device_pixel_ratio = max(1.0, float(self.devicePixelRatioF()))
            scaled_w = max(1, int(round(target_w * device_pixel_ratio)))
            scaled_h = max(1, int(round(target_h * device_pixel_ratio)))
            source_signature = (
                self.bg_image_path,
                scaled_w,
                scaled_h,
                round(device_pixel_ratio, 3),
            )
            background_signature = (
                source_signature,
                round(bg_opacity, 4),
                int(preview_vis),
                self.col_bg.rgba(),
            )

            if self.bg_source_pixmap_scaled_size != source_signature:
                self.bg_source_pixmap_scaled = load_scaled_display_pixmap(
                    self.bg_image_path,
                    self,
                    target_w,
                    target_h,
                )
                self.bg_source_pixmap_scaled_size = source_signature
                self.bg_composite_cache.clear()

            composite = self.bg_composite_cache.get(background_signature)
            if composite is None:
                source_pixmap = self.bg_source_pixmap_scaled
                if source_pixmap:
                    composite = QPixmap(scaled_w, scaled_h)
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
                    self.bg_composite_cache[background_signature] = composite
                    while len(self.bg_composite_cache) > 4:
                        self.bg_composite_cache.pop(next(iter(self.bg_composite_cache)))

            self.bg_pixmap_scaled = composite
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
                base_px_per_ms = self.pixels_per_beat * (view_bpm / 60000.0)
                view_px_per_ms = base_px_per_ms * self.zoom
                view_start = getattr(self.editor, 'timeline_visual_start', TIMELINE_START_X)
                if view_px_per_ms > 0 and wf_len > 0:
                    zoom_moving = abs(self.target_zoom - self.zoom) > self.zoom * 0.00001
                    if zoom_moving:
                        self.draw_live_waveform(
                            p,
                            strip_y,
                            strip_h,
                            w,
                            view_px_per_ms,
                            offset_ms,
                            wf_len,
                            view_start,
                        )
                    else:
                        tile_width = 1024
                        world_view_left = self.current_time * view_px_per_ms - view_start
                        world_view_right = world_view_left + w
                        first_tile = math.floor(world_view_left / tile_width)
                        last_tile = math.floor(world_view_right / tile_width)
                        p.save()
                        p.translate(-world_view_left, strip_y)
                        for tile_index in range(first_tile, last_tile + 1):
                            tile = self.get_waveform_tile(
                                tile_index,
                                tile_width,
                                strip_h,
                                view_px_per_ms,
                                offset_ms,
                                wf_len,
                            )
                            p.drawPixmap(QPointF(tile_index * tile_width, 0), tile)
                        p.restore()

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
        lane_background_key = (
            getattr(self, '_object_cache_generation', 0),
            self._live_event_cache_generation if self._live_event_cache_active else -1,
            self._waveform_cache_generation,
            self.current_time,
            w,
            h,
            self.zoom,
            getattr(self.editor, 'timeline_visual_start', TIMELINE_START_X),
            col_blue_shadow_cache.rgba(),
            col_yellow_shadow_cache.rgba(),
            col_blue_cache.rgba(),
            col_yellow_cache.rgba(),
            col_shadow_cache.rgba(),
            self.col_lane.rgba(),
            col_freestyle_right.rgba(),
            col_freestyle_left.rgba(),
        )
        lane_fill_paths = self._lane_background_cache_paths
        lane_background_cached = (
            lane_fill_paths is not None
            and self._lane_background_cache_key == lane_background_key
        )
        if lane_background_cached:
            (
                blue_shadow_path,
                yellow_shadow_path,
                blue_lane_path,
                yellow_lane_path,
                normal_shadow_path,
                normal_lane_path,
                freestyle_right_path,
                freestyle_left_path,
            ) = (entry[1] for entry in lane_fill_paths)
        else:
            blue_shadow_path = QPainterPath()
            yellow_shadow_path = QPainterPath()
            blue_lane_path = QPainterPath()
            yellow_lane_path = QPainterPath()
            normal_shadow_path = QPainterPath()
            normal_lane_path = QPainterPath()
            freestyle_right_path = QPainterPath()
            freestyle_left_path = QPainterPath()
        
        center_fill_range = () if lane_background_cached else range(idx, len(centers) + 1)
        for k in center_fill_range:
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
                    blue_shadow_path.addRect(QRectF(sx, int(lane_0_y + 30), w_rect, shadow_h))
                    blue_shadow_path.addRect(QRectF(sx, int(lane_1_y + 30), w_rect, shadow_h))
                    yellow_shadow_path.addRect(QRectF(sx, int(lane_upper_y + 30), w_rect, shadow_h))
                    yellow_shadow_path.addRect(QRectF(sx, int(lane_lower_y + 30), w_rect, shadow_h))

                    blue_lane_path.addRect(QRectF(sx, int(lane_0_y - 30), w_rect, 60))
                    blue_lane_path.addRect(QRectF(sx, int(lane_1_y - 30), w_rect, 60))
                    yellow_lane_path.addRect(QRectF(sx, int(lane_upper_y - 30), w_rect, 60))
                    yellow_lane_path.addRect(QRectF(sx, int(lane_lower_y - 30), w_rect, 60))
                else:
                    normal_shadow_path.addRect(QRectF(sx, int(lane_0_y + 30), w_rect, shadow_h))
                    normal_shadow_path.addRect(QRectF(sx, int(lane_1_y + 30), w_rect, shadow_h))

                    normal_lane_path.addRect(QRectF(sx, int(lane_0_y - 30), w_rect, 60))
                    normal_lane_path.addRect(QRectF(sx, int(lane_1_y - 30), w_rect, 60))
            
            if et_audio > audio_max_ms_pre:
                break
                
            if k < len(centers):
                cur_centered_pre = is_in_toggle_center(et_audio + 1)
            st = et
            
        segments, seg_ends = self.get_direction_segments()
        idx = bisect.bisect_right(seg_ends, audio_min_ms_pre) if seg_ends else 0

        direction_lane_fill_range = () if lane_background_cached else range(idx, len(segments))
        for k in direction_lane_fill_range:
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
                    start_y = int(lane_0_y + 40)
                    height = int(lane_1_y - 30 - start_y)
                    freestyle_path = freestyle_right_path if is_right else freestyle_left_path
                    freestyle_path.addRect(QRectF(sx, start_y, w_rect, height))

        lane_fill_paths = (
            (col_blue_shadow_cache, blue_shadow_path),
            (col_yellow_shadow_cache, yellow_shadow_path),
            (col_blue_cache, blue_lane_path),
            (col_yellow_cache, yellow_lane_path),
            (col_shadow_cache, normal_shadow_path),
            (self.col_lane, normal_lane_path),
            (col_freestyle_right, freestyle_right_path),
            (col_freestyle_left, freestyle_left_path),
        )
        if not lane_background_cached:
            self._lane_background_cache_key = lane_background_key
            self._lane_background_cache_paths = lane_fill_paths
        for lane_fill_color, lane_fill_path in lane_fill_paths:
            if not lane_fill_path.isEmpty():
                p.fillPath(lane_fill_path, QBrush(lane_fill_color))
        
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
             p.save()
             accent_col = QColor(UI_THEME["accent"])
             p.setBrush(QBrush(accent_col))
             p.setPen(QPen(Qt.GlobalColor.white))
             
             tag_y = 90
             tag_w = 40
             tag_h = 50
             
             font = QFont(self.font())
             font.setBold(True)
             font.setPixelSize(12)
             p.setFont(font)
             p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
             
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
                 selected = status == "normal" and self.timing_point_is_selected(tp)
                 p.setBrush(QBrush(accent_col.lighter(150) if selected else accent_col))
                 p.setPen(Qt.PenStyle.NoPen)
                 p.drawRoundedRect(rect, 8 * scale, 8 * scale)
                 
                 p.setPen(QColor("white"))
                 bpm_val = tp['bpm']
                 if bpm_val.is_integer():
                     text_bpm = str(int(bpm_val))
                 else:
                     text_bpm = f"{bpm_val:.1f}"
                 
                 font.setPixelSize(max(1, int(12 * scale)))
                 p.setFont(font)
                 
                 self.draw_timeline_text(p, QRectF(rect.x(), rect.y() + 5 * scale, rect.width(), 20 * scale), Qt.AlignmentFlag.AlignCenter, text_bpm)
                 self.draw_timeline_text(p, QRectF(rect.x(), rect.y() + 25 * scale, rect.width(), 20 * scale), Qt.AlignmentFlag.AlignCenter, "BPM")
                 p.setOpacity(1.0)
             
             p.restore()

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
        
        start_screen = getattr(self.editor, 'start_screen', None)
        if hasattr(self.editor, 'timeline_time_label') and not (start_screen is not None and start_screen.isVisible()):
            cur_ms = self.visual_to_audio_ms(max(0, self.current_time))
            tot_ms = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap and self.beatmap.metadata.ActualAudioLength > 0 else self.visual_to_audio_ms(song_length_ms)
            show_hours = max(abs(cur_ms), abs(tot_ms)) >= 3600000
            current_text = format_editor_timestamp(cur_ms, force_hours=show_hours, pad_minutes=False)
            total_text = format_editor_timestamp(tot_ms, force_hours=show_hours, pad_minutes=False)
            time_text = f"{current_text} / {total_text}"
            if self.editor.timeline_time_label.text() != time_text:
                self.editor.timeline_time_label.setText(time_text)
        
        obj_flip_color = self.get_event_flip_colors()
        audio_min_ms = self.visual_to_audio_ms(vis_min_ms)
        audio_max_ms = self.visual_to_audio_ms(vis_max_ms)
        
        segments, seg_ends = self.get_direction_segments()
        idx = bisect.bisect_right(seg_ends, audio_min_ms) if seg_ends else 0
        strip_colors = getattr(self, 'original_object_colors', self.object_colors)
        toggle_strip_color = QColor(strip_colors.get("toggle_center", QColor("purple")))
        right_strip_color = QColor(strip_colors.get("direction_right_event", strip_colors.get("direction_right", QColor("blue"))))
        left_strip_color = QColor(strip_colors.get("direction_left_event", strip_colors.get("direction_left", QColor("yellow"))))
        toggle_strip_color.setAlpha(150)
        right_strip_color.setAlpha(150)
        left_strip_color.setAlpha(150)
        direction_strip_key = (
            lane_background_key,
            strip_y,
            strip_h,
            toggle_strip_color.rgba(),
            right_strip_color.rgba(),
            left_strip_color.rgba(),
        )
        direction_strip_data = self._direction_strip_cache_data
        direction_strip_cached = (
            direction_strip_data is not None
            and self._direction_strip_cache_key == direction_strip_key
        )
        if direction_strip_cached:
            toggle_strip_path, right_strip_path, left_strip_path, strip_markers = direction_strip_data
        else:
            toggle_strip_path = QPainterPath()
            right_strip_path = QPainterPath()
            left_strip_path = QPainterPath()
            strip_markers = []
        
        direction_strip_range = () if direction_strip_cached else range(idx, len(segments))
        for k in direction_strip_range:
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
                strip_path = toggle_strip_path
                arrow_txt = ""
            else:
                strip_path = right_strip_path if is_r else left_strip_path
                arrow_txt = ">>>" if is_r else "<<<"
            strip_path.addRect(QRectF(sx, int(strip_y), w_rect, int(strip_h)))
            
            if arrow_txt:
                spacing = 300
                start_marker = (sx // spacing) * spacing
                if start_marker < sx: start_marker += spacing
                curr_x = start_marker
                while curr_x < ex:
                    if curr_x > 0 and curr_x < w:
                        strip_markers.append((sx, ex, curr_x, arrow_txt))
                    curr_x += spacing

        if not direction_strip_cached:
            self._direction_strip_cache_key = direction_strip_key
            self._direction_strip_cache_data = (
                toggle_strip_path,
                right_strip_path,
                left_strip_path,
                strip_markers,
            )

        for strip_color, strip_path in (
            (toggle_strip_color, toggle_strip_path),
            (right_strip_color, right_strip_path),
            (left_strip_color, left_strip_path),
        ):
            if not strip_path.isEmpty():
                p.fillPath(strip_path, QBrush(strip_color))
        if strip_markers:
            p.setPen(QColor("white"))
            for marker_start, marker_end, marker_x, marker_text in strip_markers:
                p.save()
                p.setClipRect(QRectF(marker_start, strip_y, marker_end - marker_start, strip_h), Qt.ClipOperation.IntersectClip)
                self.draw_timeline_text(p, QRectF(marker_x, int(strip_y), 50, 20), Qt.AlignmentFlag.AlignCenter, marker_text)
                p.restore()

        note_radius = 20
        hold_end_radius = 12
        screamer_end_radius = 15
        brawl_size = 30
        frame_bpm = self.beatmap.metadata.BPM if self.beatmap.metadata.BPM > 0 else 120.0
        frame_px_per_ms = self.pixels_per_beat * (frame_bpm / 60000.0) * self.zoom
        frame_start_x = getattr(self.editor, 'timeline_visual_start', TIMELINE_START_X)
        frame_current_time = self.current_time
        cached_visual_times = getattr(self, '_cached_obj_visual_times', {})
        cached_visual_end_times = getattr(self, '_cached_obj_visual_end_times', {})
        dynamic_bpm_timing = bool(getattr(self, 'dragging_bpm_tag', None))

        def frame_visual_x(visual_time):
            return (visual_time - frame_current_time) * frame_px_per_ms + frame_start_x

        def frame_audio_x(audio_time):
            return frame_visual_x(self.audio_to_visual_ms(audio_time))

        def frame_object_x(obj):
            draw_time = self.get_draw_time(obj)
            visual_time = cached_visual_times.get(obj.uid) if draw_time == obj.time and not dynamic_bpm_timing else None
            if visual_time is None:
                visual_time = self.audio_to_visual_ms(draw_time)
            return frame_visual_x(visual_time)

        def frame_object_end_x(obj):
            draw_time = self.get_draw_end_time(obj)
            visual_time = cached_visual_end_times.get(obj.uid) if draw_time == obj.end_time and not dynamic_bpm_timing else None
            if visual_time is None:
                visual_time = self.audio_to_visual_ms(draw_time)
            return frame_visual_x(visual_time)

        visible_min = self.x_to_audio_ms(-80.0)
        visible_max = self.x_to_audio_ms(w + 80.0)
        
        visible_objects = self.get_objects_in_range(visible_min, visible_max)
        visible_set = set(visible_objects)
        bpm_follow_states = self.get_bpm_follow_drag_states()
        for bpm_follow_state in bpm_follow_states:
            if 'preview_times' not in bpm_follow_state:
                continue
            preview_times = bpm_follow_state['preview_times']
            preview_start = int(np.searchsorted(preview_times, visible_min, side='left'))
            preview_end = int(np.searchsorted(preview_times, visible_max, side='right'))
            for obj in bpm_follow_state['objects'][preview_start:preview_end]:
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
            for obj in self.get_live_drag_objects_in_range(visible_min, visible_max):
                if obj not in visible_set:
                    visible_objects.append(obj)
                    visible_set.add(obj)

        visible_object_set = set(visible_objects) if self.selected_objects else set()

        non_events = []
        events = []
        for visible_object in visible_objects:
            if visible_object.custom_data is None and visible_object._classification()[1]:
                events.append(visible_object)
            else:
                non_events.append(visible_object)

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
        
        simple_visual_list = (
            not events
            and not self.dying_objects
            and self.selected_objects.isdisjoint(visible_object_set)
        )
        if simple_visual_list:
            visual_list = non_events
        else:
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
        base_object_opacity = p.opacity()
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

        def queue_static_shape(obj, classification, x):
            nonlocal batched_shape_count
            y = self.get_draw_y(obj)
            if classification[5]:
                color = self.object_colors["spike"]
                spike_size = note_radius * 1.3
                begin_batched_shape(("spike", color.rgba()), color, x, y, spike_size * 1.4)
                if classification[16] <= 0:
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
            elif classification[15]:
                color = self.object_colors["freestyle"]
                begin_batched_shape(("freestyle", color.rgba()), color, x, center_y, note_radius * 2)
                batched_shape_path.addEllipse(QPointF(x, center_y), note_radius, note_radius)
            else:
                color = self.object_colors["note"]
                begin_batched_shape(("note", color.rgba()), color, x, y, note_radius * 2)
                batched_shape_path.addEllipse(QPointF(x, y), note_radius, note_radius)
            batched_shape_count += 1

        def draw_static_event(obj, classification, x):
            flush_batched_shapes()
            color = self.object_colors.get("direction_right_event", self.object_colors.get("direction_right", QColor("blue")))
            circle_color = color
            if classification[3]:
                color = QColor(self.object_colors.get("toggle_center", QColor("purple")))
                circle_color = obj_flip_color.get(obj.uid, color)
            elif classification[2] or classification[4]:
                color = obj_flip_color.get(obj.uid, color)
                circle_color = color
            if classification[4]:
                brush_color = QColor("white")
            elif classification[3] and obj.order_index != 0:
                brush_color = circle_color
            else:
                brush_color = color
            marker_side = 0
            if obj.time in self._fast_note_times:
                if obj.order_index == 0:
                    marker_side = -1
                elif obj.order_index == 1:
                    marker_side = 1
            if len(self._static_event_picture_cache) > 256:
                self._static_event_picture_cache.clear()
            line_key = ("line", color.rgba(), int(lane_0_y), int(lane_1_y))
            line_picture = self._static_event_picture_cache.get(line_key)
            if line_picture is None:
                line_picture = QPicture()
                event_painter = QPainter(line_picture)
                event_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                event_painter.setPen(QPen(color, 3))
                event_painter.drawLine(0, int(lane_0_y), 0, int(lane_1_y))
                event_painter.end()
                self._static_event_picture_cache[line_key] = line_picture
            circle_key = ("circle", color.rgba(), brush_color.rgba(), center_y, marker_side)
            circle_picture = self._static_event_picture_cache.get(circle_key)
            if circle_picture is None:
                circle_picture = QPicture()
                event_painter = QPainter(circle_picture)
                event_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                event_painter.setPen(QPen(color, 3))
                event_painter.setBrush(brush_color)
                event_painter.drawEllipse(QPointF(0, center_y), 8, 8)
                if marker_side:
                    event_painter.setBrush(QColor("white"))
                    event_painter.setPen(Qt.PenStyle.NoPen)
                    event_painter.drawEllipse(QPointF(marker_side * 10, center_y), 4, 4)
                event_painter.end()
                self._static_event_picture_cache[circle_key] = circle_picture
            p.drawPicture(QPointF(int(x), 0), line_picture)
            p.drawPicture(QPointF(x, 0), circle_picture)

        for obj_data in visual_list:
            if simple_visual_list:
                obj = obj_data
                status = "normal"
            else:
                obj = obj_data[0]
                status = obj_data[1]

            classification = obj._classification()
            fast_static_event = (
                status == "normal"
                and obj.custom_data is None
                and classification[1]
                and obj not in self.selected_objects
                and obj not in self.visual_interpolating_objects
                and obj not in self.drag_release_times
                and (not obj.creation_time or current_time - obj.creation_time >= 0.3)
                and (not obj.last_update_time or current_time - obj.last_update_time >= 0.2)
                and not self.editor.is_playing
            )
            if fast_static_event:
                if not dynamic_bpm_timing:
                    x = frame_visual_x(cached_visual_times[obj.uid])
                else:
                    x = frame_object_x(obj)
                if -50 < x < w + 50:
                    draw_static_event(obj, classification, x)
                continue
            fast_static_shape = (
                status == "normal"
                and obj.custom_data is None
                and obj not in self.selected_objects
                and obj not in self.visual_interpolating_objects
                and obj not in self.drag_release_times
                and (not obj.creation_time or current_time - obj.creation_time >= 0.3)
                and (not obj.last_update_time or current_time - obj.last_update_time >= 0.2)
                and classification[17]
                and not (
                    self.editor.is_playing
                    and 0 <= current_audio_time - obj.time <= 500
                )
            )
            if fast_static_shape:
                if not dynamic_bpm_timing:
                    x = frame_visual_x(cached_visual_times[obj.uid])
                else:
                    x = frame_object_x(obj)
                if -50 < x < w + 50:
                    queue_static_shape(obj, classification, x)
                continue
            
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
            
            opacity_changed = anim_alpha != base_object_opacity
            if opacity_changed:
                p.setOpacity(anim_alpha)
            
            x = frame_object_x(obj)

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
                        self.draw_timeline_text(p, rect, Qt.AlignmentFlag.AlignCenter, 'Missing')
                    if opacity_changed:
                        p.setOpacity(base_object_opacity)
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
                    end_x = frame_object_end_x(obj)
                    if end_x > -50 and x < w + 50:
                        p.setPen(QPen(connection_color, max(3.0, 6.0 * anim_scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                        p.drawLine(QPointF(x, y), QPointF(end_x, y))
                        draw_custom_shape(x, y, head_scale, head_color)
                        draw_custom_shape(end_x, y, tail_scale, tail_color)
                elif -50 < x < w + 50:
                    draw_custom_shape(x, y, head_scale, head_color)
                if opacity_changed:
                    p.setOpacity(base_object_opacity)
                continue

            can_batch_static_shape = (
                status == "normal"
                and classification[17]
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
                    queue_static_shape(obj, classification, x)
                if opacity_changed:
                    p.setOpacity(base_object_opacity)
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
                    split_obj_time = self.get_draw_time(obj)
                    split_obj_end_time = self.get_draw_end_time(obj)
                    split_start = bisect.bisect_left(_center_times, split_obj_time)
                    split_end = bisect.bisect_right(_center_times, split_obj_end_time)
                    for c in centers[split_start:split_end]:
                        sx = frame_object_x(c)
                        center_time = self.get_draw_time(c)
                        is_cen = is_in_toggle_center(center_time + 1) if center_time < split_obj_end_time else is_in_toggle_center(center_time)
                        if obj.lane == -1:
                            sy = (lane_0_y - LANE_HEIGHT) if is_cen else lane_0_y
                            spy = lane_lower_y if is_cen else lane_1_y
                        else:
                            sy = lane_lower_y if is_cen else lane_1_y
                            spy = (lane_0_y - LANE_HEIGHT) if is_cen else lane_0_y
                        splits.append((sx, sy, spy))
                
                is_selected = obj in self.selected_objects
                
                if obj.is_spam:
                    end_x = frame_object_end_x(obj)
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
                    end_x = frame_object_end_x(obj)
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
                    end_x = frame_object_end_x(obj)
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
                    end_x = frame_object_end_x(obj)
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
                            self.draw_timeline_text(p, rect, Qt.AlignmentFlag.AlignCenter, str(cop_num))
                
                if not obj.is_screamer and not obj.is_spam and not obj.is_brawl_hold and not obj.is_brawl_spam:
                    if -50 < x < w + 50 or (obj.is_hold and frame_object_end_x(obj) > -50):
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
                            self.draw_timeline_text(p, rect, Qt.AlignmentFlag.AlignCenter, str(obj.brawl_cop_number))
                        
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
                            
                            self.draw_timeline_text(p, rect, Qt.AlignmentFlag.AlignCenter, str(obj.brawl_cop_number))
                        
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
                        
                        if (obj.is_hide or obj.is_no_circle_hold) and not obj.is_freestyle and not obj.is_brawl_hit and not obj.is_brawl_final:
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
                             end_x = int(frame_object_end_x(obj))
                             
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

            if opacity_changed:
                p.setOpacity(base_object_opacity)

        flush_batched_shapes()
        
        if self.selection_active_visible:
            min_x, max_x = float('inf'), float('-inf')
            min_y, max_y = float('inf'), float('-inf')
            found = False
            
            selected_objects_for_bounds = self.selected_objects
            if selected_objects_for_bounds:
                for obj in selected_objects_for_bounds:
                    ms_start = self.get_draw_time(obj)
                    x_start = frame_object_x(obj)
                    
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
                         x_end = frame_object_end_x(obj)
                         max_x = max(max_x, x_end + 30)
                         if obj.custom_data is None and obj.lane in [-1, 2]:
                             if any(obj.time <= c.time <= obj.end_time for c in centers):
                                 if obj.lane == -1:
                                     min_y = min(min_y, lane_upper_y - 30)
                                     max_y = max(max_y, lane_0_y + 30)
                                 elif obj.lane == 2:
                                     min_y = min(min_y, lane_1_y - 30)
                                     max_y = max(max_y, lane_lower_y + 30)

            if found and len(selected_objects_for_bounds) >= 2:
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
                    
                    x = frame_object_x(obj)
                    if obj.is_freestyle or obj.is_event:
                        sf = getattr(self.editor, 'global_scale', 1.0)
                        y1 = (self.height() / sf) / 2
                    else:
                        y1 = self.get_draw_y(obj)
                    
                    if obj.is_hold or obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam or obj.is_screamer:
                        end_x = frame_object_end_x(obj)
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
            if self.dragging_objects:
                previous_drag_visual_time = self.gp_drag_preview_visual_time
                drag_preview_visual_delta = current_visual_ms - previous_drag_visual_time if previous_drag_visual_time is not None else 0.0
                self.gp_drag_preview_visual_time = current_visual_ms
            else:
                drag_preview_visual_delta = 0.0
                self.gp_drag_preview_visual_time = None
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
                        live_obj_time = self.get_live_drag_time(obj)
                        phase_state = self._live_note_phase_states.get(live_obj_time)
                        if phase_state is not None:
                            phase_right, phase_centered = phase_state
                            if phase_centered and not is_freestyle:
                                if lane in [0, 1]:
                                    return True
                                if lane in [-1, 2]:
                                    return False
                            return phase_right
                        if is_freestyle:
                            pre_state = self._live_note_pre_states.get(live_obj_time)
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
                gp_max = self.visual_to_audio_ms(current_visual_ms + lookahead_visual_ms + 500)
                gp_subset = self.get_objects_in_range(gp_min, gp_max)
                gp_released_objects = set(self.drag_release_times)
                gp_live_drag_objects = self._live_drag_object_set
                if gp_released_objects or gp_live_drag_objects:
                    gp_subset_set = set(gp_subset)
                    for obj in gp_released_objects:
                        if obj not in gp_subset_set:
                            gp_subset.append(obj)
                            gp_subset_set.add(obj)
                    for obj in self.get_live_drag_objects_in_range(gp_min, gp_max):
                        if obj not in gp_subset_set:
                            gp_subset.append(obj)
                            gp_subset_set.add(obj)
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
                    obj_time = self.get_live_drag_time(obj)
                    obj_end = self.get_live_drag_end_time(obj) if obj.type == 128 or self.is_custom_length(obj) else obj_time
                    moving_preview_obj = obj in gp_released_objects or obj in gp_live_drag_objects
                    if gp_status != "dying" and not moving_preview_obj:
                        if obj_end < current_audio_ms - 200:
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
                    if gp_status != "dying" and not moving_preview_obj and elapsed_since_end > 0:
                        progress_out = min(1.0, elapsed_since_end / 100.0)
                        scale *= 1.0 + progress_out * 0.5
                        alpha_factor *= 1.0 - progress_out

                    time_until_start = obj_time - current_audio_ms
                    if obj.is_hide and gp_status != "dying" and not moving_preview_obj:
                        if 0 <= time_until_start < 250:
                            hide_alpha = max(0.0, (time_until_start - 50) / 200.0)
                            alpha_factor *= hide_alpha
                    
                    if alpha_factor <= 0:
                        continue
                        
                    rad = note_radius * scale
                    if gp_status != "dying" and not moving_preview_obj:
                        visible_visual_max = game_preview_visible_visual_max(
                            current_visual_ms,
                            lookahead_visual_ms,
                            rad,
                            min(gp_left_zone, gp_right_zone),
                        )
                        if obj_time > self.visual_to_audio_ms(visible_visual_max):
                            continue
                    p.setOpacity(alpha_factor)

                    obj_id = obj.uid << 2
                    gp_active_keys.add(obj_id)
                    dragging_preview_obj = obj in gp_live_drag_objects
                    object_visual_delta = drag_preview_visual_delta if dragging_preview_obj else 0.0
                    if moving_preview_obj and obj_id in self.gp_visual_times:
                        previous_visual_time = self.audio_to_visual_ms(self.gp_visual_times[obj_id]) + object_visual_delta
                        target_visual_time = self.audio_to_visual_ms(obj_time)
                        smooth_visual_time = previous_visual_time + (target_visual_time - previous_visual_time) * gp_lerp_alpha
                        self.gp_visual_times[obj_id] = self.visual_to_audio_ms(smooth_visual_time)
                    elif obj_id in self.gp_visual_times:
                        prev_vt = self.gp_visual_times[obj_id]
                        self.gp_visual_times[obj_id] = prev_vt + (obj_time - prev_vt) * gp_lerp_alpha
                    else:
                        self.gp_visual_times[obj_id] = float(obj_time)
                    visual_time = self.gp_visual_times[obj_id]
                    vt_visual = self.audio_to_visual_ms(visual_time)
                    vt_until_start = vt_visual - current_visual_ms

                    visual_end = obj_end
                    ve_visual = vt_visual
                    if obj.type == 128 or self.is_custom_length(obj):
                        vt_end_key = obj_id | 1
                        gp_active_keys.add(vt_end_key)
                        if moving_preview_obj and vt_end_key in self.gp_visual_times:
                            previous_end_visual = self.audio_to_visual_ms(self.gp_visual_times[vt_end_key]) + object_visual_delta
                            target_end_visual = self.audio_to_visual_ms(obj_end)
                            smooth_end_visual = previous_end_visual + (target_end_visual - previous_end_visual) * gp_lerp_alpha
                            self.gp_visual_times[vt_end_key] = self.visual_to_audio_ms(smooth_end_visual)
                        elif vt_end_key in self.gp_visual_times:
                            prev_ve = self.gp_visual_times[vt_end_key]
                            self.gp_visual_times[vt_end_key] = prev_ve + (obj_end - prev_ve) * gp_lerp_alpha
                        else:
                            self.gp_visual_times[vt_end_key] = float(obj_end)
                        visual_end = self.gp_visual_times[vt_end_key]
                        ve_visual = self.audio_to_visual_ms(visual_end)

                    lane = self.get_effective_lane_at(obj, obj_time)
                    is_right = gp_get_direction_at(visual_time, lane, obj.is_freestyle, obj=obj)
                    target_ny = gp_center_y if obj.custom_data is not None and lane == -2 else gp_dynamic_y(lane, obj.is_freestyle, vt_until_start, obj.is_fly_in)

                    vy_key = obj_id | 2
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
                        if obj.is_brawl_hold:
                            p.drawRect(QRectF(start_x - rad, ny - rad, rad * 2, rad * 2))
                        else:
                            p.drawEllipse(QPointF(start_x, ny), rad, rad)
                            if obj.is_no_circle_hold:
                                p.setPen(Qt.PenStyle.NoPen)
                                p.setBrush(QColor("black"))
                                p.drawEllipse(QPointF(start_x, ny), 6 * scale, 6 * scale)
                        p.setPen(end_pen)
                        p.setBrush(end_col)
                        if obj.is_brawl_hold:
                            tail_radius = rad * 0.8
                            p.drawRect(QRectF(end_x - tail_radius, ny - tail_radius, tail_radius * 2, tail_radius * 2))
                        else:
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
                        if obj.is_brawl_spam:
                            p.drawRect(QRectF(start_x - rad, ny - rad, rad * 2, rad * 2))
                            p.drawRect(QRectF(start_x - rad, pair_y - rad, rad * 2, rad * 2))
                        else:
                            p.drawEllipse(QPointF(start_x, ny), rad, rad)
                            p.drawEllipse(QPointF(start_x, pair_y), rad, rad)
                        p.setPen(end_pen)
                        p.setBrush(end_col)
                        if obj.is_brawl_spam:
                            tail_radius = rad * 0.8
                            p.drawRect(QRectF(end_x - tail_radius, ny - tail_radius, tail_radius * 2, tail_radius * 2))
                            p.drawRect(QRectF(end_x - tail_radius, pair_y - tail_radius, tail_radius * 2, tail_radius * 2))
                        else:
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
                            p.drawRect(QRectF(nx - rad, ny - rad, rad * 2, rad * 2))
                        elif obj.is_brawl_final:
                            col = QColor(self.object_colors.get("brawl_knockout", QColor("#000000")))
                            if flash_alpha > 0: col = QColor(255, 255, 255, flash_alpha)
                            p.setPen(gp_note_pen)
                            p.setBrush(col)
                            p.drawRect(QRectF(nx - rad, ny - rad, rad * 2, rad * 2))
                        elif obj.is_hide and not obj.is_freestyle:
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
                            is_small_freestyle = obj.uid in getattr(self, "_preview_small_freestyle_uids", ())
                            freestyle_rad = max(4.0, rad * 0.5) if is_small_freestyle else rad
                            p.drawEllipse(QPointF(nx, ny), freestyle_rad, freestyle_rad)
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

        preview_target_path = QPainterPath()
        for target_x in (gp_left_line_x, gp_right_line_x):
            for target_y in (gp_lane_top_y, gp_lane_bot_y):
                preview_target_path.addEllipse(QPointF(target_x, target_y), 20, 20)
        p.setPen(QPen(QColor("white"), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(preview_target_path)

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

        preview_font = QFont(self.font())
        preview_font.setPixelSize(22)
        preview_font.setBold(True)
        p.setFont(preview_font)
        accent = QColor(UI_THEME["accent"])
        preview_background = QColor(30, 30, 35)
        preview_text_strength = 120 / 255.0
        preview_text_col = QColor(
            round(preview_background.red() + (accent.red() - preview_background.red()) * preview_text_strength),
            round(preview_background.green() + (accent.green() - preview_background.green()) * preview_text_strength),
            round(preview_background.blue() + (accent.blue() - preview_background.blue()) * preview_text_strength),
        )
        p.setPen(preview_text_col)
        gp_pad = 10
        self.draw_timeline_raster_text(
            p,
            QRectF(gp_x + gp_pad, gp_top + gp_pad - 5, 200, 30),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            "PREVIEW",
        )

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

    def camera_preview_anticipation_time(self, boundary, segment_start):
        boundary = float(boundary)
        segment_start = min(boundary, float(segment_start))
        if segment_start >= boundary:
            return boundary

        timing_boundaries = {segment_start}
        for timing_point in self.get_sorted_timing_points():
            timing_time = float(timing_point.get('time', segment_start))
            if segment_start < timing_time < boundary:
                timing_boundaries.add(timing_time)
        timing_boundaries = sorted(timing_boundaries)

        remaining_beats = 2.0
        timing_end = boundary
        for timing_start in reversed(timing_boundaries):
            bpm = self.get_bpm_at_ms(timing_start)
            beat_ms = 60000.0 / bpm if bpm > 0 else 500.0
            section_beats = max(0.0, timing_end - timing_start) / beat_ms
            if section_beats >= remaining_beats:
                return timing_end - remaining_beats * beat_ms
            remaining_beats -= section_beats
            timing_end = timing_start

        return segment_start

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
                anticipation_time = self.camera_preview_anticipation_time(boundary, segment[0])
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
                anticipation_time = self.camera_preview_anticipation_time(boundary, segment[0])
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
