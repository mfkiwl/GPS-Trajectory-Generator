import numpy as np
import argparse
import csv
import math
import os
import random
import sys
import traceback # For detailed error printing

# --- 常量定义 ---
EARTH_RADIUS = 6371000
HEIGHT_FLUCTUATION = 0.003
SMOOTHING_FACTOR = 0.15
DEFAULT_HEIGHT = 100.0
TIME_STEP = 0.1

# --- 速度模式定义 (米/秒) ---
SPEED_MODES = {
    "1": (1.2, 1.5), "2": (2.8, 3.5), "3": (4.5, 5.5), "4": (12.0, 16.0)
}
DEFAULT_SPEED_MODE = "1"

# --- 坐标转换和距离计算函数 ---
def calculate_distance(lat1, lon1, lat2, lon2):
    # (No changes needed)
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None: return 0.0
    if abs(lat1 - lat2) < 1e-9 and abs(lon1 - lon2) < 1e-9: return 0.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1; dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    a = max(0, min(a, 1.0)); c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS * c

def get_last_entry_from_file(filename):
    # (No changes needed)
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        try:
            with open(filename, "r", encoding='utf-8') as f:
                lines = f.readlines(); last_line_content = ""; last_line = None
                for line in reversed(lines):
                    stripped_line = line.strip()
                    if stripped_line and ',' in stripped_line: last_line_content = stripped_line; break
                if last_line_content: last_line = last_line_content.split(",")
                if last_line and len(last_line) >= 3:
                    time = float(last_line[0]); lat = float(last_line[1]); lon = float(last_line[2])
                    try: height = float(last_line[3]) if len(last_line) > 3 else DEFAULT_HEIGHT
                    except (ValueError, IndexError): height = DEFAULT_HEIGHT
                    print(f"检测到轨迹文件 '{filename}'，最后记录: T={time:.1f}, Lat={lat:.8f}, Lon={lon:.8f}, H={height:.3f}")
                    return time, lat, lon, height
                else: print(f"警告: 文件 '{filename}' 为空或最后有效行格式不正确，将重新开始。"); return None, None, None, None
        except Exception as e: print(f"读取轨迹文件 '{filename}' 错误: {e}，将重新开始。"); return None, None, None, None
    print(f"轨迹文件 '{filename}' 不存在或为空，将重新开始。"); return None, None, None, None

def out_of_china(lng, lat):
    # (No changes needed)
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)

def transform_lat_gcj(x, y):
    # (No changes needed)
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret

def transform_lng_gcj(x, y):
    # (No changes needed)
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret

def gcj02_to_wgs84(gcj_lng, gcj_lat):
    # (No changes needed)
    if out_of_china(gcj_lng, gcj_lat): return gcj_lng, gcj_lat
    a = 6378245.0; ee = 0.00669342162296594323
    dlat = transform_lat_gcj(gcj_lng - 105.0, gcj_lat - 35.0)
    dlng = transform_lng_gcj(gcj_lng - 105.0, gcj_lat - 35.0)
    radlat = gcj_lat / 180.0 * math.pi; magic = math.sin(radlat); magic = 1 - ee * magic * magic; sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    return gcj_lng - dlng, gcj_lat - dlat

def bd09_to_gcj02(bd_lng, bd_lat):
    # (No changes needed)
    x_pi = 3.14159265358979324 * 3000.0 / 180.0; x = bd_lng - 0.0065; y = bd_lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * x_pi)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * x_pi)
    return z * math.cos(theta), z * math.sin(theta)

def bd09_to_wgs84(bd_lng, bd_lat):
    # (No changes needed)
    gcj_lng, gcj_lat = bd09_to_gcj02(bd_lng, bd_lat)
    return gcj02_to_wgs84(gcj_lng, gcj_lat)


