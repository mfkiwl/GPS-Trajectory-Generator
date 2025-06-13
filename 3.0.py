# -*- coding: utf-8 -*-
import argparse
import csv
import math
import os
import random
import sys
import traceback
from datetime import datetime, timezone, timedelta

# --- 常量定义 ---
EARTH_RADIUS = 6371000
HEIGHT_FLUCTUATION = 0.003
SMOOTHING_FACTOR = 0.15
DEFAULT_HEIGHT = 100.0
TIME_STEP = 0.1
KNOTS_PER_METER_PER_SECOND = 1.94384
# 速度模式定义 (米/秒)
SPEED_MODES = {"1": (1.2, 1.5), "2": (2.8, 3.5), "3": (4.5, 5.5), "4": (12.0, 16.0)}
DEFAULT_SPEED_MODE = "1"

# --- 核心计算与坐标转换函数 (无变化) ---
def calculate_distance(lat1, lon1, lat2, lon2):
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None: return 0.0
    if abs(lat1 - lat2) < 1e-9 and abs(lon1 - lon2) < 1e-9: return 0.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1; dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    a = max(0, min(a, 1.0)); c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS * c
def calculate_bearing(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dLon = lon2 - lon1
    if abs(dLon) < 1e-9 and abs(lat2-lat1) < 1e-9: return 0.0
    y = math.sin(dLon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dLon)
    bearing = math.atan2(y, x)
    return (math.degrees(bearing) + 360) % 360
def get_last_entry_from_file(filename):
    if not filename or not os.path.exists(filename) or os.path.getsize(filename) == 0: return None, None, None, None
    try:
        with open(filename, "r", encoding='utf-8') as f:
            lines = f.readlines()
            for line in reversed(lines):
                line_content = line.strip()
                if line_content and ',' in line_content and line_content.split(',')[0].replace('.', '', 1).isdigit():
                    parts = line_content.split(",")
                    if len(parts) >= 3:
                        time, lat, lon = float(parts[0]), float(parts[1]), float(parts[2])
                        height = float(parts[3]) if len(parts) > 3 else DEFAULT_HEIGHT
                        print(f"检测到轨迹文件 '{filename}'，最后记录: T={time:.1f}, Lat={lat:.8f}, Lon={lon:.8f}, H={height:.3f}")
                        return time, lat, lon, height
    except Exception as e: print(f"读取轨迹文件 '{filename}' 错误: {e}")
    return None, None, None, None
def out_of_china(lng, lat): return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)
def transform_lat_gcj(x, y):
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret
def transform_lng_gcj(x, y):
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret
def gcj02_to_wgs84(gcj_lng, gcj_lat):
    if out_of_china(gcj_lng, gcj_lat): return gcj_lng, gcj_lat
    a = 6378245.0; ee = 0.00669342162296594323
    dlat = transform_lat_gcj(gcj_lng - 105.0, gcj_lat - 35.0)
    dlng = transform_lng_gcj(gcj_lng - 105.0, gcj_lat - 35.0)
    radlat = gcj_lat / 180.0 * math.pi; magic = math.sin(radlat); magic = 1 - ee * magic * magic; sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    return gcj_lng - dlng, gcj_lat - dlat
def bd09_to_gcj02(bd_lng, bd_lat):
    x_pi = 3.14159265358979324 * 3000.0 / 180.0; x = bd_lng - 0.0065; y = bd_lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * x_pi)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * x_pi)
    return z * math.cos(theta), z * math.sin(theta)
def bd09_to_wgs84(bd_lng, bd_lat):
    gcj_lng, gcj_lat = bd09_to_gcj02(bd_lng, bd_lat)
    return gcj02_to_wgs84(gcj_lng, gcj_lat)

# --- 数据格式化与写入模块 (无变化) ---
def nmea_checksum(sentence_body):
    checksum = 0
    for char in sentence_body: checksum ^= ord(char)
    return f"{checksum:02X}"
