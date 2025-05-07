import argparse
import subprocess
import re
import requests
import time
import os
import signal
import json
from math import radians, cos, sin, sqrt, atan2

AGPS_TIMESTAMP_FILE = "/tmp/last_agps_injection.time"
LAST_COORDS_FILE = "/tmp/last_gps_coordinates.json"

def needs_agps_injection(threshold_minutes=30):
    try:
        if not os.path.exists(AGPS_TIMESTAMP_FILE):
            return True
        age = time.time() - os.path.getmtime(AGPS_TIMESTAMP_FILE)
        return age > threshold_minutes * 60
    except Exception:
        return True

def mark_agps_injected():
    with open(AGPS_TIMESTAMP_FILE, "w") as f:
        f.write(str(time.time()))

def save_last_coordinates(lat, lon):
    with open(LAST_COORDS_FILE, "w") as f:
        json.dump({"lat": lat, "lon": lon}, f)

def load_last_coordinates():
    try:
        with open(LAST_COORDS_FILE) as f:
            data = json.load(f)
            return data["lat"], data["lon"]
    except Exception:
        return None, None

def get_gps_coordinates(timeout=30):
    print("📡 Initializing GNSS for fast fix...")

    # Power on GNSS
    try:
        subprocess.run(['sudo', 'tee', '/sys/class/gnss/gnss0/power/control'], input=b'on\n', check=True, stdout=subprocess.DEVNULL)
        print("✅ GNSS powered on.")
    except Exception as e:
        print(f"⚠️ GNSS power control failed: {e}")

    # Stop gpsd to avoid injection conflict
    subprocess.run(['sudo', 'killall', 'gpsd'], stderr=subprocess.DEVNULL)

    # Inject A-GPS if needed
    agps_path = os.path.expanduser('~/ps/droid4-agps/droid4-agps')
    if needs_agps_injection():
        if os.path.exists(agps_path):
            print("📥 Injecting A-GPS data...")
            try:
                subprocess.run(['sudo', agps_path], timeout=20)
                mark_agps_injected()
                print("✅ A-GPS injected.")
            except Exception as e:
                print(f"⚠️ A-GPS injection failed: {e}")
        else:
            print("⚠️ A-GPS binary not found.")
    else:
        print("🕒 A-GPS already injected recently — skipping.")

    # Start gpsd on correct device
    subprocess.run(['sudo', 'gpsd', '/dev/gnss0', '-F', '/var/run/gpsd.sock'])
    print("🚀 gpsd started.")

    # Read GPS data
    print("🔍 Waiting for GPS fix...")
    try:
        proc = subprocess.Popen(['gpspipe', '-w'], stdout=subprocess.PIPE, text=True)
        start = time.time()
        for line in proc.stdout:
            if '"class":"TPV"' in line:
                try:
                    data = json.loads(line)
                    if data.get("mode", 0) >= 2 and "lat" in data and "lon" in data:
                        os.kill(proc.pid, signal.SIGTERM)
                        lat, lon = data["lat"], data["lon"]
                        print(f"✅ GPS FIX: ({lat}, {lon})")
                        save_last_coordinates(lat, lon)
                        return lat, lon
                except json.JSONDecodeError:
                    continue
            if time.time() - start > timeout:
                os.kill(proc.pid, signal.SIGTERM)
                print("❌ Timeout: No GPS fix.")
                break
    except Exception as e:
        print(f"❌ GPS read error: {e}")

    # Use fallback
    lat, lon = load_last_coordinates()
    if lat and lon:
        print(f"📍 Using last known coordinates: ({lat}, {lon})")
        return lat, lon
    else:
        print("❌ No GPS fix and no fallback available.")
        exit(1)
def fetch_citybikes_data(city_query):
    try:
        networks = requests.get("https://api.citybik.es/v2/networks").json()["networks"]
        matches = [n for n in networks if city_query.lower() in n["location"]["city"].lower()]
        if len(matches) == 1:
            network_id = matches[0]["id"]
            city_used = matches[0]["location"]["city"]
            stations = requests.get(f"https://api.citybik.es/v2/networks/{network_id}").json()["network"]["stations"]
            return stations, city_used
        elif len(matches) > 1:
            print("🔎 Multiple matches found:")
            for m in matches:
                print(f"- {m['location']['city']} ({m['id']})")
            exit(1)
        else:
            print("❌ No matching city found.")
            exit(1)
    except Exception as e:
        print(f"Error fetching citybikes data: {e}")
        exit(1)

def fetch_gbfs_vienna():
    try:
        info = requests.get("https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_wr/en/station_information.json").json()
        status = requests.get("https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_wr/en/station_status.json").json()
        free_bikes_data = requests.get("https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_wr/en/free_bike_status.json").json()

        info_stations = {s["station_id"]: s for s in info["data"]["stations"]}
        status_stations = {s["station_id"]: s for s in status["data"]["stations"]}

        merged = []
        for sid, station in info_stations.items():
            s = station.copy()
            s["free_bikes"] = status_stations.get(sid, {}).get("num_bikes_available", 0)
            merged.append(s)

        free_bikes = []
        for bike in free_bikes_data["data"]["bikes"]:
            free_bikes.append({
                "name": f"Free Bike {bike['bike_id']}",
                "bike_id": bike['bike_id'],
                "lat": bike["lat"],
                "lon": bike["lon"],
                "free_bikes": 1
            })

        return free_bikes, merged, "Vienna"
    except Exception as e:
        print(f"Error fetching GBFS Vienna data: {e}")
        exit(1)

