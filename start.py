import numpy as np
import argparse
import csv
import math
import os
import random

# 常量定义
EARTH_RADIUS = 6371000  # 地球半径（米）
HEIGHT_FLUCTUATION = 0.003  # 高度浮动范围
SMOOTHING_FACTOR = 0.1  # 平滑系数
MIN_SPEED = 0.1  # 最小速度
DEFAULT_HEIGHT = 100.0  # 默认高度

# 计算两点间球面距离（单位：米）
def calculate_distance(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS * c

# 读取 CSV 文件的最后一行
def get_last_entry_from_file(filename):
    """读取 CSV 文件的最后一行，返回时间、经纬度和完整数据"""
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        try:
            with open(filename, "r") as f:
                lines = f.readlines()
                if lines:
                    last_line = lines[-1].strip().split(",")
                    time = float(last_line[0])
                    lat = float(last_line[1])
                    lon = float(last_line[2])
                    height = float(last_line[3]) if len(last_line) > 3 else DEFAULT_HEIGHT
                    return time, lat, lon, height, last_line
        except Exception as e:
            print(f"读取文件时发生错误: {e}")
            return 0.0, None, None, None, None
    return 0.0, None, None, None, None

# 判断是否在中国境内
def out_of_china(lng, lat):
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)

# 经纬度转换函数
def transform_lat(x, y):
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret

def transform_lng(x, y):
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret

def gcj02_to_wgs84(lng, lat):
    if out_of_china(lng, lat):
        return lng, lat
    dlat = transform_lat(lng - 105.0, lat - 35.0)
    dlng = transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - 0.00669342162296594323 * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((6378245.0 * (1 - 0.00669342162296594323)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (6378245.0 / sqrtmagic * math.cos(radlat) * math.pi)
    return lng - dlng, lat - dlat

def bd09_to_gcj02(bd_lng, bd_lat):
    x = bd_lng - 0.0065
    y = bd_lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * math.pi * 3000.0 / 180.0)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * math.pi * 3000.0 / 180.0)
    gg_lng = z * math.cos(theta)
    gg_lat = z * math.sin(theta)
    return gg_lng, gg_lat

def bd09_to_wgs84(bd_lng, bd_lat):
    gcj_lng, gcj_lat = bd09_to_gcj02(bd_lng, bd_lat)
    return gcj02_to_wgs84(gcj_lng, gcj_lat)

# 解析命令行参数
parser = argparse.ArgumentParser(
    description="生成轨迹文件（.csv 格式）。",
    epilog="by：兮辰 | GitHub: https://github.com/xichenyun/GPS-Trajectory-Generator"
)
parser.add_argument("-x", "--clear", action="store_true", help="清空 trajectory.csv 文件后运行。")
parser.add_argument("-n", "--newfile", type=str, default="trajectory.csv", help="指定新的轨迹文件（不存在则创建）。")
group = parser.add_mutually_exclusive_group()
group.add_argument("-g", "--gaode", action='store_true', help="使用高德/谷歌坐标（GCJ-02），转换为 WGS-84。注：谷歌坐标需要反转使用，高德坐标获取：https://lbs.amap.com/tools/picker")
group.add_argument("-b", "--baidu", action='store_true', help="使用百度坐标（BD-09），转换为 WGS-84。百度坐标获取：https://api.map.baidu.com/lbsapi/getpoint/index.html")
args = parser.parse_args()

trajectory_file = args.newfile

if args.clear:
    open(trajectory_file, "w").close()
    print(f"文件 {trajectory_file} 已清空。")

# 获取最后一条记录
last_time, last_lat, last_lon, last_height, last_entry = get_last_entry_from_file(trajectory_file)

# 初始化起点经纬度
start_lat = None
start_lon = None