# --- 核心轨迹段生成函数 ---
def generate_segment(writer, start_lat, start_lon, end_lat, end_lon,
                     speed_mode_key, current_time, current_height, previous_speed):
    """在两个WGS-84点之间生成插值点并写入writer。返回结束状态。"""
    # (No changes needed in this function itself)
    if speed_mode_key not in SPEED_MODES:
        print(f"  警告: 无效的速度模式 '{speed_mode_key}'，使用默认 '{DEFAULT_SPEED_MODE}'。")
        speed_mode_key = DEFAULT_SPEED_MODE
    speed_range = SPEED_MODES[speed_mode_key]

    distance = calculate_distance(start_lat, start_lon, end_lat, end_lon)
    print(f"  距离: {distance:.2f} 米")

    if distance < 0.01:
        print("  距离过小，跳过插值。")
        return end_lat, end_lon, current_time, current_height, previous_speed

    target_speed_in_range = random.uniform(*speed_range)
    if previous_speed is None: current_segment_avg_speed = target_speed_in_range
    else:
        current_segment_avg_speed = previous_speed + SMOOTHING_FACTOR * (target_speed_in_range - previous_speed)
        current_segment_avg_speed = max(speed_range[0] * 0.8, min(current_segment_avg_speed, speed_range[1] * 1.2))
    current_segment_avg_speed = max(current_segment_avg_speed, 0.05)
    print(f"  目标速度范围: {speed_range[0]:.2f}-{speed_range[1]:.2f} m/s")
    print(f"  平滑后平均速度: {current_segment_avg_speed:.2f} m/s")

    total_time_seconds = distance / current_segment_avg_speed
    num_steps = max(1, int(round(total_time_seconds / TIME_STEP)))
    actual_time_step = total_time_seconds / num_steps
    lat_step = (end_lat - start_lat) / num_steps; lon_step = (end_lon - start_lon) / num_steps
    print(f"  预计时间: {total_time_seconds:.2f} 秒")
    print(f"  插值步数: {num_steps} (每步约 {actual_time_step:.3f} 秒)")

    temp_lat = start_lat; temp_lon = start_lon; new_time = current_time; new_height = current_height
    for step in range(num_steps):
        if step == num_steps - 1: temp_lat = end_lat; temp_lon = end_lon
        else: temp_lat += lat_step; temp_lon += lon_step
        new_time += actual_time_step
        height_fluctuation = random.uniform(-HEIGHT_FLUCTUATION, HEIGHT_FLUCTUATION) * 10
        new_height += height_fluctuation; new_height = max(1.0, min(new_height, DEFAULT_HEIGHT + 50))
        writer.writerow([round(new_time, 1), round(temp_lat, 8), round(temp_lon, 8), round(new_height, 3)])

    return end_lat, end_lon, new_time, new_height, current_segment_avg_speed