def coordinates_to_address(lat, lon):
    try:
        coord_string = f"{lat},{lon}"
        result = subprocess.check_output(["python3", "gpstoadd.py", coord_string], timeout=10).decode().strip()
        return result
    except Exception as e:
        print(f"Error calling gpstoadd.py: {e}")
        return "Address unknown"

def haversine(lat1, lon1, lat2, lon2):
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return float('inf')
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def group_and_sort_spots(lat, lon, bikes, stations):
    spots_dict = {}

    for s in stations:
        station_lat = s.get("latitude", s.get("lat"))
        station_lon = s.get("longitude", s.get("lon"))
        if station_lat is None or station_lon is None:
            continue
        key = (round(station_lat, 6), round(station_lon, 6))

        if key not in spots_dict:
            spots_dict[key] = {
                "lat": station_lat,
                "lon": station_lon,
                "station_bikes": 0,
                "station_names": set(),
                "free_bike_ids": set()
            }
        spots_dict[key]["station_bikes"] += s.get("free_bikes", 0)
        spots_dict[key]["station_names"].add(s.get("name", "Unnamed"))

    for b in bikes:
        bike_lat = b.get("latitude", b.get("lat"))
        bike_lon = b.get("longitude", b.get("lon"))
        if bike_lat is None or bike_lon is None:
            continue
        key = (round(bike_lat, 6), round(bike_lon, 6))

        if key not in spots_dict:
            spots_dict[key] = {
                "lat": bike_lat,
                "lon": bike_lon,
                "station_bikes": 0,
                "station_names": set(),
                "free_bike_ids": set()
            }
        spots_dict[key]["free_bike_ids"].add(b.get("bike_id", "unknown"))

    spots = []
    for (lat2, lon2), info in spots_dict.items():
        dist = haversine(lat, lon, lat2, lon2)
        spots.append({
            "lat": lat2,
            "lon": lon2,
            "station_names": info["station_names"],
            "station_bikes": info["station_bikes"],
            "free_bike_ids": info["free_bike_ids"],
            "distance_km": round(dist, 3),
            "direction": calculate_direction(lat, lon, lat2, lon2)
        })

    spots.sort(key=lambda x: x["distance_km"])
    return spots[:3]

def calculate_direction(lat1, lon1, lat2, lon2):
    dlon = radians(lon2 - lon1)
    lat1 = radians(lat1)
    lat2 = radians(lat2)
    x = sin(dlon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    bearing = atan2(x, y)
    bearing = (bearing * 180 / 3.14159265 + 360) % 360

    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int((bearing + 22.5) // 45) % 8
    return directions[idx]

def main():
    parser = argparse.ArgumentParser(description="Find nearest Nextbike or GBFS bikes to coordinates.")
    parser.add_argument("param1", nargs="?", help="Latitude or City name or empty (GPS auto)")
    parser.add_argument("param2", nargs="?", help="Longitude (optional)")
    parser.add_argument("param3", nargs="?", help="City name (optional)")
    args = parser.parse_args()

    if args.param1 is None:
        lat, lon = get_gps_coordinates()
        city = None
    elif args.param2 is None:
        lat, lon = get_gps_coordinates()
        city = args.param1
    elif args.param3 is None:
        lat = float(args.param1)
        lon = float(args.param2)
        city = None
    else:
        lat = float(args.param1)
        lon = float(args.param2)
        city = args.param3

    if city is None:
        print("📍 Defaulting to WienMobil Rad (Vienna, GBFS)...")
        bikes, stations, city_used = fetch_gbfs_vienna()
    else:
        stations, city_used = fetch_citybikes_data(city)
        bikes = []

    nearest = group_and_sort_spots(lat, lon, bikes, stations)

    if not nearest:
        print("No bikes found nearby.")
        return

    print(f"\n🚲 Nearest {len(nearest)} bike spots to ({lat}, {lon}) in {city_used}:\n")
    for spot in nearest:
        all_station_names = ', '.join(spot['station_names']) if spot['station_names'] else "No Station"
        free_bike_ids = ', '.join(list(spot['free_bike_ids'])[:3])
        if len(spot['free_bike_ids']) > 3:
            free_bike_ids += f" (+{len(spot['free_bike_ids'])-3} more)"

        address = coordinates_to_address(spot["lat"], spot["lon"])

        print(f"- {all_station_names}")
        print(f"  Location: ({spot['lat']}, {spot['lon']})")
        print(f"  Address: {address}")
        print(f"  Distance: {spot['distance_km']} km")
        print(f"  Bikes at station: {spot['station_bikes']}")
        if spot['free_bike_ids']:
            print(f"  Free bikes nearby: {free_bike_ids}")
        print(f"  Direction: {spot['direction']}")
        print(f"  Map: https://www.google.com/maps/search/?api=1&query={spot['lat']},{spot['lon']}\n")

if __name__ == "__main__":
    main()