def decimal_to_dmm(degrees, is_lat):
    is_negative = degrees < 0; degrees = abs(degrees)
    d = int(degrees); m = (degrees - d) * 60
    if is_lat: return f"{d:02d}{m:07.4f}", 'S' if is_negative else 'N'
    else: return f"{d:03d}{m:07.4f}", 'W' if is_negative else 'E'
def create_gpgga_sentence(p):
    time_str = p['utc_time'].strftime("%H%M%S.%f")[:9]
    lat_dmm, lat_hem = decimal_to_dmm(p['lat'], True); lon_dmm, lon_hem = decimal_to_dmm(p['lon'], False)
    body = f"GPGGA,{time_str},{lat_dmm},{lat_hem},{lon_dmm},{lon_hem},1,12,0.8,{p['height']:.1f},M,,M,,"
    return f"${body}*{nmea_checksum(body)}"
def create_gprmc_sentence(p):
    time_str = p['utc_time'].strftime("%H%M%S.%f")[:9]; date_str = p['utc_time'].strftime("%d%m%y")
    lat_dmm, lat_hem = decimal_to_dmm(p['lat'], True); lon_dmm, lon_hem = decimal_to_dmm(p['lon'], False)
    body = f"GPRMC,{time_str},A,{lat_dmm},{lat_hem},{lon_dmm},{lon_hem},{p['speed_knots']:.2f},{p['bearing']:.2f},{date_str},,"
    return f"${body}*{nmea_checksum(body)}"