# --- 交互模式 (通用框架) ---
def run_interactive_core(output_file, coord_system_name, conversion_func=None):
    """处理交互式输入 (WGS-84, GCJ-02, or BD-09)"""
    print(f"--- 交互模式 ({coord_system_name} 输入) ---")
    # Changed prompt_coord_type logic slightly for clarity
    prompt_coord_type = coord_system_name # e.g., "WGS-84", "GCJ-02", "BD-09"

    last_time, last_lat, last_lon, last_height = get_last_entry_from_file(output_file)

    if last_lat is None: # 文件为空或无效
        while True:
            try:
                start_input = input(f"请输入起点 {prompt_coord_type} 经纬度 (格式: 经度,纬度): ").strip()
                start_lon_in, start_lat_in = map(float, start_input.split(","))
                if conversion_func:
                    current_lon, current_lat = conversion_func(start_lon_in, start_lat_in)
                    print(f"  转换后起点 WGS-84 坐标: ({current_lon:.8f}, {current_lat:.8f})") # Added clarification
                else:
                    current_lon, current_lat = start_lon_in, start_lat_in # WGS-84 input
                current_time = 0.0
                current_height = DEFAULT_HEIGHT
                is_first_point = True
                break
            except ValueError: print("输入格式错误，请重新输入。")
            except Exception as e: print(f"处理起点时出错: {e}"); traceback.print_exc(); sys.exit(1) # Added traceback
    else: # 从文件末尾继续
        current_lat, current_lon, current_time, current_height = last_lat, last_lon, last_time, last_height
        is_first_point = False
        print(f"从文件最后点继续: WGS-84 ({current_lon:.8f}, {current_lat:.8f}), T={current_time:.1f}")

    previous_speed = None

    try:
        with open(output_file, "a", newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if is_first_point: # 写入首点
                 writer.writerow([round(current_time, 1), round(current_lat, 8), round(current_lon, 8), round(current_height, 3)])
                 print(f"写入初始点: T={current_time:.1f}, Lat={current_lat:.8f}, Lon={current_lon:.8f}, H={current_height:.3f}")

            while True:
                try:
                    end_input = input(f"请输入下一个终点 {prompt_coord_type} 经纬度 (格式: 经度,纬度, 或输入 'x' 退出): ").strip()
                    if end_input.lower() == 'x': break
                    end_lon_in, end_lat_in = map(float, end_input.split(","))
                    if conversion_func:
                        end_lon, end_lat = conversion_func(end_lon_in, end_lat_in)
                        print(f"  转换后终点 WGS-84 坐标: ({end_lon:.8f}, {end_lat:.8f})") # Added clarification
                    else:
                        end_lon, end_lat = end_lon_in, end_lat_in # WGS-84 input

                    print("选择运动模式: 1. 走路 2. 慢跑 3. 快跑 4. 开车")
                    mode_input = input("请输入模式编号 (1-4): ").strip()
                    # Use a while loop for better input validation
                    while mode_input not in SPEED_MODES:
                        mode_input = input("输入无效，请输入 1, 2, 3 或 4：").strip()

                    print(f"\n--- 生成段落 ---")
                    print(f"  起点 (WGS-84): ({current_lon:.8f}, {current_lat:.8f})")
                    print(f"  终点 (WGS-84): ({end_lon:.8f}, {end_lat:.8f})")
                    print(f"  速度模式: {mode_input}")

                    new_lat, new_lon, new_time, new_height, new_speed = generate_segment(
                        writer, current_lat, current_lon, end_lat, end_lon,
                        mode_input, current_time, current_height, previous_speed
                    )
                    # Update state for the next iteration
                    current_lat, current_lon, current_time, current_height, previous_speed = \
                        new_lat, new_lon, new_time, new_height, new_speed
                    print(f"--- 段落结束 --- (当前: T={current_time:.1f}, Lat={current_lat:.8f}, Lon={current_lon:.8f})")

                except ValueError: print("输入格式错误，请重新输入。"); continue
                except Exception as e: print(f"处理段落时发生错误: {e}"); traceback.print_exc(); break # Exit loop on error

        print("\n交互模式结束。")
    except IOError as e: print(f"错误：无法打开或写入输出文件 '{output_file}'。原因: {e}"); sys.exit(1)
    except Exception as e: print(f"交互模式中发生未知错误: {e}"); traceback.print_exc(); sys.exit(1) # Catch unexpected errors


# --- CSV 文件模式 (-gg) ---
# Renamed to be specific to GCJ-02 CSV
def run_gcj02_csv_mode(input_csv_file, output_file):
    """处理从 GCJ-02 CSV 文件读取数据生成轨迹"""
    coord_system = 'gcj02' # Hardcoded for this function
    print(f"--- CSV 模式 (-gg): 读取高德/GCJ-02 格式 CSV '{input_csv_file}' ---")
    conversion_func = gcj02_to_wgs84; coord_system_name = "GCJ-02"

    # --- The rest of this function is identical to the previous run_csv_mode ---
    # --- It specifically uses gcj02_to_wgs84 ---

    raw_waypoints = []; print(f"正在读取输入文件: {input_csv_file}")
    try:
        with open(input_csv_file, 'r', encoding='utf-8-sig') as infile:
            reader = csv.reader(infile);
            try:
                header = next(reader)
            except StopIteration:
                 print(f"错误：输入文件 '{input_csv_file}' 为空或无法读取表头。"); sys.exit(1)
            print(f"输入文件表头: {header}")
            try: lon_idx = header.index('经度'); lat_idx = header.index('纬度'); spd_idx = header.index('速度')
            except ValueError:
                 try: lon_idx = header.index('longitude'); lat_idx = header.index('latitude'); spd_idx = header.index('speed')
                 except ValueError: print(f"错误：输入 CSV 缺少列标题 ('经度', '纬度', '速度' 或 'longitude', 'latitude', 'speed')。"); sys.exit(1)

            for i, row in enumerate(reader):
                line_num = i + 2 # Header is line 1
                if not row or len(row) <= max(lon_idx, lat_idx): print(f"警告：跳过输入第 {line_num} 行，数据不足或为空: {row}"); continue
                try:
                    lon_str = row[lon_idx].strip(); lat_str = row[lat_idx].strip()
                    if not lon_str or not lat_str: print(f"警告：跳过输入第 {line_num} 行，经纬度为空: {row}"); continue
                    lon = float(lon_str); lat = float(lat_str)
                    # Speed mode logic: Use column if present and valid, else None
                    speed_mode_str = ""
                    if len(row) > spd_idx:
                        speed_mode_str = row[spd_idx].strip()

                    mode_in = None # Default if speed col is missing/empty or for first point
                    if i > 0: # Don't use speed from the first point row itself
                        if speed_mode_str and speed_mode_str in SPEED_MODES:
                            mode_in = speed_mode_str
                        elif speed_mode_str: # If present but invalid
                            print(f"警告：输入第 {line_num} 行速度模式 '{speed_mode_str}' 无效，将用前段/默认。")
                            mode_in = None # Mark as invalid/use previous
                        # else: mode_in remains None (empty cell)

                    raw_waypoints.append({'orig_lon': lon, 'orig_lat': lat, 'mode_in': mode_in, 'line': line_num})
                except ValueError as e: print(f"错误：处理输入第 {line_num} 行数值转换错误: {e}。行数据: {row}"); sys.exit(1)

    except FileNotFoundError: print(f"错误：输入文件 '{input_csv_file}' 未找到。"); sys.exit(1)
    # Removed StopIteration catch here, handled inside the 'with open' block now.
    except Exception as e: print(f"读取或解析输入文件 '{input_csv_file}' 时发生未知错误: {e}"); traceback.print_exc(); sys.exit(1)

    if len(raw_waypoints) < 1: print("错误：输入文件未包含有效航点。"); sys.exit(1)
    elif len(raw_waypoints) == 1: print("警告：输入文件只包含一个航点，无法生成轨迹段。")
    print(f"成功读取 {len(raw_waypoints)} 个原始航点。")

    wgs_waypoints = []; last_valid_segment_mode = DEFAULT_SPEED_MODE
    print(f"\n开始转换 {coord_system_name} 坐标为 WGS-84 并确定段速度...")
    for i, wp in enumerate(raw_waypoints):
        wgs_lon, wgs_lat = conversion_func(wp['orig_lon'], wp['orig_lat'])
        segment_mode = None # For the first point, it doesn't define the *segment leading to it*
        if i == 0:
            print(f"  航点 0 (行 {wp['line']}): 起点 WGS-84 ({wgs_lon:.8f}, {wgs_lat:.8f}) (速度忽略)")
        else:
            # The speed mode associated with waypoint 'i' defines the segment *from i-1 to i*
            mode_in = wp['mode_in']
            if mode_in is None: # Speed was missing, invalid, or empty in CSV for this point
                segment_mode = last_valid_segment_mode # Use the mode from the *previous* valid segment
                print(f"  航点 {i} (行 {wp['line']}): WGS-84 ({wgs_lon:.8f}, {wgs_lat:.8f}), 速度 '{segment_mode}' (继承/默认)")
            else: # Speed was validly specified in the CSV for this point
                segment_mode = mode_in
                last_valid_segment_mode = segment_mode # Update the last known good mode
                print(f"  航点 {i} (行 {wp['line']}): WGS-84 ({wgs_lon:.8f}, {wgs_lat:.8f}), 速度 '{segment_mode}' (来自输入)")
        # Store the *segment* speed mode with the *end* waypoint of that segment
        wgs_waypoints.append({'lon': wgs_lon, 'lat': wgs_lat, 'segment_mode': segment_mode, 'line': wp['line']})

    print(f"\n开始生成轨迹到文件: {output_file}")
    last_time, last_lat, last_lon, last_height = get_last_entry_from_file(output_file)

    start_wgs_wp_index = 0; is_first_output_point = True; is_appending = False
    if last_lat is None: # File empty or invalid - start from first waypoint
        if not wgs_waypoints: print("错误：没有有效 WGS 航点。"); sys.exit(1)
        current_lat = wgs_waypoints[0]['lat']; current_lon = wgs_waypoints[0]['lon']
        current_time = 0.0; current_height = DEFAULT_HEIGHT
        start_wgs_wp_index = 0; is_first_output_point = True
        print("从输入文件的第一个点开始新轨迹。")
        if len(wgs_waypoints) == 1: # Handle single point input CSV
            try:
                with open(output_file, "w", newline='', encoding='utf-8') as f: # Use 'w' to overwrite if starting fresh
                    writer = csv.writer(f); writer.writerow([round(current_time, 1), round(current_lat, 8), round(current_lon, 8), round(current_height, 3)])
                print(f"写入单个起始点: T={current_time:.1f}, Lat={current_lat:.8f}, Lon={current_lon:.8f}, H={current_height:.3f}"); sys.exit(0)
            except IOError as e: print(f"错误：写入输出文件 '{output_file}'。原因: {e}"); sys.exit(1)
    else: # Continue from last point in file
        current_lat = last_lat; current_lon = last_lon; current_time = last_time; current_height = last_height
        start_wgs_wp_index = 0 # We always process segments starting from index 0 of wgs_waypoints
        is_first_output_point = False
        is_appending = True # Flag that we need an initial segment from file-end to first waypoint
        print(f"从文件最后点继续: WGS-84 ({current_lon:.8f}, {current_lat:.8f}), T={current_time:.1f}")

    previous_speed = None # Reset previous speed when starting generation loop
    try:
        # Use 'a' mode here as we might be appending or writing the first point of a new file
        with open(output_file, "a", newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if is_first_output_point and len(wgs_waypoints) > 0: # Write first point only if starting fresh
                writer.writerow([round(current_time, 1), round(current_lat, 8), round(current_lon, 8), round(current_height, 3)])
                print(f"写入初始点 (来自航点 0): T={current_time:.1f}, Lat={current_lat:.8f}, Lon={current_lon:.8f}, H={current_height:.3f}")

            num_wgs_waypoints = len(wgs_waypoints)

            # Loop through segments defined by waypoints
            # The loop goes from 0 to num_wgs_waypoints-2, processing segments (0->1, 1->2, ..., n-2 -> n-1)
            # If appending, an extra segment (file_end -> 0) is handled before the loop.
            loop_start_index = 0
            if is_appending and num_wgs_waypoints > 0:
                # Generate the segment from the file's last point to the first waypoint from the CSV
                end_wp = wgs_waypoints[0]
                end_lat = end_wp['lat']; end_lon = end_wp['lon']
                # Use the speed mode defined for the *first segment* (0->1) if available, else default
                segment_speed_mode = DEFAULT_SPEED_MODE
                if num_wgs_waypoints > 1 and wgs_waypoints[1]['segment_mode'] is not None:
                    segment_speed_mode = wgs_waypoints[1]['segment_mode']
                elif num_wgs_waypoints == 1: # Only one point in CSV, use default speed for append segment
                     segment_speed_mode = DEFAULT_SPEED_MODE # Or maybe prompt? Default is simpler.

                print(f"\n--- 处理追加段 (文件末尾 -> 航点 0) ---")
                print(f"  起点: ({current_lon:.8f}, {current_lat:.8f}) (来自文件)")
                print(f"  终点: ({end_lon:.8f}, {end_lat:.8f}) (来自航点 0, 行 {end_wp['line']})")
                print(f"  速度模式: {segment_speed_mode} (来自航点1/默认)")

                new_lat, new_lon, new_time, new_height, new_speed = generate_segment(
                    writer, current_lat, current_lon, end_lat, end_lon,
                    segment_speed_mode, current_time, current_height, previous_speed
                )
                current_lat, current_lon, current_time, current_height, previous_speed = \
                    new_lat, new_lon, new_time, new_height, new_speed
                # Now current state matches waypoint 0, proceed with segments from waypoint 0 onwards
            # else: # Not appending, start normal loop from index 0

            # Generate segments between waypoints from the CSV file
            for i in range(loop_start_index, num_wgs_waypoints - 1):
                start_wp = wgs_waypoints[i]
                end_wp = wgs_waypoints[i + 1]
                start_lat = start_wp['lat']; start_lon = start_wp['lon']
                end_lat = end_wp['lat']; end_lon = end_wp['lon']
                # The speed for segment i -> i+1 is stored in end_wp (i.e., wgs_waypoints[i+1])
                segment_speed_mode = end_wp['segment_mode'] if end_wp['segment_mode'] is not None else DEFAULT_SPEED_MODE

                print(f"\n--- 处理段 {i} -> {i+1} (行 {start_wp['line']} -> {end_wp['line']}) ---")
                print(f"  起点: ({start_lon:.8f}, {start_lat:.8f})")
                print(f"  终点: ({end_lon:.8f}, {end_lat:.8f})")
                print(f"  速度模式: {segment_speed_mode}")

                new_lat, new_lon, new_time, new_height, new_speed = generate_segment(
                    writer, start_lat, start_lon, end_lat, end_lon,
                    segment_speed_mode, current_time, current_height, previous_speed
                )
                current_lat, current_lon, current_time, current_height, previous_speed = \
                    new_lat, new_lon, new_time, new_height, new_speed

            print(f"\n轨迹生成完成。最后点: T={current_time:.1f}, Lat={current_lat:.8f}, Lon={current_lon:.8f}, H={current_height:.3f}")

    except IOError as e: print(f"错误：写入输出文件 '{output_file}'。原因: {e}"); sys.exit(1)
    except Exception as e: print(f"生成轨迹过程中发生未知错误: {e}"); traceback.print_exc(); sys.exit(1)


# --- 主程序入口 ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="生成 GPS 轨迹文件 (.csv)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="模式选择 (若不指定，则默认为 WGS-84 交互模式):\n"
               "  (无参数)       : 交互模式，手动输入 WGS-84 坐标点和速度模式。\n"
               "  -g             : 交互模式，手动输入高德/GCJ-02 坐标点和速度模式。\n"
               "  -b             : 交互模式，手动输入百度/BD-09 坐标点和速度模式。\n" # Added -b description
               "  -gg <文件路径> : CSV模式，读取高德/GCJ-02 格式的CSV文件。\n"
               "                   CSV格式: 经度,纬度,速度 (列标题需包含 '经度'/'纬度'/'速度' 或 'longitude'/'latitude'/'speed')。\n"
               "                   速度列为可选，若缺少或无效则继承上一段。\n"
               # "-b <文件路径> : CSV模式，读取百度/BD-09 格式的CSV文件 (假设格式同-gg)。\n\n" # Removed Baidu CSV option for now
               "\n通用选项:\n"
               "  -o <文件名>    : 指定输出文件名 (默认: trajectory.csv)。\n"
               "  -x             : 清空输出文件后再运行。\n\n"
               "by：兮辰 | GitHub: https://github.com/xichenyun/GPS-Trajectory-Generator"
    )
    parser.add_argument("-o", "--output", type=str, default="trajectory.csv", help="输出的 WGS-84 轨迹文件名。")
    parser.add_argument("-x", "--clear", action="store_true", help="清空输出文件后再开始生成。")

    # --- 模式选择 (互斥，但非必需) ---
    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument("-g", "--gaode_interactive", action='store_true', help="交互模式，手动输入高德/GCJ-02坐标。")
    mode_group.add_argument("-b", "--baidu_interactive", action='store_true', help="交互模式，手动输入百度/BD-09坐标。") # Added -b flag
    mode_group.add_argument("-gg", "--gaode_csv", type=str, metavar='INPUT_CSV', help="CSV模式，读取高德/GCJ-02格式的CSV文件。后接文件路径。")
    # mode_group.add_argument("-bb", "--baidu_csv", type=str, metavar='INPUT_CSV', help="CSV模式，读取百度/BD-09格式的CSV文件。后接文件路径。") # Example if Baidu CSV needed later

    # Parse arguments
    try:
        args = parser.parse_args()
    except Exception as e:
        print(f"参数解析错误: {e}")
        parser.print_help()
        sys.exit(1)


    output_file = args.output

    # --- 清空输出文件 ---
    if args.clear:
        try:
            # Ensure the directory exists before trying to create/clear the file
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
                print(f"创建目录: '{output_dir}'")
            with open(output_file, "w", encoding='utf-8') as f: # Ensure encoding consistency
                # Optionally write header if desired for empty files
                # writer = csv.writer(f)
                # writer.writerow(["Timestamp", "Latitude", "Longitude", "Height"])
                pass # Just clear it
            print(f"文件 '{output_file}' 已清空。")
        except IOError as e:
            print(f"错误：无法清空或创建文件 '{output_file}'。原因: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"清空文件时发生未知错误: {e}")
            traceback.print_exc()
            sys.exit(1)

    # --- 执行选定模式 ---
    try:
        if args.gaode_csv: # -gg <filepath> was used
            if not os.path.exists(args.gaode_csv):
                 print(f"错误: -gg 指定的文件不存在: '{args.gaode_csv}'")
                 sys.exit(1)
            # Changed to use the specific function
            run_gcj02_csv_mode(args.gaode_csv, output_file)
        # elif args.baidu_csv: # Example if Baidu CSV mode existed
        #     if not os.path.exists(args.baidu_csv):
        #          print(f"错误: -bb 指定的文件不存在: '{args.baidu_csv}'")
        #          sys.exit(1)
        #     run_bd09_csv_mode(args.baidu_csv, output_file) # Assumes run_bd09_csv_mode exists
        elif args.baidu_interactive: # -b was used (Interactive Baidu)
            run_interactive_core(output_file, "BD-09", bd09_to_wgs84)
        elif args.gaode_interactive: # -g was used (Interactive GCJ-02)
            run_interactive_core(output_file, "GCJ-02", gcj02_to_wgs84)
        else: # Default: No mode flag was used
            run_interactive_core(output_file, "WGS-84", None) # WGS-84 interactive
    except SystemExit: # Allow sys.exit() to propagate
        pass
    except Exception as e:
        print("\n--- 程序意外终止 ---")
        print(f"发生未处理的错误: {e}")
        traceback.print_exc()
        sys.exit(1)