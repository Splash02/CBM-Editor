from .dialogs import *
from PyQt6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, pyqtProperty
from PyQt6.QtGui import QCursor, QPainterPath, QPicture, QRegion
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QStyle, QStyleOptionTab, QStyleOptionViewItem, QStyledItemDelegate, QTabBar, QTabWidget

register_shared_globals(globals())

class TimelineInteractionMixin:
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
                                 self.selected_timing_points = [selected for selected in self.selected_timing_points if selected is not tp]
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
                                 pk = self.pressed_keys | getattr(self.editor, 'pressed_keys', set())
                                 is_multiselect = check_modifier(e.modifiers(), getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("multiselect_modifier", "Shift"), pk)
                                 if is_multiselect and self.selected_objects:
                                      return
                                 if not is_multiselect:
                                      self.selected_objects.clear()
                                      if not self.timing_point_is_selected(tp):
                                           self.selected_timing_points = [tp]
                                 elif self.timing_point_is_selected(tp):
                                      self.selected_timing_points = [selected for selected in self.selected_timing_points if selected is not tp]
                                      self.update()
                                      return
                                 else:
                                      self.selected_timing_points.append(tp)
                                 selected_ids = {id(selected) for selected in self.selected_timing_points}
                                 self.selected_timing_points = [point for point in self.beatmap.timing_points if id(point) in selected_ids]
                                 self._bpm_drag_undo_depth = len(self.undo_stack)
                                 self.save_undo_state()
                                 self.dragging_bpm_tag = tp
                                 self.bpm_drag_initial_times = {id(point): float(point['time']) for point in self.selected_timing_points}
                                 self.bpm_follow_drag_states = [
                                     state for state in (self.capture_bpm_follow_state(point) for point in self.selected_timing_points)
                                     if state is not None
                                 ]
                                 self.bpm_follow_drag_state = self.bpm_follow_drag_states[0] if len(self.bpm_follow_drag_states) == 1 else None
                                 first_point = self.beatmap.timing_points[0] if self.beatmap.timing_points else None
                                 self.drag_bpm_was_first = first_point is not None and id(first_point) in self.bpm_drag_initial_times
                                 visual_tp_time = self.audio_to_visual_ms(tp['time'])
                                 self.bpm_drag_offset = visual_tp_time - self.x_to_ms(click_x)
                                 drag_start_time = time.time()
                                 for point in self.selected_timing_points:
                                      self.bpm_drag_start_times[id(point)] = drag_start_time
                                      self.bpm_drag_release_times.pop(id(point), None)
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

                if self.selected_timing_points:
                    if is_shift or is_alt or is_alt_ctrl:
                        return
                    self.selected_timing_points.clear()

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
                            self.editor.mark_unsaved(invalidate_timeline=False)
                            self.sync_structural_object_caches(targets)
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
                        self.editor.mark_unsaved(invalidate_timeline=False)
                        self.sync_structural_object_caches(targets)
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
                        self.editor.mark_unsaved(invalidate_timeline=False)
                        self.sync_structural_object_caches(targets)
                        self.update()
                        return
                    
                    if clicked_obj.is_hold:
                        self.save_undo_state()

                        if clicked_obj.is_no_circle_hold:
                            next_style = "normal"
                        elif clicked_obj.is_fly_in:
                            next_style = "no_circle"
                        else:
                            next_style = "fly_in"
                        
                        for t in targets:
                            if t.is_hold:
                                parts = t.hitSample.rstrip(":").split(":")
                                while len(parts) < 4:
                                    parts.append("0")

                                if next_style == "normal":
                                    parts[0] = "0"
                                    t.hitSound = 0
                                elif next_style == "fly_in":
                                    parts[0] = "1"
                                    t.hitSound = 0
                                else:
                                    parts[0] = "0"
                                    t.hitSound = 8
                                
                                t.hitSample = ":".join(parts) + ":"
                                t.last_update_time = time.time()
                        
                        self.editor.play_ui_sound_suppressed('UI Change', self.editor.get_pan_for_widget(self))
                        self.editor.mark_unsaved(invalidate_timeline=False)
                        self.sync_structural_object_caches(targets)
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
                        self.editor.mark_unsaved(invalidate_timeline=False)
                        self.sync_structural_object_caches(targets)
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
                self._drag_undo_saved = False
                self.dragging_objects = True
                self.gp_drag_preview_visual_time = None
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
                self._drag_base_timing_selection = list(self.selected_timing_points)
                if self.selected_objects:
                    self.selection_kind = "objects"
                elif self.selected_timing_points:
                    self.selection_kind = "timing"
                else:
                    self.selection_kind = "auto"
            else:
                self.selected_objects.clear()
                self.selected_timing_points.clear()
                self._drag_base_selection = set()
                self._drag_base_timing_selection = []
                self.selection_kind = "auto"
            
            if is_shift or not in_lane_area:
                self.timeline_click_pos = e.pos()
                self.selection_start = self.x_to_ms(e.pos().x())
                self.selection_start_y = e.pos().y()
                self.selection_rect = None
                return
            
            if in_lane_area:
                ms = self.x_to_ms(e.pos().x())
                snapped_visual, snapped_ms = self.get_snapped_timeline_time(ms)
                
                song_length_ms = self.get_visual_song_length()
                if snapped_visual < 0 or (song_length_ms > 0 and snapped_visual > song_length_ms):
                    return
                
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
                            elif style == "Hide":
                                hit_sound = 8
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
                        grid_div = max(1, int(self.grid_snap_div))
                        snap_len = (60000.0 / bpm) / grid_div
                        end_visual = snapped_visual + snap_len
                        end_ms = max(snapped_ms + 1, round(self.visual_to_audio_ms(end_visual)))
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
                    if type_data.get("kind") == "Compound":
                        clicked_lane = self.get_compound_placement_lane(e.pos().y(), snapped_ms)
                        if self.place_compound(type_data, snapped_ms, clicked_lane):
                            global_x = self.mapToGlobal(e.pos()).x()
                            self.editor.play_ui_sound_suppressed("UI Place", self.editor.calculate_pan(global_x))
                        self.update()
                        return
                    clicked_lane = self.get_custom_lane_for_y(type_data, e.pos().y(), snapped_ms)
                    end_ms = snapped_ms
                    if type_data.get('kind') == 'Note' and type_data.get('length'):
                        bpm = self.beatmap.metadata.BPM if self.beatmap.metadata.BPM > 0 else 120
                        beat_ms = 60000 / bpm
                        snap_len = beat_ms / self.grid_snap_div
                        if snap_len >= 10:
                            end_ms = int(round(self.visual_to_audio_ms(snapped_visual + snap_len)))
                        else:
                            end_ms = snapped_ms + 10
                    new_obj = self.create_custom_compound_object(type_data, snapped_ms, clicked_lane, end_ms)
                    if new_obj is None:
                        return
                    if self.is_custom_space_free(snapped_ms, end_ms, clicked_lane, type_data):
                        self.save_undo_state()
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
                to_remove_set = set(to_remove_list)
                self.queue_delete_animations(to_remove_list)
                for o in to_remove_list:
                    if o in self.drag_start_time_map: del self.drag_start_time_map[o]
                    if o in self.drag_start_lane_map: del self.drag_start_lane_map[o]
                    if o in self.drag_original_end_time_map: del self.drag_original_end_time_map[o]
                self.beatmap.hit_objects[:] = [
                    obj for obj in self.beatmap.hit_objects
                    if obj not in to_remove_set
                ]
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
                            has_notes = any(
                                obj is not t and obj.time == t.time and not obj.is_event
                                for obj in self.get_objects_in_range(t.time, t.time)
                            )
                            if has_notes:
                                t.order_index = 1 if t.order_index == 0 else 0
                                t.last_update_time = time.time()
                                has_changes = True
                        
                        if has_changes:
                            for time_ms in {target.time for target in targets}:
                                group = list(self.get_objects_in_range(time_ms, time_ms))
                                ordered_group = self.beatmap.ordered_objects_at(time_ms, group)
                                moved = [obj for obj in ordered_group if obj in targets]
                                remaining = [obj for obj in ordered_group if obj not in targets]
                                moved_pre = [obj for obj in moved if obj.order_index == 0]
                                moved_post = [obj for obj in moved if obj.order_index != 0]
                                insert_at = next(
                                    (index for index, obj in enumerate(remaining) if not obj.is_event),
                                    len(remaining),
                                )
                                remaining[insert_at:insert_at] = moved_pre
                                remaining.extend(moved_post)
                                self.beatmap.set_object_order(
                                    time_ms,
                                    [obj.uid for obj in remaining],
                                    remaining,
                                )
                            self.beatmap.hit_objects.sort(key=lambda x: (x.time, 0 if x.is_event and x.order_index == 0 else (2 if x.is_event else 1), 0 if getattr(x, 'is_freestyle', False) else 1, 0.5 if not x.is_event else float(x.order_index)))
                            self.editor.play_ui_sound_suppressed('UI Change', self.editor.get_pan_for_widget(self))
                            self.editor.mark_unsaved()
                            self._force_cache_update = True
                            self.sync_structural_object_caches(targets)
                            if hasattr(self, 'side_panel'):
                                self.side_panel._object_signature = None
                                self.side_panel.refresh_active_tab(force=True)
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
                new_visual_snapped, new_time_snapped = self.get_snapped_timeline_time(new_visual_raw)
                new_time = new_time_snapped
                new_time_raw = self.visual_to_audio_ms(new_visual_raw)
                
                if getattr(self, 'is_g_pressed', False):
                    new_time = round(new_time_raw)
                    
                if new_time < 0: new_time = 0

                original_lane = self.drag_start_lane_map[obj]
                new_lane = original_lane
                
                custom_type = self.get_custom_type_data(obj)
                if custom_type is not None:
                    new_lane = self.get_custom_lane_for_y(custom_type, self.last_mouse_pos.y(), new_time)
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
            if self.beatmap.metadata.ActualAudioLength > 0:
                max_duration = self.beatmap.metadata.ActualAudioLength * 1000

            for obj in self.selected_objects:
                if obj.type == 128 or self.is_custom_length(obj):
                    orig_end_visual = self.audio_to_visual_ms(self.drag_original_end_time_map[obj])
                    new_end_visual_raw = orig_end_visual + time_delta
                    new_end_visual, new_end_time_snapped = self.get_snapped_timeline_time(new_end_visual_raw)
                    new_end_time_raw = self.visual_to_audio_ms(new_end_visual_raw)
                    new_end_time = new_end_time_snapped
                    
                    if getattr(self, 'is_g_pressed', False):
                        new_end_time = round(new_end_time_raw)
                    
                    if new_end_time > max_duration:
                        new_end_time = int(max_duration)
                        new_end_time_raw = float(max_duration)
                        new_end_time_snapped = int(max_duration)
                    
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
            actual_change = False
            for obj, target_time, target_end, target_lane, *_ in potential_moves:
                if int(target_time) != obj.time:
                    actual_change = True
                    break
                if (obj.type == 128 or self.is_custom_length(obj)) and int(target_end) != obj.end_time:
                    actual_change = True
                    break
                if obj.custom_data is not None and int(target_lane) != obj.custom_data.lane:
                    actual_change = True
                    break
                if obj.custom_data is None and not obj.is_event and not obj.is_freestyle and target_lane is not None and int(target_lane) != obj.lane:
                    actual_change = True
                    break
            if not actual_change:
                for obj, _, _, _, target_visual_time, target_visual_end, *_ in potential_moves:
                    obj._target_visual_time = target_visual_time
                    if obj.type == 128 or self.is_custom_length(obj):
                        obj._target_visual_end_time = target_visual_end
                    self.visual_interpolating_objects.add(obj)
                self.update()
                return
            if not getattr(self, "_drag_undo_saved", False):
                self.save_undo_state()
                self._drag_undo_saved = True
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

    def update_dragged_bpm_tags(self, pointer_x):
        if not getattr(self, 'dragging_bpm_tag', None) or not self.beatmap:
            return
        selected = [tp for tp in self.beatmap.timing_points if id(tp) in self.bpm_drag_initial_times]
        if not selected:
            return
        current_audio = self.visual_to_audio_ms(self.current_time)
        offset = getattr(self, 'bpm_drag_offset', 0)
        new_visual_raw = self.x_to_ms(pointer_x) + offset
        new_anchor_time = float(self.visual_to_audio_ms(new_visual_raw, ignore_bpm_tag=selected))
        anchor_initial = self.bpm_drag_initial_times[id(self.dragging_bpm_tag)]
        desired_delta = int(round(new_anchor_time - anchor_initial))
        initial_times = [self.bpm_drag_initial_times[id(tp)] for tp in selected]
        minimum_delta = int(math.ceil(-min(initial_times)))
        audio_len = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap.metadata.ActualAudioLength > 0 else 0
        maximum_delta = int(math.floor(audio_len - max(initial_times))) if audio_len > 0 else desired_delta
        if audio_len > 0:
            for state in self.get_bpm_follow_drag_states():
                state_initial = self.bpm_drag_initial_times[id(state['timing_point'])]
                maximum_delta = min(maximum_delta, int(math.floor(audio_len - self.get_bpm_follow_max_offset(state) - state_initial)))
        if getattr(self, 'drag_bpm_was_first', False) and self.beatmap.hit_objects:
            first_selected = min(selected, key=lambda point: self.bpm_drag_initial_times[id(point)])
            has_follow_state = any(state['timing_point'] is first_selected for state in self.get_bpm_follow_drag_states())
            if not has_follow_state:
                first_note = min(obj.time for obj in self.beatmap.hit_objects)
                maximum_delta = min(maximum_delta, int(math.floor(first_note - self.bpm_drag_initial_times[id(first_selected)])))
        maximum_delta = max(minimum_delta, maximum_delta)
        desired_delta = max(minimum_delta, min(maximum_delta, desired_delta))
        selected_ids = {id(tp) for tp in selected}
        occupied = {int(round(tp['time'])) for tp in self.beatmap.timing_points if id(tp) not in selected_ids}

        def available(delta):
            return all(int(round(self.bpm_drag_initial_times[id(tp)] + delta)) not in occupied for tp in selected)

        delta = desired_delta
        if not available(delta):
            span = max(1, len(self.beatmap.timing_points) + 1)
            candidates = []
            for distance in range(1, span + 1):
                candidates.extend((desired_delta + distance, desired_delta - distance))
            delta = next((candidate for candidate in candidates if minimum_delta <= candidate <= maximum_delta and available(candidate)), desired_delta)
        changed = False
        for tp in selected:
            new_time = self.bpm_drag_initial_times[id(tp)] + delta
            if tp['time'] != new_time:
                changed = True
            tp['time'] = new_time
            tp['_target_visual_time'] = float(new_time)
            if tp not in self.bpm_interpolating:
                self.bpm_interpolating.append(tp)
        for state in self.get_bpm_follow_drag_states():
            self.update_bpm_follow_preview(state)
        self.beatmap.timing_points.sort(key=lambda point: point['time'])
        self._update_tps_cache(self.beatmap.timing_points)
        if self.editor.is_playing:
            self.current_time = self.audio_to_visual_ms(current_audio)
            self.target_time = self.current_time
        if hasattr(self.editor, 'update_bpm_list'):
            self.editor.update_bpm_list()
        if changed:
            self.editor.mark_unsaved()
        self.update_scrollbar()
        self.update()

    def mouseMoveEvent(self, e: QMouseEvent):
        if getattr(self.editor, 'start_screen', None) and self.editor.start_screen.isVisible():
            return
        sf = getattr(self.editor, 'global_scale', 1.0)
        if sf != 1.0:
            p = e.position()
            e = QMouseEvent(e.type(), QPointF(p.x() / sf, p.y() / sf), e.globalPosition(), e.button(), e.buttons(), e.modifiers())
        
        if hasattr(self, 'dragging_bpm_tag') and self.dragging_bpm_tag:
             self.last_mouse_pos = e.pos()
             self.update_dragged_bpm_tags(e.pos().x())
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
                if not self.edge_scroll_speed:
                    self._last_edge_scroll_tick = time.perf_counter()
                self.edge_scroll_speed = scroll * 50
            else:
                self.edge_scroll_speed = 0
            
            self.update_dragged_objects()
            self.update()
        
        elif self.selection_start is not None:
            self.last_mouse_pos = e.pos()
            self.selection_last_mouse_y = e.pos().y()
            margin = 50
            w = self.width() / sf
            scroll = 0
            if e.pos().x() < margin: scroll = -1
            elif e.pos().x() > w - margin: scroll = 1
            
            if scroll != 0:
                if not self.edge_scroll_speed:
                    self._last_edge_scroll_tick = time.perf_counter()
                self.edge_scroll_speed = scroll * 50
            else:
                self.edge_scroll_speed = 0

            self.update_selection_rect()
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
        self._ensure_undo_chunks()
        return {
            'hit_object_chunks': tuple(self._undo_object_chunks),
            'timing_points': self._snapshot_timing_points(),
            'object_order': tuple(
                (int(time_ms), tuple(uids))
                for time_ms, uids in self.beatmap.object_order_overrides.items()
            ),
        }

    def release_bpm_tag(self):
        if hasattr(self, 'dragging_bpm_tag') and self.dragging_bpm_tag:
             selected = [tp for tp in self.beatmap.timing_points if id(tp) in self.bpm_drag_initial_times]
             changed = any(float(tp['time']) != self.bpm_drag_initial_times[id(tp)] for tp in selected)
             release_time = time.time()
             for tp in selected:
                  tp['time'] = int(round(tp['time']))
                  self.bpm_drag_release_times[id(tp)] = release_time
                  self.bpm_drag_start_times.pop(id(tp), None)
                  tp['_target_visual_time'] = tp['time']
                  if tp not in self.bpm_interpolating:
                       self.bpm_interpolating.append(tp)
             for state in self.get_bpm_follow_drag_states():
                  self.apply_bpm_follow_state(state)
             if not changed and len(self.undo_stack) > getattr(self, '_bpm_drag_undo_depth', len(self.undo_stack)):
                  self.undo_stack.pop()
             self.beatmap.timing_points.sort(key=lambda point: point['time'])
             self._update_tps_cache(self.beatmap.timing_points)
             if hasattr(self.editor, 'update_bpm_list'):
                  self.editor.update_bpm_list()
             self.dragging_bpm_tag = None
             self.bpm_follow_drag_state = None
             self.bpm_follow_drag_states.clear()
             self.bpm_drag_initial_times.clear()

    def mouseReleaseEvent(self, e: QMouseEvent):
        if getattr(self.editor, 'start_screen', None) and self.editor.start_screen.isVisible():
            return
        sf = getattr(self.editor, 'global_scale', 1.0)
        if sf != 1.0:
            p = e.position()
            e = QMouseEvent(e.type(), QPointF(p.x() / sf, p.y() / sf), e.globalPosition(), e.button(), e.buttons(), e.modifiers())
        
        if hasattr(self, 'dragging_bpm_tag') and self.dragging_bpm_tag:
             self.release_bpm_tag()
             pk = self.pressed_keys | getattr(self.editor, 'pressed_keys', set())
             is_shift = check_modifier(e.modifiers(), getattr(self.editor, 'current_keybinds', DEFAULT_KEYBINDS).get("multiselect_modifier", "Shift"), pk)
             if not is_shift:
                  self.selected_timing_points.clear()

        self.edge_scroll_speed = 0
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
            
            drag_changed = False
            dragged_objects = ()
            if self.dragging_objects:
                dragged_objects = tuple(self.selected_objects)
                drag_changed = getattr(self, "_drag_undo_saved", False)
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
                returned_to_origin = drag_changed and all(
                    obj.time == self.drag_start_time_map.get(obj, obj.time)
                    and (
                        obj.type != 128 and not self.is_custom_length(obj)
                        or obj.end_time == self.drag_original_end_time_map.get(obj, obj.end_time)
                    )
                    and (
                        obj.is_event
                        or obj.is_freestyle
                        or obj.lane == self.drag_start_lane_map.get(obj, obj.lane)
                    )
                    for obj in dragged_objects
                )
                if returned_to_origin and self.undo_stack:
                    self.undo_stack.pop()
                    drag_changed = False
                
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
            
            if self.beatmap and hasattr(self.beatmap, "hit_objects") and drag_changed:
                self.beatmap.hit_objects.sort(key=lambda x: (x.time, 0 if x.is_event and x.order_index == 0 else (2 if x.is_event else 1), 0 if getattr(x, 'is_freestyle', False) else 1, 0.5 if not x.is_event else float(x.order_index)))
                self.sync_structural_object_caches(dragged_objects)
            
            self.dragging_objects = False
            self._drag_undo_saved = False
            self.last_mouse_pos = None
            self.selection_start = None
            self.selection_start_y = None
            self.selection_rect = None
            self.selection_last_mouse_y = None
            self.timeline_click_pos = None
            self.selection_kind = None
            self._drag_base_timing_selection = []
            
            if hasattr(self.editor, 'update_add_bpm_button_text'):
                self.editor.update_add_bpm_button_text()
            self.update()

    def show_clipboard_toast(self, text, duration=0.8):
        toast = getattr(self.editor, 'save_toast', None)
        if toast is not None:
            toast.show_message(text, duration=duration, key="clipboard_action")

    def build_clipboard_preview(self, items):
        if not items:
            return (), 0
        duration = max(
            max(0, int(item.get('relative_time', 0))) + max(0, int(item.get('duration', 0)))
            for item in items
        )
        sample_limit = 2048
        stride = max(1, math.ceil(len(items) / sample_limit))
        sampled = list(items[::stride])
        if sampled[-1] is not items[-1]:
            sampled.append(items[-1])
        snapshots = set()
        overview = getattr(self, 'timeline_scrollbar', None)
        for sample_index, item in enumerate(sampled):
            start_time = max(0, int(item.get('relative_time', 0)))
            item_duration = max(0, int(item.get('duration', 0)))
            custom_data = custom_object_data_from_tuple(item.get('custom_data'))
            if custom_data is not None:
                custom_data.end_time = start_time + item_duration
            object_params = item.get('objectParams', '0')
            if int(item.get('type', 1)) == 128:
                object_params = str(start_time + item_duration)
            obj = HitObject(
                int(item.get('x', 0)),
                int(item.get('y', 0)),
                start_time,
                int(item.get('type', 1)),
                int(item.get('hitSound', 0)),
                object_params,
                item.get('hitSample', '0:0:0:'),
                item.get('order_index', 0),
                uid=-(sample_index + 2),
                custom_data=custom_data,
            )
            type_data = self.get_custom_type_data(obj)
            if overview is not None and hasattr(overview, 'overview_snapshot'):
                snapshot = overview.overview_snapshot(obj)
                start_time, end_time, row, end_row, pair_row, head_color, line_color, tail_color, diagonal = snapshot
            else:
                start_time = int(obj.time)
                end_time = int(obj.end_time)
                row = {-1: 0, 0: 1, 1: 3, 2: 4}.get(obj.lane, 2)
                end_row = row
                pair_row = -1
                head_color = QColor("#64C8FF").rgba()
                line_color = QColor("#FF5050").rgba() if end_time > start_time else 0
                tail_color = head_color
                diagonal = False
            if duration > 0:
                start_bucket = max(0, min(255, int(round(start_time * 255.0 / duration))))
                end_bucket = max(start_bucket, min(255, int(round(end_time * 255.0 / duration))))
            else:
                start_bucket = 128
                end_bucket = 128
            event_kind = 0
            if obj.is_event or bool(type_data and type_data.get('kind') == 'Event'):
                event_kind = 2 if obj.is_instant_flip else 1
            snapshots.add((
                start_bucket,
                end_bucket,
                int(row),
                int(end_row),
                int(pair_row),
                int(head_color),
                int(line_color),
                int(tail_color),
                bool(diagonal),
                event_kind,
            ))
        return tuple(sorted(snapshots, key=lambda item: (item[0], item[2], item[1]))), duration

    def activate_clipboard_history_entry(self, entry):
        if not any(history_entry is entry for history_entry in self.clipboard_history):
            return
        self.clipboard = entry['items']
        self.active_clipboard_entry = entry
        self.show_clipboard_toast("Copied")

    def copy_selected(self):
        if not self.selected_objects:
            return
        
        copyable = sorted(
            (obj for obj in self.selected_objects if not self.is_custom_missing(obj)),
            key=lambda obj: (obj.time, obj.creation_time, obj.uid),
        )
        if not copyable:
            return
        normalized_starts = {
            obj: self.normalize_grid_audio_time(obj.time)
            for obj in copyable
        }
        min_time = min(normalized_starts.values())
        clipboard = []
        pattern_duration = 0
        for obj in copyable:
            normalized_start = normalized_starts[obj]
            relative_time = normalized_start - min_time
            duration = 0
            if obj.type == 128 or self.is_custom_length(obj):
                normalized_end = self.normalize_grid_audio_time(obj.end_time)
                duration = max(0, normalized_end - normalized_start)
            pattern_duration = max(pattern_duration, relative_time + duration)
                
            clipboard.append({
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
        entry = {
            'items': tuple(clipboard),
            'preview': None,
            'count': len(clipboard),
            'duration': pattern_duration,
        }
        self.clipboard = entry['items']
        self.active_clipboard_entry = entry
        self.clipboard_history.insert(0, entry)
        del self.clipboard_history[100:]
        self._clipboard_history_generation += 1
        if hasattr(self, 'side_panel'):
            self.side_panel.notify_clipboard_history_changed()
        self.show_clipboard_toast("Copied")
        self.selected_objects.clear()
        self.update()

    def paste_clipboard(self):
                
        if not self.clipboard or not self.beatmap:
            return
        
        _, paste_time = self.get_snapped_timeline_time(self.current_time)
        
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
            self.show_clipboard_toast("Paste failed due to notes blocking the target area", duration=1.2)
            self.update()
            return
        
        self.save_undo_state()
        self.selected_timing_points.clear()
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
                self.update_dragged_bpm_tags(self.last_mouse_pos.x())

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

    def delete_selected_timing_points(self):
        if not self.beatmap or not self.selected_timing_points:
            return False
        selected_ids = {id(tp) for tp in self.selected_timing_points}
        remaining = [tp for tp in self.beatmap.timing_points if id(tp) not in selected_ids]
        if not remaining:
            return False
        remaining.sort(key=lambda point: point['time'])
        if self.beatmap.hit_objects:
            first_note_time = min(obj.time for obj in self.beatmap.hit_objects)
            if first_note_time < remaining[0]['time']:
                QMessageBox.warning(self.editor if self.editor else None, "Action Prevented", "Cannot delete these BPM tags because a note would be left without a preceding BPM tag.")
                return False
        self.save_undo_state()
        current_audio = self.visual_to_audio_ms(self.current_time)
        deletion_time = time.time()
        for tp in self.selected_timing_points:
            self.dying_bpm_tags.append((tp.copy(), deletion_time))
        self.beatmap.timing_points = remaining
        self.selected_timing_points.clear()
        self._update_tps_cache(remaining)
        self.current_time = self.audio_to_visual_ms(current_audio)
        self.target_time = self.current_time
        if hasattr(self.editor, 'sync_audio_to_time'):
            self.editor.sync_audio_to_time()
        if hasattr(self.editor, 'update_bpm_list'):
            self.editor.update_bpm_list()
        self.editor.mark_unsaved()
        self.update_scrollbar()
        self.update()
        return True

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
        is_grid_half = check_keybind_match(kb.get("grid_half", "E"), e.key(), e.modifiers(), pk)
        is_grid_double = check_keybind_match(kb.get("grid_double", "R"), e.key(), e.modifiers(), pk)

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

        if is_grid_half:
            self.halve_grid()
            e.accept()
            return

        if is_grid_double:
            self.double_grid()
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
                self.selected_timing_points.clear()
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
            if self.selected_timing_points:
                self.delete_selected_timing_points()
            elif self.selected_objects and self.beatmap:
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