# 1、若没有数据, 需要先从控制台输入，根据`-g` `-b`判断
if not last_entry:
    if args.gaode:
        print("请输入高德坐标系的起点经纬度，格式为: 经度,纬度 (例如 119.231495,39.865392)")
    elif args.baidu:
        print("请输入百度坐标系的起点经纬度，格式为: 经度,纬度 (例如 119.231495,39.865392)")
    else:
        print("请输入起点经纬度，格式为: 经度,纬度 (例如 119.231495,39.865392)") #如果没有参数默认的也给出提示

    start_input = input("请输入起点经纬度：")
    try:
        start_lon, start_lat = map(float, start_input.split(","))#  先分割坐标
         #  再根据 是否选择高德或者百度坐标选择 是否转换坐标
        if args.gaode:
            start_lon, start_lat = gcj02_to_wgs84(start_lon, start_lat) #转换坐标,纬度和经度换算
        elif args.baidu:
            start_lon, start_lat = bd09_to_wgs84(start_lon, start_lat)   #转换坐标,纬度和经度换算
    except ValueError:
        print("经纬度格式错误，请确保格式为：经度,纬度 (例如 119.231495,39.865392)")
        exit()

# 2、从文件读取
if last_entry:
    print(f"检测到已有轨迹数据，最后一条数据：{last_entry}")
    start_lat = float(last_entry[1])
    start_lon = float(last_entry[2])

current_time = 0.0 if not last_entry else float(last_entry[0])
current_height = DEFAULT_HEIGHT if not last_entry else float(last_entry[3]) if len(last_entry) > 3 else DEFAULT_HEIGHT

# 速度初始化
previous_speed = None

while True:
    try:
        end_input = input("请输入终点经纬度（格式: 经度,纬度）：").strip()
        end_lon, end_lat = map(float, end_input.split(","))

        # 根据是否使用了 -g 或 -b 参数进行转换, 无论有没有指定初始的 都要有同样的逻辑判断做坐标转换.
        if args.gaode:
            end_lon, end_lat = gcj02_to_wgs84(end_lon, end_lat)
        elif args.baidu:
            end_lon, end_lat = bd09_to_wgs84(end_lon, end_lat)

        print("选择运动模式：1. 走路 2. 慢跑 3. 快跑 4. 开车")
        mode = input("请输入模式编号（1-4）：").strip()
        speed_modes = {"1": (1.2, 1.5), "2": (2.8, 3.5), "3": (4.5, 5.5), "4": (12.0, 16.0)}
        while mode not in speed_modes:
            mode = input("输入无效，请输入 1, 2, 3 或 4：").strip()

        speed_range = speed_modes[mode]
        # 速度初始化
        if previous_speed is None:
            avg_speed = random.uniform(*speed_range)
            previous_speed = avg_speed
        else:
            avg_speed = previous_speed

        distance = calculate_distance(start_lat, start_lon, end_lat, end_lon)
        total_time_seconds = max(distance / avg_speed, 0.1)

        # 计算步长
        time_step = 0.1  # 每隔 0.1 秒记录一次
        num_steps = int(total_time_seconds / time_step)
        lat_step = (end_lat - start_lat) / num_steps
        lon_step = (end_lon - start_lon) / num_steps

        with open(trajectory_file, "a", newline='') as f:
            writer = csv.writer(f)
            current_lat = start_lat
            current_lon = start_lon

            for i in range(num_steps + 1):
                # 平滑速度
                target_speed = random.uniform(*speed_range)
                avg_speed = avg_speed + SMOOTHING_FACTOR * (target_speed - avg_speed)
                previous_speed = avg_speed

                # 位置更新
                current_lat += lat_step
                current_lon += lon_step

                # 高度随机浮动
                height_fluctuation = random.uniform(-HEIGHT_FLUCTUATION, HEIGHT_FLUCTUATION)
                current_height += height_fluctuation

                # 时间更新
                current_time += time_step
                writer.writerow(
                    [round(current_time, 1), round(current_lat, 8), round(current_lon, 8), round(current_height, 3)])

        # 更新起点为终点，为下一次迭代做准备
        start_lat = end_lat
        start_lon = end_lon
        last_time = current_time

    except ValueError:
        print("输入格式错误，请重新输入。")
        continue

    user_choice = input("继续输入新的经纬度？(输入 'x' 退出)：").strip().lower()
    if user_choice == "x":
        break
