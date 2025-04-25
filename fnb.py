import argparse
import math
import requests

# GBFS base URL for WienMobil Rad
GBFS_BASE = "https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_wr/"

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def compass_direction(lat1, lon1, lat2, lon2):
    dLon = math.radians(lon2 - lon1)
    y = math.sin(dLon) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - \
        math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dLon)
    bearing = math.degrees(math.atan2(y, x))
    compass = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    idx = round(((bearing + 360) % 360) / 45) % 8
    return compass[idx]

def fetch_gbfs_data():
    lang = "en"
    base = f"{GBFS_BASE}{lang}/"

    def safe_get_json(endpoint, name):
        url = base + endpoint
        print(f"Fetching {name} from {url} ...")
        r = requests.get(url)
        if r.status_code != 200:
            raise Exception(f"Failed to fetch {name} (HTTP {r.status_code})")
        try:
            return r.json()
        except Exception:
            print(f"Could not decode {name} response as JSON.")
            print(f"Response content: {r.text[:200]}...")
            raise

    # Fetch feeds
    free_bikes_data = safe_get_json("free_bike_status.json", "free bikes")
    stations_info_data = safe_get_json("station_information.json", "station info")
    stations_status_data = safe_get_json("station_status.json", "station status")

    free_bikes = free_bikes_data["data"]["bikes"]
    stations_info = stations_info_data["data"]["stations"]
    stations_status = stations_status_data["data"]["stations"]

    # Merge station info with status
    stations = {}
    for s in stations_info:
        stations[s["station_id"]] = {
            "name": s.get("name", "Unnamed"),
            "lat": s["lat"],
            "lon": s["lon"],
            "bikes": 0
        }
    for s in stations_status:
        sid = s["station_id"]
        if sid in stations:
            stations[sid]["bikes"] = s.get("num_bikes_available", 0)

    return free_bikes, list(stations.values())

def find_nearest_spots(user_lat, user_lon, free_bikes, stations, top_n=3):
    seen = set()
    spots = []

    # Free-floating bikes
    for bike in free_bikes:
        lat, lon = round(bike["lat"], 5), round(bike["lon"], 5)
        key = (lat, lon)
        if key in seen:
            continue
        seen.add(key)
        dist = haversine_distance(user_lat, user_lon, lat, lon)
        direction = compass_direction(user_lat, user_lon, lat, lon)
        spots.append({
            "name": f"Free-floating Bike #{bike['bike_id']}",
            "lat": lat,
            "lon": lon,
            "bikes": 1,
            "distance_km": round(dist, 3),
            "direction": direction
        })

    # Station bikes
    for station in stations:
        if station["bikes"] <= 0:
            continue
        lat, lon = round(station["lat"], 5), round(station["lon"], 5)
        key = (lat, lon)
        if key in seen:
            continue
        seen.add(key)
        dist = haversine_distance(user_lat, user_lon, lat, lon)
        direction = compass_direction(user_lat, user_lon, lat, lon)
        spots.append({
            "name": station["name"],
            "lat": lat,
            "lon": lon,
            "bikes": station["bikes"],
            "distance_km": round(dist, 3),
            "direction": direction
        })

    spots.sort(key=lambda x: x["distance_km"])
    return spots[:top_n]

def main():
    parser = argparse.ArgumentParser(description="Find nearest bikes (station + free) from WienMobil Rad (Nextbike)")
    parser.add_argument("lat", type=float, help="Your latitude")
    parser.add_argument("lon", type=float, help="Your longitude")
    args = parser.parse_args()

    print("Fetching GBFS data...")
    try:
        free_bikes, stations = fetch_gbfs_data()
    except Exception as e:
        print(f"Error while fetching data: {e}")
        return

    nearest = find_nearest_spots(args.lat, args.lon, free_bikes, stations)

    if not nearest:
        print("No bikes found nearby.")
        return

    print(f"\nNearest {len(nearest)} bike locations to ({args.lat}, {args.lon}):\n")
    for spot in nearest:
        print(f"- {spot['name']}")
        print(f"  Location: ({spot['lat']}, {spot['lon']})")
        print(f"  Distance: {spot['distance_km']} km")
        print(f"  Bikes available: {spot['bikes']}")
        print(f"  Direction: {spot['direction']}")
        print(f"  Map: https://www.google.com/maps/search/?api=1&query={spot['lat']},{spot['lon']}\n")

if __name__ == "__main__":
    main()