def write_kml_file(trajectory_points, kml_filename, track_name="Converted Track"):
    if not trajectory_points: print("警告: 没有有效的坐标点，无法生成KML文件。"); return
    print(f"正在将 {len(trajectory_points)} 个点写入KML文件: {kml_filename}")
    try:
        with open(kml_filename, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">\n  <Document>\n')
            f.write(f'    <name>{track_name}</name>\n    <Placemark>\n      <name>Trajectory</name>\n      <LineString>\n')
            f.write('        <tessellate>1</tessellate>\n        <altitudeMode>absolute</altitudeMode>\n        <coordinates>\n          ')
            coords_str = "\n          ".join([f"{p['lon']:.8f},{p['lat']:.8f},{p['height']:.3f}" for p in trajectory_points])
            f.write(coords_str)
            f.write('\n        </coordinates>\n      </LineString>\n    </Placemark>\n  </Document>\n</kml>\n')
        print(f"KML文件 '{kml_filename}' 生成成功。")
    except IOError as e: print(f"错误: 无法写入KML文件 '{kml_filename}'。原因: {e}")

# --- KML转换模块 (无变化) ---
def dmm_to_decimal(dmm_str, hemisphere):
    dmm_val = float(dmm_str)
    degrees = int(dmm_val / 100)
    minutes = dmm_val - degrees * 100
    decimal = degrees + minutes / 60.0
    if hemisphere in ['S', 'W']: return -decimal
    return decimal
def parse_csv_to_points(filepath):
    points = []
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if not row or len(row) < 3: continue
                if not row[0].replace('.', '', 1).isdigit(): continue
                try:
                    lon = float(row[2]); lat = float(row[1]) # 调换顺序
                    height = float(row[3]) if len(row) > 3 and row[3] else DEFAULT_HEIGHT
                    points.append({'lon': lon, 'lat': lat, 'height': height})
                except (ValueError, IndexError):
                    print(f"  警告: 跳过CSV第 {i+1} 行: {row}")
                    continue
    except Exception as e: print(f"解析CSV文件 '{filepath}' 出错: {e}")
    return points
def parse_gpgga_to_points(filepath):
    points = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('$GPGGA'):
                    parts = line.strip().split('*')[0].split(',')
                    if len(parts) > 10 and parts[2] and parts[4] and parts[9]:
                        lat = dmm_to_decimal(parts[2], parts[3]); lon = dmm_to_decimal(parts[4], parts[5]); height = float(parts[9])
                        points.append({'lon': lon, 'lat': lat, 'height': height})
    except Exception as e: print(f"解析GPGGA文件 '{filepath}' 出错: {e}")
    return points
def parse_gprmc_to_points(filepath):
    points = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('$GPRMC'):
                    parts = line.strip().split('*')[0].split(',')
                    if len(parts) > 6 and parts[3] and parts[5]:
                        lat = dmm_to_decimal(parts[3], parts[4]); lon = dmm_to_decimal(parts[5], parts[6])
                        points.append({'lon': lon, 'lat': lat, 'height': DEFAULT_HEIGHT})
    except Exception as e: print(f"解析GPRMC文件 '{filepath}' 出错: {e}")
    return points
def run_kml_conversion_mode(input_file):
    print(f"--- KML 转换模式 ---")
    if not os.path.exists(input_file): print(f"错误: 输入文件 '{input_file}' 不存在。"); sys.exit(1)
    file_ext = os.path.splitext(input_file)[1].lower()
    points = []
    if file_ext == '.csv':
        print(f"检测到 CSV 文件，将按 time,lat,lon 格式解析...")
        points = parse_csv_to_points(input_file)
    else:
        try:
            with open(input_file, 'r', encoding='utf-8') as f: first_line = f.readline().strip()
        except Exception as e: print(f"无法读取文件 '{input_file}': {e}"); sys.exit(1)
        if first_line.startswith('$GPGGA'): print(f"检测到 GPGGA 格式..."); points = parse_gpgga_to_points(input_file)
        elif first_line.startswith('$GPRMC'): print(f"检测到 GPRMC 格式..."); points = parse_gprmc_to_points(input_file)
        else: print(f"错误: 无法识别文件 '{input_file}' 的格式。"); sys.exit(1)
    if points: write_kml_file(points, f"{os.path.splitext(input_file)[0]}.kml")
    else: print("未从文件中解析出任何坐标点。")


# --- 轨迹生成模块 (已修改) ---
def generate_segment(start_lat, start_lon, end_lat, end_lon, speed_range, current_time, current_height, previous_speed, utc_start_time):
    """【修改】: speed_mode_key 参数改为 speed_range (min_speed, max_speed)"""
    segment_points = []
    distance = calculate_distance(start_lat, start_lon, end_lat, end_lon)
    if distance < 0.01: return [], end_lat, end_lon, current_time, current_height, previous_speed
    
    # 速度平滑和随机化逻辑保持不变，直接使用传入的 speed_range
    target_speed_in_range = random.uniform(*speed_range)
    current_segment_avg_speed = target_speed_in_range if previous_speed is None else previous_speed + SMOOTHING_FACTOR * (target_speed_in_range - previous_speed)
    # 限制速度平滑后的值在合理范围内
    current_segment_avg_speed = max(speed_range[0] * 0.8, min(current_segment_avg_speed, speed_range[1] * 1.2))
    current_segment_avg_speed = max(current_segment_avg_speed, 0.05)
    
    total_time_seconds = distance / current_segment_avg_speed
    num_steps = max(1, int(round(total_time_seconds / TIME_STEP)))
    actual_time_step = total_time_seconds / num_steps
    lat_step = (end_lat - start_lat) / num_steps; lon_step = (end_lon - start_lon) / num_steps
    
    prev_point_lat, prev_point_lon = start_lat, start_lon
    temp_lat, temp_lon, new_time, new_height = start_lat, start_lon, current_time, current_height
    for step in range(num_steps):
        if step == num_steps - 1: temp_lat, temp_lon = end_lat, end_lon
        else: temp_lat += lat_step; temp_lon += lon_step
        new_time += actual_time_step
        new_height += random.uniform(-HEIGHT_FLUCTUATION, HEIGHT_FLUCTUATION) * 10
        step_dist = calculate_distance(prev_point_lat, prev_point_lon, temp_lat, temp_lon)
        instant_speed_ms = step_dist / actual_time_step if actual_time_step > 0 else 0
        point_data = {
            'time': new_time, 'lat': temp_lat, 'lon': temp_lon, 'height': new_height,
            'utc_time': utc_start_time + timedelta(seconds=new_time),
            'speed_knots': instant_speed_ms * KNOTS_PER_METER_PER_SECOND,
            'bearing': calculate_bearing(prev_point_lat, prev_point_lon, temp_lat, temp_lon)
        }
        segment_points.append(point_data)
        prev_point_lat, prev_point_lon = temp_lat, temp_lon
    return segment_points, end_lat, end_lon, new_time, new_height, current_segment_avg_speed

def run_trajectory_generation(args):
    print("--- 轨迹生成模式 ---")

    # --- 【新增】解析自定义速度 ---
    custom_speed_range = None
    if args.speed:
        try:
            parts = [float(p.strip()) for p in args.speed.split('-')]
            if len(parts) == 1:
                # 如果只输入一个数字，比如 -s 10，我们认为是一个固定速度，可设一个微小范围
                custom_speed_range = (parts[0] * 0.98, parts[0] * 1.02)
            elif len(parts) == 2:
                custom_speed_range = (min(parts), max(parts))
            else:
                raise ValueError
            print(f"信息: 使用自定义速度范围: {custom_speed_range[0]:.2f}-{custom_speed_range[1]:.2f} m/s。将忽略所有其他速度设置。")
        except (ValueError, IndexError):
            print(f"错误: 无效的速度范围格式 '{args.speed}'。请使用格式 '最小速度-最大速度' (例如 '10-15')。")
            sys.exit(1)

    should_write_csv = not (args.gaode_csv and (args.gprmc or args.gpgga))
    if not should_write_csv: print("信息: 检测到 -gg 与 -c 或 -a 同用，将不生成 .csv 文件。")
    base_name, _ = os.path.splitext(args.output)
    output_csv_file = f"{base_name}.csv" if should_write_csv else None
    output_gprmc_file = f"{base_name}_gprmc.txt" if args.gprmc else None
    output_gpgga_file = f"{base_name}_gpgga.txt" if args.gpgga else None
    if args.clear:
        for f_path in [output_csv_file, output_gprmc_file, output_gpgga_file]:
            if f_path and os.path.exists(f_path): os.remove(f_path); print(f"文件 '{f_path}' 已清空。")
    waypoints = []
    if args.gaode_csv:
        print(f"正在读取高德CSV: {args.gaode_csv}")
        try:
            with open(args.gaode_csv, 'r', encoding='utf-8-sig') as infile:
                reader = csv.reader(infile); header = next(reader)
                lon_idx, lat_idx, spd_idx = header.index('经度'), header.index('纬度'), header.index('速度')
                for i, row in enumerate(reader):
                    lon, lat = float(row[lon_idx]), float(row[lat_idx])
                    wgs_lon, wgs_lat = gcj02_to_wgs84(lon, lat)
                    # 如果有自定义速度，则忽略CSV中的速度
                    mode = row[spd_idx].strip() if not custom_speed_range and len(row) > spd_idx and row[spd_idx].strip() in SPEED_MODES else None
                    waypoints.append({'lon': wgs_lon, 'lat': wgs_lat, 'mode': mode})
        except Exception as e: print(f"读取或解析输入CSV时出错: {e}"); sys.exit(1)
    
    csv_file, gprmc_file, gpgga_file, csv_writer = None, None, None, None
    try:
        if output_csv_file: csv_file = open(output_csv_file, 'a', newline='', encoding='utf-8'); csv_writer = csv.writer(csv_file)
        if output_gprmc_file: gprmc_file = open(output_gprmc_file, 'a', encoding='utf-8')
        if output_gpgga_file: gpgga_file = open(output_gpgga_file, 'a', encoding='utf-8')
        
        last_time, last_lat, last_lon, last_height = get_last_entry_from_file(output_csv_file)
        is_appending = last_lat is not None
        
        if args.gaode_csv:
            if is_appending: current_lat, current_lon, current_time, current_height = last_lat, last_lon, last_time, last_height
            elif waypoints: current_lat, current_lon, current_time, current_height = waypoints[0]['lat'], waypoints[0]['lon'], 0.0, DEFAULT_HEIGHT
            else: print("错误: CSV文件为空或无效。"); sys.exit(1)
            previous_speed = None
            utc_start_time = datetime.now(timezone.utc) - timedelta(seconds=current_time)
            if csv_writer and not is_appending and waypoints:
                csv_writer.writerow([round(current_time, 1), round(current_lat, 8), round(current_lon, 8), round(current_height, 3)])
            wp_to_process = ([{'lon': current_lon, 'lat': current_lat}] + waypoints) if is_appending else waypoints
            last_valid_mode = DEFAULT_SPEED_MODE
            for i in range(len(wp_to_process) - 1):
                start_wp, end_wp = wp_to_process[i], wp_to_process[i+1]
                # 【修改】速度选择逻辑
                if custom_speed_range:
                    speed_range = custom_speed_range
                else:
                    mode = end_wp.get('mode') or last_valid_mode
                    if end_wp.get('mode'): last_valid_mode = end_wp.get('mode')
                    speed_range = SPEED_MODES.get(mode, SPEED_MODES[DEFAULT_SPEED_MODE])
                
                segment_points, new_lat, new_lon, new_time, new_height, new_speed = generate_segment(
                    start_wp['lat'], start_wp['lon'], end_wp['lat'], end_wp['lon'], speed_range,
                    current_time, current_height, previous_speed, utc_start_time
                )
                for p in segment_points:
                    if csv_writer: csv_writer.writerow([round(p['time'], 1), p['lat'], p['lon'], round(p['height'], 3)])
                    if gprmc_file: gprmc_file.write(create_gprmc_sentence(p) + '\n')
                    if gpgga_file: gpgga_file.write(create_gpgga_sentence(p) + '\n')
                current_time, current_height, previous_speed = new_time, new_height, new_speed
        
        elif args.gaode_interactive or args.baidu_interactive:
            prompt = "高德/GCJ-02" if args.gaode_interactive else "百度/BD-09"
            conversion_func = gcj02_to_wgs84 if args.gaode_interactive else bd09_to_wgs84
            if is_appending: current_lat, current_lon, current_time, current_height = last_lat, last_lon, last_time, last_height
            else:
                while True:
                    try:
                        start_input = input(f"请输入起点 {prompt} 经纬度 (格式: 经度,纬度): ").strip()
                        start_lon_in, start_lat_in = map(float, start_input.split(","))
                        current_lon, current_lat = conversion_func(start_lon_in, start_lat_in)
                        current_time, current_height = 0.0, DEFAULT_HEIGHT
                        if csv_writer: csv_writer.writerow([round(current_time, 1), current_lat, current_lon, round(current_height, 3)])
                        print(f"起点 WGS-84 坐标: ({current_lon:.8f}, {current_lat:.8f})")
                        break
                    except ValueError: print("输入格式错误，请重新输入。")
            previous_speed = None
            utc_start_time = datetime.now(timezone.utc) - timedelta(seconds=current_time)
            while True:
                try:
                    end_input = input(f"请输入下一个终点 {prompt} 经纬度 (或输入 'x' 退出): ").strip()
                    if end_input.lower() == 'x': break
                    end_lon_in, end_lat_in = map(float, end_input.split(","))
                    end_lon, end_lat = conversion_func(end_lon_in, end_lat_in)
                    print(f"  转换后终点 WGS-84 坐标: ({end_lon:.8f}, {end_lat:.8f})")
                    
                    # 【修改】速度选择逻辑
                    if custom_speed_range:
                        speed_range = custom_speed_range
                    else:
                        print("选择运动模式: 1. 走路 2. 慢跑 3. 快跑 4. 开车")
                        mode_input = input("请输入模式编号 (1-4): ").strip()
                        while mode_input not in SPEED_MODES: mode_input = input("输入无效，请输入 1-4：").strip()
                        speed_range = SPEED_MODES[mode_input]

                    segment_points, new_lat, new_lon, new_time, new_height, new_speed = generate_segment(
                        current_lat, current_lon, end_lat, end_lon, speed_range,
                        current_time, current_height, previous_speed, utc_start_time
                    )
                    for p in segment_points:
                        if csv_writer: csv_writer.writerow([round(p['time'], 1), p['lat'], p['lon'], round(p['height'], 3)])
                        if gprmc_file: gprmc_file.write(create_gprmc_sentence(p) + '\n')
                        if gpgga_file: gpgga_file.write(create_gpgga_sentence(p) + '\n')
                    current_lat, current_lon, current_time, current_height, previous_speed = new_lat, new_lon, new_time, new_height, new_speed
                    print(f"--- 段落结束 --- (当前: T={current_time:.1f}, Lat={current_lat:.8f}, Lon={current_lon:.8f})")
                except ValueError: print("输入格式错误，请重新输入。")
                except Exception as e: print(f"处理段落时发生错误: {e}"); traceback.print_exc(); break
    finally:
        if csv_file: csv_file.close()
        if gprmc_file: gprmc_file.close()
        if gpgga_file: gpgga_file.close()
    print("轨迹生成完毕。")

# --- 主程序入口 ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="GPS轨迹生成与KML转换工具",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
用法示例:

1. 从高德CSV生成GPRMC，使用自定义速度 20-25 m/s:
   python %(prog)s -gg my_route.csv -o track -c -s "20-25"

2. 启动交互模式，使用固定速度 15 m/s:
   python %(prog)s -g -o my_interactive_track -s 15

3. 将本脚本生成的CSV/TXT文件转换为KML:
   python %(prog)s -k track.csv
-------------------------------------------------------------------
by: 兮辰，仅在小黄鱼（兮辰666）使用，其他均为盗版
GitHub: https://github.com/xichenyun/GPS-Trajectory-Generator
"""
    )
    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument("-k", "--kml_convert", type=str, metavar='INPUT_FILE', help="【独立模式】将指定的轨迹文件转换为KML。")
    mode_group.add_argument("-gg", "--gaode_csv", type=str, metavar='CSV_FILE', help="【生成模式】从CSV文件生成轨迹。")
    mode_group.add_argument("-g", "--gaode_interactive", action='store_true', help="【生成模式】高德交互模式。")
    mode_group.add_argument("-b", "--baidu_interactive", action='store_true', help="【生成模式】百度交互模式。")
    
    # 【新增】-s 参数
    parser.add_argument("-s", "--speed", type=str, help="【生成模式】自定义速度范围(m/s), 如 '10-15'。将覆盖所有其他速度设置。")
    
    parser.add_argument("-o", "--output", type=str, default="trajectory", help="输出文件名的基础部分。")
    parser.add_argument("-c", "--gprmc", action="store_true", help="生成GPRMC NMEA文件。")
    parser.add_argument("-a", "--gpgga", action="store_true", help="生成GPGGA NMEA文件。")
    parser.add_argument("-x", "--clear", action="store_true", help="清空输出文件。")

    args = parser.parse_args()

    try:
        is_generation_mode = args.gaode_csv or args.gaode_interactive or args.baidu_interactive
        
        if args.kml_convert:
            if is_generation_mode or args.speed:
                 print("警告: -k 模式为独立模式，将忽略所有生成模式相关参数 (-gg, -g, -b, -s 等)。")
            run_kml_conversion_mode(args.kml_convert)
        elif is_generation_mode:
            run_trajectory_generation(args)
        # 如果用户只输入了 -s 但没有指定生成方式，也算错误
        elif args.speed and not is_generation_mode:
            print("错误: -s 参数必须与一种生成模式 (-gg, -g, -b) 联用。")
            parser.print_help()
            sys.exit(1)
        else:
            print("错误: 请指定一种操作模式。")
            parser.print_help()
            sys.exit(1)

    except SystemExit:
        pass
    except Exception as e:
        print("\n--- 程序意外终止 ---")
        traceback.print_exc()
        sys.exit(1)